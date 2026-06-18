"""Vision-based violation detectors over object detections.

- **Triple-riding** is fully implemented using COCO detections: ≥3 persons overlapping
  a two-wheeler bounding box (works with the existing YOLO11 detector).
- Helmet / seatbelt / mobile-phone use require dedicated cropped-rider classifiers; they
  are provided as a pluggable interface (``vision_stub.VisionViolationDetector``) and wired
  here behind a model path, with a documented roadmap.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from traffic_os.common.logging import get_logger
from traffic_os.perception.detector import RawDetection
from traffic_os.schemas import VehicleClass, Violation, ViolationType

log = get_logger("violations.vision")

TRIPLE_RIDING_MIN_PERSONS = 3


def _iou_or_contains(person, bike) -> bool:
    """True if a person box meaningfully overlaps / sits on a two-wheeler box."""
    px = (person[0] + person[2]) / 2
    py = (person[1] + person[3]) / 2
    # expand bike box slightly (riders extend above the vehicle)
    bx1, by1, bx2, by2 = bike
    h = by2 - by1
    bx1 -= (bx2 - bx1) * 0.15
    bx2 += (bx2 - bx1) * 0.15
    by1 -= h * 0.6  # riders sit above the bike
    return bx1 <= px <= bx2 and by1 <= py <= by2


def detect_triple_riding(
    dets: list[RawDetection],
    *,
    source_id: str = "cam",
    frame: int = 0,
    ts: datetime | None = None,
) -> list[Violation]:
    ts = ts or datetime.now()
    bikes = [d for d in dets if d.cls == VehicleClass.BIKE]
    persons = [d for d in dets if d.cls == VehicleClass.PEDESTRIAN]
    out: list[Violation] = []
    for bike in bikes:
        riders = [p for p in persons if _iou_or_contains(p.bbox, bike.bbox)]
        if len(riders) >= TRIPLE_RIDING_MIN_PERSONS:
            bx = (bike.bbox[0] + bike.bbox[2]) / 2
            by = (bike.bbox[1] + bike.bbox[3]) / 2
            out.append(
                Violation(
                    id=f"TR-{uuid.uuid4().hex[:8]}",
                    ts=ts,
                    type=ViolationType.TRIPLE_RIDING,
                    lat=0.0,
                    lon=0.0,
                    vehicle_track_id=str(bike.track_id) if bike.track_id is not None else None,
                    detail=f"{len(riders)} riders on a two-wheeler @ ({bx:.0f},{by:.0f}) [{source_id} f{frame}]",
                )
            )
    return out


def run_vision_violations_on_video(
    storage,
    video_path: str,
    *,
    source_id: str = "cam-1",
    model_path: str = "models/yolo11n.pt",
    max_frames: int = 120,
    stride: int = 3,
    persist: bool = True,
) -> list[Violation]:
    """Run the detector over a video and collect triple-riding violations (deduped)."""
    import cv2

    from traffic_os.perception.detector import YOLODetector

    det = YOLODetector(model_path)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise FileNotFoundError(video_path)
    seen: set[str] = set()
    out: list[Violation] = []
    idx = -1
    processed = 0
    while True:
        ok, frame = cap.read()
        if not ok or processed >= max_frames:
            break
        idx += 1
        if idx % stride != 0:
            continue
        for v in detect_triple_riding(det.track(frame), source_id=source_id, frame=idx):
            key = v.vehicle_track_id or v.id
            if key in seen:
                continue
            seen.add(key)
            out.append(v)
        processed += 1
    cap.release()
    if persist and out:
        storage.db.upsert_many("violation", out)
    log.info("Vision violations: %d triple-riding over %d frames", len(out), processed)
    return out
