"""Emergency Corridor Optimizer — ambulance / fire / police / disaster response.

Computes the fastest route for an emergency vehicle and the signals to preempt
along it, reporting the ETA saving versus normal (congested) travel.
"""

from __future__ import annotations

import uuid

from traffic_os.common.logging import get_logger
from traffic_os.decision.routing import build_graph, nearest_junction, route_segments
from traffic_os.schemas import EmergencyVehicle, GreenCorridor, SegmentMetric
from traffic_os.simulation.network import RoadNetwork

log = get_logger("decision.emergency")


def plan_corridor(
    net: RoadNetwork,
    metrics: dict[str, SegmentMetric],
    ev: EmergencyVehicle,
    *,
    blocked: set[str] | None = None,
) -> GreenCorridor | None:
    origin = nearest_junction(net, ev.lat, ev.lon)
    dest = nearest_junction(net, ev.dest_lat, ev.dest_lon)
    if origin == dest:
        return None
    # route on current travel time (avoid congestion + blockages)
    graph = build_graph(net, metrics, blocked=blocked, weight="time")
    segs = route_segments(net, graph, origin, dest)
    if not segs:
        # fall back to distance-only routing
        segs = route_segments(net, build_graph(net, blocked=blocked), origin, dest)
    if not segs:
        return None

    distance = 0.0
    baseline_eta = 0.0
    corridor_eta = 0.0
    signals_preempted: list[str] = []
    for sid in segs:
        seg = net.segments[sid]
        distance += seg.length_m
        m = metrics.get(sid)
        cur_speed = m.speed_kph if m and m.speed_kph > 1 else seg.speed_limit_kph
        baseline_eta += seg.length_m / max(cur_speed / 3.6, 0.5)
        # preempted corridor: emergency travels at near free-flow, and never slower
        # than the current traffic (so a corridor is always >= as fast as baseline)
        corridor_speed = max(cur_speed, seg.speed_limit_kph * 0.9)
        corridor_eta += seg.length_m / max(corridor_speed / 3.6, 0.5)
        sig = net.signal_for_junction(seg.to_junction)
        if sig is not None:
            signals_preempted.append(sig.id)

    return GreenCorridor(
        id=f"GC-{uuid.uuid4().hex[:8]}",
        vehicle_id=ev.id,
        type=ev.type,
        route_segments=segs,
        signals_preempted=signals_preempted,
        eta_s=round(corridor_eta, 1),
        baseline_eta_s=round(baseline_eta, 1),
        distance_m=round(distance, 1),
    )


def apply_corridor(
    signals, net: RoadNetwork, corridor: GreenCorridor, *, hold_s: float = 25.0
) -> None:
    """Preempt each signal along the corridor to green the approaching movement."""
    for sid in corridor.route_segments:
        seg = net.segments[sid]
        sig = net.signal_for_junction(seg.to_junction)
        if sig is not None:
            signals.preempt(sig.id, {sid}, hold_s)
