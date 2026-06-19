"""Disaster evacuation planning — capacity-aware mass-egress routing."""

from __future__ import annotations

from traffic_os.common.geo import haversine_m
from traffic_os.decision.routing import build_graph, route_segments
from traffic_os.simulation.network import RoadNetwork


def plan_evacuation(
    net: RoadNetwork,
    zone_junctions: list[str],
    exit_junctions: list[str],
    *,
    population: int = 10000,
    exit_capacity: int = 3000,
    blocked: set[str] | None = None,
) -> dict:
    """Assign evacuees from a danger zone to the nearest exits within capacity."""
    graph = build_graph(net, blocked=blocked)
    per_origin = max(1, population // max(len(zone_junctions), 1))
    remaining = dict.fromkeys(exit_junctions, exit_capacity)
    assignments = []
    unassigned = 0

    for origin in zone_junctions:
        # rank exits by route distance, fill until capacity
        ranked = []
        for ex in exit_junctions:
            segs = route_segments(net, graph, origin, ex)
            if not segs:
                continue
            dist = sum(net.segments[s].length_m for s in segs)
            ranked.append((dist, ex, segs))
        ranked.sort(key=lambda x: x[0])
        people = per_origin
        for dist, ex, segs in ranked:
            if people <= 0:
                break
            take = min(people, remaining[ex])
            if take <= 0:
                continue
            remaining[ex] -= take
            people -= take
            assignments.append(
                {
                    "from": origin,
                    "to_exit": ex,
                    "people": take,
                    "distance_m": round(dist, 0),
                    "route_segments": segs,
                }
            )
        unassigned += max(0, people)

    return {
        "population": population,
        "zone_junctions": zone_junctions,
        "exits": exit_junctions,
        "assignments": assignments,
        "evacuated": population - unassigned,
        "unassigned": unassigned,
        "feasible": unassigned == 0,
    }


def nearest_exits(net: RoadNetwork, zone_center: tuple[float, float], k: int = 3) -> list[str]:
    """Pick boundary junctions farthest from the zone centre as exits."""
    clat, clon = zone_center
    ranked = sorted(net.junctions.values(), key=lambda j: -haversine_m(clat, clon, j.lat, j.lon))
    return [j.id for j in ranked[:k]]
