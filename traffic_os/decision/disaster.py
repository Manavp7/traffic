"""Disaster routing — reroute around blocked segments (flood / fire / earthquake)."""

from __future__ import annotations

from dataclasses import dataclass

from traffic_os.decision.routing import build_graph, route_segments
from traffic_os.schemas import SegmentMetric
from traffic_os.simulation.network import RoadNetwork


@dataclass
class Reroute:
    origin: str
    destination: str
    blocked: list[str]
    original_route: list[str]
    detour_route: list[str]
    feasible: bool
    extra_distance_m: float


def _distance(net: RoadNetwork, segs: list[str]) -> float:
    return sum(net.segments[s].length_m for s in segs if s in net.segments)


def reroute_around(
    net: RoadNetwork,
    origin: str,
    destination: str,
    blocked: set[str],
    metrics: dict[str, SegmentMetric] | None = None,
) -> Reroute:
    original = route_segments(net, build_graph(net, metrics), origin, destination)
    detour = route_segments(net, build_graph(net, metrics, blocked=blocked), origin, destination)
    feasible = bool(detour) and not (set(detour) & blocked)
    return Reroute(
        origin=origin,
        destination=destination,
        blocked=sorted(blocked),
        original_route=original,
        detour_route=detour,
        feasible=feasible,
        extra_distance_m=round(_distance(net, detour) - _distance(net, original), 1),
    )
