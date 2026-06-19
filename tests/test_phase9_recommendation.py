"""Phase 9: AI recommendation engine tests."""

from __future__ import annotations

from datetime import datetime

from traffic_os.intelligence import IntelligenceService
from traffic_os.knowledge_graph import KnowledgeGraphService
from traffic_os.recommendation import RecommendationEngine
from traffic_os.schemas import ActionType, Incident, IncidentStatus, IncidentType, Recommendation
from traffic_os.simulation import SimulationEngine, build_grid_network, save_network
from traffic_os.storage import memory_storage


def _busy_storage(demand=90, ticks=50):
    net = build_grid_network(5)
    st = memory_storage()
    save_network(net, st.db)
    st.settings.sim_demand_scale = demand
    eng = SimulationEngine(net, st.settings)
    for _ in range(ticks):
        eng.persist(st, eng.step_once())
    return net, st


def _inject_blocking_incident(net, st):
    junction = "J2_2"
    road = net.in_segments[junction][0]
    seg = net.segments[road]
    mid = seg.geometry[len(seg.geometry) // 2]
    st.db.upsert(
        "incident",
        Incident(
            id="INC-block",
            ts=datetime.now(),
            type=IncidentType.ACCIDENT,
            lat=mid[0],
            lon=mid[1],
            segment_id=road,
            severity=0.9,
            segments_blocked=[road],
            status=IncidentStatus.ACTIVE,
            description="Accident blocking road",
        ),
    )
    return road


def test_recommendations_generated_and_ranked():
    net, st = _busy_storage()
    _inject_blocking_incident(net, st)
    intel = IntelligenceService(st)
    kg = KnowledgeGraphService(st, intel)
    eng = RecommendationEngine(st, intel, kg=kg)
    recs = eng.generate()
    assert recs, "expected at least one recommendation"
    # ranked by impact descending
    scores = [r.impact_score for r in recs]
    assert scores == sorted(scores, reverse=True)
    # all are actionable with effect + target
    for r in recs:
        assert isinstance(r.action_type, ActionType)
        assert r.target and r.expected_effect
        assert 0 <= r.confidence <= 1
    # the blocking incident produced a divert/alert recommendation referencing it
    inc_recs = [r for r in recs if r.params.get("incident") == "INC-block"]
    assert inc_recs
    assert inc_recs[0].rationale
    # persisted
    assert st.db.count("recommendation") == len(recs)


def test_recommendations_persist_roundtrip():
    net, st = _busy_storage(demand=70, ticks=40)
    _inject_blocking_incident(net, st)
    intel = IntelligenceService(st)
    eng = RecommendationEngine(st, intel, kg=KnowledgeGraphService(st, intel))
    recs = eng.generate()
    stored = st.db.find("recommendation", Recommendation)
    assert len(stored) == len(recs)
    assert all(isinstance(r, Recommendation) for r in stored)


def test_risk_recommendations_with_prediction():
    import pytest

    pytest.importorskip("xgboost")
    from traffic_os.prediction import PredictionService
    from traffic_os.simulation import generate_history

    net, st = _busy_storage(demand=80, ticks=40)
    generate_history(net, st.db, days=5, step_min=30, seed=3)
    intel = IntelligenceService(st)
    pred = PredictionService(st)
    pred.train(horizons=(60,))
    eng = RecommendationEngine(st, intel, kg=KnowledgeGraphService(st, intel), prediction=pred)
    recs = eng.generate()
    # engine integrates risk without error; risk alerts (if any) are well-formed
    assert isinstance(recs, list)
    for r in recs:
        if r.action_type == ActionType.ALERT and "risk_pct" in r.params:
            assert 0 <= r.params["risk_pct"] <= 100
