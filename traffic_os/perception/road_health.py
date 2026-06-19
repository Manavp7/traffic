"""Road-health detection — potholes / cracks / waterlogging.

Two paths:
- **Pluggable ML model** (`RoadHealthModel`): if a trained pothole/crack YOLO weight is
  provided it is used directly (recommended for production).
- **Classical-CV heuristic** (`detect_potholes_cv`): a real, dependency-light fallback that
  flags dark, roughly-elliptical surface anomalies — good enough to demonstrate the pipeline
  end-to-end without a trained model. Clearly labelled `method="cv-heuristic"`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from traffic_os.common.logging import get_logger
from traffic_os.common.timeutil import utcnow
from traffic_os.schemas import RoadHealthIssue, RoadHealthKind

log = get_logger("perception.road_health")


def detect_potholes_cv(
    image,
    *,
    source_id: str = "cam",
    ts: datetime | None = None,
    min_area_frac: float = 0.0008,
    max_area_frac: float = 0.15,
) -> list[RoadHealthIssue]:
    """Heuristic pothole candidates: dark, blob-like regions on the road surface."""
    import cv2
    import numpy as np

    ts = ts or utcnow()
    h, w = image.shape[:2]
    area = float(h * w)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    blur = cv2.GaussianBlur(gray, (7, 7), 0)
    # dark regions relative to local mean
    thr = cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 51, 15
    )
    thr = cv2.morphologyEx(thr, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(thr, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    issues: list[RoadHealthIssue] = []
    for c in contours:
        a = cv2.contourArea(c)
        if a < area * min_area_frac or a > area * max_area_frac:
            continue
        x, y, bw, bh = cv2.boundingRect(c)
        aspect = bw / max(bh, 1)
        if not (0.4 <= aspect <= 2.5):  # potholes are roughly round-ish
            continue
        fill = a / max(bw * bh, 1)
        if fill < 0.45:  # avoid thin/sparse shapes
            continue
        severity = min(1.0, a / (area * 0.05))
        issues.append(
            RoadHealthIssue(
                id=f"RH-{uuid.uuid4().hex[:8]}",
                source_id=source_id,
                ts=ts,
                kind=RoadHealthKind.POTHOLE,
                bbox=(float(x), float(y), float(x + bw), float(y + bh)),
                confidence=round(0.4 + 0.4 * fill, 2),
                severity=round(severity, 2),
                method="cv-heuristic",
            )
        )
    return issues


def scan_video(
    storage,
    video_path: str,
    *,
    source_id: str = "cam-1",
    model_path: str | None = None,
    max_frames: int = 40,
    stride: int = 10,
    persist: bool = True,
) -> list[RoadHealthIssue]:
    """Scan a video for road-health issues and store them."""
    import cv2

    model = RoadHealthModel(model_path)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise FileNotFoundError(video_path)
    issues: list[RoadHealthIssue] = []
    idx = -1
    processed = 0
    while True:
        ok, frame = cap.read()
        if not ok or processed >= max_frames:
            break
        idx += 1
        if idx % stride != 0:
            continue
        issues.extend(model.analyze(frame, source_id=source_id))
        processed += 1
    cap.release()
    if persist and issues:
        storage.db.upsert_many("road_health", issues)
    log.info(
        "Road-health scan: %d issues over %d frames (%s)", len(issues), processed, model.method
    )
    return issues


class RoadHealthModel:
    """Pluggable trained detector (pothole/crack). Falls back to CV heuristic if absent."""

    def __init__(self, model_path: str | None = None) -> None:
        self.model = None
        self.method = "cv-heuristic"
        if model_path and Path(model_path).exists():
            try:
                from ultralytics import YOLO

                self.model = YOLO(model_path)
                self.method = f"model:{Path(model_path).stem}"
                log.info("Loaded road-health model %s", model_path)
            except Exception as exc:  # pragma: no cover
                log.warning("Failed to load road-health model (%s); using CV heuristic", exc)

    def analyze(
        self, image, *, source_id: str = "cam", ts: datetime | None = None
    ) -> list[RoadHealthIssue]:
        ts = ts or utcnow()
        if self.model is None:
            return detect_potholes_cv(image, source_id=source_id, ts=ts)
        res = self.model.predict(image, verbose=False)[0]
        out: list[RoadHealthIssue] = []
        boxes: list = list(res.boxes) if res.boxes is not None else []
        for b in boxes:
            x1, y1, x2, y2 = (float(v) for v in b.xyxy[0])
            out.append(
                RoadHealthIssue(
                    id=f"RH-{uuid.uuid4().hex[:8]}",
                    source_id=source_id,
                    ts=ts,
                    kind=RoadHealthKind.POTHOLE,
                    bbox=(x1, y1, x2, y2),
                    confidence=float(b.conf),
                    severity=0.6,
                    method=self.method,
                )
            )
        return out
