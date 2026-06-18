"""Rule-based violation detectors over vehicle trajectories.

All detectors are pure functions of a :class:`Track` plus the road network (and,
for red-light running, a green-phase predicate). Vision-model violations
(no-helmet/seatbelt/phone/triple-riding/zebra) are roadmap and live behind the
``VisionViolationDetector`` interface in :mod:`traffic_os.violations.vision_stub`.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime

from traffic_os.common.geo import angular_diff_deg, bearing_deg, haversine_m
from traffic_os.schemas import Track, Violation, ViolationType
from traffic_os.simulation.network import RoadNetwork

# tuning
SPEEDING_TOLERANCE = 0.15  # 15% over limit
WRONGWAY_ANGLE_DEG = 110.0
WRONGWAY_MIN_POINTS = 3
PARK_SPEED_KPH = 2.0
PARK_MIN_SECONDS = 90.0
PARK_MIN_DIST_FROM_JUNCTION_M = 30.0
REDLIGHT_NEAR_JUNCTION_M = 18.0
REDLIGHT_MIN_SPEED_KPH = 12.0

IsGreen = Callable[[str, datetime], bool]


def _vid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _seg_bearing(net: RoadNetwork, seg_id: str) -> float | None:
    seg = net.segments.get(seg_id)
    if seg is None or len(seg.geometry) < 2:
        return None
    (la1, lo1), (la2, lo2) = seg.geometry[0], seg.geometry[-1]
    return bearing_deg(la1, lo1, la2, lo2)


def detect_speeding(track: Track, net: RoadNetwork) -> list[Violation]:
    seg = net.segments.get(track.segment_id or "")
    if seg is None:
        return []
    limit = seg.speed_limit_kph * (1 + SPEEDING_TOLERANCE)
    worst = None
    for p in track.points:
        if p.speed_kph > limit and (worst is None or p.speed_kph > worst.speed_kph):
            worst = p
    if worst is None:
        return []
    return [
        Violation(
            id=_vid("SPD"),
            ts=worst.ts,
            type=ViolationType.SPEEDING,
            lat=worst.lat or 0.0,
            lon=worst.lon or 0.0,
            segment_id=seg.id,
            vehicle_track_id=track.track_id,
            detail=f"{worst.speed_kph:.0f} km/h in {seg.speed_limit_kph:.0f} km/h zone",
        )
    ]


def detect_wrong_side(track: Track, net: RoadNetwork) -> list[Violation]:
    seg = net.segments.get(track.segment_id or "")
    if seg is None or not seg.one_way:
        return []
    sb = _seg_bearing(net, seg.id)
    if sb is None:
        return []
    moving = [p for p in track.points if p.speed_kph > 2.0]
    if len(moving) < WRONGWAY_MIN_POINTS:
        return []
    opposed = [p for p in moving if angular_diff_deg(p.heading_deg, sb) > WRONGWAY_ANGLE_DEG]
    if len(opposed) >= WRONGWAY_MIN_POINTS and len(opposed) / len(moving) > 0.6:
        p = opposed[-1]
        return [
            Violation(
                id=_vid("WS"),
                ts=p.ts,
                type=ViolationType.WRONG_SIDE,
                lat=p.lat or 0.0,
                lon=p.lon or 0.0,
                segment_id=seg.id,
                vehicle_track_id=track.track_id,
                detail=f"Travelling against one-way direction on {seg.name}",
            )
        ]
    return []


def detect_illegal_parking(track: Track, net: RoadNetwork) -> list[Violation]:
    seg = net.segments.get(track.segment_id or "")
    if seg is None:
        return []
    from_j = net.junctions.get(seg.from_junction)
    to_j = net.junctions.get(seg.to_junction)
    pts = track.points
    # find longest contiguous stationary run
    best_start = best_len = 0
    i = 0
    while i < len(pts):
        if pts[i].speed_kph <= PARK_SPEED_KPH:
            j = i
            while j < len(pts) and pts[j].speed_kph <= PARK_SPEED_KPH:
                j += 1
            if j - i > best_len:
                best_len, best_start = j - i, i
            i = j
        else:
            i += 1
    if best_len < 2:
        return []
    run = pts[best_start : best_start + best_len]
    dur = (run[-1].ts - run[0].ts).total_seconds()
    if dur < PARK_MIN_SECONDS:
        return []
    p = run[len(run) // 2]
    if p.lat is None or p.lon is None:
        return []
    # stationary near a junction == queueing (legal); only flag mid-block stops
    near_junction = False
    for jn in (from_j, to_j):
        if jn and haversine_m(p.lat, p.lon, jn.lat, jn.lon) < PARK_MIN_DIST_FROM_JUNCTION_M:
            near_junction = True
    if near_junction:
        return []
    return [
        Violation(
            id=_vid("PARK"),
            ts=p.ts,
            type=ViolationType.ILLEGAL_PARKING,
            lat=p.lat,
            lon=p.lon,
            segment_id=seg.id,
            vehicle_track_id=track.track_id,
            detail=f"Stationary {dur:.0f}s mid-block on {seg.name}",
        )
    ]


def detect_red_light(track: Track, net: RoadNetwork, is_green: IsGreen) -> list[Violation]:
    seg = net.segments.get(track.segment_id or "")
    if seg is None:
        return []
    to_j = net.junctions.get(seg.to_junction)
    if to_j is None or not to_j.has_signal:
        return []
    for p in track.points:
        if p.lat is None or p.lon is None:
            continue
        dist = haversine_m(p.lat, p.lon, to_j.lat, to_j.lon)
        if (
            dist <= REDLIGHT_NEAR_JUNCTION_M
            and p.speed_kph >= REDLIGHT_MIN_SPEED_KPH
            and not is_green(seg.id, p.ts)
        ):
            return [
                Violation(
                    id=_vid("RLJ"),
                    ts=p.ts,
                    type=ViolationType.RED_LIGHT,
                    lat=p.lat,
                    lon=p.lon,
                    segment_id=seg.id,
                    vehicle_track_id=track.track_id,
                    detail=f"Crossed stop line at {p.speed_kph:.0f} km/h on red",
                )
            ]
    return []
