"""Edge AI layer — on-device detection + compact uplink (Camera -> Edge -> Center)."""

from traffic_os.edge.cameras import CameraManager
from traffic_os.edge.node import EdgeNode, EdgeStats, http_sink

__all__ = ["EdgeNode", "EdgeStats", "http_sink", "CameraManager"]
