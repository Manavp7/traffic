"""Tracking-based incident detection (replaces opaque video action models).

From ByteTrack/GPS trajectories we detect, explainably:
- **sudden stop**: a sharp deceleration from cruising speed to ~0,
- **abnormal motion**: wrong-way travel or erratic heading,
- **collision**: two tracks converging to near-coincident points and stopping.
"""

from __future__ import annotations

import uuid

from traffic_os.common.geo import angular_diff_deg, bearing_deg, haversine_m
from traffic_os.schemas import CollisionEvent, CollisionKind, Track
from traffic_os.simulation.network import RoadNetwork

SUDDEN_STOP_FROM_KPH = 18.0
SUDDEN_STOP_TO_KPH = 3.0
COLLISION_DIST_M = 12.0
COLLISION_SPEED_KPH = 4.0
WRONGWAY_ANGLE_DEG = 110.0
WRONGWAY_MIN_POINTS = 3


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def detect_sudden_stops(track: Track) -> list[CollisionEvent]:
    events: list[CollisionEvent] = []
    pts = track.points
    for i in range(1, len(pts)):
        if pts[i - 1].speed_kph >= SUDDEN_STOP_FROM_KPH and pts[i].speed_kph <= SUDDEN_STOP_TO_KPH:
            events.append(
                CollisionEvent(
                    id=_new_id("SS"),
                    ts=pts[i].ts,
                    lat=pts[i].lat,
                    lon=pts[i].lon,
                    segment_id=track.segment_id,
                    track_ids=[track.track_id],
                    kind=CollisionKind.SUDDEN_STOP,
                    confidence=0.7,
                )
            )
    return events


def detect_abnormal_motion(track: Track, net: RoadNetwork | None = None) -> list[CollisionEvent]:
    events: list[CollisionEvent] = []
    pts = track.points
    if len(pts) < WRONGWAY_MIN_POINTS:
        return events

    # wrong-way: travel heading opposes the segment's geometric direction
    if net is not None and track.segment_id in net.segments:
        seg = net.segments[track.segment_id]
        (la1, lo1), (la2, lo2) = seg.geometry[0], seg.geometry[-1]
        seg_bearing = bearing_deg(la1, lo1, la2, lo2)
        moving = [p for p in pts if p.speed_kph > 2.0]
        if len(moving) >= WRONGWAY_MIN_POINTS:
            opposed = sum(
                1
                for p in moving
                if angular_diff_deg(p.heading_deg, seg_bearing) > WRONGWAY_ANGLE_DEG
            )
            if opposed >= WRONGWAY_MIN_POINTS and opposed / len(moving) > 0.6:
                p = moving[-1]
                events.append(
                    CollisionEvent(
                        id=_new_id("AM"),
                        ts=p.ts,
                        lat=p.lat,
                        lon=p.lon,
                        segment_id=track.segment_id,
                        track_ids=[track.track_id],
                        kind=CollisionKind.ABNORMAL_MOTION,
                        confidence=0.65,
                    )
                )
                return events

    # erratic heading: large heading variance while moving
    headings = [p.heading_deg for p in pts if p.speed_kph > 5.0]
    if len(headings) >= WRONGWAY_MIN_POINTS:
        swings = [angular_diff_deg(headings[i], headings[i - 1]) for i in range(1, len(headings))]
        if swings and sum(s > 70 for s in swings) >= 2:
            p = pts[-1]
            events.append(
                CollisionEvent(
                    id=_new_id("AM"),
                    ts=p.ts,
                    lat=p.lat,
                    lon=p.lon,
                    segment_id=track.segment_id,
                    track_ids=[track.track_id],
                    kind=CollisionKind.ABNORMAL_MOTION,
                    confidence=0.5,
                )
            )
    return events


def detect_collisions(tracks: list[Track]) -> list[CollisionEvent]:
    """Pairwise: two tracks coincide spatially at the same time and both stop."""
    events: list[CollisionEvent] = []
    # index sudden-stop timestamps per track for corroboration
    stop_ts: dict[str, set] = {}
    for tr in tracks:
        stop_ts[tr.track_id] = {e.ts for e in detect_sudden_stops(tr)}

    for i in range(len(tracks)):
        for j in range(i + 1, len(tracks)):
            a, b = tracks[i], tracks[j]
            # align by timestamp
            bmap = {p.ts: p for p in b.points}
            for pa in a.points:
                pb = bmap.get(pa.ts)
                if pb is None:
                    continue
                dist = haversine_m(pa.lat, pa.lon, pb.lat, pb.lon)
                if (
                    dist <= COLLISION_DIST_M
                    and pa.speed_kph <= COLLISION_SPEED_KPH
                    and pb.speed_kph <= COLLISION_SPEED_KPH
                    and (pa.ts in stop_ts[a.track_id] or pa.ts in stop_ts[b.track_id])
                ):
                    conf = min(0.95, 0.6 + (COLLISION_DIST_M - dist) / COLLISION_DIST_M * 0.35)
                    events.append(
                        CollisionEvent(
                            id=_new_id("COL"),
                            ts=pa.ts,
                            lat=(pa.lat + pb.lat) / 2,
                            lon=(pa.lon + pb.lon) / 2,
                            segment_id=a.segment_id,
                            track_ids=[a.track_id, b.track_id],
                            kind=CollisionKind.COLLISION,
                            confidence=round(conf, 2),
                        )
                    )
                    break  # one collision per pair
    return events


def detect_all(tracks: list[Track], net: RoadNetwork | None = None) -> list[CollisionEvent]:
    events = detect_collisions(tracks)
    collided = {tid for e in events for tid in e.track_ids}
    for tr in tracks:
        if tr.track_id in collided:
            continue
        events.extend(detect_sudden_stops(tr))
        events.extend(detect_abnormal_motion(tr, net))
    return events
