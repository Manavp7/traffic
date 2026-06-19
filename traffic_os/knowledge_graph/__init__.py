"""Knowledge Graph layer — connected city model + causal reasoning."""

from traffic_os.knowledge_graph.ingest import KGIngestor
from traffic_os.knowledge_graph.reasoning import why_congested
from traffic_os.knowledge_graph.schema import EdgeType, NodeType
from traffic_os.knowledge_graph.service import KnowledgeGraphService

__all__ = [
    "KnowledgeGraphService",
    "KGIngestor",
    "why_congested",
    "EdgeType",
    "NodeType",
]
