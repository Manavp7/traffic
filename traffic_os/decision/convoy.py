"""VIP / convoy routing with a rolling green-wave preemption schedule."""

from __future__ import annotations

from traffic_os.decision.routing import build_graph, nearest_junction, route_segments
from traffic_os.intelligence.current import current_metrics
from traffic_os.simulation.network import RoadNetwork


def plan_convoy(
    net: RoadNetwork,
    storage,
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    *,
    speed_kph: float = 50.0,
) -> dict:
    """Route a convoy and compute when each signal must turn green (rolling green wave)."""
    metrics = current_metrics(storage.db)
    o = nearest_junction(net, origin_lat, origin_lon)
    d = nearest_junction(net, dest_lat, dest_lon)
    segs = route_segments(net, build_graph(net, metrics, weight="time"), o, d)
    if not segs:
        segs = route_segments(net, build_graph(net), o, d)
    if not segs:
        return {"feasible": False, "route_segments": [], "green_wave": []}

    schedule = []
    t = 0.0  # seconds from convoy start
    convoy_mps = speed_kph / 3.6
    for sid in segs:
        seg = net.segments[sid]
        sig = net.signal_for_junction(seg.to_junction)
        t += seg.length_m / max(convoy_mps, 1.0)
        if sig is not None:
            schedule.append(
                {
                    "signal_id": sig.id,
                    "junction_id": seg.to_junction,
                    "green_at_s": round(t, 1),
                    "approach_segment": sid,
                }
            )
    return {
        "feasible": True,
        "origin": o,
        "destination": d,
        "route_segments": segs,
        "distance_m": round(sum(net.segments[s].length_m for s in segs), 0),
        "eta_s": round(t, 1),
        "green_wave": schedule,
    }
