"""Per-frame perception metrics: counts, road occupancy %, queue length."""

from __future__ import annotations

from collections import Counter

from traffic_os.perception.detector import RawDetection
from traffic_os.schemas import VehicleClass

AVG_VEHICLE_LEN_M = 4.5


def _bbox_area(b: tuple[float, float, float, float]) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def occupancy_pct(dets: list[RawDetection], frame_area: float, roi_frac: float = 0.6) -> float:
    """Fraction of the (road ROI) area covered by vehicle boxes, capped at 100%."""
    roi = max(frame_area * roi_frac, 1.0)
    covered = sum(_bbox_area(d.bbox) for d in dets if d.cls != VehicleClass.PEDESTRIAN)
    return round(min(covered / roi * 100.0, 100.0), 1)


def counts_by_class(dets: list[RawDetection]) -> dict[str, int]:
    c = Counter(d.cls.value for d in dets)
    return dict(c)


def queue_length_m(
    stationary_ids: set[int],
    *,
    meters_per_vehicle: float = AVG_VEHICLE_LEN_M + 1.5,
) -> float:
    """Estimate standing-queue length from the count of stationary tracked vehicles."""
    return round(len(stationary_ids) * meters_per_vehicle, 1)
