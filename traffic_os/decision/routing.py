"""Shared routing helpers for the decision layer (graph + nearest junction)."""

from __future__ import annotations

import networkx as nx

from traffic_os.common.geo import haversine_m
from traffic_os.schemas import SegmentMetric
from traffic_os.simulation.network import RoadNetwork


def build_graph(
    net: RoadNetwork,
    metrics: dict[str, SegmentMetric] | None = None,
    *,
    blocked: set[str] | None = None,
    weight: str = "length",
) -> nx.DiGraph:
    blocked = blocked or set()
    g = nx.DiGraph()
    for seg in net.segments.values():
        if seg.id in blocked:
            continue
        if weight == "time" and metrics and seg.id in metrics:
            w = max(metrics[seg.id].travel_time_s, 0.1)
        else:
            w = seg.length_m
        g.add_edge(seg.from_junction, seg.to_junction, seg=seg.id, weight=w)
    return g


def nearest_junction(net: RoadNetwork, lat: float, lon: float) -> str:
    return min(
        net.junctions.values(),
        key=lambda j: haversine_m(lat, lon, j.lat, j.lon),
    ).id


def route_segments(net: RoadNetwork, graph: nx.DiGraph, origin: str, destination: str) -> list[str]:
    try:
        nodes = nx.shortest_path(graph, origin, destination, weight="weight")
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return []
    segs = []
    for a, b in zip(nodes[:-1], nodes[1:], strict=False):
        sid = net.pair_to_segment.get((a, b))
        if sid is None:
            return []
        segs.append(sid)
    return segs
