"""Sync domain state (network, metrics, incidents, weather, events) into the graph.

Idempotent: re-running updates node/edge properties in place. This is what lets the
Copilot and reasoning layer answer *causal* questions over a live, connected model.
"""

from __future__ import annotations

from traffic_os.common.logging import get_logger
from traffic_os.knowledge_graph.schema import EdgeType, NodeType
from traffic_os.schemas import (
    CityEvent,
    Incident,
    IncidentStatus,
    KGEdge,
    KGNode,
    SegmentMetric,
    Weather,
)
from traffic_os.simulation.network import RoadNetwork, load_network

log = get_logger("kg.ingest")


class KGIngestor:
    def __init__(self, graph) -> None:
        self.graph = graph

    def sync(
        self,
        net: RoadNetwork,
        metrics: dict[str, SegmentMetric],
        incidents: list[Incident],
        weather: Weather | None,
        events: list[CityEvent],
        *,
        faulted_signals: set[str] | None = None,
        reset: bool = True,
    ) -> dict[str, int]:
        faulted_signals = faulted_signals or set()
        if reset:
            self.graph.reset()

        # junctions
        for jid, jn in net.junctions.items():
            incoming = [s for s in net.in_segments.get(jid, []) if s in metrics]
            cong = (
                round(max((metrics[s].congestion_score for s in incoming), default=0.0), 1)
                if incoming
                else 0.0
            )
            self.graph.upsert_node(
                KGNode(
                    type=NodeType.JUNCTION,
                    id=jid,
                    props={
                        "name": jn.name,
                        "lat": jn.lat,
                        "lon": jn.lon,
                        "has_signal": jn.has_signal,
                        "congestion": cong,
                    },
                )
            )

        # roads + connectivity
        for sid, seg in net.segments.items():
            m = metrics.get(sid)
            self.graph.upsert_node(
                KGNode(
                    type=NodeType.ROAD,
                    id=sid,
                    props={
                        "name": seg.name,
                        "lanes": seg.lanes,
                        "speed_limit": seg.speed_limit_kph,
                        "congestion": m.congestion_score if m else 0.0,
                        "speed": m.speed_kph if m else seg.speed_limit_kph,
                        "queue_len_m": m.queue_len_m if m else 0.0,
                        "blocked": False,
                    },
                )
            )
            self.graph.upsert_edge(
                KGEdge(
                    type=EdgeType.FROM,
                    src_type=NodeType.ROAD,
                    src_id=sid,
                    dst_type=NodeType.JUNCTION,
                    dst_id=seg.from_junction,
                )
            )
            self.graph.upsert_edge(
                KGEdge(
                    type=EdgeType.TO,
                    src_type=NodeType.ROAD,
                    src_id=sid,
                    dst_type=NodeType.JUNCTION,
                    dst_id=seg.to_junction,
                )
            )

        # signals
        for sig in net.signals.values():
            self.graph.upsert_node(
                KGNode(
                    type=NodeType.SIGNAL,
                    id=sig.id,
                    props={"junction": sig.junction_id, "fault": sig.id in faulted_signals},
                )
            )
            self.graph.upsert_edge(
                KGEdge(
                    type=EdgeType.CONTROLS,
                    src_type=NodeType.SIGNAL,
                    src_id=sig.id,
                    dst_type=NodeType.JUNCTION,
                    dst_id=sig.junction_id,
                )
            )

        # incidents
        n_inc = 0
        for inc in incidents:
            if inc.status == IncidentStatus.RESOLVED:
                continue
            n_inc += 1
            self.graph.upsert_node(
                KGNode(
                    type=NodeType.INCIDENT,
                    id=inc.id,
                    props={
                        "itype": inc.type.value,
                        "severity": inc.severity,
                        "status": inc.status.value,
                        "blocked": bool(inc.segments_blocked),
                        "description": inc.description,
                    },
                )
            )
            if inc.segment_id:
                self.graph.upsert_edge(
                    KGEdge(
                        type=EdgeType.OCCURRED_ON,
                        src_type=NodeType.INCIDENT,
                        src_id=inc.id,
                        dst_type=NodeType.ROAD,
                        dst_id=inc.segment_id,
                    )
                )
                # mark road blocked
                if inc.segments_blocked:
                    rn = self.graph.get_node(NodeType.ROAD, inc.segment_id)
                    if rn:
                        rn.props["blocked"] = True
                        self.graph.upsert_node(rn)

        # weather (single 'current' node) affecting all junctions implicitly
        if weather is not None:
            self.graph.upsert_node(
                KGNode(
                    type=NodeType.WEATHER,
                    id="current",
                    props={
                        "kind": weather.kind.value,
                        "rain_mm": weather.rain_mm,
                        "capacity_factor": weather.capacity_factor,
                        "visibility_m": weather.visibility_m,
                    },
                )
            )

        # events
        for ev in events:
            self.graph.upsert_node(
                KGNode(
                    type=NodeType.EVENT,
                    id=ev.id,
                    props={
                        "etype": ev.type.value,
                        "name": ev.name,
                        "attendance": ev.expected_attendance,
                        "start": ev.start.isoformat(),
                        "end": ev.end.isoformat(),
                    },
                )
            )
            if ev.nearest_junction:
                self.graph.upsert_edge(
                    KGEdge(
                        type=EdgeType.NEAR,
                        src_type=NodeType.EVENT,
                        src_id=ev.id,
                        dst_type=NodeType.JUNCTION,
                        dst_id=ev.nearest_junction,
                    )
                )

        stats = self.graph.stats()
        log.info("KG synced: %s (incidents=%d, events=%d)", stats, n_inc, len(events))
        return stats

    def sync_from_storage(self, storage, intelligence, *, faulted_signals=None) -> dict[str, int]:
        net = load_network(storage.db)
        metrics = intelligence.latest_metrics()
        incidents = storage.db.find("incident", Incident, where={"status": "active"})
        incidents += storage.db.find("incident", Incident, where={"status": "clearing"})
        weathers = storage.db.find("weather", Weather, order_by_ts=True, desc=True, limit=1)
        events = storage.db.find("city_event", CityEvent, limit=200)
        return self.sync(
            net,
            metrics,
            incidents,
            weathers[0] if weathers else None,
            events,
            faulted_signals=faulted_signals,
        )
