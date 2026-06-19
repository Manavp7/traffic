"""Multi-camera registry + ingestion (Camera -> Edge node -> Command Center).

Each registered camera is processed by an :class:`EdgeNode` (on-device detection)
that uplinks compact ``CameraFrameMetric`` rows. Sources may be RTSP URLs or local
video files (the demo loops bundled files since no live RTSP source is available).
"""

from __future__ import annotations

from traffic_os.common.logging import get_logger
from traffic_os.edge.node import EdgeNode
from traffic_os.schemas import Camera, CameraFrameMetric

log = get_logger("edge.cameras")


class CameraManager:
    def __init__(self, storage, *, model_path: str = "models/yolo11n.pt") -> None:
        self.storage = storage
        self.model_path = model_path

    # -- registry --------------------------------------------------------- #
    def register(self, camera: Camera) -> Camera:
        self.storage.db.upsert("camera", camera)
        return camera

    def list_cameras(self) -> list[Camera]:
        return self.storage.db.find("camera", Camera, limit=500)

    # -- ingestion -------------------------------------------------------- #
    def ingest_once(self, camera_id: str, *, max_frames: int = 20, stride: int = 5) -> dict:
        camera = self.storage.db.get("camera", camera_id, Camera)
        if camera is None:
            raise KeyError(camera_id)
        node = EdgeNode(source_id=camera.id, model_path=self.model_path)
        latest: CameraFrameMetric | None = None

        def sink(metric: CameraFrameMetric) -> None:
            nonlocal latest
            latest = metric

        stats = node.run(camera.source, sink, max_frames=max_frames, stride=stride)
        if latest is not None:
            # store under a stable id so /cameras shows the latest per camera
            latest.id = camera.id
            self.storage.db.upsert("camera_metric", latest)
        camera.status = "online"
        self.storage.db.upsert("camera", camera)
        return {
            "camera_id": camera.id,
            "frames": stats.frames,
            "unique_tracks": stats.unique_tracks if hasattr(stats, "unique_tracks") else None,
            "uplink_kb": round(stats.uplink_bytes / 1024, 1),
            "bandwidth_saved_pct": stats.reduction_pct,
            "latest": latest.model_dump(mode="json") if latest else None,
        }
