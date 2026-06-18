"""Public-transport intelligence — bus routes, delays, passenger load."""

from __future__ import annotations

from traffic_os.common.logging import get_logger
from traffic_os.decision.routing import build_graph, route_segments
from traffic_os.intelligence.current import current_metrics
from traffic_os.schemas import BusRoute
from traffic_os.simulation.network import RoadNetwork, load_network

log = get_logger("mobility.transit")


class TransitService:
    def __init__(self, storage) -> None:
        self.storage = storage
        self._net: RoadNetwork | None = None

    @property
    def net(self) -> RoadNetwork:
        if self._net is None or not self._net.segments:
            self._net = load_network(self.storage.db)
        return self._net

    def build_routes(self, n: int = 4, *, persist: bool = True) -> list[BusRoute]:
        net = self.net
        js = list(net.junctions)
        if not js:
            return []
        graph = build_graph(net)
        # OD pairs spread across the network (corners + centre crossings)
        pairs = [
            (js[0], js[-1]),
            (js[len(js) // 4], js[-len(js) // 4]),
            (js[len(js) // 2], js[0]),
            (js[-1], js[len(js) // 3]),
        ][:n]
        routes: list[BusRoute] = []
        for i, (a, b) in enumerate(pairs):
            segs = route_segments(net, graph, a, b)
            if not segs:
                continue
            stops = [net.segments[segs[0]].from_junction] + [
                net.segments[s].to_junction for s in segs
            ]
            routes.append(
                BusRoute(id=f"BUS-{i+1}", name=f"Route {i+1}", segments=segs, stops=stops)
            )
        if persist and routes:
            self.storage.db.clear("bus_route")
            self.storage.db.upsert_many("bus_route", routes)
        return routes

    def routes(self) -> list[BusRoute]:
        routes = self.storage.db.find("bus_route", BusRoute, limit=100)
        return routes or self.build_routes()

    def status(self) -> list[dict]:
        net = self.net
        metrics = current_metrics(self.storage.db)
        out = []
        for r in self.routes():
            current = sum(
                (
                    metrics[s].travel_time_s
                    if s in metrics
                    else net.segments[s].length_m / max(net.segments[s].speed_limit_kph / 3.6, 1)
                )
                for s in r.segments
                if s in net.segments
            )
            free = sum(
                net.segments[s].length_m / max(net.segments[s].speed_limit_kph / 3.6, 1)
                for s in r.segments
                if s in net.segments
            )
            scheduled = free * 1.15
            delay = max(0.0, current - scheduled)
            cong = [metrics[s].congestion_score for s in r.segments if s in metrics]
            avg_cong = sum(cong) / len(cong) if cong else 0.0
            out.append(
                {
                    "id": r.id,
                    "name": r.name,
                    "stops": len(r.stops),
                    "current_min": round(current / 60, 1),
                    "scheduled_min": round(scheduled / 60, 1),
                    "delay_min": round(delay / 60, 1),
                    "on_time": delay <= scheduled * 0.2,
                    "passenger_load_pct": round(min(100.0, 40 + avg_cong * 0.5), 0),
                }
            )
        return out
