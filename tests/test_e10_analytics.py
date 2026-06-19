"""E10: historical analytics aggregations."""

from __future__ import annotations

from traffic_os.intelligence.analytics import daily_profile, hourly_profile, network_timeseries
from traffic_os.simulation import build_grid_network, generate_history
from traffic_os.storage import memory_storage


def _history(days=3):
    net = build_grid_network(4)
    st = memory_storage()
    generate_history(net, st.db, days=days, step_min=30, seed=9)
    return st


def test_network_timeseries():
    st = _history()
    ts = network_timeseries(st.db, hours=24)
    assert ts, "expected a non-empty time series"
    assert all(0 <= p["congestion"] <= 100 for p in ts)
    # timestamps strictly increasing
    times = [p["ts"] for p in ts]
    assert times == sorted(times)


def test_hourly_profile_has_24_buckets():
    st = _history()
    hp = hourly_profile(st.db)
    hours = {p["hour"] for p in hp}
    assert hours == set(range(24))
    # morning/evening peaks should exceed deep-night
    by_hour = {p["hour"]: p["congestion"] for p in hp}
    assert by_hour[9] > by_hour[3]


def test_daily_profile():
    st = _history(days=3)
    dp = daily_profile(st.db)
    assert len(dp) >= 3
    assert all(0 <= p["congestion"] <= 100 for p in dp)
