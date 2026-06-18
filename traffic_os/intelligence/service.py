"""IntelligenceService — turns raw metrics/tracks into traffic intelligence.

Loads the network + latest metrics from storage, recomputes the authoritative
congestion score, and exposes hotspots, bottlenecks, travel-time and collision
detection to the API and other layers.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime

from traffic_os.common.logging import get_logger
from traffic_os.intelligence.bottleneck import Bottleneck, find_bottlenecks
from traffic_os.intelligence.collision import detect_all
from traffic_os.intelligence.congestion import DEFAULT_MODEL, CongestionModel, level
from traffic_os.intelligence.hotspots import Hotspot, top_hotspots
from traffic_os.intelligence.travel_time import RouteEstimate, TravelTimeEstimator
from traffic_os.schemas import CollisionEvent, SegmentMetric, Track
from traffic_os.simulation.network import RoadNetwork, load_network

log = get_logger("intelligence")


class IntelligenceService:
    def __init__(self, storage, model: CongestionModel = DEFAULT_MODEL) -> None:
        self.storage = storage
        self.model = model
        self._net: RoadNetwork | None = None

    @property
    def net(self) -> RoadNetwork:
        if self._net is None or not self._net.segments:
            self._net = load_network(self.storage.db)
        return self._net

    def refresh_network(self) -> None:
        self._net = load_network(self.storage.db)

    # -- metrics ---------------------------------------------------------- #
    def latest_metrics(self) -> dict[str, SegmentMetric]:
        rows = self.storage.db.latest_per_segment(SegmentMetric)
        out: dict[str, SegmentMetric] = {}
        for m in rows:
            seg = self.net.segments.get(m.segment_id)
            if seg is None:
                continue
            m.congestion_score = self.model.score(m, seg)  # authoritative
            out[m.segment_id] = m
        return out

    def recompute_history(self) -> int:
        """Rewrite the authoritative congestion score across all stored metrics."""
        rows = self.storage.db.metrics_range(SegmentMetric)
        changed = []
        for m in rows:
            seg = self.net.segments.get(m.segment_id)
            if seg is None:
                continue
            m.congestion_score = self.model.score(m, seg)
            changed.append(m)
        self.storage.db.upsert_many("segment_metric", changed)
        return len(changed)

    # -- intelligence ----------------------------------------------------- #
    def hotspots(self, top_n: int = 20) -> list[Hotspot]:
        return top_hotspots(self.net, self.latest_metrics(), top_n=top_n)

    def bottlenecks(self, top_n: int = 10) -> list[Bottleneck]:
        return find_bottlenecks(self.net, self.latest_metrics(), top_n=top_n)

    def travel_time(self, origin: str, destination: str) -> RouteEstimate | None:
        est = TravelTimeEstimator(self.net, self.latest_metrics())
        return est.estimate(origin, destination)

    def collisions(self) -> list[CollisionEvent]:
        tracks = self.storage.db.find("track", Track, limit=2000)
        events = detect_all(tracks, self.net)
        if events:
            self.storage.db.upsert_many("collision", events)
        return events

    def summary(self) -> dict:
        metrics = self.latest_metrics()
        if not metrics:
            return {"avg_congestion": 0.0, "segments": 0, "severe": 0, "worst": None}
        scores = [m.congestion_score for m in metrics.values()]
        avg = sum(scores) / len(scores)
        severe = sum(1 for s in scores if s >= 75)
        spots = top_hotspots(self.net, metrics, top_n=1)
        worst = asdict(spots[0]) if spots else None
        return {
            "avg_congestion": round(avg, 1),
            "level": level(avg),
            "segments": len(metrics),
            "severe": severe,
            "worst": worst,
            "ts": _latest_ts(metrics),
        }


def _latest_ts(metrics: dict[str, SegmentMetric]) -> str | None:
    ts: datetime | None = None
    for m in metrics.values():
        if ts is None or m.ts > ts:
            ts = m.ts
    return ts.isoformat() if ts else None
