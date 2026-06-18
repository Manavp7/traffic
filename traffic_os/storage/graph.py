"""Knowledge-graph adapters.

- ``NetworkxGraph``: pure-Python, always available, robust (default dev fallback).
- ``KuzuGraph``: embedded graph DB with Cypher (dev parity with prod Neo4j).

Both implement the same primitives; causal reasoning is backend-agnostic.
"""

from __future__ import annotations

from typing import Any

import networkx as nx

from traffic_os.common.logging import get_logger
from traffic_os.schemas.kg import KGEdge, KGNode
from traffic_os.storage.ports import KnowledgeGraph

log = get_logger("storage.graph")


def _nid(node_type: str, node_id: str) -> str:
    return f"{node_type}:{node_id}"


class NetworkxGraph(KnowledgeGraph):
    """In-memory directed multigraph implementation."""

    def __init__(self) -> None:
        self.g = nx.MultiDiGraph()

    def reset(self) -> None:
        self.g.clear()

    def upsert_node(self, node: KGNode) -> None:
        self.g.add_node(
            _nid(node.type, node.id), type=node.type, id=node.id, props=dict(node.props)
        )

    def upsert_edge(self, edge: KGEdge) -> None:
        src = _nid(edge.src_type, edge.src_id)
        dst = _nid(edge.dst_type, edge.dst_id)
        if src not in self.g:
            self.g.add_node(src, type=edge.src_type, id=edge.src_id, props={})
        if dst not in self.g:
            self.g.add_node(dst, type=edge.dst_type, id=edge.dst_id, props={})
        # use edge type as key so re-upserts replace rather than duplicate
        self.g.add_edge(src, dst, key=edge.type, type=edge.type, props=dict(edge.props))

    def get_node(self, node_type: str, node_id: str) -> KGNode | None:
        key = _nid(node_type, node_id)
        if key not in self.g:
            return None
        d = self.g.nodes[key]
        return KGNode(type=d["type"], id=d["id"], props=d.get("props", {}))

    def neighbors(
        self,
        node_type: str,
        node_id: str,
        *,
        edge_type: str | None = None,
        direction: str = "out",
    ) -> list[tuple[KGEdge, KGNode]]:
        key = _nid(node_type, node_id)
        if key not in self.g:
            return []
        out: list[tuple[KGEdge, KGNode]] = []

        def collect(u: str, v: str, k: str, data: dict[str, Any]) -> None:
            if edge_type and k != edge_type:
                return
            sd = self.g.nodes[u]
            dd = self.g.nodes[v]
            edge = KGEdge(
                type=k,
                src_type=sd["type"],
                src_id=sd["id"],
                dst_type=dd["type"],
                dst_id=dd["id"],
                props=data.get("props", {}),
            )
            other = dd if u == key else sd
            out.append(
                (edge, KGNode(type=other["type"], id=other["id"], props=other.get("props", {})))
            )

        if direction in ("out", "both"):
            for _, v, k, data in self.g.out_edges(key, keys=True, data=True):
                collect(key, v, k, data)
        if direction in ("in", "both"):
            for u, _, k, data in self.g.in_edges(key, keys=True, data=True):
                collect(u, key, k, data)
        return out

    def nodes_of_type(self, node_type: str) -> list[KGNode]:
        return [
            KGNode(type=d["type"], id=d["id"], props=d.get("props", {}))
            for _, d in self.g.nodes(data=True)
            if d.get("type") == node_type
        ]

    def stats(self) -> dict[str, int]:
        return {"nodes": self.g.number_of_nodes(), "edges": self.g.number_of_edges()}


class KuzuGraph(KnowledgeGraph):
    """Embedded Kùzu graph DB using a generic (Node)-[Edge]->(Node) schema.

    We keep the schema generic (a single ``Node`` table + single ``Rel`` table with
    a ``type`` discriminator) so arbitrary domain types map cleanly and Cypher used
    here stays close to Neo4j.
    """

    def __init__(self, path: str) -> None:
        import kuzu  # local import: optional dependency

        self.db = kuzu.Database(path)
        self.conn = kuzu.Connection(self.db)
        self._ensure_schema()

    def _q(self, query: str, params: dict[str, Any] | None = None) -> Any:
        """Execute a single Cypher statement and return its QueryResult (typed Any)."""
        return self.conn.execute(query, params or {})

    def _ensure_schema(self) -> None:
        try:
            self.conn.execute(
                "CREATE NODE TABLE IF NOT EXISTS Node("
                "uid STRING, ntype STRING, nid STRING, props STRING, PRIMARY KEY(uid))"
            )
            self.conn.execute(
                "CREATE REL TABLE IF NOT EXISTS Rel(FROM Node TO Node, etype STRING, props STRING)"
            )
        except Exception as exc:  # pragma: no cover - depends on kuzu version
            log.warning("Kuzu schema init issue: %s", exc)

    def reset(self) -> None:
        self.conn.execute("MATCH (n:Node) DETACH DELETE n")

    def upsert_node(self, node: KGNode) -> None:
        import orjson

        uid = _nid(node.type, node.id)
        props = orjson.dumps(node.props).decode()
        self.conn.execute(
            "MERGE (n:Node {uid: $uid}) SET n.ntype=$t, n.nid=$i, n.props=$p",
            {"uid": uid, "t": node.type, "i": node.id, "p": props},
        )

    def _ensure_node(self, node_type: str, node_id: str) -> None:
        """Create an endpoint node if missing WITHOUT clobbering existing props."""
        uid = _nid(node_type, node_id)
        self.conn.execute(
            "MERGE (n:Node {uid: $uid}) " "ON CREATE SET n.ntype=$t, n.nid=$i, n.props='{}'",
            {"uid": uid, "t": node_type, "i": node_id},
        )

    def upsert_edge(self, edge: KGEdge) -> None:
        import orjson

        self._ensure_node(edge.src_type, edge.src_id)
        self._ensure_node(edge.dst_type, edge.dst_id)
        src = _nid(edge.src_type, edge.src_id)
        dst = _nid(edge.dst_type, edge.dst_id)
        props = orjson.dumps(edge.props).decode()
        self.conn.execute(
            "MATCH (a:Node {uid:$s}),(b:Node {uid:$d}) "
            "MERGE (a)-[r:Rel {etype:$e}]->(b) SET r.props=$p",
            {"s": src, "d": dst, "e": edge.type, "p": props},
        )

    def _row_to_node(self, ntype: str, nid: str, props: str) -> KGNode:
        import orjson

        return KGNode(type=ntype, id=nid, props=orjson.loads(props) if props else {})

    def get_node(self, node_type: str, node_id: str) -> KGNode | None:
        res = self._q(
            "MATCH (n:Node {uid:$u}) RETURN n.ntype, n.nid, n.props",
            {"u": _nid(node_type, node_id)},
        )
        while res.has_next():
            r = res.get_next()
            return self._row_to_node(r[0], r[1], r[2])
        return None

    def neighbors(
        self,
        node_type: str,
        node_id: str,
        *,
        edge_type: str | None = None,
        direction: str = "out",
    ) -> list[tuple[KGEdge, KGNode]]:
        uid = _nid(node_type, node_id)
        out: list[tuple[KGEdge, KGNode]] = []
        patterns = []
        if direction in ("out", "both"):
            patterns.append(("(a:Node {uid:$u})-[r:Rel]->(b:Node)", "out"))
        if direction in ("in", "both"):
            patterns.append(("(b:Node)-[r:Rel]->(a:Node {uid:$u})", "in"))
        for pat, _dir in patterns:
            q = f"MATCH {pat} RETURN r.etype, r.props, b.ntype, b.nid, b.props"
            res = self._q(q, {"u": uid})
            while res.has_next():
                etype, eprops, bt, bi, bp = res.get_next()
                if edge_type and etype != edge_type:
                    continue
                import orjson

                node = self._row_to_node(bt, bi, bp)
                edge = KGEdge(
                    type=etype,
                    src_type=node_type if _dir == "out" else bt,
                    src_id=node_id if _dir == "out" else bi,
                    dst_type=bt if _dir == "out" else node_type,
                    dst_id=bi if _dir == "out" else node_id,
                    props=orjson.loads(eprops) if eprops else {},
                )
                out.append((edge, node))
        return out

    def nodes_of_type(self, node_type: str) -> list[KGNode]:
        res = self._q("MATCH (n:Node {ntype:$t}) RETURN n.ntype, n.nid, n.props", {"t": node_type})
        out = []
        while res.has_next():
            r = res.get_next()
            out.append(self._row_to_node(r[0], r[1], r[2]))
        return out

    def stats(self) -> dict[str, int]:
        n = self._q("MATCH (n:Node) RETURN count(n)")
        e = self._q("MATCH ()-[r:Rel]->() RETURN count(r)")
        nodes = n.get_next()[0] if n.has_next() else 0
        edges = e.get_next()[0] if e.has_next() else 0
        return {"nodes": int(nodes), "edges": int(edges)}
