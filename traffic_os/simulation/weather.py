"""Synthetic weather generation with traffic-capacity impact."""

from __future__ import annotations

import math
import random
from datetime import datetime

from traffic_os.schemas import Weather, WeatherKind

# capacity multiplier per weather kind (rain/fog slow traffic)
_CAPACITY = {
    WeatherKind.CLEAR: 1.0,
    WeatherKind.RAIN: 0.85,
    WeatherKind.HEAVY_RAIN: 0.65,
    WeatherKind.FOG: 0.8,
    WeatherKind.FLOOD: 0.45,
}


def weather_at(ts: datetime, rng: random.Random) -> Weather:
    """Deterministic-ish weather: a slow seasonal sine plus daily noise."""
    day = ts.timetuple().tm_yday
    # rain more likely on some days (monsoon-like wave)
    wave = 0.5 + 0.5 * math.sin(day / 9.0)
    roll = rng.random()
    if roll < 0.04 * wave:
        kind = WeatherKind.HEAVY_RAIN
        rain = rng.uniform(20, 50)
    elif roll < 0.18 * wave:
        kind = WeatherKind.RAIN
        rain = rng.uniform(2, 15)
    elif roll < 0.22:
        kind = WeatherKind.FOG
        rain = 0.0
    else:
        kind = WeatherKind.CLEAR
        rain = 0.0
    vis = 300.0 if kind == WeatherKind.FOG else (2000.0 if rain > 15 else 10000.0)
    return Weather(
        ts=ts,
        kind=kind,
        rain_mm=round(rain, 1),
        visibility_m=vis,
        capacity_factor=_CAPACITY[kind],
    )
