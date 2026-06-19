"""Causal reasoning over the knowledge graph.

The flagship query ``why_congested(junction)`` traverses the connected model to
return ranked, human-readable causes — e.g. "Road 9 closed (accident)",
"Signal 12 malfunction", "rainfall reduces capacity", "concert nearby".
"""

from __future__ import annotations

from datetime import datetime

from traffic_os.knowledge_graph.schema import EdgeType, NodeType
from traffic_os.schemas import CausalFactor

_INCIDENT_LABEL = {
    "accident": "Accident",
    "breakdown": "Vehicle breakdown",
    "flood": "Flooding",
    "fire": "Fire",
    "hazard": "Road hazard",
    "roadwork": "Roadworks",
}


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def why_congested(
    graph,
    junction_id: str,
    *,
    ref_ts: datetime | None = None,
    min_factor: float = 0.05,
) -> list[CausalFactor]:
    factors: list[CausalFactor] = []
    jn = graph.get_node(NodeType.JUNCTION, junction_id)
    if jn is None:
        return factors

    # incoming roads -> incidents / blockages / upstream congestion
    incoming = graph.neighbors(
        NodeType.JUNCTION, junction_id, edge_type=EdgeType.TO, direction="in"
    )
    for _edge, road in incoming:
        rid = road.id
        rname = road.props.get("name", rid)
        rcong = float(road.props.get("congestion", 0.0))

        incidents = graph.neighbors(
            NodeType.ROAD, rid, edge_type=EdgeType.OCCURRED_ON, direction="in"
        )
        for _e, inc in incidents:
            itype = inc.props.get("itype", "incident")
            sev = float(inc.props.get("severity", 0.5))
            iblocked = inc.props.get("blocked", False)
            label = _INCIDENT_LABEL.get(itype, itype.title())
            weight = sev * (1.6 if iblocked else 1.0)
            desc = f"{label} on {rname}" + (" (road blocked)" if iblocked else "")
            factors.append(
                CausalFactor(
                    kind="road_closed" if iblocked else "incident",
                    description=desc,
                    weight=round(weight, 3),
                    node_type=NodeType.ROAD,
                    node_id=rid,
                )
            )
        # upstream congestion contribution (no incident but heavy)
        if not incidents and rcong >= 60:
            factors.append(
                CausalFactor(
                    kind="upstream_congestion",
                    description=f"Heavy upstream congestion on {rname} ({rcong:.0f}/100)",
                    weight=round(rcong / 100.0 * 0.8, 3),
                    node_type=NodeType.ROAD,
                    node_id=rid,
                )
            )

    # signal fault
    signals = graph.neighbors(
        NodeType.JUNCTION, junction_id, edge_type=EdgeType.CONTROLS, direction="in"
    )
    for _e, sig in signals:
        if sig.props.get("fault"):
            factors.append(
                CausalFactor(
                    kind="signal_fault",
                    description=f"Signal {sig.id} malfunction at this junction",
                    weight=0.9,
                    node_type=NodeType.SIGNAL,
                    node_id=sig.id,
                )
            )

    # weather
    wx = graph.get_node(NodeType.WEATHER, "current")
    if wx is not None:
        cf = float(wx.props.get("capacity_factor", 1.0))
        if cf < 1.0:
            kind = wx.props.get("kind", "weather")
            factors.append(
                CausalFactor(
                    kind="weather",
                    description=f"{kind.replace('_', ' ').title()} reduces road capacity "
                    f"(~{int((1 - cf) * 100)}% loss)",
                    weight=round((1.0 - cf) * 1.2, 3),
                    node_type=NodeType.WEATHER,
                    node_id="current",
                )
            )

    # nearby events (active around ref_ts)
    events = graph.neighbors(
        NodeType.JUNCTION, junction_id, edge_type=EdgeType.NEAR, direction="in"
    )
    for _e, ev in events:
        start = _parse(ev.props.get("start"))
        end = _parse(ev.props.get("end"))
        active = True
        if ref_ts and start and end:
            active = start <= ref_ts <= end
        if active:
            att = int(ev.props.get("attendance", 0))
            factors.append(
                CausalFactor(
                    kind="event",
                    description=f"{ev.props.get('name', 'Event')} nearby (~{att:,} attendees)",
                    weight=round(min(att / 40000.0, 1.0) * 0.9, 3),
                    node_type=NodeType.EVENT,
                    node_id=ev.id,
                )
            )

    factors = [f for f in factors if f.weight >= min_factor]
    factors.sort(key=lambda f: f.weight, reverse=True)
    return factors
