"""Bottleneck analysis — find the road *causing* congestion, not just where it shows.

A bottleneck is a constriction: the segment itself is slow/queued while its
*downstream* is comparatively free-flowing, so demand piles up behind it and the
congestion shock-wave propagates *upstream*. We rank candidates by that signature.
"""

from __future__ import annotations

from dataclasses import dataclass

from traffic_os.schemas import SegmentMetric
from traffic_os.simulation.network import RoadNetwork


@dataclass
class Bottleneck:
    segment_id: str
    name: str
    lat: float
    lon: float
    congestion: float
    speed_kph: float
    downstream_speed_kph: float
    upstream_congestion: float
    score: float
    affected_upstream: list[str]
    explanation: str


def find_bottlenecks(
    net: RoadNetwork,
    metrics: dict[str, SegmentMetric],
    *,
    top_n: int = 10,
    min_congestion: float = 40.0,
) -> list[Bottleneck]:
    out: list[Bottleneck] = []
    for sid, seg in net.segments.items():
        m = metrics.get(sid)
        if m is None or m.congestion_score < min_congestion:
            continue

        down_ids = [s for s in net.out_segments.get(seg.to_junction, []) if s in metrics]
        up_ids = [
            s for s in net.in_segments.get(seg.from_junction, []) if s in metrics and s != sid
        ]
        down_speed = (
            sum(metrics[s].speed_kph for s in down_ids) / len(down_ids)
            if down_ids
            else seg.speed_limit_kph
        )
        up_cong = sum(metrics[s].congestion_score for s in up_ids) / len(up_ids) if up_ids else 0.0

        # constriction signature: this segment much slower than what's ahead
        speed_drop = max(0.0, down_speed - m.speed_kph)
        score = speed_drop * 1.2 + m.queue_len_m / 10.0 + m.congestion_score * 0.3 + up_cong * 0.2
        affected = [s for s in up_ids if metrics[s].congestion_score > 50]
        expl = (
            f"{seg.name}: {m.speed_kph:.0f} km/h here vs {down_speed:.0f} km/h downstream, "
            f"queue {m.queue_len_m:.0f} m, backing up {len(affected)} upstream road(s)."
        )
        mlat, mlon = seg.geometry[len(seg.geometry) // 2]
        out.append(
            Bottleneck(
                segment_id=sid,
                name=seg.name,
                lat=mlat,
                lon=mlon,
                congestion=m.congestion_score,
                speed_kph=m.speed_kph,
                downstream_speed_kph=round(down_speed, 1),
                upstream_congestion=round(up_cong, 1),
                score=round(score, 2),
                affected_upstream=affected,
                explanation=expl,
            )
        )
    out.sort(key=lambda b: b.score, reverse=True)
    return out[:top_n]
