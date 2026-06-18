"""Phase 11: AI Copilot (deterministic router) tests."""

from __future__ import annotations

from datetime import datetime

from traffic_os.copilot import CopilotService
from traffic_os.intelligence import IntelligenceService
from traffic_os.knowledge_graph import KnowledgeGraphService
from traffic_os.planning import PlanningService
from traffic_os.recommendation import RecommendationEngine
from traffic_os.schemas import Incident, IncidentStatus, IncidentType
from traffic_os.simulation import SimulationEngine, build_grid_network, save_network
from traffic_os.storage import memory_storage


def _copilot(demand=80, ticks=45):
    net = build_grid_network(5)
    st = memory_storage()
    save_network(net, st.db)
    st.settings.sim_demand_scale = demand
    eng = SimulationEngine(net, st.settings)
    for _ in range(ticks):
        eng.persist(st, eng.step_once())
    # a couple of accidents this period
    for k in range(3):
        seg = list(net.segments.values())[k]
        mid = seg.geometry[len(seg.geometry) // 2]
        st.db.upsert("incident", Incident(
            id=f"ACC-{k}", ts=datetime.now(), type=IncidentType.ACCIDENT,
            lat=mid[0], lon=mid[1], segment_id=seg.id, severity=0.7,
            segments_blocked=[seg.id] if k == 0 else [], status=IncidentStatus.ACTIVE,
            description="accident",
        ))
    intel = IntelligenceService(st)
    kg = KnowledgeGraphService(st, intel)
    planning = PlanningService(st)
    rec = RecommendationEngine(st, intel, kg=kg)
    cp = CopilotService(st, intel, kg=kg, planning=planning, recommendation=rec)
    return cp, net


def test_why_is_traffic_bad():
    cp, _ = _copilot()
    r = cp.ask("Why is traffic bad today?")
    assert r["tool"] == "why_congested"
    assert r["answer"]
    assert r["mode"] == "deterministic"


def test_why_specific_junction():
    cp, _ = _copilot()
    r = cp.ask("Why is junction J2_2 congested?")
    assert r["tool"] == "why_congested"
    assert "J2_2" in str(r["data"].get("junction_id", "")) or r["answer"]


def test_worst_junction():
    cp, _ = _copilot()
    r = cp.ask("Which junction causes maximum congestion?")
    assert r["tool"] == "worst_junction"
    assert r["answer"]


def test_accidents_count():
    cp, _ = _copilot()
    r = cp.ask("How many accidents this month?")
    assert r["tool"] == "accidents_count"
    assert r["data"]["count"] >= 3


def test_economic_cost():
    cp, _ = _copilot()
    r = cp.ask("What is the congestion cost today?")
    assert r["tool"] == "economic_cost"
    assert "₹" in r["answer"]


def test_recommend_actions():
    cp, _ = _copilot()
    r = cp.ask("What should we do about Junction J2_2?")
    assert r["tool"] == "recommend_actions"
    assert r["answer"]


def test_forecast_routes_even_without_model():
    cp, _ = _copilot()
    r = cp.ask("What is the expected traffic next hour?")
    assert r["tool"] == "forecast"


def test_default_summary():
    cp, _ = _copilot()
    r = cp.ask("Give me a status update")
    assert r["tool"] in ("network_summary", "worst_junction")
    assert r["answer"]
