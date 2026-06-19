"""Vulnerable-road-user (pedestrian/cyclist) near-miss detection from trajectories."""

from __future__ import annotations

from traffic_os.common.geo import haversine_m
from traffic_os.schemas import Track

NEAR_MISS_DIST_M = 6.0
VEHICLE_MIN_SPEED_KPH = 15.0  # a near-miss means the vehicle was still moving fast
VRU_CLASSES = {"pedestrian", "bike"}
VEHICLE_CLASSES = {"car", "bus", "truck", "auto"}


def detect_near_misses(tracks: list[Track]) -> list[dict]:
    """Pedestrian/cyclist ↔ vehicle close approach while the vehicle is moving fast."""
    vrus = [t for t in tracks if t.cls in VRU_CLASSES]
    vehicles = [t for t in tracks if t.cls in VEHICLE_CLASSES]
    out: list[dict] = []
    for vru in vrus:
        vru_pts = {p.ts: p for p in vru.points}
        for veh in vehicles:
            for vp in veh.points:
                pp = vru_pts.get(vp.ts)
                if pp is None or None in (pp.lat, pp.lon, vp.lat, vp.lon):
                    continue
                assert pp.lat is not None and pp.lon is not None
                assert vp.lat is not None and vp.lon is not None
                dist = haversine_m(pp.lat, pp.lon, vp.lat, vp.lon)
                if dist <= NEAR_MISS_DIST_M and vp.speed_kph >= VEHICLE_MIN_SPEED_KPH:
                    out.append(
                        {
                            "ts": vp.ts.isoformat(),
                            "lat": round((pp.lat + vp.lat) / 2, 6),
                            "lon": round((pp.lon + vp.lon) / 2, 6),
                            "vru_track": vru.track_id,
                            "vru_class": vru.cls,
                            "vehicle_track": veh.track_id,
                            "distance_m": round(dist, 1),
                            "vehicle_speed_kph": vp.speed_kph,
                            "severity": round(
                                min(1.0, vp.speed_kph / 50.0) * (1 - dist / NEAR_MISS_DIST_M), 2
                            ),
                        }
                    )
                    break  # one near-miss per (vru, vehicle) pair
    return out
