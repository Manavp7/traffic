"""Neo4j knowledge-graph adapter (prod) — mirrors the embedded Kùzu adapter.

Generic schema: a single ``:Node`` label (uid/ntype/nid/props) connected by ``:REL``
relationships carrying an ``etype`` discriminator, so the backend-agnostic reasoning
in :mod:`traffic_os.knowledge_graph` works unchanged against Neo4j.
"""

from __future__ import annotations

from typing import Any

import orjson

from traffic_os.common.logging import get_logger
from traffic_os.schemas.kg import KGEdge, KGNode
from traffic_os.storage.ports import KnowledgeGraph

log = get_logger("storage.neo4j")


def _nid(node_type: str, node_id: str) -> str:
    return f"{node_type}:{node_id}"


class Neo4jGraph(KnowledgeGraph):
    def __init__(self, uri: str, user: str, password: str) -> None:
        from neo4j import GraphDatabase  # optional dependency

        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        with self.driver.session() as s:
            s.run("CREATE CONSTRAINT node_uid IF NOT EXISTS FOR (n:Node) REQUIRE n.uid IS UNIQUE")

    def reset(self) -> None:
        with self.driver.session() as s:
            s.run("MATCH (n:Node) DETACH DELETE n")

    def upsert_node(self, node: KGNode) -> None:
        with self.driver.session() as s:
            s.run(
                "MERGE (n:Node {uid:$uid}) SET n.ntype=$t, n.nid=$i, n.props=$p",
                uid=_nid(node.type, node.id),
                t=node.type,
                i=node.id,
                p=orjson.dumps(node.props).decode(),
            )

    def _ensure_node(self, s, node_type: str, node_id: str) -> None:
        s.run(
            "MERGE (n:Node {uid:$uid}) ON CREATE SET n.ntype=$t, n.nid=$i, n.props='{}'",
            uid=_nid(node_type, node_id),
            t=node_type,
            i=node_id,
        )

    def upsert_edge(self, edge: KGEdge) -> None:
        with self.driver.session() as s:
            self._ensure_node(s, edge.src_type, edge.src_id)
            self._ensure_node(s, edge.dst_type, edge.dst_id)
            s.run(
                "MATCH (a:Node {uid:$su}),(b:Node {uid:$du}) "
                "MERGE (a)-[r:REL {etype:$e}]->(b) SET r.props=$p",
                su=_nid(edge.src_type, edge.src_id),
                du=_nid(edge.dst_type, edge.dst_id),
                e=edge.type,
                p=orjson.dumps(edge.props).decode(),
            )

    def _node(self, ntype: str, nid: str, props: str | None) -> KGNode:
        return KGNode(type=ntype, id=nid, props=orjson.loads(props) if props else {})

    def get_node(self, node_type: str, node_id: str) -> KGNode | None:
        with self.driver.session() as s:
            rec = s.run(
                "MATCH (n:Node {uid:$u}) RETURN n.ntype AS t, n.nid AS i, n.props AS p",
                u=_nid(node_type, node_id),
            ).single()
        return self._node(rec["t"], rec["i"], rec["p"]) if rec else None

    def neighbors(
        self, node_type: str, node_id: str, *, edge_type: str | None = None, direction: str = "out"
    ) -> list[tuple[KGEdge, KGNode]]:
        uid = _nid(node_type, node_id)
        out: list[tuple[KGEdge, KGNode]] = []
        queries = []
        if direction in ("out", "both"):
            queries.append(
                (
                    "MATCH (a:Node {uid:$u})-[r:REL]->(b:Node) "
                    "RETURN r.etype AS e, r.props AS ep, b.ntype AS t, b.nid AS i, b.props AS p",
                    "out",
                )
            )
        if direction in ("in", "both"):
            queries.append(
                (
                    "MATCH (b:Node)-[r:REL]->(a:Node {uid:$u}) "
                    "RETURN r.etype AS e, r.props AS ep, b.ntype AS t, b.nid AS i, b.props AS p",
                    "in",
                )
            )
        with self.driver.session() as s:
            for q, dir_ in queries:
                for rec in s.run(q, u=uid):
                    if edge_type and rec["e"] != edge_type:
                        continue
                    other = self._node(rec["t"], rec["i"], rec["p"])
                    eprops: dict[str, Any] = orjson.loads(rec["ep"]) if rec["ep"] else {}
                    edge = KGEdge(
                        type=rec["e"],
                        src_type=node_type if dir_ == "out" else other.type,
                        src_id=node_id if dir_ == "out" else other.id,
                        dst_type=other.type if dir_ == "out" else node_type,
                        dst_id=other.id if dir_ == "out" else node_id,
                        props=eprops,
                    )
                    out.append((edge, other))
        return out

    def nodes_of_type(self, node_type: str) -> list[KGNode]:
        with self.driver.session() as s:
            recs = s.run(
                "MATCH (n:Node {ntype:$t}) RETURN n.ntype AS t, n.nid AS i, n.props AS p",
                t=node_type,
            )
            return [self._node(r["t"], r["i"], r["p"]) for r in recs]

    def stats(self) -> dict[str, int]:
        with self.driver.session() as s:
            n = s.run("MATCH (n:Node) RETURN count(n) AS c").single()["c"]
            e = s.run("MATCH ()-[r:REL]->() RETURN count(r) AS c").single()["c"]
        return {"nodes": int(n), "edges": int(e)}
