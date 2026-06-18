"""E5: operational alerts endpoint."""

from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient

from traffic_os.api import runtime
from traffic_os.api.app import app
from traffic_os.api.runtime import AppState
from traffic_os.schemas import Incident, IncidentStatus, IncidentType
from traffic_os.storage import memory_storage


def test_alerts_include_active_incident():
    storage = memory_storage()
    storage.settings.sim_grid_size = 4
    storage.settings.sim_demand_scale = 70
    state = AppState(storage, history_days=1)
    state.tick_sleep_s = 10.0  # keep loop idle during the test
    for _ in range(20):
        state.engine.persist_live(storage, state.engine.step_once())
    net = state.engine.net
    seg = net.in_segments["J2_2"][0]
    mid = net.segments[seg].geometry[1]
    storage.db.upsert(
        "incident",
        Incident(
            id="A1",
            ts=datetime.now(),
            type=IncidentType.ACCIDENT,
            lat=mid[0],
            lon=mid[1],
            segment_id=seg,
            severity=0.9,
            segments_blocked=[seg],
            status=IncidentStatus.ACTIVE,
            description="major accident",
        ),
    )
    runtime.set_state(state)
    try:
        with TestClient(app) as c:
            alerts = c.get("/alerts").json()
        assert any(a["kind"] == "incident" for a in alerts)
        # critical severity sorts first
        assert alerts[0]["severity"] in ("critical", "high")
    finally:
        runtime.set_state(None)  # type: ignore[arg-type]
