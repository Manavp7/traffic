"""F2: stolen/blacklist watchlist + live matching."""

from __future__ import annotations

from datetime import datetime

from traffic_os.enforcement import WatchlistService, plate_for_track
from traffic_os.schemas import Track, TrackPoint
from traffic_os.storage import memory_storage


def _track(tid):
    return Track(
        track_id=tid,
        source_id="sim",
        cls="car",
        segment_id="S1",
        points=[TrackPoint(ts=datetime(2025, 1, 1, 9), lat=12.97, lon=77.6, speed_kph=30)],
    )


def test_add_list_remove():
    st = memory_storage()
    svc = WatchlistService(st)
    svc.add("KA01AB1234", "stolen")
    assert len(svc.entries()) == 1
    assert svc.is_listed("ka01ab1234") is not None  # case-insensitive
    svc.remove("KA01AB1234")
    assert svc.entries() == []


def test_scan_detects_listed_vehicle():
    st = memory_storage()
    svc = WatchlistService(st)
    target_plate = plate_for_track("V42")
    svc.add(target_plate, "wanted")
    tracks = [_track("V1"), _track("V42"), _track("V7")]
    hits = svc.scan_tracks(tracks)
    assert len(hits) == 1
    assert hits[0]["plate"] == target_plate
    assert hits[0]["track_id"] == "V42"
    assert hits[0]["reason"] == "wanted"
