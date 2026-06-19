"""KPI / SLA evaluation + breach alerts, and historical snapshot replay."""

from __future__ import annotations

from datetime import datetime

from traffic_os.intelligence.current import current_metrics
from traffic_os.schemas import SegmentMetric

DEFAULT_TARGETS = {
    "max_avg_congestion": 50.0,
    "min_avg_speed_kph": 25.0,
    "max_severe_segments": 5,
}


def evaluate_kpis(storage, targets: dict | None = None) -> dict:
    targets = {**DEFAULT_TARGETS, **(targets or {})}
    metrics = current_metrics(storage.db)
    if not metrics:
        return {"targets": targets, "current": {}, "breaches": []}
    avg_cong = sum(m.congestion_score for m in metrics.values()) / len(metrics)
    avg_speed = sum(m.speed_kph for m in metrics.values()) / len(metrics)
    severe = sum(1 for m in metrics.values() if m.congestion_score >= 75)
    current = {
        "avg_congestion": round(avg_cong, 1),
        "avg_speed_kph": round(avg_speed, 1),
        "severe_segments": severe,
    }
    breaches = []
    if avg_cong > targets["max_avg_congestion"]:
        breaches.append(
            {
                "kpi": "avg_congestion",
                "value": current["avg_congestion"],
                "target": targets["max_avg_congestion"],
            }
        )
    if avg_speed < targets["min_avg_speed_kph"]:
        breaches.append(
            {
                "kpi": "avg_speed_kph",
                "value": current["avg_speed_kph"],
                "target": targets["min_avg_speed_kph"],
            }
        )
    if severe > targets["max_severe_segments"]:
        breaches.append(
            {"kpi": "severe_segments", "value": severe, "target": targets["max_severe_segments"]}
        )
    return {
        "targets": targets,
        "current": current,
        "breaches": breaches,
        "status": "breach" if breaches else "ok",
    }


def replay_snapshot(storage, ts: datetime) -> dict:
    """Return the historical per-segment congestion nearest to ``ts``."""
    from datetime import UTC

    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    rows = storage.db.metrics_range(SegmentMetric)
    if not rows:
        return {"ts": None, "segments": []}

    def _aware(t: datetime) -> datetime:
        return t if t.tzinfo else t.replace(tzinfo=UTC)

    # bucket by timestamp, pick the nearest bucket
    times = sorted({m.ts for m in rows})
    nearest = min(times, key=lambda t: abs((_aware(t) - ts).total_seconds()))
    snap = [
        {"segment_id": m.segment_id, "congestion": m.congestion_score, "speed": m.speed_kph}
        for m in rows
        if m.ts == nearest
    ]
    return {"ts": nearest.isoformat(), "count": len(snap), "segments": snap}
