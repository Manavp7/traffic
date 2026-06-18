"""E3: live adaptive signal apply + auto mode."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from traffic_os.api import runtime
from traffic_os.api.app import app
from traffic_os.api.runtime import AppState
from traffic_os.storage import memory_storage


@pytest.fixture()
def client():
    storage = memory_storage()
    storage.settings.sim_grid_size = 4
    storage.settings.sim_demand_scale = 70
    state = AppState(storage, history_days=1)
    state.tick_sleep_s = 0.05
    for _ in range(25):
        state.engine.persist_live(storage, state.engine.step_once())
    runtime.set_state(state)
    with TestClient(app) as c:
        yield c, state
    runtime.set_state(None)  # type: ignore[arg-type]


COMMISSIONER = {"X-Role": "commissioner"}


def test_apply_changes_live_signals(client):
    c, state = client
    r = c.post("/signals/apply", headers=COMMISSIONER).json()
    assert r["applied"] == len(state.engine.net.signals)
    assert r["plan"] and "phases" in r["plan"][0]
    # at least one signal received green overrides applied to the live controller
    overrides = [rt.green_override for rt in state.engine.signals.rt.values() if rt.green_override]
    assert overrides, "expected adaptive green overrides on the live engine"


def test_auto_toggle(client):
    c, state = client
    assert (
        c.post("/signals/auto", json={"enabled": True}, headers=COMMISSIONER).json()["adaptive"]
        is True
    )
    assert state.adaptive is True
    assert (
        c.post("/signals/auto", json={"enabled": False}, headers=COMMISSIONER).json()["adaptive"]
        is False
    )
    assert state.adaptive is False
