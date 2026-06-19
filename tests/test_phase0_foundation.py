"""Phase 0: schemas, storage DB, and knowledge-graph adapter smoke tests."""

from __future__ import annotations

from datetime import timedelta

import pytest

from traffic_os.common.geo import angular_diff_deg, bearing_deg, haversine_m
from traffic_os.common.timeutil import utcnow
from traffic_os.schemas import (
    Incident,
    IncidentStatus,
    IncidentType,
    KGEdge,
    KGNode,
    RoadSegment,
    SegmentMetric,
    VehicleClass,
)
from traffic_os.storage import memory_storage
from traffic_os.storage.graph import NetworkxGraph


def test_pcu_values():
    assert VehicleClass.CAR.pcu == 1.0
    assert VehicleClass.BUS.pcu > VehicleClass.CAR.pcu
    assert VehicleClass.BIKE.pcu < VehicleClass.CAR.pcu


def test_geo_helpers():
    # ~111 km per degree latitude
    d = haversine_m(12.97, 77.59, 12.98, 77.59)
    assert 1000 < d < 1200
    assert bearing_deg(0, 0, 1, 0) == pytest.approx(0, abs=1)
    assert angular_diff_deg(350, 10) == pytest.approx(20, abs=1)


def test_road_segment_capacity():
    seg = RoadSegment(
        id="s1",
        name="MG Rd",
        from_junction="a",
        to_junction="b",
        length_m=500,
        lanes=3,
    )
    assert seg.capacity_pcu_per_h == 1800 * 3


def test_db_upsert_get_list():
    st = memory_storage()
    inc = Incident(
        id="i1",
        ts=utcnow(),
        type=IncidentType.ACCIDENT,
        lat=12.9,
        lon=77.6,
        status=IncidentStatus.ACTIVE,
    )
    st.db.upsert("incident", inc)
    got = st.db.get("incident", "i1", Incident)
    assert got is not None and got.type == IncidentType.ACCIDENT
    active = st.db.find("incident", Incident, where={"status": "active"})
    assert len(active) == 1
    assert st.db.count("incident", {"status": "active"}) == 1
    assert st.db.count("incident", {"status": "resolved"}) == 0


def test_db_metrics_range_and_latest():
    st = memory_storage()
    t0 = utcnow()
    metrics = [
        SegmentMetric(segment_id="s1", ts=t0 + timedelta(minutes=i), congestion_score=i * 10)
        for i in range(5)
    ]
    metrics += [
        SegmentMetric(segment_id="s2", ts=t0 + timedelta(minutes=i), congestion_score=i)
        for i in range(3)
    ]
    # ids must be unique for the generic store; metrics have no id -> autoid
    for m in metrics:
        st.db.upsert("segment_metric", m)
    # NOTE: autoid makes ids unique; range query by segment
    rng = st.db.metrics_range(SegmentMetric, segment_id="s1")
    assert len(rng) == 5
    assert [m.congestion_score for m in rng] == [0, 10, 20, 30, 40]
    latest = {m.segment_id: m for m in st.db.latest_per_segment(SegmentMetric)}
    assert latest["s1"].congestion_score == 40
    assert latest["s2"].congestion_score == 2


def test_networkx_graph_primitives():
    g = NetworkxGraph()
    g.upsert_node(KGNode(type="Junction", id="J14", props={"name": "Silk Board"}))
    g.upsert_node(KGNode(type="Road", id="R9", props={"name": "Hosur Rd"}))
    g.upsert_edge(
        KGEdge(type="AFFECTS", src_type="Road", src_id="R9", dst_type="Junction", dst_id="J14")
    )
    assert g.stats() == {"nodes": 2, "edges": 1}
    node = g.get_node("Junction", "J14")
    assert node is not None and node.props["name"] == "Silk Board"
    out = g.neighbors("Road", "R9", direction="out")
    assert len(out) == 1 and out[0][1].id == "J14"
    inc = g.neighbors("Junction", "J14", direction="in")
    assert len(inc) == 1 and inc[0][1].id == "R9"
    # idempotent edge upsert
    g.upsert_edge(
        KGEdge(type="AFFECTS", src_type="Road", src_id="R9", dst_type="Junction", dst_id="J14")
    )
    assert g.stats()["edges"] == 1


def test_kuzu_graph_primitives(tmp_path):
    from traffic_os.storage.graph import KuzuGraph

    g = KuzuGraph(str(tmp_path / "kuzu_test"))
    g.reset()
    g.upsert_node(KGNode(type="Junction", id="J1", props={"name": "Test"}))
    g.upsert_node(KGNode(type="Road", id="R1"))
    g.upsert_edge(
        KGEdge(type="AFFECTS", src_type="Road", src_id="R1", dst_type="Junction", dst_id="J1")
    )
    s = g.stats()
    assert s["nodes"] == 2 and s["edges"] == 1
    node = g.get_node("Junction", "J1")
    assert node is not None and node.props.get("name") == "Test"
    out = g.neighbors("Road", "R1", direction="out")
    assert any(n.id == "J1" for _, n in out)
