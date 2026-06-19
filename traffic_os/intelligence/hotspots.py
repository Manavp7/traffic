"""Hotspot detection — rank the worst congestion points (junction-level)."""

from __future__ import annotations

from dataclasses import dataclass

from traffic_os.schemas import SegmentMetric
from traffic_os.simulation.network import RoadNetwork


@dataclass
class Hotspot:
    junction_id: str
    name: str
    lat: float
    lon: float
    congestion: float
    worst_segment: str | None
    incoming_segments: int


def top_hotspots(
    net: RoadNetwork,
    metrics: dict[str, SegmentMetric],
    *,
    top_n: int = 20,
) -> list[Hotspot]:
    """Aggregate incoming-segment congestion to each junction and rank."""
    spots: list[Hotspot] = []
    for jid, jn in net.junctions.items():
        incoming = net.in_segments.get(jid, [])
        scored = [(s, metrics[s].congestion_score) for s in incoming if s in metrics]
        if not scored:
            continue
        # junction congestion = mean of incoming, emphasising the worst approach
        worst_seg, worst = max(scored, key=lambda x: x[1])
        mean = sum(c for _, c in scored) / len(scored)
        cong = round(0.6 * worst + 0.4 * mean, 1)
        spots.append(
            Hotspot(
                junction_id=jid,
                name=jn.name,
                lat=jn.lat,
                lon=jn.lon,
                congestion=cong,
                worst_segment=worst_seg,
                incoming_segments=len(scored),
            )
        )
    spots.sort(key=lambda h: h.congestion, reverse=True)
    return spots[:top_n]
