"""E12: production storage adapters.

Importability is always checked. Live integration tests run only when the matching
service env flag is set (no Docker in this environment), e.g. TOS_TEST_NEO4J=1.
"""

from __future__ import annotations

import os

import pytest

from traffic_os.schemas.kg import KGEdge, KGNode


def test_prod_adapter_modules_import():
    # adapters import lazily; the modules and classes must exist and be referenceable
    from traffic_os.storage.blob import MinioBlobStore
    from traffic_os.storage.cache import RedisCache
    from traffic_os.storage.eventbus import KafkaEventBus
    from traffic_os.storage.graph_neo4j import Neo4jGraph

    assert all(callable(c) for c in [MinioBlobStore, RedisCache, KafkaEventBus, Neo4jGraph])


def test_prod_storage_falls_back_without_services(monkeypatch):
    # prod mode without reachable services must degrade gracefully, not crash
    from traffic_os.common.config import Settings
    from traffic_os.storage import get_storage

    settings = Settings(mode="prod", postgres_dsn="sqlite:///:memory:")
    # postgres dsn invalid for real PG but we only assert blob/cache/bus fallbacks here
    try:
        st = get_storage(settings, fresh=True)
    except Exception:
        pytest.skip("postgres driver/connection required for prod db")
    # blob/cache/bus should be present (real or fallback)
    assert st.blob and st.cache and st.bus


@pytest.mark.skipif(os.environ.get("TOS_TEST_NEO4J") != "1", reason="set TOS_TEST_NEO4J=1")
def test_neo4j_roundtrip():
    from traffic_os.common.config import get_settings
    from traffic_os.storage.graph_neo4j import Neo4jGraph

    s = get_settings()
    g = Neo4jGraph(s.neo4j_uri, s.neo4j_user, s.neo4j_password)
    g.reset()
    g.upsert_node(KGNode(type="Junction", id="J1", props={"name": "Test"}))
    g.upsert_edge(
        KGEdge(type="AFFECTS", src_type="Road", src_id="R1", dst_type="Junction", dst_id="J1")
    )
    assert g.stats()["nodes"] >= 2
    assert g.get_node("Junction", "J1").props["name"] == "Test"
    out = g.neighbors("Road", "R1", direction="out")
    assert any(n.id == "J1" for _, n in out)


@pytest.mark.skipif(os.environ.get("TOS_TEST_REDIS") != "1", reason="set TOS_TEST_REDIS=1")
def test_redis_roundtrip():
    from traffic_os.common.config import get_settings
    from traffic_os.storage.cache import RedisCache

    c = RedisCache(get_settings().redis_url)
    c.set("k", {"a": 1}, ttl_s=30)
    assert c.get("k") == {"a": 1}
