"""E7: vision-based triple-riding detection (COCO-based, no model needed for the rule)."""

from __future__ import annotations

from traffic_os.perception.detector import RawDetection
from traffic_os.schemas import VehicleClass
from traffic_os.violations import detect_triple_riding


def _d(cls, bbox, tid=None):
    return RawDetection(cls=cls, conf=0.9, bbox=bbox, track_id=tid)


def test_triple_riding_flagged():
    # a motorcycle with three persons sitting on/above it
    bike = _d(VehicleClass.BIKE, (100, 200, 160, 280), tid=7)
    p1 = _d(VehicleClass.PEDESTRIAN, (110, 150, 130, 210))
    p2 = _d(VehicleClass.PEDESTRIAN, (125, 150, 145, 210))
    p3 = _d(VehicleClass.PEDESTRIAN, (135, 150, 155, 210))
    v = detect_triple_riding([bike, p1, p2, p3])
    assert len(v) == 1
    assert v[0].type.value == "triple_riding"
    assert v[0].vehicle_track_id == "7"


def test_two_riders_not_flagged():
    bike = _d(VehicleClass.BIKE, (100, 200, 160, 280))
    p1 = _d(VehicleClass.PEDESTRIAN, (110, 160, 130, 210))
    p2 = _d(VehicleClass.PEDESTRIAN, (130, 160, 150, 210))
    assert detect_triple_riding([bike, p1, p2]) == []


def test_persons_far_from_bike_not_flagged():
    bike = _d(VehicleClass.BIKE, (100, 200, 160, 280))
    far = [_d(VehicleClass.PEDESTRIAN, (600, 600, 620, 660)) for _ in range(3)]
    assert detect_triple_riding([bike, *far]) == []
