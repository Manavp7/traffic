"""Edge AI node stub — Camera -> Edge AI Node -> Command Center.

Demonstrates the deployment-ready edge architecture: detection runs *on the edge
device* (Jetson Orin Nano / Raspberry Pi 5 / Intel NUC) and only compact metrics
(counts, occupancy, queue) are uplinked — not raw video — slashing bandwidth and
preserving privacy. See ``docs/edge-ai.md`` for hardware sizing.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from traffic_os.common.logging import get_logger
from traffic_os.common.timeutil import utcnow
from traffic_os.perception.detector import YOLODetector
from traffic_os.perception.metrics import counts_by_class, occupancy_pct, queue_length_m
from traffic_os.schemas import CameraFrameMetric

log = get_logger("edge.node")

Sink = Callable[[CameraFrameMetric], None]


@dataclass
class EdgeStats:
    source_id: str
    frames: int
    uplink_bytes: int
    raw_video_bytes: int

    @property
    def reduction_pct(self) -> float:
        if not self.raw_video_bytes:
            return 0.0
        return round((1 - self.uplink_bytes / self.raw_video_bytes) * 100.0, 2)


class EdgeNode:
    """Runs detection locally and emits compact metrics to a sink (uplink)."""

    def __init__(
        self, *, source_id: str = "edge-1", model_path: str = "models/yolo11n.pt", conf: float = 0.3
    ) -> None:
        self.source_id = source_id
        self.detector = YOLODetector(model_path, conf=conf)

    def run(
        self,
        video_path: str,
        sink: Sink,
        *,
        max_frames: int | None = 60,
        stride: int = 5,
        base_ts: datetime | None = None,
    ) -> EdgeStats:
        import cv2

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise FileNotFoundError(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 12.0
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frame_area = float(w * h)
        base_ts = base_ts or utcnow()

        frames = uplink = raw = 0
        seen: set[int] = set()
        idx = -1
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            idx += 1
            if idx % stride != 0:
                continue
            if max_frames is not None and frames >= max_frames:
                break
            dets = self.detector.track(frame)
            for d in dets:
                if d.track_id is not None:
                    seen.add(d.track_id)
            metric = CameraFrameMetric(
                id=f"{self.source_id}-{frames}",
                source_id=self.source_id,
                ts=base_ts + timedelta(seconds=frames * stride / fps),
                frame=idx,
                counts=counts_by_class(dets),
                total_vehicles=sum(1 for d in dets if d.cls.value != "pedestrian"),
                occupancy_pct=occupancy_pct(dets, frame_area),
                queue_len_m=queue_length_m({d.track_id for d in dets if d.track_id is not None}),
                unique_tracks=len(seen),
            )
            payload = metric.model_dump_json()
            uplink += len(payload.encode())
            raw += int(frame.nbytes)  # raw frame would have to be sent in a naive system
            frames += 1
            sink(metric)
        cap.release()
        stats = EdgeStats(self.source_id, frames, uplink, raw)
        log.info(
            "Edge node %s: %d frames, uplink %.1f KB vs raw %.1f MB (%.1f%% reduction)",
            self.source_id,
            frames,
            uplink / 1024,
            raw / 1e6,
            stats.reduction_pct,
        )
        return stats


def http_sink(api_base: str):
    """A sink that POSTs each metric to the Command Center ingest endpoint."""
    import httpx

    client = httpx.Client(base_url=api_base, timeout=10)

    def _sink(metric: CameraFrameMetric) -> None:
        client.post(
            "/ingest/camera",
            content=metric.model_dump_json(),
            headers={"content-type": "application/json"},
        )

    return _sink
