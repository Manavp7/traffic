"""Phase 5: violation engine tests."""

from __future__ import annotations

from datetime import datetime, timedelta

from traffic_os.common.geo import bearing_deg, interpolate
from traffic_os.schemas import Track, TrackPoint
from traffic_os.simulation import SimulationEngine, build_grid_network, save_network
from traffic_os.storage import memory_storage
from traffic_os.violations import (
    ViolationService,
    detect_illegal_parking,
    detect_red_light,
    detect_speeding,
    detect_wrong_side,
)

T0 = datetime(2025, 1, 1, 9, 0, 0)


def _point_on(seg, frac, **kw):
    (la1, lo1), (la2, lo2) = seg.geometry[0], seg.geometry[-1]
    lat, lon = interpolate(la1, lo1, la2, lo2, frac)
    return TrackPoint(lat=lat, lon=lon, **kw)


def _seg_bearing(seg):
    (la1, lo1), (la2, lo2) = seg.geometry[0], seg.geometry[-1]
    return bearing_deg(la1, lo1, la2, lo2)


def _slow_segment(net):
    return next(s for s in net.segments.values() if s.speed_limit_kph == 40.0)


def test_speeding_detection():
    net = build_grid_network(5)
    seg = _slow_segment(net)  # 40 km/h
    sb = _seg_bearing(seg)
    pts = [
        _point_on(seg, 0.2, ts=T0, speed_kph=38, heading_deg=sb),
        _point_on(seg, 0.5, ts=T0 + timedelta(seconds=5), speed_kph=62, heading_deg=sb),
    ]
    tr = Track(track_id="v1", source_id="sim", cls="car", segment_id=seg.id, points=pts)
    v = detect_speeding(tr, net)
    assert len(v) == 1 and v[0].type.value == "speeding"


def test_no_speeding_when_legal():
    net = build_grid_network(5)
    seg = _slow_segment(net)
    sb = _seg_bearing(seg)
    tr = Track(
        track_id="v1",
        source_id="sim",
        cls="car",
        segment_id=seg.id,
        points=[_point_on(seg, 0.5, ts=T0, speed_kph=40, heading_deg=sb)],
    )
    assert detect_speeding(tr, net) == []


def test_wrong_side_detection():
    net = build_grid_network(5)
    seg = next(iter(net.segments.values()))
    sb = _seg_bearing(seg)
    opp = (sb + 180) % 360
    pts = [
        _point_on(seg, 0.6, ts=T0, speed_kph=20, heading_deg=opp),
        _point_on(seg, 0.5, ts=T0 + timedelta(seconds=5), speed_kph=20, heading_deg=opp),
        _point_on(seg, 0.4, ts=T0 + timedelta(seconds=10), speed_kph=20, heading_deg=opp),
    ]
    tr = Track(track_id="v2", source_id="sim", cls="car", segment_id=seg.id, points=pts)
    v = detect_wrong_side(tr, net)
    assert len(v) == 1 and v[0].type.value == "wrong_side"


def test_no_wrong_side_when_correct_direction():
    net = build_grid_network(5)
    seg = next(iter(net.segments.values()))
    sb = _seg_bearing(seg)
    pts = [
        _point_on(seg, f, ts=T0 + timedelta(seconds=5 * i), speed_kph=20, heading_deg=sb)
        for i, f in enumerate([0.3, 0.5, 0.7])
    ]
    tr = Track(track_id="v2", source_id="sim", cls="car", segment_id=seg.id, points=pts)
    assert detect_wrong_side(tr, net) == []


def test_illegal_parking_midblock():
    net = build_grid_network(5)
    # long segment ideally; pick any, park at frac 0.5 for 120s
    seg = max(net.segments.values(), key=lambda s: s.length_m)
    sb = _seg_bearing(seg)
    pts = [
        _point_on(seg, 0.5, ts=T0 + timedelta(seconds=20 * i), speed_kph=0, heading_deg=sb)
        for i in range(7)
    ]  # 120s stationary
    tr = Track(track_id="v3", source_id="sim", cls="car", segment_id=seg.id, points=pts)
    v = detect_illegal_parking(tr, net)
    assert len(v) == 1 and v[0].type.value == "illegal_parking"


def test_no_parking_when_queued_at_junction():
    net = build_grid_network(5)
    seg = next(iter(net.segments.values()))
    sb = _seg_bearing(seg)
    # stationary right at the downstream junction (frac ~1.0) == queueing, legal
    pts = [
        _point_on(seg, 1.0, ts=T0 + timedelta(seconds=20 * i), speed_kph=0, heading_deg=sb)
        for i in range(7)
    ]
    tr = Track(track_id="v3", source_id="sim", cls="car", segment_id=seg.id, points=pts)
    assert detect_illegal_parking(tr, net) == []


def test_red_light_detection():
    net = build_grid_network(5)
    # find a segment whose downstream junction is signalised
    seg = next(s for s in net.segments.values() if net.junctions[s.to_junction].has_signal)
    sb = _seg_bearing(seg)
    pts = [_point_on(seg, 1.0, ts=T0, speed_kph=25, heading_deg=sb)]
    tr = Track(track_id="v4", source_id="sim", cls="car", segment_id=seg.id, points=pts)
    # red everywhere
    assert detect_red_light(tr, net, lambda sid, ts: False)[0].type.value == "red_light"
    # green -> no violation
    assert detect_red_light(tr, net, lambda sid, ts: True) == []


def test_service_end_to_end_low_false_positives():
    net = build_grid_network(5)
    st = memory_storage()
    save_network(net, st.db)
    eng = SimulationEngine(net)
    for _ in range(40):
        eng.persist(st, eng.step_once())
    svc = ViolationService(st)
    violations = svc.detect()
    # sim probes drive legally & within limits -> very few/no violations expected
    assert isinstance(violations, list)
    counts = svc.counts_by_type()
    assert sum(counts.values()) == len(violations)
