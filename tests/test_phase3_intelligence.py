"""Phase 3: intelligence layer tests."""

from __future__ import annotations

from datetime import datetime, timedelta

from traffic_os.intelligence import (
    CongestionModel,
    IntelligenceService,
    detect_all,
    find_bottlenecks,
    top_hotspots,
)
from traffic_os.intelligence.collision import detect_collisions, detect_sudden_stops
from traffic_os.schemas import SegmentMetric, Track, TrackPoint
from traffic_os.simulation import SimulationEngine, build_grid_network, save_network
from traffic_os.simulation.network import RoadSegment
from traffic_os.storage import memory_storage


def _seg(sid, **kw):
    return RoadSegment(id=sid, name=sid, from_junction="a", to_junction="b", length_m=300, **kw)


def test_congestion_bounds():
    m = CongestionModel()
    seg = _seg("s1", lanes=2, speed_limit_kph=50)
    free = SegmentMetric(
        segment_id="s1",
        ts=datetime.now(),
        speed_kph=50,
        occupancy_pct=2,
        density_pcu_per_km=3,
        queue_len_m=0,
    )
    jam = SegmentMetric(
        segment_id="s1",
        ts=datetime.now(),
        speed_kph=2,
        occupancy_pct=100,
        density_pcu_per_km=300,
        queue_len_m=300,
    )
    assert m.score(free, seg) < 10
    assert m.score(jam, seg) > 85


def test_hotspots_and_bottleneck_on_crafted_graph():
    # chain: A -> B -> C -> D ; make B->C the bottleneck (slow, queued)
    net = build_grid_network(4)
    metrics = {}
    ts = datetime.now()
    for sid, seg in net.segments.items():
        metrics[sid] = SegmentMetric(
            segment_id=sid,
            ts=ts,
            speed_kph=seg.speed_limit_kph,
            occupancy_pct=5,
            density_pcu_per_km=5,
            queue_len_m=0,
            congestion_score=5,
            travel_time_s=30,
        )
    # choose a segment whose downstream is free; make it slow & queued
    target = next(iter(net.segments))
    metrics[target] = SegmentMetric(
        segment_id=target,
        ts=ts,
        speed_kph=6,
        occupancy_pct=90,
        density_pcu_per_km=120,
        queue_len_m=220,
        congestion_score=88,
        travel_time_s=300,
    )
    bns = find_bottlenecks(net, metrics, min_congestion=40)
    assert bns and bns[0].segment_id == target
    spots = top_hotspots(net, metrics, top_n=5)
    assert spots and spots[0].congestion >= spots[-1].congestion


def test_sudden_stop_detection():
    t0 = datetime(2025, 1, 1, 9, 0, 0)
    pts = [
        TrackPoint(ts=t0, lat=12.9, lon=77.6, speed_kph=30, heading_deg=90),
        TrackPoint(
            ts=t0 + timedelta(seconds=5), lat=12.9001, lon=77.6, speed_kph=28, heading_deg=90
        ),
        TrackPoint(
            ts=t0 + timedelta(seconds=10), lat=12.9002, lon=77.6, speed_kph=1, heading_deg=90
        ),
    ]
    tr = Track(track_id="t1", source_id="sim", cls="car", segment_id="s1", points=pts)
    evs = detect_sudden_stops(tr)
    assert len(evs) == 1 and evs[0].kind.value == "sudden_stop"


def test_collision_detection_pair():
    t0 = datetime(2025, 1, 1, 9, 0, 0)
    # two vehicles converge to the same point and stop at t+10s
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
    evs = detect_collisions([a, b])
    assert len(evs) == 1
    assert set(evs[0].track_ids) == {"A", "B"}
    assert evs[0].confidence > 0.6


def test_no_false_collision_when_far():
    t0 = datetime(2025, 1, 1, 9, 0, 0)
    a = Track(
        track_id="A",
        source_id="sim",
        cls="car",
        segment_id="s1",
        points=[
            TrackPoint(ts=t0, lat=12.90, lon=77.60, speed_kph=2, heading_deg=90),
        ],
    )
    b = Track(
        track_id="B",
        source_id="sim",
        cls="car",
        segment_id="s2",
        points=[
            TrackPoint(ts=t0, lat=12.95, lon=77.65, speed_kph=2, heading_deg=90),  # ~7km away
        ],
    )
    assert detect_collisions([a, b]) == []


def test_intelligence_service_end_to_end():
    net = build_grid_network(5)
    st = memory_storage()
    save_network(net, st.db)
    eng = SimulationEngine(net)
    for _ in range(40):
        snap = eng.step_once()
        eng.persist(st, snap)
    svc = IntelligenceService(st)
    metrics = svc.latest_metrics()
    assert len(metrics) == len(net.segments)
    summary = svc.summary()
    assert summary["segments"] == len(net.segments)
    assert 0 <= summary["avg_congestion"] <= 100
    spots = svc.hotspots(top_n=5)
    assert len(spots) <= 5
    # travel time between two corners returns current >= free-flow
    est = svc.travel_time("J0_0", "J4_4")
    assert est is not None and est.current_s >= est.free_flow_s - 1e-6
    # collisions runs without error (may be empty) and returns a list
    assert isinstance(svc.collisions(), list)
    # detect_all integrates per-track + pairwise detectors
    assert isinstance(detect_all(list(eng.micro.tracks.values()), net), list)
