"""J1: data connector providers (local + third-party fallback)."""

from __future__ import annotations

from traffic_os.integrations import (
    LocalTrafficProvider,
    get_traffic_provider,
    get_weather_provider,
    provider_status,
)
from traffic_os.simulation import SimulationEngine, build_grid_network, save_network
from traffic_os.storage import memory_storage


def _city():
    net = build_grid_network(4)
    st = memory_storage()
    save_network(net, st.db)
    eng = SimulationEngine(net, st.settings)
    for _ in range(15):
        eng.persist_live(st, eng.step_once())
    return st


def test_local_traffic_provider():
    st = _city()
    p = LocalTrafficProvider(st)
    speeds = p.segment_speeds()
    assert speeds and all(v >= 0 for v in speeds.values())


def test_factory_falls_back_to_local(monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    monkeypatch.delenv("OPENWEATHER_API_KEY", raising=False)
    st = _city()
    assert get_traffic_provider(st).name == "local-sim"
    assert get_weather_provider(st).name == "local-sim"


def test_provider_status_reports_active(monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    status = provider_status()
    assert status["traffic"]["active"] == "local-sim"
    assert "weather" in status and "transit" in status
