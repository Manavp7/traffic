"""J4: JWT auth layered over RBAC."""

from __future__ import annotations

from fastapi.testclient import TestClient

from traffic_os.api import runtime
from traffic_os.api.app import app
from traffic_os.api.jwt_auth import create_token, verify_token
from traffic_os.api.runtime import AppState
from traffic_os.storage import memory_storage


def test_token_roundtrip_and_expiry():
    secret = "s3cret"
    tok = create_token({"role": "commissioner"}, secret, exp_s=60)
    payload = verify_token(tok, secret)
    assert payload and payload["role"] == "commissioner"
    # wrong secret fails
    assert verify_token(tok, "other") is None
    # expired fails
    expired = create_token({"role": "operator"}, secret, exp_s=-1)
    assert verify_token(expired, secret) is None
    # tampered fails
    assert verify_token(tok + "x", secret) is None


def test_jwt_grants_commissioner_access():
    storage = memory_storage()
    storage.settings.sim_grid_size = 4
    state = AppState(storage, history_days=1)
    state.tick_sleep_s = 10.0
    for _ in range(10):
        state.engine.persist_live(storage, state.engine.step_once())
    runtime.set_state(state)
    try:
        with TestClient(app) as c:
            tok = c.post("/auth/token", json={"role": "commissioner"}).json()["access_token"]
            # without token -> operator default -> 403 on a commissioner route
            assert c.post("/signals/apply").status_code == 403
            # with bearer token -> allowed
            r = c.post("/signals/apply", headers={"Authorization": f"Bearer {tok}"})
            assert r.status_code == 200
    finally:
        runtime.set_state(None)  # type: ignore[arg-type]
