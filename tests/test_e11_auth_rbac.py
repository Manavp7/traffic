"""E11: auth (API key) + RBAC (roles) + audit log."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from traffic_os.api import runtime
from traffic_os.api.app import app
from traffic_os.api.runtime import AppState
from traffic_os.storage import memory_storage


@pytest.fixture()
def state_and_client():
    storage = memory_storage()
    storage.settings.sim_grid_size = 4
    storage.settings.sim_demand_scale = 60
    state = AppState(storage, history_days=1)
    state.tick_sleep_s = 10.0
    for _ in range(15):
        state.engine.persist_live(storage, state.engine.step_once())
    runtime.set_state(state)
    with TestClient(app) as c:
        yield state, c
    runtime.set_state(None)  # type: ignore[arg-type]


def test_operator_denied_commissioner_endpoints(state_and_client):
    _, c = state_and_client
    assert c.get("/commissioner", headers={"X-Role": "operator"}).status_code == 403
    assert c.post("/signals/apply", headers={"X-Role": "operator"}).status_code == 403


def test_commissioner_allowed_and_audited(state_and_client):
    state, c = state_and_client
    assert c.post("/signals/apply", headers={"X-Role": "commissioner"}).status_code == 200
    audit = c.get("/audit", headers={"X-Role": "commissioner"}).json()
    assert any(a["action"] == "signals.apply" for a in audit)


def test_public_endpoints_open_to_operator(state_and_client):
    _, c = state_and_client
    assert c.get("/healthz").status_code == 200
    assert c.get("/network", headers={"X-Role": "operator"}).status_code == 200
    assert c.get("/intelligence/summary", headers={"X-Role": "operator"}).status_code == 200


def test_api_key_enforced_when_set(state_and_client):
    state, c = state_and_client
    state.settings.api_key = "secret-123"
    # missing key -> 401 on a protected (non-public) path
    assert c.get("/network").status_code == 401
    # correct key -> ok
    assert c.get("/network", headers={"X-API-Key": "secret-123"}).status_code == 200
    # healthz stays public
    assert c.get("/healthz").status_code == 200
    state.settings.api_key = None
