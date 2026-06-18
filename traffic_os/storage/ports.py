"""Storage port interfaces (ports-and-adapters).

Dev adapters require no external services; prod adapters target Postgres/PostGIS,
TimescaleDB, Neo4j, Redis, MinIO and Redpanda while satisfying the same contracts.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from traffic_os.schemas.kg import KGEdge, KGNode


class Database(ABC):
    """Document + time-series store keyed by ``collection`` and ``id``."""

    @abstractmethod
    def upsert(self, collection: str, obj: BaseModel) -> None: ...

    @abstractmethod
    def upsert_many(self, collection: str, objs: list[BaseModel]) -> None: ...

    @abstractmethod
    def get(self, collection: str, id_: str, model: type[BaseModel]) -> Any | None: ...

    @abstractmethod
    def find(
        self,
        collection: str,
        model: type[BaseModel],
        *,
        where: dict[str, Any] | None = None,
        order_by_ts: bool = False,
        desc: bool = False,
        limit: int | None = None,
    ) -> list[Any]: ...

    @abstractmethod
    def metrics_range(
        self,
        model: type[BaseModel],
        *,
        segment_id: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int | None = None,
    ) -> list[Any]: ...

    @abstractmethod
    def latest_per_segment(self, model: type[BaseModel]) -> list[Any]: ...

    @abstractmethod
    def count(self, collection: str, where: dict[str, Any] | None = None) -> int: ...

    @abstractmethod
    def clear(self, collection: str | None = None) -> None: ...


class BlobStore(ABC):
    @abstractmethod
    def put(self, key: str, data: bytes) -> str: ...

    @abstractmethod
    def get(self, key: str) -> bytes | None: ...

    @abstractmethod
    def url(self, key: str) -> str: ...


class Cache(ABC):
    @abstractmethod
    def get(self, key: str) -> Any | None: ...

    @abstractmethod
    def set(self, key: str, value: Any, ttl_s: int | None = None) -> None: ...


class EventBus(ABC):
    @abstractmethod
    async def publish(self, topic: str, message: dict[str, Any]) -> None: ...

    @abstractmethod
    def subscribe(self, topic: str) -> Subscription: ...

    def latest(self, topic: str) -> dict[str, Any] | None:
        """Most recent message on a topic, if the backend retains one."""
        return None


class Subscription(ABC):
    @abstractmethod
    async def __aiter__(self) -> Any: ...


class KnowledgeGraph(ABC):
    """Backend-agnostic property graph (dev: Kùzu/networkx, prod: Neo4j).

    Adapters expose graph *primitives*; higher-level causal reasoning lives in
    ``traffic_os.knowledge_graph`` so it works identically on any backend.
    """

    @abstractmethod
    def reset(self) -> None: ...

    @abstractmethod
    def upsert_node(self, node: KGNode) -> None: ...

    @abstractmethod
    def upsert_edge(self, edge: KGEdge) -> None: ...

    @abstractmethod
    def get_node(self, node_type: str, node_id: str) -> KGNode | None: ...

    @abstractmethod
    def neighbors(
        self,
        node_type: str,
        node_id: str,
        *,
        edge_type: str | None = None,
        direction: str = "out",  # "out" | "in" | "both"
    ) -> list[tuple[KGEdge, KGNode]]: ...

    @abstractmethod
    def nodes_of_type(self, node_type: str) -> list[KGNode]: ...

    @abstractmethod
    def stats(self) -> dict[str, int]: ...
