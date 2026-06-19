"""Wave I: scenario library/ROI, A/B testing, anomaly detection, KPI/replay."""

from __future__ import annotations

from datetime import datetime

from traffic_os.decision.abtest import ab_test
from traffic_os.intelligence.anomaly import detect_anomalies
from traffic_os.intelligence.kpi import evaluate_kpis, replay_snapshot
from traffic_os.planning import PlanningService, ScenarioLibrary
from traffic_os.schemas import InfraScenario, ScenarioEdit, ScenarioOp, SegmentMetric
from traffic_os.simulation import (
    SimulationEngine,
    build_grid_network,
    generate_history,
    save_network,
)
from traffic_os.storage import memory_storage


def _city(demand=90, ticks=25, history_days=0):
    net = build_grid_network(5)
    st = memory_storage()
    save_network(net, st.db)
    st.settings.sim_demand_scale = demand
    if history_days:
        generate_history(net, st.db, days=history_days, step_min=30, seed=4)
    eng = SimulationEngine(net, st.settings)
    for _ in range(ticks):
        eng.persist_live(st, eng.step_once())
    return net, st


def test_scenario_library_and_roi():
    net, st = _city()
    svc = PlanningService(st)
    central = svc.net.in_segments["J2_2"][0]
    scenario = InfraScenario(
        id="flyover",
        name="Flyover",
        edits=[ScenarioEdit(op=ScenarioOp.ADD_FLYOVER, target=central)],
    )
    result = svc.run_scenario(scenario, ticks=120)
    lib = ScenarioLibrary(st)
    assert lib.results()
    roi = lib.roi(result, build_cost_inr=50_000_000)
    assert "payback_days" in roi and "annual_saving_inr" in roi


def test_ab_test_significance():
    net, st = _city()
    res = ab_test(st, net, runs=3, ticks=80, warmup=25, demand_scale=70)
    assert res["runs"] == 3
    assert "p_value" in res and 0 <= res["p_value"] <= 1
    assert "improvement_pct" in res


def test_anomaly_detection():
    net, st = _city(history_days=3)
    # inject an extreme current value for one segment -> should flag as spike
    sid = next(iter(net.segments))
    st.db.clear("live_metric")
    metrics = [
        SegmentMetric(segment_id=s, ts=datetime.now(), congestion_score=10, speed_kph=40)
        for s in net.segments
    ]
    metrics[0] = SegmentMetric(segment_id=sid, ts=datetime.now(), congestion_score=99, speed_kph=3)
    st.db.upsert_many("live_metric", metrics)
    anomalies = detect_anomalies(st, z_threshold=2.0)
    assert any(a["segment_id"] == sid and a["direction"] == "spike" for a in anomalies)


def test_kpis_and_replay():
    net, st = _city(history_days=2)
    kpis = evaluate_kpis(st)
    assert "status" in kpis and "current" in kpis
    snap = replay_snapshot(st, datetime.now())
    assert snap["count"] > 0
    assert all(0 <= s["congestion"] <= 100 for s in snap["segments"])
