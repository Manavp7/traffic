"""Travel-time estimation: current (live) vs expected (free-flow) per route."""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

from traffic_os.schemas import SegmentMetric
from traffic_os.simulation.network import RoadNetwork


@dataclass
class RouteEstimate:
    origin: str
    destination: str
    segments: list[str]
    distance_m: float
    current_s: float
    free_flow_s: float

    @property
    def delay_s(self) -> float:
        return max(0.0, self.current_s - self.free_flow_s)

    @property
    def delay_ratio(self) -> float:
        return self.current_s / self.free_flow_s if self.free_flow_s else 1.0


class TravelTimeEstimator:
    def __init__(self, net: RoadNetwork, metrics: dict[str, SegmentMetric]) -> None:
        self.net = net
        self.metrics = metrics
        self._cur = self._graph(use_current=True)
        self._free = self._graph(use_current=False)

    def _graph(self, *, use_current: bool) -> nx.DiGraph:
        g = nx.DiGraph()
        for seg in self.net.segments.values():
            if use_current and seg.id in self.metrics:
                w = self.metrics[seg.id].travel_time_s
            else:
                w = seg.length_m / max(seg.speed_limit_kph / 3.6, 1.0)
            g.add_edge(seg.from_junction, seg.to_junction, seg=seg.id, weight=max(w, 0.1))
        return g

    def estimate(self, origin: str, destination: str) -> RouteEstimate | None:
        try:
            nodes = nx.shortest_path(self._cur, origin, destination, weight="weight")
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None
        segs, dist, cur, free = [], 0.0, 0.0, 0.0
        for a, b in zip(nodes[:-1], nodes[1:], strict=False):
            sid = self.net.pair_to_segment.get((a, b))
            if sid is None:
                continue
            seg = self.net.segments[sid]
            segs.append(sid)
            dist += seg.length_m
            free += seg.length_m / max(seg.speed_limit_kph / 3.6, 1.0)
            cur += (
                self.metrics[sid].travel_time_s
                if sid in self.metrics
                else (seg.length_m / max(seg.speed_limit_kph / 3.6, 1.0))
            )
        return RouteEstimate(
            origin=origin,
            destination=destination,
            segments=segs,
            distance_m=round(dist, 1),
            current_s=round(cur, 1),
            free_flow_s=round(free, 1),
        )
