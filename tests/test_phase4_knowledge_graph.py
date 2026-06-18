"""Phase 4: knowledge graph ingestion + causal reasoning."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from traffic_os.intelligence import IntelligenceService
from traffic_os.knowledge_graph import KnowledgeGraphService
from traffic_os.schemas import (
    CityEvent,
    EventType,
    Incident,
    IncidentStatus,
    IncidentType,
    Weather,
    WeatherKind,
)
from traffic_os.simulation import build_grid_network, save_network
from traffic_os.storage import memory_storage
from traffic_os.storage.database import SqlDatabase


def _kuzu_storage(tmp_path):
    from traffic_os.common.config import Settings
    from traffic_os.storage import Storage
    from traffic_os.storage.blob import FsBlobStore
    from traffic_os.storage.cache import MemoryCache
    from traffic_os.storage.eventbus import MemoryEventBus
    from traffic_os.storage.graph import KuzuGraph

    return Storage(
        db=SqlDatabase.sqlite(":memory:"),
        blob=FsBlobStore(tmp_path / "blobs"),
        cache=MemoryCache(),
        bus=MemoryEventBus(),
        graph=KuzuGraph(str(tmp_path / "kuzu")),
        settings=Settings(mode="dev"),
    )


def _seed_scenario(storage):
    """Junction J2_2 congested due to: blocked road + signal fault + rain + nearby event."""
    net = build_grid_network(5)
    save_network(net, storage.db)
    junction = "J2_2"
    incoming = net.in_segments[junction]
    blocked_road = incoming[0]
    ref = datetime(2025, 1, 1, 18, 0, 0)

    storage.db.upsert(
        "incident",
        Incident(
            id="INC-1", ts=ref, type=IncidentType.ACCIDENT,
            lat=net.junctions[junction].lat, lon=net.junctions[junction].lon,
            segment_id=blocked_road, severity=0.9, segments_blocked=[blocked_road],
            status=IncidentStatus.ACTIVE, description="Accident",
        ),
    )
    storage.db.upsert(
        "weather",
        Weather(ts=ref, kind=WeatherKind.HEAVY_RAIN, rain_mm=30, visibility_m=2000, capacity_factor=0.65),
    )
    storage.db.upsert(
        "city_event",
        CityEvent(
            id="EV-1", type=EventType.CONCERT, name="Live Concert",
            venue_lat=net.junctions[junction].lat, venue_lon=net.junctions[junction].lon,
            start=ref - timedelta(minutes=30), end=ref + timedelta(minutes=30),
            expected_attendance=40000, nearest_junction=junction,
        ),
    )
    sig = net.signal_for_junction(junction)
    return net, junction, sig.id, ref


def _assert_causes(kg, junction, ref):
    explanation = kg.explain_junction(junction, ref_ts=ref)
    kinds = {c["kind"] for c in explanation["causes"]}
    assert "road_closed" in kinds, kinds
    assert "signal_fault" in kinds, kinds
    assert "weather" in kinds, kinds
    assert "event" in kinds, kinds
    # ranked by weight descending
    weights = [c["weight"] for c in explanation["causes"]]
    assert weights == sorted(weights, reverse=True)


def test_why_congested_networkx():
    st = memory_storage()
    net, junction, sig_id, ref = _seed_scenario(st)
    kg = KnowledgeGraphService(st, IntelligenceService(st))
    stats = kg.sync(faulted_signals={sig_id})
    assert stats["nodes"] > 0 and stats["edges"] > 0
    _assert_causes(kg, junction, ref)


def test_why_congested_kuzu(tmp_path):
    st = _kuzu_storage(tmp_path)
    net, junction, sig_id, ref = _seed_scenario(st)
    kg = KnowledgeGraphService(st, IntelligenceService(st))
    kg.sync(faulted_signals={sig_id})
    _assert_causes(kg, junction, ref)


def test_no_causes_when_healthy():
    st = memory_storage()
    net = build_grid_network(4)
    save_network(net, st.db)
    kg = KnowledgeGraphService(st, IntelligenceService(st))
    kg.sync()
    # a quiet junction with no incidents/weather/events -> no strong causes
    explanation = kg.explain_junction("J1_1")
    assert explanation["causes"] == []


def test_kg_neighbors_query():
    st = memory_storage()
    net = build_grid_network(4)
    save_network(net, st.db)
    kg = KnowledgeGraphService(st, IntelligenceService(st))
    kg.sync()
    # each interior junction should have incoming roads
    res = kg.neighbors("Junction", "J1_1", edge_type="TO", direction="in")
    assert res and all(r["node_type"] == "Road" for r in res)


@pytest.mark.parametrize("junction", ["J2_2", "J1_3"])
def test_explain_returns_structure(junction):
    st = memory_storage()
    net = build_grid_network(5)
    save_network(net, st.db)
    kg = KnowledgeGraphService(st, IntelligenceService(st))
    kg.sync()
    out = kg.explain_junction(junction)
    assert out["junction_id"] == junction
    assert "causes" in out and isinstance(out["causes"], list)
