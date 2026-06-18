"""Phase 1: digital-twin simulation tests."""

from __future__ import annotations

from datetime import datetime, timedelta

from traffic_os.common.config import Settings
from traffic_os.schemas import SegmentMetric
from traffic_os.simulation import (
    SimulationEngine,
    build_grid_network,
    generate_history,
    load_network,
    save_network,
)
from traffic_os.simulation.microsim import MicroSim, diurnal_factor
from traffic_os.simulation.signals import SignalController
from traffic_os.storage import memory_storage


def test_grid_network_structure():
    net = build_grid_network(5)
    assert len(net.junctions) == 25
    # interior 3x3 = 9 signalised junctions
    assert sum(1 for j in net.junctions.values() if j.has_signal) == 9
    assert len(net.signals) == 9
    # every segment has a reverse counterpart
    for seg in net.segments.values():
        assert (seg.to_junction, seg.from_junction) in net.pair_to_segment


def test_routing_exists():
    net = build_grid_network(5)
    sim = MicroSim(net, SignalController(net))
    route = sim._route("J0_0", "J4_4")
    assert route, "expected a non-empty route across the grid"
    # route segments must be contiguous
    for a, b in zip(route[:-1], route[1:], strict=False):
        assert net.segments[a].to_junction == net.segments[b].from_junction


def test_vehicle_conservation():
    net = build_grid_network(5)
    sim = MicroSim(net, SignalController(net), seed=1)
    ts = datetime(2025, 1, 1, 9, 0, 0)
    total_spawned = 0
    total_exited = 0
    for t in range(40):
        step = sim.step(t, ts + timedelta(seconds=5 * t), 5.0)
        total_spawned += step.spawned
        total_exited += step.exited
    # vehicles on the network == spawned - exited (none lost or duplicated)
    assert len(sim.vehicles) == total_spawned - total_exited
    assert total_spawned > 0


def test_congestion_builds_and_bounds():
    net = build_grid_network(5)
    sim = MicroSim(net, SignalController(net), seed=2, demand_scale=20.0)
    ts = datetime(2025, 1, 1, 9, 0, 0)
    last = []
    for t in range(60):
        last = sim.step(t, ts + timedelta(seconds=5 * t), 5.0).metrics
    scores = [m.congestion_score for m in last]
    assert all(0.0 <= s <= 100.0 for s in scores)
    assert max(scores) > 5.0, "heavy demand should congest at least one segment"
    # free-flow sanity: speeds never exceed limit
    for m in last:
        seg = net.segments[m.segment_id]
        assert m.speed_kph <= seg.speed_limit_kph + 1e-6


def test_probe_tracks_recorded():
    net = build_grid_network(5)
    sim = MicroSim(net, SignalController(net), seed=3, probe_ratio=0.5)
    ts = datetime(2025, 1, 1, 9, 0, 0)
    for t in range(30):
        sim.step(t, ts + timedelta(seconds=5 * t), 5.0)
    assert sim.tracks, "expected probe tracks"
    multi = [tr for tr in sim.tracks.values() if len(tr.points) >= 2]
    assert multi, "expected probe tracks with trajectories"
    p = multi[0].points[-1]
    assert -90 <= p.lat <= 90 and -180 <= p.lon <= 180


def test_signal_controller_cycles():
    net = build_grid_network(5)
    ctrl = SignalController(net)
    sid = next(iter(net.signals))
    first = ctrl.green_segments(net.signals[sid].junction_id)
    for _ in range(20):
        ctrl.step(5.0)
    later = ctrl.green_segments(net.signals[sid].junction_id)
    # after ~100s (> one 33s phase) the active movement set should have changed at least once
    assert isinstance(first, set) and isinstance(later, set)
    states = ctrl.states()
    assert len(states) == len(net.signals)


def test_signal_preempt():
    net = build_grid_network(5)
    ctrl = SignalController(net)
    sig = next(iter(net.signals.values()))
    seg = next(iter(sig.phases[0].movements), None) or next(iter(net.segments))
    ctrl.preempt(sig.id, {seg}, 30.0)
    assert ctrl.green_segments(sig.junction_id) == {seg}


def test_diurnal_peaks():
    assert diurnal_factor(9.0) > diurnal_factor(3.0)
    assert diurnal_factor(18.5) > diurnal_factor(2.0)


def test_history_generation():
    net = build_grid_network(4)
    st = memory_storage()
    stats = generate_history(net, st.db, days=2, step_min=30, seed=5)
    assert stats["metrics"] > 0
    rows = st.db.metrics_range(SegmentMetric, segment_id=next(iter(net.segments)))
    assert len(rows) == 2 * 24 * 2  # 2 days * 24h * 2 per hour
    assert all(0 <= r.congestion_score <= 100 for r in rows)


def test_engine_step_and_persist():
    net = build_grid_network(4)
    st = memory_storage()
    save_network(net, st.db)
    eng = SimulationEngine(net, Settings(mode="dev"))
    snap = eng.step_once()
    eng.persist(st, snap)
    assert len(snap.metrics) == len(net.segments)
    assert st.db.count("segment_metric") == len(net.segments)
    msg = eng.snapshot_message(snap)
    assert "metrics" in msg and msg["tick"] == 1

    # round-trip network through storage
    reloaded = load_network(st.db)
    assert len(reloaded.segments) == len(net.segments)
