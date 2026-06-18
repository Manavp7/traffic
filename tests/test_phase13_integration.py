"""Phase 13: cross-cutting integration + edge AI tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from traffic_os.decision import DecisionService
from traffic_os.intelligence import IntelligenceService
from traffic_os.knowledge_graph import KnowledgeGraphService
from traffic_os.planning import PlanningService
from traffic_os.recommendation import RecommendationEngine
from traffic_os.simulation import SimulationEngine, build_grid_network, save_network
from traffic_os.storage import memory_storage


def _running_city(demand=90, ticks=45):
    net = build_grid_network(5)
    st = memory_storage()
    save_network(net, st.db)
    st.settings.sim_demand_scale = demand
    eng = SimulationEngine(net, st.settings)
    for _ in range(ticks):
        eng.persist_live(st, eng.step_once())
    return net, st


def test_full_pipeline_consistency():
    net, st = _running_city()
    intel = IntelligenceService(st)
    kg = KnowledgeGraphService(st, intel)
    decision = DecisionService(st)
    planning = PlanningService(st)
    recs_engine = RecommendationEngine(st, intel, kg=kg)
    from traffic_os.copilot import CopilotService

    copilot = CopilotService(st, intel, kg=kg, planning=planning, recommendation=recs_engine)

    # intelligence
    summary = intel.summary()
    assert summary["segments"] == len(net.segments)
    assert 0 <= summary["avg_congestion"] <= 100

    # knowledge graph syncs and reasons
    stats = kg.sync()
    assert stats["nodes"] > 0 and stats["edges"] > 0
    worst = intel.hotspots(top_n=1)[0].junction_id
    assert isinstance(kg.why_congested(worst), list)

    # decision: adaptive plan covers all signals
    assert len(decision.signal_plan()) == len(net.signals)

    # economics produce a positive cost
    assert planning.economic_summary()["cost_inr"] >= 0

    # recommendation engine yields actionable, ranked items
    recs = recs_engine.generate()
    assert recs
    assert [r.impact_score for r in recs] == sorted((r.impact_score for r in recs), reverse=True)

    # copilot routes the flagship questions
    assert copilot.ask("Why is traffic bad today?")["tool"] == "why_congested"
    assert copilot.ask("Which junction is worst?")["tool"] == "worst_junction"
    assert "₹" in copilot.ask("What is the congestion cost today?")["answer"]


@pytest.mark.skipif(
    not Path("data/samples/highway.mp4").exists(),
    reason="sample video not present (run scripts/fetch_samples.sh)",
)
def test_edge_node_uplink_reduction():
    pytest.importorskip("ultralytics")
    pytest.importorskip("cv2")
    from traffic_os.edge import EdgeNode
    from traffic_os.schemas import CameraFrameMetric

    received: list[CameraFrameMetric] = []
    node = EdgeNode(source_id="edge-test")
    stats = node.run("data/samples/highway.mp4", received.append, max_frames=8, stride=4)
    assert stats.frames > 0
    assert received and all(isinstance(m, CameraFrameMetric) for m in received)
    # compact metrics are vastly smaller than raw frames
    assert stats.uplink_bytes < stats.raw_video_bytes
    assert stats.reduction_pct > 90.0
