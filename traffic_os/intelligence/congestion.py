"""Authoritative congestion scoring.

Combines speed deficit, queue length, occupancy and density into a single 0..100
score. The simulator writes a provisional score; this module is the source of truth
and recomputes it consistently for both live and historical metrics.
"""

from __future__ import annotations

from dataclasses import dataclass

from traffic_os.schemas import RoadSegment, SegmentMetric
from traffic_os.simulation.microsim import JAM_DENSITY_PER_LANE


@dataclass(frozen=True)
class CongestionModel:
    w_speed: float = 0.40
    w_queue: float = 0.25
    w_occupancy: float = 0.20
    w_density: float = 0.15
    queue_ref_m: float = 250.0  # queue length that maps to "full" contribution

    def score(self, metric: SegmentMetric, seg: RoadSegment) -> float:
        speed_deficit = max(0.0, 1.0 - metric.speed_kph / max(seg.speed_limit_kph, 1.0))
        queue_norm = min(metric.queue_len_m / self.queue_ref_m, 1.0)
        occ_norm = min(metric.occupancy_pct / 100.0, 1.0)
        dens_norm = min(metric.density_pcu_per_km / (JAM_DENSITY_PER_LANE * max(seg.lanes, 1)), 1.0)
        raw = (
            self.w_speed * speed_deficit
            + self.w_queue * queue_norm
            + self.w_occupancy * occ_norm
            + self.w_density * dens_norm
        )
        return round(min(100.0, max(0.0, raw * 100.0)), 1)


DEFAULT_MODEL = CongestionModel()


def level(score: float) -> str:
    if score < 25:
        return "free"
    if score < 50:
        return "moderate"
    if score < 75:
        return "heavy"
    return "severe"
