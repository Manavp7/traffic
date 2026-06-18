"""Freight optimisation — truck fleet routing + fuel-cost estimation."""

from __future__ import annotations

import random

from traffic_os.common.config import Settings
from traffic_os.common.logging import get_logger
from traffic_os.decision.routing import build_graph, route_segments
from traffic_os.intelligence.current import current_metrics
from traffic_os.schemas import FreightTrip
from traffic_os.simulation.network import RoadNetwork, load_network

log = get_logger("mobility.freight")

TRUCK_FUEL_L_PER_KM = 0.35  # heavy vehicle baseline
TRUCK_IDLE_L_PER_H = 2.5


class FreightService:
    def __init__(self, storage) -> None:
        self.storage = storage
        self.settings: Settings = getattr(storage, "settings", None) or Settings(mode="dev")
        self._net: RoadNetwork | None = None

    @property
    def net(self) -> RoadNetwork:
        if self._net is None or not self._net.segments:
            self._net = load_network(self.storage.db)
        return self._net

    def plan(self, n: int = 8, *, seed: int = 0, persist: bool = True) -> dict:
        net = self.net
        rng = random.Random(seed)
        metrics = current_metrics(self.storage.db)
        graph_t = build_graph(net, metrics, weight="time")
        js = list(net.junctions)
        trips: list[FreightTrip] = []
        for i in range(n):
            o, d = rng.choice(js), rng.choice(js)
            if o == d:
                continue
            segs = route_segments(net, graph_t, o, d)
            if not segs:
                continue
            dist = sum(net.segments[s].length_m for s in segs)
            cur = sum(
                (
                    metrics[s].travel_time_s
                    if s in metrics
                    else net.segments[s].length_m / max(net.segments[s].speed_limit_kph / 3.6, 1)
                )
                for s in segs
            )
            free = sum(
                net.segments[s].length_m / max(net.segments[s].speed_limit_kph / 3.6, 1)
                for s in segs
            )
            delay_h = max(0.0, cur - free) / 3600.0
            fuel = dist / 1000.0 * TRUCK_FUEL_L_PER_KM + delay_h * TRUCK_IDLE_L_PER_H
            cost = (
                fuel * self.settings.fuel_price_inr_per_litre
                + delay_h * self.settings.value_of_time_inr_per_hour * 2  # freight time is costlier
            )
            trips.append(
                FreightTrip(
                    id=f"TRK-{i+1}",
                    origin=o,
                    destination=d,
                    segments=segs,
                    distance_m=round(dist, 1),
                    eta_s=round(cur, 1),
                    free_flow_s=round(free, 1),
                    fuel_litres=round(fuel, 2),
                    cost_inr=round(cost, 1),
                )
            )
        if persist and trips:
            self.storage.db.clear("freight_trip")
            self.storage.db.upsert_many("freight_trip", trips)
        return {
            "trucks": len(trips),
            "total_distance_km": round(sum(t.distance_m for t in trips) / 1000.0, 1),
            "total_fuel_litres": round(sum(t.fuel_litres for t in trips), 1),
            "total_cost_inr": round(sum(t.cost_inr for t in trips), 1),
            "avg_delay_min": round(
                sum((t.eta_s - t.free_flow_s) for t in trips) / max(len(trips), 1) / 60, 1
            ),
            "trips": [t.model_dump(mode="json") for t in trips],
        }
