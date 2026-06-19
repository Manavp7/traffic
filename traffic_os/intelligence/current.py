"""Shared accessor for *current* (live) segment metrics.

The live API loop overwrites a small ``live_metric`` collection each tick (no growth),
while ``segment_metric`` holds the historical series used for forecasting. This helper
returns the freshest metrics, preferring live data and falling back to history.
"""

from __future__ import annotations

from traffic_os.schemas import SegmentMetric


def current_metrics(db) -> dict[str, SegmentMetric]:
    live = db.find("live_metric", SegmentMetric, limit=100000)
    if live:
        return {m.segment_id: m for m in live}
    return {m.segment_id: m for m in db.latest_per_segment(SegmentMetric)}
