"""Vehicle detection via Ultralytics YOLO (YOLO11 by default; RT-DETR optional).

CPU-friendly: defaults to the nano model and supports frame striding so the demo
runs without a GPU.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from traffic_os.common.logging import get_logger
from traffic_os.schemas import VehicleClass

log = get_logger("perception.detector")

# COCO class id -> Traffic-OS VehicleClass
COCO_TO_CLASS: dict[int, VehicleClass] = {
    0: VehicleClass.PEDESTRIAN,  # person
    1: VehicleClass.BIKE,  # bicycle
    2: VehicleClass.CAR,  # car
    3: VehicleClass.BIKE,  # motorcycle
    5: VehicleClass.BUS,  # bus
    7: VehicleClass.TRUCK,  # truck
    16: VehicleClass.ANIMAL,  # dog (proxy for stray animals)
    17: VehicleClass.ANIMAL,  # horse
}


@dataclass
class RawDetection:
    cls: VehicleClass
    conf: float
    bbox: tuple[float, float, float, float]  # x1,y1,x2,y2
    track_id: int | None = None


class YOLODetector:
    def __init__(
        self,
        model_path: str = "models/yolo11n.pt",
        *,
        conf: float = 0.3,
        iou: float = 0.5,
        device: str = "cpu",
        imgsz: int = 640,
    ) -> None:
        from ultralytics import YOLO  # local import: optional dependency

        # fall back to auto-download name if local weights absent
        path = model_path if Path(model_path).exists() else Path(model_path).name
        self.model = YOLO(str(path))
        self.conf = conf
        self.iou = iou
        self.device = device
        self.imgsz = imgsz
        self.names = self.model.names

    def detect(self, frame) -> list[RawDetection]:
        res = self.model.predict(
            frame,
            conf=self.conf,
            iou=self.iou,
            device=self.device,
            imgsz=self.imgsz,
            verbose=False,
        )[0]
        return self._parse(res)

    def track(self, frame) -> list[RawDetection]:
        """Detect + ByteTrack (persistent IDs across frames)."""
        res = self.model.track(
            frame,
            conf=self.conf,
            iou=self.iou,
            device=self.device,
            imgsz=self.imgsz,
            persist=True,
            tracker="bytetrack.yaml",
            verbose=False,
        )[0]
        return self._parse(res)

    @staticmethod
    def _parse(res) -> list[RawDetection]:
        out: list[RawDetection] = []
        if res.boxes is None:
            return out
        ids = res.boxes.id
        for k, box in enumerate(res.boxes):
            cid = int(box.cls)
            cls = COCO_TO_CLASS.get(cid)
            if cls is None:
                continue
            x1, y1, x2, y2 = (float(v) for v in box.xyxy[0])
            tid = int(ids[k]) if ids is not None else None
            out.append(
                RawDetection(cls=cls, conf=float(box.conf), bbox=(x1, y1, x2, y2), track_id=tid)
            )
        return out
