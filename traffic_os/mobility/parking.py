"""Smart parking — lots, occupancy, availability map + nearest-free guidance."""

from __future__ import annotations

import random

from traffic_os.common.geo import haversine_m
from traffic_os.common.logging import get_logger
from traffic_os.intelligence.current import current_metrics
from traffic_os.schemas import ParkingLot
from traffic_os.simulation.network import RoadNetwork, load_network

log = get_logger("mobility.parking")


class ParkingService:
    def __init__(self, storage) -> None:
        self.storage = storage
        self._net: RoadNetwork | None = None

    @property
    def net(self) -> RoadNetwork:
        if self._net is None or not self._net.segments:
            self._net = load_network(self.storage.db)
        return self._net

    def seed_lots(self, n: int = 8, *, seed: int = 0) -> list[ParkingLot]:
        rng = random.Random(seed)
        js = list(self.net.junctions.values())
        lots = []
        for i, jn in enumerate(rng.sample(js, min(n, len(js)))):
            cap = rng.choice([60, 120, 200, 350])
            lots.append(
                ParkingLot(
                    id=f"P{i+1}",
                    name=f"{jn.name} Parking",
                    junction_id=jn.id,
                    lat=jn.lat,
                    lon=jn.lon,
                    capacity=cap,
                    occupied=0,
                )
            )
        self.storage.db.clear("parking_lot")
        self.storage.db.upsert_many("parking_lot", lots)
        return lots

    def lots(self) -> list[ParkingLot]:
        lots = self.storage.db.find("parking_lot", ParkingLot, limit=500)
        return lots or self.seed_lots()

    def update_occupancy(self) -> list[ParkingLot]:
        """Occupancy correlates with nearby congestion + time-of-day noise."""
        metrics = current_metrics(self.storage.db)
        net = self.net
        rng = random.Random(len(metrics))
        lots = self.lots()
        for lot in lots:
            incoming = net.in_segments.get(lot.junction_id or "", [])
            cong = [metrics[s].congestion_score for s in incoming if s in metrics]
            base = (sum(cong) / len(cong) / 100.0) if cong else 0.4
            occ = min(lot.capacity, int(lot.capacity * min(1.0, base + rng.uniform(-0.1, 0.2))))
            lot.occupied = max(0, occ)
        self.storage.db.upsert_many("parking_lot", lots)
        return lots

    def nearest_free(self, lat: float, lon: float, *, need: int = 1) -> dict | None:
        candidates = [lot for lot in self.update_occupancy() if lot.available >= need]
        if not candidates:
            return None
        best = min(candidates, key=lambda lot: haversine_m(lat, lon, lot.lat, lot.lon))
        return {
            "id": best.id,
            "name": best.name,
            "available": best.available,
            "capacity": best.capacity,
            "lat": best.lat,
            "lon": best.lon,
            "distance_m": round(haversine_m(lat, lon, best.lat, best.lon), 0),
        }

    def status(self) -> list[dict]:
        return [
            {
                "id": lot.id,
                "name": lot.name,
                "lat": lot.lat,
                "lon": lot.lon,
                "capacity": lot.capacity,
                "occupied": lot.occupied,
                "available": lot.available,
                "occupancy_pct": round(lot.occupied / max(lot.capacity, 1) * 100, 0),
            }
            for lot in self.update_occupancy()
        ]
