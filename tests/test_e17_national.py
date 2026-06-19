"""E17: multi-city / national rollout."""

from __future__ import annotations

from traffic_os.national import NationalService


def test_national_aggregation():
    # small, fast cities for the test
    specs = [("a", "City A", 4, 70.0), ("b", "City B", 4, 80.0)]
    svc = NationalService(specs, warm_ticks=15)
    assert len(svc.cities) == 2

    summary = svc.national_summary()
    assert summary["city_count"] == 2
    assert len(summary["cities"]) == 2
    assert summary["national_cost_inr"] >= 0
    assert 0 <= summary["national_avg_congestion"] <= 100
    assert "₹" in summary["national_cost_human"]
    # cities are isolated — each has its own segments
    for c in summary["cities"]:
        assert c["segments"] > 0
        assert 0 <= c["avg_congestion"] <= 100

    # stepping advances all cities without error
    svc.step_all(2)
    assert svc.national_summary()["city_count"] == 2
