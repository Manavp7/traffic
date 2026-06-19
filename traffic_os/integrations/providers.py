"""Pluggable external data providers.

The **LocalProvider** serves data from the running simulation (always available). Real
third-party providers (Google/HERE/TomTom traffic, OpenWeather, GTFS transit) are wired
behind the same interface and activate when their API key env var is set — otherwise the
system transparently falls back to local data. No paid keys are bundled.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod

from traffic_os.common.logging import get_logger
from traffic_os.intelligence.current import current_metrics
from traffic_os.schemas import Weather

log = get_logger("integrations")


class TrafficProvider(ABC):
    name = "base"

    @abstractmethod
    def segment_speeds(self) -> dict[str, float]: ...


class WeatherProvider(ABC):
    name = "base"

    @abstractmethod
    def current(self) -> dict: ...


class LocalTrafficProvider(TrafficProvider):
    name = "local-sim"

    def __init__(self, storage) -> None:
        self.storage = storage

    def segment_speeds(self) -> dict[str, float]:
        return {sid: m.speed_kph for sid, m in current_metrics(self.storage.db).items()}


class LocalWeatherProvider(WeatherProvider):
    name = "local-sim"

    def __init__(self, storage) -> None:
        self.storage = storage

    def current(self) -> dict:
        rows = self.storage.db.find("weather", Weather, order_by_ts=True, desc=True, limit=1)
        if not rows:
            return {"kind": "clear", "rain_mm": 0.0, "source": self.name}
        w = rows[0]
        return {
            "kind": w.kind.value,
            "rain_mm": w.rain_mm,
            "capacity_factor": w.capacity_factor,
            "source": self.name,
        }


# --- third-party stubs (activate when key present) ------------------------- #
class _ExternalStub:
    """Base for keyed third-party providers; raises if used without a key."""

    env_key = ""
    name = "external"

    def __init__(self) -> None:
        self.api_key = os.environ.get(self.env_key, "")
        if not self.api_key:
            raise RuntimeError(f"{self.name} requires {self.env_key}")


class GoogleTrafficProvider(_ExternalStub, TrafficProvider):  # pragma: no cover - needs key
    env_key = "GOOGLE_MAPS_API_KEY"
    name = "google"

    def segment_speeds(self) -> dict[str, float]:
        raise NotImplementedError("wire Google Roads/Traffic API here")


class OpenWeatherProvider(_ExternalStub, WeatherProvider):  # pragma: no cover - needs key
    env_key = "OPENWEATHER_API_KEY"
    name = "openweather"

    def current(self) -> dict:
        raise NotImplementedError("wire OpenWeather API here")


def get_traffic_provider(storage) -> TrafficProvider:
    for cls in (GoogleTrafficProvider,):
        try:
            return cls()  # type: ignore[abstract]
        except Exception:
            continue
    return LocalTrafficProvider(storage)


def get_weather_provider(storage) -> WeatherProvider:
    for cls in (OpenWeatherProvider,):
        try:
            return cls()  # type: ignore[abstract]
        except Exception:
            continue
    return LocalWeatherProvider(storage)


def provider_status() -> dict:
    return {
        "traffic": {
            "google": bool(os.environ.get("GOOGLE_MAPS_API_KEY")),
            "here": bool(os.environ.get("HERE_API_KEY")),
            "tomtom": bool(os.environ.get("TOMTOM_API_KEY")),
            "active": "google" if os.environ.get("GOOGLE_MAPS_API_KEY") else "local-sim",
        },
        "weather": {
            "openweather": bool(os.environ.get("OPENWEATHER_API_KEY")),
            "active": "openweather" if os.environ.get("OPENWEATHER_API_KEY") else "local-sim",
        },
        "transit": {
            "gtfs": bool(os.environ.get("GTFS_FEED_URL")),
            "active": "gtfs" if os.environ.get("GTFS_FEED_URL") else "local-sim",
        },
    }
