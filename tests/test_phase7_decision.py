"""Phase 7: decision engine tests (adaptive signals, emergency, disaster reroute)."""

from __future__ import annotations

from datetime import datetime

from traffic_os.decision import (
    DecisionService,
    compute_signal_plan,
    nearest_junction,
    reroute_around,
)
from traffic_os.decision.emergency import plan_corridor
from traffic_os.schemas import EmergencyType, EmergencyVehicle, SegmentMetric
from traffic_os.simulation import SimulationEngine, build_grid_network, save_network
from traffic_os.storage import memory_storage


def _metrics_for(net, busy_segments, *, busy=80.0, calm=2.0):
    ts = datetime(2025, 1, 1, 9, 0, 0)
    out = {}
    for sid, seg in net.segments.items():
        is_busy = sid in busy_segments
        out[sid] = SegmentMetric(
            segment_id=sid,
            ts=ts,
            speed_kph=8 if is_busy else seg.speed_limit_kph,
            density_pcu_per_km=120 if is_busy else 5,
            occupancy_pct=90 if is_busy else 5,
            queue_len_m=busy if is_busy else calm,
            congestion_score=90 if is_busy else 4,
            travel_time_s=300 if is_busy else 30,
        )
    return out


def test_signal_plan_favours_pressure():
    net = build_grid_network(5)
    sig = net.signal_for_junction("J2_2")
    # make one phase's movements busy
    busy_phase = sig.phases[0]
    metrics = _metrics_for(net, set(busy_phase.movements))
    plans = compute_signal_plan(net, metrics)
    plan = next(p for p in plans if p.signal_id == sig.id)
    busy = next(pp for pp in plan.phases if pp.phase_id == busy_phase.id)
    other = next(pp for pp in plan.phases if pp.phase_id != busy_phase.id)
    assert busy.green_s > other.green_s
    assert busy.pressure > other.pressure


def test_adaptive_beats_fixed_on_peak_throughput():
    net = build_grid_network(5)
    st = memory_storage()
    save_network(net, st.db)
    st.settings.sim_demand_scale = 70
    d = DecisionService(st)
    r = d.evaluate_signal_strategy(ticks=150, warmup=45, demand_scale=70)
    assert r["adaptive_throughput"] > r["fixed_throughput"]
    assert r["throughput_gain_pct"] > 0.0


def test_emergency_corridor():
    net = build_grid_network(5)
    st = memory_storage()
    save_network(net, st.db)
    eng = SimulationEngine(net)
    for _ in range(20):
        eng.persist(st, eng.step_once())
    d = DecisionService(st)
    corner = net.junctions["J0_0"]
    center = net.junctions["J2_2"]
    ev = EmergencyVehicle(
        id="AMB-1",
        type=EmergencyType.AMBULANCE,
        lat=corner.lat,
        lon=corner.lon,
        dest_lat=center.lat,
        dest_lon=center.lon,
    )
    corridor = d.emergency_corridor(ev)
    assert corridor is not None
    assert corridor.route_segments
    assert corridor.signals_preempted  # passes signalised junctions
    assert corridor.distance_m > 0
    # preempted corridor is at least as fast as the congested baseline
    assert corridor.eta_s <= corridor.baseline_eta_s + 1e-6


def test_emergency_supports_all_types():
    net = build_grid_network(4)
    metrics = {
        sid: SegmentMetric(
            segment_id=sid, ts=datetime.now(), speed_kph=s.speed_limit_kph, travel_time_s=30
        )
        for sid, s in net.segments.items()
    }
    for etype in EmergencyType:
        ev = EmergencyVehicle(
            id=f"E-{etype.value}",
            type=etype,
            lat=net.junctions["J0_0"].lat,
            lon=net.junctions["J0_0"].lon,
            dest_lat=net.junctions["J3_3"].lat,
            dest_lon=net.junctions["J3_3"].lon,
        )
        c = plan_corridor(net, metrics, ev)
        assert c is not None and c.type == etype


def test_disaster_reroute_avoids_blocked():
    net = build_grid_network(5)
    # original route along row 0: J0_0 -> J0_4
    from traffic_os.decision.routing import build_graph, route_segments

    original = route_segments(net, build_graph(net), "J0_0", "J0_4")
    assert original
    blocked = {original[1]}
    rr = reroute_around(net, "J0_0", "J0_4", blocked)
    assert rr.feasible
    assert not (set(rr.detour_route) & blocked)
    assert rr.extra_distance_m >= 0


def test_nearest_junction():
    net = build_grid_network(4)
    j = net.junctions["J1_1"]
    assert nearest_junction(net, j.lat + 1e-5, j.lon + 1e-5) == "J1_1"
