"""Phase 8: strategic planning (economic loss + infrastructure what-if)."""

from __future__ import annotations

from datetime import datetime

from traffic_os.common.config import Settings
from traffic_os.planning import EconomicLossEngine, PlanningService, format_inr
from traffic_os.planning.economics import format_inr as fmt
from traffic_os.schemas import InfraScenario, ScenarioEdit, ScenarioOp, SegmentMetric
from traffic_os.simulation import SimulationEngine, build_grid_network, save_network
from traffic_os.storage import memory_storage


def test_economic_loss_scales_with_congestion():
    net = build_grid_network(4)
    eng = EconomicLossEngine.from_settings(Settings(mode="dev"))
    ts = datetime(2025, 1, 1, 9, 0, 0)
    free = {
        sid: SegmentMetric(segment_id=sid, ts=ts, vehicle_count=10, speed_kph=s.speed_limit_kph)
        for sid, s in net.segments.items()
    }
    jam = {
        sid: SegmentMetric(segment_id=sid, ts=ts, vehicle_count=10, speed_kph=4)
        for sid, s in net.segments.items()
    }
    free_cost = eng.city_impact(net, free).cost_inr
    jam_cost = eng.city_impact(net, jam).cost_inr
    assert jam_cost > free_cost
    assert free_cost >= 0


def test_format_inr():
    assert "crore" in fmt(2.5e7)
    assert "lakh" in fmt(3e5)
    assert format_inr(5000).startswith("₹")


def test_economic_summary_end_to_end():
    net = build_grid_network(5)
    st = memory_storage()
    save_network(net, st.db)
    eng = SimulationEngine(net)
    for _ in range(40):
        st_snap = eng.step_once()
        eng.persist(st, st_snap)
    svc = PlanningService(st)
    summ = svc.economic_summary()
    assert summ["cost_inr"] >= 0
    assert "₹" in summ["cost_human"]
    breakdown = svc.economic_breakdown(top_n=5)
    assert len(breakdown) <= 5
    # sorted by cost desc
    costs = [e.cost_inr for e in breakdown]
    assert costs == sorted(costs, reverse=True)


def test_close_road_increases_cost():
    net = build_grid_network(5)
    st = memory_storage()
    save_network(net, st.db)
    st.settings.sim_demand_scale = 70
    svc = PlanningService(st)
    # close a central arterial segment -> should worsen KPIs
    central = svc.net.in_segments["J2_2"][0]
    scenario = InfraScenario(
        id="close-1",
        name="Close central road",
        edits=[ScenarioEdit(op=ScenarioOp.CLOSE_ROAD, target=central)],
    )
    result = svc.run_scenario(scenario, ticks=120)
    assert set(result.baseline_kpis) == set(result.scenario_kpis)
    assert "congestion" in result.summary.lower() or "cost" in result.summary.lower()
    # closing a road should not improve throughput
    assert result.scenario_kpis["throughput"] <= result.baseline_kpis["throughput"] * 1.05


def test_widen_lane_helps_or_neutral():
    net = build_grid_network(5)
    st = memory_storage()
    save_network(net, st.db)
    st.settings.sim_demand_scale = 90
    svc = PlanningService(st)
    central = svc.net.in_segments["J2_2"][0]
    scenario = InfraScenario(
        id="widen-1",
        name="Widen central road",
        edits=[ScenarioEdit(op=ScenarioOp.WIDEN_LANE, target=central, params={"delta": 2})],
    )
    result = svc.run_scenario(scenario, ticks=120)
    # widening capacity should not reduce throughput
    assert result.scenario_kpis["throughput"] >= result.baseline_kpis["throughput"] * 0.95
    assert isinstance(result.deltas["daily_cost_inr"], float)
