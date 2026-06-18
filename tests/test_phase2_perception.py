"""Phase 2: perception layer tests.

Pure metric tests always run. The end-to-end YOLO+ByteTrack test runs only when
the CV stack and a sample video are available (skipped otherwise, e.g. in base CI).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from traffic_os.perception.detector import COCO_TO_CLASS, RawDetection
from traffic_os.perception.metrics import counts_by_class, occupancy_pct, queue_length_m
from traffic_os.schemas import VehicleClass


def _det(cls, box, conf=0.9, tid=None):
    return RawDetection(cls=cls, conf=conf, bbox=box, track_id=tid)


def test_coco_mapping():
    assert COCO_TO_CLASS[2] == VehicleClass.CAR
    assert COCO_TO_CLASS[5] == VehicleClass.BUS
    assert COCO_TO_CLASS[7] == VehicleClass.TRUCK
    assert COCO_TO_CLASS[3] == VehicleClass.BIKE


def test_counts_by_class():
    dets = [
        _det(VehicleClass.CAR, (0, 0, 10, 10)),
        _det(VehicleClass.CAR, (0, 0, 10, 10)),
        _det(VehicleClass.TRUCK, (0, 0, 10, 10)),
    ]
    assert counts_by_class(dets) == {"car": 2, "truck": 1}


def test_occupancy_bounds():
    # huge box -> capped at 100; tiny -> small
    big = [_det(VehicleClass.CAR, (0, 0, 1000, 1000))]
    small = [_det(VehicleClass.CAR, (0, 0, 5, 5))]
    assert occupancy_pct(big, frame_area=1000 * 1000) <= 100.0
    assert occupancy_pct(small, frame_area=1000 * 1000) < 1.0
    # pedestrians excluded from occupancy
    ped = [_det(VehicleClass.PEDESTRIAN, (0, 0, 1000, 1000))]
    assert occupancy_pct(ped, frame_area=1000 * 1000) == 0.0


def test_queue_length():
    assert queue_length_m(set()) == 0.0
    assert queue_length_m({1, 2, 3}) == pytest.approx(3 * 6.0)


@pytest.mark.skipif(
    not Path("data/samples/highway.mp4").exists(),
    reason="sample video not present (run scripts/fetch_samples.sh)",
)
def test_pipeline_end_to_end():
    pytest.importorskip("ultralytics")
    pytest.importorskip("cv2")
    from traffic_os.perception import PerceptionPipeline
    from traffic_os.schemas import CameraFrameMetric
    from traffic_os.storage import memory_storage

    st = memory_storage()
    pipe = PerceptionPipeline(st, source_id="test-cam")
    summary = pipe.run("data/samples/highway.mp4", max_frames=12, stride=3, sample_every=2)
    assert summary.frames_processed > 0
    assert summary.unique_tracks > 0
    # real vehicles detected
    assert summary.class_totals.get("car", 0) > 0
    # camera metrics persisted
    assert st.db.count("camera_metric") > 0
    rows = st.db.find("camera_metric", CameraFrameMetric, limit=1)
    assert rows and rows[0].total_vehicles >= 0
