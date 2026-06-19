"""Perception pipeline: video -> YOLO+ByteTrack -> normalized detections/metrics.

Outputs (all into the configured storage):
- ``camera_metric``: per-processed-frame counts / occupancy / queue,
- ``detection``: sampled normalized detections,
- ``track``: per-vehicle pixel-space trajectories with estimated speed,
- annotated frames + an annotated MP4 written to the blob store as evidence.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from traffic_os.common.logging import get_logger
from traffic_os.common.timeutil import utcnow
from traffic_os.perception.detector import YOLODetector
from traffic_os.perception.metrics import counts_by_class, occupancy_pct, queue_length_m
from traffic_os.schemas import CameraFrameMetric, Detection, Track, TrackPoint

log = get_logger("perception.pipeline")

STATIONARY_KPH = 3.0


@dataclass
class PerceptionSummary:
    source_id: str
    frames_processed: int
    unique_tracks: int
    class_totals: dict[str, int]
    peak_occupancy_pct: float
    peak_queue_m: float
    avg_vehicles_per_frame: float
    annotated_video_key: str | None = None
    sample_frame_keys: list[str] = field(default_factory=list)


class PerceptionPipeline:
    def __init__(
        self,
        storage,
        *,
        source_id: str = "cam-1",
        model_path: str = "models/yolo11n.pt",
        meters_per_pixel: float = 0.05,
        conf: float = 0.3,
        device: str = "cpu",
    ) -> None:
        self.storage = storage
        self.source_id = source_id
        self.mpp = meters_per_pixel
        self.detector = YOLODetector(model_path, conf=conf, device=device)

    def run(
        self,
        video_path: str,
        *,
        max_frames: int | None = 200,
        stride: int = 3,
        annotate: bool = True,
        sample_every: int = 10,
        base_ts: datetime | None = None,
    ) -> PerceptionSummary:
        import cv2

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise FileNotFoundError(f"cannot open video: {video_path}")
        fps = cap.get(cv2.CAP_PROP_FPS) or 12.0
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frame_area = float(w * h)
        base_ts = base_ts or utcnow()
        dt_s = stride / fps

        writer = None
        tmp_video = None
        if annotate:
            tmp_video = Path(tempfile.mkdtemp()) / "annotated.mp4"
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")  # type: ignore[attr-defined]
            writer = cv2.VideoWriter(str(tmp_video), fourcc, fps / stride, (w, h))

        tracks: dict[int, Track] = {}
        prev_pos: dict[int, tuple[float, float]] = {}
        class_totals: dict[str, int] = {}
        seen_tracks: set[int] = set()
        peak_occ = 0.0
        peak_queue = 0.0
        total_vehicles = 0
        processed = 0
        sample_keys: list[str] = []

        raw_idx = -1
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            raw_idx += 1
            if raw_idx % stride != 0:
                continue
            if max_frames is not None and processed >= max_frames:
                break

            ts = base_ts + timedelta(seconds=processed * dt_s)
            dets = self.detector.track(frame)

            vehicle_dets = [d for d in dets if d.cls.value != "pedestrian"]
            occ = occupancy_pct(dets, frame_area)
            counts = counts_by_class(dets)
            total_vehicles += len(vehicle_dets)
            peak_occ = max(peak_occ, occ)

            stationary: set[int] = set()
            for d in dets:
                if d.track_id is None:
                    continue
                seen_tracks.add(d.track_id)
                cx = (d.bbox[0] + d.bbox[2]) / 2
                cy = (d.bbox[1] + d.bbox[3]) / 2
                speed_kph = 0.0
                if d.track_id in prev_pos:
                    px, py = prev_pos[d.track_id]
                    dist_m = ((cx - px) ** 2 + (cy - py) ** 2) ** 0.5 * self.mpp
                    speed_kph = round(dist_m / max(dt_s, 1e-3) * 3.6, 1)
                prev_pos[d.track_id] = (cx, cy)
                if d.cls.value != "pedestrian" and speed_kph < STATIONARY_KPH:
                    stationary.add(d.track_id)
                tr = tracks.get(d.track_id)
                if tr is None:
                    tr = Track(
                        track_id=f"{self.source_id}-{d.track_id}",
                        source_id=self.source_id,
                        cls=d.cls.value,
                    )
                    tracks[d.track_id] = tr
                tr.points.append(TrackPoint(ts=ts, px=cx, py=cy, speed_kph=speed_kph))

            queue = queue_length_m(stationary)
            peak_queue = max(peak_queue, queue)
            for k, v in counts.items():
                class_totals[k] = class_totals.get(k, 0) + v

            if processed % sample_every == 0:
                self.storage.db.upsert(
                    "camera_metric",
                    CameraFrameMetric(
                        id=f"{self.source_id}-{processed}",
                        source_id=self.source_id,
                        ts=ts,
                        frame=raw_idx,
                        counts=counts,
                        total_vehicles=len(vehicle_dets),
                        occupancy_pct=occ,
                        queue_len_m=queue,
                        unique_tracks=len(seen_tracks),
                    ),
                )
                for di, d in enumerate(dets[:20]):
                    self.storage.db.upsert(
                        "detection",
                        Detection(
                            id=f"{self.source_id}-{processed}-{di}",
                            source_id=self.source_id,
                            ts=ts,
                            cls=d.cls.value,
                            bbox=d.bbox,
                            conf=d.conf,
                        ),
                    )

            if annotate:
                annotated = self._annotate(frame, dets)
                if writer is not None:
                    writer.write(annotated)
                if processed % sample_every == 0:
                    ok2, buf = cv2.imencode(".jpg", annotated)
                    if ok2:
                        key = f"perception/{self.source_id}/frame_{processed:04d}.jpg"
                        self.storage.blob.put(key, buf.tobytes())
                        sample_keys.append(key)
            processed += 1

        cap.release()
        video_key = None
        if writer is not None:
            writer.release()
            if tmp_video and tmp_video.exists():
                video_key = f"perception/{self.source_id}/annotated.mp4"
                self.storage.blob.put(video_key, tmp_video.read_bytes())

        # persist tracks
        if tracks:
            self.storage.db.upsert_many("track", list(tracks.values()))

        summary = PerceptionSummary(
            source_id=self.source_id,
            frames_processed=processed,
            unique_tracks=len(seen_tracks),
            class_totals=class_totals,
            peak_occupancy_pct=round(peak_occ, 1),
            peak_queue_m=round(peak_queue, 1),
            avg_vehicles_per_frame=round(total_vehicles / processed, 2) if processed else 0.0,
            annotated_video_key=video_key,
            sample_frame_keys=sample_keys,
        )
        log.info("Perception done: %s", summary)
        return summary

    @staticmethod
    def _annotate(frame, dets):
        import cv2

        colors = {
            "car": (0, 200, 0),
            "bus": (255, 140, 0),
            "truck": (0, 0, 255),
            "bike": (255, 0, 255),
            "auto": (0, 200, 200),
            "pedestrian": (200, 200, 200),
            "animal": (128, 0, 128),
        }
        out = frame.copy()
        for d in dets:
            x1, y1, x2, y2 = (int(v) for v in d.bbox)
            color = colors.get(d.cls.value, (255, 255, 255))
            cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
            label = f"{d.cls.value}" + (f" #{d.track_id}" if d.track_id is not None else "")
            cv2.putText(out, label, (x1, max(0, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
        return out
