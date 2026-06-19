"""E13: multi-camera registry + ingestion."""

from __future__ import annotations

from pathlib import Path

import pytest

from traffic_os.edge import CameraManager
from traffic_os.schemas import Camera
from traffic_os.storage import memory_storage


def test_camera_registry():
    st = memory_storage()
    mgr = CameraManager(st)
    mgr.register(
        Camera(id="cam-1", name="MG Road", source="data/samples/highway.mp4", lat=12.97, lon=77.6)
    )
    mgr.register(Camera(id="cam-2", name="Silk Board", source="rtsp://example/stream"))
    cams = mgr.list_cameras()
    assert {c.id for c in cams} == {"cam-1", "cam-2"}


@pytest.mark.skipif(
    not Path("data/samples/highway.mp4").exists(),
    reason="sample video not present (run scripts/fetch_samples.sh)",
)
def test_camera_ingest_once():
    pytest.importorskip("ultralytics")
    pytest.importorskip("cv2")
    from traffic_os.schemas import CameraFrameMetric

    st = memory_storage()
    mgr = CameraManager(st)
    mgr.register(Camera(id="cam-h", name="Highway", source="data/samples/highway.mp4"))
    result = mgr.ingest_once("cam-h", max_frames=8, stride=4)
    assert result["frames"] > 0
    assert result["bandwidth_saved_pct"] > 90.0
    # latest metric stored under the stable camera id
    m = st.db.get("camera_metric", "cam-h", CameraFrameMetric)
    assert m is not None and m.source_id == "cam-h"
