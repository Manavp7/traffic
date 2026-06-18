"""Phase 10: API gateway tests (FastAPI TestClient with an injected small state)."""

from __future__ import annotations

import pytest

pytest.importorskip("xgboost")

from fastapi.testclient import TestClient  # noqa: E402

from traffic_os.api import runtime  # noqa: E402
from traffic_os.api.app import app  # noqa: E402
from traffic_os.api.runtime import AppState  # noqa: E402
from traffic_os.storage import memory_storage  # noqa: E402


@pytest.fixture(scope="module")
def client():
    storage = memory_storage()
    storage.settings.sim_grid_size = 4
    storage.settings.sim_demand_scale = 60
    state = AppState(storage, history_days=2)
    state.tick_sleep_s = 0.05
    # warm a few live ticks synchronously so endpoints have current data
    for _ in range(20):
        state.engine.persist_live(storage, state.engine.step_once())
    runtime.set_state(state)
    with TestClient(app) as c:
        yield c
    runtime.set_state(None)  # type: ignore[arg-type]


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_network(client):
    r = client.get("/network").json()
    assert len(r["junctions"]) == 16
    assert len(r["segments"]) > 0
    assert r["segments"][0]["geometry"]


def test_live_and_summary(client):
    assert client.get("/live").status_code == 200
    summ = client.get("/intelligence/summary").json()
    assert "avg_congestion" in summ


def test_hotspots_bottlenecks(client):
    assert isinstance(client.get("/intelligence/hotspots?n=5").json(), list)
    assert isinstance(client.get("/intelligence/bottlenecks").json(), list)


def test_economics(client):
    r = client.get("/economics").json()
    assert "₹" in r["summary"]["cost_human"]


def test_recommendations(client):
    assert isinstance(client.get("/recommendations").json(), list)


def test_kg_why(client):
    r = client.get("/kg/why", params={"junction": "J1_1"}).json()
    assert r["junction_id"] == "J1_1"
    assert "causes" in r


def test_copilot(client):
    r = client.post("/copilot", json={"question": "Which junction is worst?"}).json()
    assert r["tool"] == "worst_junction"
    assert r["answer"]


def test_signals(client):
    r = client.get("/signals").json()
    assert "states" in r and "recommended_plan" in r


def test_emergency(client):
    net = client.get("/network").json()
    j = {x["id"]: x for x in net["junctions"]}
    a, b = j["J0_0"], j["J3_3"]
    r = client.post(
        "/emergency",
        json={
            "type": "ambulance",
            "lat": a["lat"],
            "lon": a["lon"],
            "dest_lat": b["lat"],
            "dest_lon": b["lon"],
        },
    ).json()
    assert r["route_segments"]
    assert r["eta_s"] <= r["baseline_eta_s"] + 1e-6


def test_planning_scenario(client):
    net = client.get("/network").json()
    seg = net["segments"][0]["id"]
    r = client.post(
        "/planning/scenario",
        json={
            "id": "t1",
            "name": "Widen",
            "edits": [
                {"op": "widen_lane", "target": seg, "params": {"delta": 1}},
            ],
        },
    ).json()
    assert "deltas" in r and "summary" in r


def test_forecast(client):
    r = client.get("/forecast", params={"horizon": 60}).json()
    assert isinstance(r, list) and r
    assert 0 <= r[0]["predicted_congestion"] <= 100


def test_citizen_report_roundtrip(client):
    payload = {
        "id": "R1",
        "ts": "2025-01-01T09:00:00+00:00",
        "type": "pothole",
        "lat": 12.97,
        "lon": 77.59,
        "note": "big pothole",
    }
    assert client.post("/reports", json=payload).json()["status"] == "received"
    reports = client.get("/reports").json()
    assert any(r["id"] == "R1" for r in reports)
