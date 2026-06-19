"""Anomaly detection — flag segments whose current congestion deviates from history."""

from __future__ import annotations

import statistics

from traffic_os.intelligence.current import current_metrics
from traffic_os.schemas import SegmentMetric


def detect_anomalies(storage, *, z_threshold: float = 2.5, min_history: int = 12) -> list[dict]:
    """Per-segment z-score of current congestion vs its historical distribution."""
    history = storage.db.metrics_range(SegmentMetric)
    by_seg: dict[str, list[float]] = {}
    for m in history:
        by_seg.setdefault(m.segment_id, []).append(m.congestion_score)

    anomalies = []
    for sid, m in current_metrics(storage.db).items():
        hist = by_seg.get(sid, [])
        if len(hist) < min_history:
            continue
        mean = statistics.fmean(hist)
        std = statistics.pstdev(hist) or 1.0
        z = (m.congestion_score - mean) / std
        if abs(z) >= z_threshold:
            anomalies.append(
                {
                    "segment_id": sid,
                    "current": round(m.congestion_score, 1),
                    "historical_mean": round(mean, 1),
                    "z_score": round(z, 2),
                    "direction": "spike" if z > 0 else "drop",
                }
            )
    anomalies.sort(key=lambda a: abs(a["z_score"]), reverse=True)  # type: ignore[arg-type]
    return anomalies
