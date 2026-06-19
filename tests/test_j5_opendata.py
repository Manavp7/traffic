"""J5: open-data portal — GeoJSON exports (public, no auth)."""

from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient

from traffic_os.api import runtime
from traffic_os.api.app import app
from traffic_os.api.runtime import AppState
from traffic_os.schemas import Incident, IncidentStatus, IncidentType
from traffic_os.storage import memory_storage


def test_opendata_geojson_public_even_with_api_key():
    storage = memory_storage()
    storage.settings.sim_grid_size = 4
    storage.settings.api_key = "locked"  # enable auth; opendata must remain public
    state = AppState(storage, history_days=1)
    state.tick_sleep_s = 10.0
    for _ in range(10):
        state.engine.persist_live(storage, state.engine.step_once())
    storage.db.upsert(
        "incident",
        Incident(
            id="I1",
            ts=datetime.now(),
            type=IncidentType.ACCIDENT,
            lat=12.97,
            lon=77.6,
            severity=0.8,
            status=IncidentStatus.ACTIVE,
        ),
    )
    runtime.set_state(state)
    try:
        with TestClient(app) as c:
            net = c.get("/opendata/network.geojson").json()
            assert net["type"] == "FeatureCollection"
            assert len(net["features"]) > 0
            f = net["features"][0]
            assert f["geometry"]["type"] == "LineString"
            assert len(f["geometry"]["coordinates"][0]) == 2  # [lon, lat]

            inc = c.get("/opendata/incidents.geojson").json()
            assert inc["type"] == "FeatureCollection"
            assert any(ft["properties"]["id"] == "I1" for ft in inc["features"])
    finally:
        runtime.set_state(None)  # type: ignore[arg-type]
