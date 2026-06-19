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


def _prod_blob(settings: Settings) -> BlobStore:
    try:
        from traffic_os.storage.blob import MinioBlobStore

        return MinioBlobStore(
            settings.minio_endpoint,
            settings.minio_access_key,
            settings.minio_secret_key,
            settings.minio_bucket,
        )
    except Exception as exc:  # pragma: no cover
        log.warning("MinIO unavailable (%s); using filesystem blobs", exc)
        return FsBlobStore(settings.blob_dir)


def _prod_cache(settings: Settings) -> Cache:
    try:
        from traffic_os.storage.cache import RedisCache

        return RedisCache(settings.redis_url)
    except Exception as exc:  # pragma: no cover
        log.warning("Redis unavailable (%s); using in-memory cache", exc)
        return MemoryCache()


def _prod_bus(settings: Settings) -> EventBus:
    try:
        from traffic_os.storage.eventbus import KafkaEventBus

        return KafkaEventBus(settings.kafka_bootstrap)
    except Exception as exc:  # pragma: no cover
        log.warning("Kafka unavailable (%s); using in-memory bus", exc)
        return MemoryEventBus()


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
        blob: BlobStore = _prod_blob(settings)
        cache: Cache = _prod_cache(settings)
        bus: EventBus = _prod_bus(settings)
    else:
        db = SqlDatabase.sqlite(str(settings.sqlite_path))
        blob = FsBlobStore(settings.blob_dir)
        cache = MemoryCache()
        bus = MemoryEventBus()

    storage = Storage(
        db=db,
        blob=blob,
        cache=cache,
        bus=bus,
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
