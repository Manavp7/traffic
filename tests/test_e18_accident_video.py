"""E18: optional video accident model with tracking-based fallback."""

from __future__ import annotations

import os
from datetime import datetime, timedelta

import pytest

from traffic_os.perception.accident_video import analyze_clip
from traffic_os.schemas import Track, TrackPoint


def _colliding_tracks():
    t0 = datetime(2025, 1, 1, 9, 0, 0)
    a = Track(
        track_id="A",
        source_id="sim",
        cls="car",
        segment_id="s1",
        points=[
            TrackPoint(ts=t0, lat=12.9000, lon=77.6000, speed_kph=30, heading_deg=90),
            TrackPoint(
                ts=t0 + timedelta(seconds=5), lat=12.9001, lon=77.6001, speed_kph=25, heading_deg=90
            ),
            TrackPoint(
                ts=t0 + timedelta(seconds=10),
                lat=12.90020,
                lon=77.60020,
                speed_kph=1,
                heading_deg=90,
            ),
        ],
    )
    b = Track(
        track_id="B",
        source_id="sim",
        cls="bike",
        segment_id="s2",
        points=[
            TrackPoint(ts=t0, lat=12.9010, lon=77.6010, speed_kph=28, heading_deg=270),
            TrackPoint(
                ts=t0 + timedelta(seconds=5),
                lat=12.9005,
                lon=77.6005,
                speed_kph=20,
                heading_deg=270,
            ),
            TrackPoint(
                ts=t0 + timedelta(seconds=10),
                lat=12.90021,
                lon=77.60021,
                speed_kph=1,
                heading_deg=270,
            ),
        ],
    )
    return [a, b]


def test_fallback_uses_tracking_based_detection():
    res = analyze_clip(tracks=_colliding_tracks())
    assert res["method"] == "tracking-based"
    assert res["count"] >= 1
    assert any(e["kind"] == "collision" for e in res["events"])


@pytest.mark.skipif(os.environ.get("TOS_TEST_VIDEOMAE") != "1", reason="set TOS_TEST_VIDEOMAE=1")
def test_videomae_classifier():
    pytest.importorskip("transformers")
    import numpy as np

    from traffic_os.perception.accident_video import VideoAccidentClassifier

    clf = VideoAccidentClassifier()
    frames = [np.zeros((224, 224, 3), dtype="uint8") for _ in range(16)]
    out = clf.classify(frames)
    assert "label" in out and 0 <= out["score"] <= 1
