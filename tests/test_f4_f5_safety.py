"""F4 + F5: VRU near-miss detection and driver-behavior scoring."""

from __future__ import annotations

from datetime import datetime, timedelta

from traffic_os.safety import detect_near_misses, driver_scores, score_track
from traffic_os.schemas import Track, TrackPoint

T0 = datetime(2025, 1, 1, 9, 0, 0)


def _pt(i, lat, lon, spd, hdg=90):
    return TrackPoint(
        ts=T0 + timedelta(seconds=5 * i), lat=lat, lon=lon, speed_kph=spd, heading_deg=hdg
    )


def test_near_miss_detected():
    ped = Track(
        track_id="P1",
        source_id="cam",
        cls="pedestrian",
        segment_id="S1",
        points=[_pt(0, 12.9000, 77.6000, 4), _pt(1, 12.90001, 77.60001, 4)],
    )
    car = Track(
        track_id="C1",
        source_id="cam",
        cls="car",
        segment_id="S1",
        points=[_pt(0, 12.9009, 77.6009, 35), _pt(1, 12.900012, 77.600012, 30)],
    )
    nm = detect_near_misses([ped, car])
    assert len(nm) == 1
    assert nm[0]["vru_track"] == "P1" and nm[0]["vehicle_track"] == "C1"
    assert nm[0]["severity"] > 0


def test_no_near_miss_when_vehicle_slow():
    ped = Track(
        track_id="P1",
        source_id="cam",
        cls="pedestrian",
        segment_id="S1",
        points=[_pt(0, 12.9000, 77.6000, 2)],
    )
    car = Track(
        track_id="C1",
        source_id="cam",
        cls="car",
        segment_id="S1",
        points=[_pt(0, 12.90001, 77.60001, 3)],
    )  # crawling -> not a near-miss
    assert detect_near_misses([ped, car]) == []


def test_driver_scoring_flags_harsh_and_weaving():
    # harsh braking 35->2 and a sharp heading swing
    reckless = Track(
        track_id="R1",
        source_id="sim",
        cls="car",
        segment_id="S1",
        points=[
            _pt(0, 12.90, 77.60, 35, 90),
            _pt(1, 12.9005, 77.6005, 2, 150),
            _pt(2, 12.9006, 77.6006, 30, 95),
        ],
    )
    s = score_track(reckless)
    assert s["harsh_braking"] >= 1
    assert s["weaving"] >= 1
    assert s["risk_score"] > 0

    calm = Track(
        track_id="C1",
        source_id="sim",
        cls="car",
        segment_id="S1",
        points=[
            _pt(0, 12.90, 77.60, 30, 90),
            _pt(1, 12.9005, 77.6005, 30, 90),
        ],
    )
    ranked = driver_scores([reckless, calm])
    assert ranked[0]["track_id"] == "R1"  # reckless ranks first
