"""Incident auto-dispatch — assign the nearest available emergency unit + corridor."""

from __future__ import annotations

from dataclasses import dataclass

from traffic_os.common.geo import haversine_m
from traffic_os.decision.emergency import plan_corridor
from traffic_os.intelligence.current import current_metrics
from traffic_os.schemas import EmergencyType, EmergencyVehicle, Incident, IncidentType
from traffic_os.simulation.network import RoadNetwork

# which unit type responds to which incident
_RESPONSE = {
    IncidentType.ACCIDENT: EmergencyType.AMBULANCE,
    IncidentType.FIRE: EmergencyType.FIRE,
    IncidentType.FLOOD: EmergencyType.DISASTER,
    IncidentType.BREAKDOWN: EmergencyType.POLICE,
    IncidentType.HAZARD: EmergencyType.POLICE,
    IncidentType.ROADWORK: EmergencyType.POLICE,
}


@dataclass
class Unit:
    id: str
    type: EmergencyType
    lat: float
    lon: float
    available: bool = True


@dataclass
class DispatchResult:
    incident_id: str
    unit_id: str | None
    unit_type: str | None
    corridor: dict | None
    eta_s: float | None
    note: str = ""


def default_depots(net: RoadNetwork) -> list[Unit]:
    """Place a small fleet at spread-out junctions."""
    js = list(net.junctions.values())
    if not js:
        return []
    picks = js[:: max(1, len(js) // 6)][:6]
    units: list[Unit] = []
    types = [
        EmergencyType.AMBULANCE,
        EmergencyType.FIRE,
        EmergencyType.POLICE,
        EmergencyType.AMBULANCE,
        EmergencyType.DISASTER,
        EmergencyType.POLICE,
    ]
    for i, jn in enumerate(picks):
        units.append(Unit(id=f"U{i+1}", type=types[i % len(types)], lat=jn.lat, lon=jn.lon))
    return units


class DispatchService:
    def __init__(self, storage) -> None:
        self.storage = storage

    def dispatch(
        self, incidents: list[Incident], net: RoadNetwork, units: list[Unit] | None = None
    ) -> list[DispatchResult]:
        units = units if units is not None else default_depots(net)
        metrics = current_metrics(self.storage.db)
        results: list[DispatchResult] = []
        for inc in incidents:
            want = _RESPONSE.get(inc.type, EmergencyType.POLICE)
            pool = [u for u in units if u.available and u.type == want] or [
                u for u in units if u.available
            ]
            if not pool:
                results.append(DispatchResult(inc.id, None, None, None, None, "no units available"))
                continue
            unit = min(pool, key=lambda u: haversine_m(u.lat, u.lon, inc.lat, inc.lon))
            ev = EmergencyVehicle(
                id=unit.id,
                type=unit.type,
                lat=unit.lat,
                lon=unit.lon,
                dest_lat=inc.lat,
                dest_lon=inc.lon,
            )
            corridor = plan_corridor(net, metrics, ev)
            unit.available = False
            results.append(
                DispatchResult(
                    inc.id,
                    unit.id,
                    unit.type.value,
                    corridor.model_dump(mode="json") if corridor else None,
                    corridor.eta_s if corridor else None,
                    "dispatched",
                )
            )
        return results
