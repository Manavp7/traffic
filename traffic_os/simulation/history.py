"""Fast statistical history generator for the forecasting/accident-risk models.

Running the microsim for weeks would be far too slow, so historical ``SegmentMetric``
series are generated analytically with realistic diurnal + weekly + weather + event
patterns and noise — calibrated to resemble the live simulator. Weather and events
are stored alongside so the prediction layer can use them as features.
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta

from traffic_os.common.logging import get_logger
from traffic_os.common.timeutil import utcnow
from traffic_os.schemas import SegmentMetric, Weather
from traffic_os.simulation.events import make_event
from traffic_os.simulation.microsim import JAM_DENSITY_PER_LANE, diurnal_factor
from traffic_os.simulation.network import RoadNetwork
from traffic_os.simulation.weather import weather_at

log = get_logger("sim.history")


def _segment_importance(net: RoadNetwork) -> dict[str, float]:
    """Higher for arterials and central segments -> they congest more."""
    lats = [j.lat for j in net.junctions.values()]
    lons = [j.lon for j in net.junctions.values()]
    clat, clon = sum(lats) / len(lats), sum(lons) / len(lons)
    maxd = max(math.hypot(j.lat - clat, j.lon - clon) for j in net.junctions.values()) or 1.0
    out = {}
    for sid, seg in net.segments.items():
        mlat, mlon = seg.geometry[len(seg.geometry) // 2]
        centrality = 1.0 - math.hypot(mlat - clat, mlon - clon) / maxd
        arterial = 0.3 if seg.lanes >= 3 else 0.0
        out[sid] = max(0.1, 0.55 * centrality + arterial + 0.15)
    return out


def generate_history(
    net: RoadNetwork,
    db,
    *,
    days: int = 14,
    step_min: int = 15,
    seed: int = 42,
    end: datetime | None = None,
) -> dict[str, int]:
    """Generate ``days`` of history at ``step_min`` resolution and persist it."""
    rng = random.Random(seed)
    end = end or utcnow().replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=days)
    importance = _segment_importance(net)

    steps = int(days * 24 * 60 / step_min)
    metrics: list[SegmentMetric] = []
    weathers: list[Weather] = []
    events = []

    # a few events scattered through the period
    for _ in range(max(2, days // 3)):
        ev_day = rng.randint(0, days - 1)
        ev_hour = rng.choice([11, 17, 19])
        ev_start = start + timedelta(days=ev_day, hours=ev_hour)
        events.append(make_event(net, ev_start, rng))

    cur = start
    daily_weather: dict[int, Weather] = {}
    for _ in range(steps):
        hour = cur.hour + cur.minute / 60.0
        weekday = cur.weekday()  # 0=Mon
        weekend = 0.6 if weekday >= 5 else 1.0
        dfac = diurnal_factor(hour)

        # one weather sample per day (cache), stored hourly
        day_key = cur.toordinal()
        if day_key not in daily_weather:
            daily_weather[day_key] = weather_at(cur, rng)
        wx = daily_weather[day_key]
        if cur.minute == 0:
            weathers.append(
                Weather(
                    ts=cur,
                    kind=wx.kind,
                    rain_mm=wx.rain_mm,
                    visibility_m=wx.visibility_m,
                    capacity_factor=wx.capacity_factor,
                )
            )

        # event surge near venue time
        ev_boost = 0.0
        for ev in events:
            if ev.start - timedelta(hours=1) <= cur <= ev.end:
                ev_boost = 0.25

        wx_penalty = (1.0 - wx.capacity_factor) * 0.6

        for sid, seg in net.segments.items():
            imp = importance[sid]
            base = 100.0 * imp * dfac * weekend
            cong = base * (1.0 + wx_penalty) + ev_boost * 100.0 * imp
            cong += rng.gauss(0, 6)
            cong = max(0.0, min(100.0, cong))

            # derive consistent physical metrics from congestion
            speed = max(4.0, seg.speed_limit_kph * (1.0 - 0.85 * cong / 100.0))
            occ = min(100.0, cong * 0.9 + rng.uniform(0, 5))
            dens = occ / 100.0 * JAM_DENSITY_PER_LANE
            queue = max(0.0, (cong - 40) / 60.0) * 180.0 * imp
            tt = seg.length_m / max(speed / 3.6, 0.5)
            metrics.append(
                SegmentMetric(
                    segment_id=sid,
                    ts=cur,
                    vehicle_count=int(dens * seg.lanes * seg.length_m / 1000.0 / 1.2),
                    density_pcu_per_km=round(dens, 2),
                    speed_kph=round(speed, 2),
                    occupancy_pct=round(occ, 2),
                    queue_len_m=round(queue, 1),
                    congestion_score=round(cong, 1),
                    travel_time_s=round(tt, 1),
                )
            )
        cur += timedelta(minutes=step_min)

    log.info(
        "Persisting %d historical metrics, %d weather rows, %d events ...",
        len(metrics),
        len(weathers),
        len(events),
    )
    db.clear("segment_metric")
    # batch insert in chunks to keep memory/SQL reasonable
    _chunked_upsert(db, "segment_metric", metrics, 5000)
    db.clear("weather")
    _chunked_upsert(db, "weather", weathers, 5000)
    db.clear("city_event")
    db.upsert_many("city_event", events)
    return {"metrics": len(metrics), "weather": len(weathers), "events": len(events)}


def _chunked_upsert(db, collection: str, objs: list, size: int) -> None:
    for i in range(0, len(objs), size):
        db.upsert_many(collection, objs[i : i + size])
