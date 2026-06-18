"""KnowledgeGraphService — ingest + causal reasoning over storage."""

from __future__ import annotations

from datetime import datetime

from traffic_os.common.logging import get_logger
from traffic_os.knowledge_graph.ingest import KGIngestor
from traffic_os.knowledge_graph.reasoning import why_congested
from traffic_os.knowledge_graph.schema import EdgeType, NodeType
from traffic_os.schemas import CausalFactor

log = get_logger("kg.service")


class KnowledgeGraphService:
    def __init__(self, storage, intelligence) -> None:
        self.storage = storage
        self.intelligence = intelligence
        self.ingestor = KGIngestor(storage.graph)

    def sync(self, *, faulted_signals: set[str] | None = None) -> dict[str, int]:
        return self.ingestor.sync_from_storage(
            self.storage, self.intelligence, faulted_signals=faulted_signals
        )

    def why_congested(self, junction_id: str, ref_ts: datetime | None = None) -> list[CausalFactor]:
        return why_congested(self.storage.graph, junction_id, ref_ts=ref_ts)

    def explain_junction(self, junction_id: str, ref_ts: datetime | None = None) -> dict:
        jn = self.storage.graph.get_node(NodeType.JUNCTION, junction_id)
        factors = self.why_congested(junction_id, ref_ts)
        return {
            "junction_id": junction_id,
            "name": jn.props.get("name") if jn else junction_id,
            "congestion": jn.props.get("congestion") if jn else None,
            "causes": [f.model_dump() for f in factors],
        }

    def neighbors(self, node_type: str, node_id: str, edge_type: str | None = None, direction: str = "both"):
        res = self.storage.graph.neighbors(node_type, node_id, edge_type=edge_type, direction=direction)
        return [{"edge": e.type, "node_type": n.type, "node_id": n.id, "props": n.props} for e, n in res]

    def stats(self) -> dict[str, int]:
        return self.storage.graph.stats()


__all__ = ["KnowledgeGraphService", "EdgeType", "NodeType"]
