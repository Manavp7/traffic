"""Driver-behavior scoring from trajectories (harsh braking, weaving, speeding)."""

from __future__ import annotations

from traffic_os.common.geo import angular_diff_deg
from traffic_os.schemas import Track
from traffic_os.simulation.network import RoadNetwork

HARSH_DECEL_KPH = 25.0  # speed drop between consecutive points
WEAVE_HEADING_DEG = 40.0
SPEEDING_TOLERANCE = 1.1


def score_track(track: Track, net: RoadNetwork | None = None) -> dict:
    pts = track.points
    harsh = weave = speeding = 0
    for i in range(1, len(pts)):
        if pts[i - 1].speed_kph - pts[i].speed_kph >= HARSH_DECEL_KPH:
            harsh += 1
        if (
            angular_diff_deg(pts[i].heading_deg, pts[i - 1].heading_deg) >= WEAVE_HEADING_DEG
            and pts[i].speed_kph > 8
        ):
            weave += 1
    limit = None
    if net is not None and track.segment_id in net.segments:
        limit = net.segments[track.segment_id].speed_limit_kph
    if limit:
        speeding = sum(1 for p in pts if p.speed_kph > limit * SPEEDING_TOLERANCE)
    # weighted risk score 0..100 from absolute event counts (robust to short tracks)
    score = min(100.0, harsh * 15.0 + weave * 8.0 + speeding * 6.0)
    return {
        "track_id": track.track_id,
        "class": track.cls,
        "harsh_braking": harsh,
        "weaving": weave,
        "speeding_points": speeding,
        "samples": len(pts),
        "risk_score": round(score, 1),
        "rating": "high" if score >= 60 else "medium" if score >= 30 else "low",
    }


def driver_scores(tracks: list[Track], net: RoadNetwork | None = None) -> list[dict]:
    scores = [score_track(t, net) for t in tracks if len(t.points) >= 2]
    scores.sort(key=lambda s: s["risk_score"], reverse=True)
    return scores
