"""Storage assembly — selects dev or prod adapters from ``Settings``."""

from __future__ import annotations

from dataclasses import dataclass

from traffic_os.common.config import Settings, get_settings
from traffic_os.common.logging import get_logger
from traffic_os.storage.blob import FsBlobStore
from traffic_os.storage.cache import MemoryCache
from traffic_os.storage.database import SqlDatabase
from traffic_os.storage.eventbus import MemoryEventBus
from traffic_os.storage.graph import KuzuGraph, NetworkxGraph
from traffic_os.storage.ports import (
    BlobStore,
    Cache,
    Database,
    EventBus,
    KnowledgeGraph,
)

log = get_logger("storage")


@dataclass
class Storage:
    db: Database
    blob: BlobStore
    cache: Cache
    bus: EventBus
    graph: KnowledgeGraph
    settings: Settings


def _build_graph(settings: Settings) -> KnowledgeGraph:
    if settings.mode == "prod":
        try:
            from traffic_os.storage.graph_neo4j import Neo4jGraph

            return Neo4jGraph(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)
        except Exception as exc:  # pragma: no cover
            log.warning("Neo4j unavailable (%s); using in-memory graph", exc)
            return NetworkxGraph()
    # dev: prefer embedded Kùzu, fall back to networkx
    try:
        return KuzuGraph(str(settings.kuzu_path))
    except Exception as exc:
        log.info("Kùzu unavailable (%s); using networkx graph", exc)
        return NetworkxGraph()


_singleton: Storage | None = None


def get_storage(settings: Settings | None = None, *, fresh: bool = False) -> Storage:
    """Return a process-wide ``Storage`` (or a fresh one when ``fresh=True``)."""
    global _singleton
    if _singleton is not None and not fresh:
        return _singleton

    settings = settings or get_settings()
    settings.ensure_dirs()

    if settings.mode == "prod":
        db: Database = SqlDatabase.postgres(settings.postgres_dsn)
    else:
        db = SqlDatabase.sqlite(str(settings.sqlite_path))

    storage = Storage(
        db=db,
        blob=FsBlobStore(settings.blob_dir),
        cache=MemoryCache(),
        bus=MemoryEventBus(),
        graph=_build_graph(settings),
        settings=settings,
    )
    if not fresh:
        _singleton = storage
    return storage


def memory_storage() -> Storage:
    """A fully in-memory storage for tests (SQLite ``:memory:`` + networkx)."""
    settings = Settings(mode="dev")
    return Storage(
        db=SqlDatabase.sqlite(":memory:"),
        blob=FsBlobStore(settings.blob_dir),
        cache=MemoryCache(),
        bus=MemoryEventBus(),
        graph=NetworkxGraph(),
        settings=settings,
    )


__all__ = ["Storage", "get_storage", "memory_storage"]
