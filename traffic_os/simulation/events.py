"""City events (matches, rallies, concerts, festivals) that surge local demand."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from traffic_os.schemas import CityEvent, EventType
from traffic_os.simulation.network import RoadNetwork

_EVENT_NAMES = {
    EventType.MATCH: "Cricket Match @ Stadium",
    EventType.RALLY: "Political Rally",
    EventType.CONCERT: "Live Concert",
    EventType.FESTIVAL: "City Festival",
}


def make_event(
    net: RoadNetwork,
    start: datetime,
    rng: random.Random,
    *,
    etype: EventType | None = None,
) -> CityEvent:
    etype = etype or rng.choice(list(EventType))
    jn = rng.choice(list(net.junctions.values()))
    duration_h = rng.choice([2, 3, 4])
    attendance = rng.choice([5_000, 12_000, 25_000, 40_000])
    return CityEvent(
        id=f"EV-{start:%Y%m%d}-{rng.randint(100, 999)}",
        type=etype,
        name=_EVENT_NAMES[etype],
        venue_lat=jn.lat,
        venue_lon=jn.lon,
        start=start,
        end=start + timedelta(hours=duration_h),
        expected_attendance=attendance,
        nearest_junction=jn.id,
    )


def event_demand(events: list[CityEvent], ts: datetime) -> float:
    """Extra vehicles/tick from events active (or ramping) near ``ts``."""
    extra = 0.0
    for ev in events:
        ramp_start = ev.start - timedelta(hours=1)
        ramp_end = ev.end + timedelta(hours=1)
        if ramp_start <= ts <= ramp_end:
            extra += ev.expected_attendance / 6000.0
    return extra
