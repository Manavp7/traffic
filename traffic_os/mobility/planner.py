"""Multimodal trip planner — car/EV vs bus+walk, accessibility-aware."""

from __future__ import annotations

from traffic_os.intelligence.current import current_metrics
from traffic_os.intelligence.travel_time import TravelTimeEstimator
from traffic_os.simulation.network import RoadNetwork, load_network

WALK_SPEED_MPS = 1.3
BUS_OVERHEAD_S = 300  # average wait + stops overhead


class TripPlanner:
    def __init__(self, storage, transit) -> None:
        self.storage = storage
        self.transit = transit
        self._net: RoadNetwork | None = None

    @property
    def net(self) -> RoadNetwork:
        if self._net is None or not self._net.segments:
            self._net = load_network(self.storage.db)
        return self._net

    def plan(self, origin: str, destination: str, *, accessible: bool = False) -> dict:
        net = self.net
        metrics = current_metrics(self.storage.db)
        est = TravelTimeEstimator(net, metrics)
        drive = est.estimate(origin, destination)

        options: list[dict] = []
        if drive:
            options.append(
                {
                    "mode": "car",
                    "duration_min": round(drive.current_s / 60, 1),
                    "distance_km": round(drive.distance_m / 1000, 1),
                    "legs": [{"mode": "car", "from": origin, "to": destination}],
                }
            )
            # EV variant — same time, zero tailpipe emissions
            options.append(
                {
                    "mode": "ev",
                    "duration_min": round(drive.current_s / 60, 1),
                    "distance_km": round(drive.distance_m / 1000, 1),
                    "zero_emission": True,
                    "legs": [{"mode": "ev", "from": origin, "to": destination}],
                }
            )

        # public transport: a bus route whose stops include both endpoints
        for route in self.transit.routes():
            stops = route.stops
            if origin in stops and destination in stops:
                i, j = stops.index(origin), stops.index(destination)
                hops = abs(j - i)
                bus_s = hops * 90 + BUS_OVERHEAD_S
                options.append(
                    {
                        "mode": "bus",
                        "route": route.name,
                        "duration_min": round(bus_s / 60, 1),
                        "stops": hops,
                        "accessible": True,
                        "legs": [
                            {"mode": "walk", "to": f"stop {origin}"},
                            {"mode": "bus", "route": route.name, "from": origin, "to": destination},
                            {"mode": "walk", "to": destination},
                        ],
                    }
                )
                break

        if accessible:
            options = [o for o in options if o.get("accessible") or o["mode"] in ("car", "ev")]
        options.sort(key=lambda o: float(o["duration_min"]))
        return {
            "origin": origin,
            "destination": destination,
            "accessible": accessible,
            "options": options,
            "recommended": options[0] if options else None,
        }
