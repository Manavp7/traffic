"""Stochastic incident injection (accidents, breakdowns, flooding, roadwork).

Active incidents reduce capacity / block their segment until they resolve.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime

from traffic_os.common.timeutil import utcnow
from traffic_os.schemas import Incident, IncidentStatus, IncidentType
from traffic_os.simulation.network import RoadNetwork

# probability per tick that a new incident appears (scaled by congestion & weather)
BASE_HAZARD = 0.01


@dataclass
class _ActiveIncident:
    incident: Incident
    remaining_s: float


class IncidentManager:
    def __init__(self, net: RoadNetwork, seed: int = 7) -> None:
        self.net = net
        self.rng = random.Random(seed)
        self.active: dict[str, _ActiveIncident] = {}
        self._seq = 0

    def blocked_segments(self) -> set[str]:
        out: set[str] = set()
        for ai in self.active.values():
            out.update(ai.incident.segments_blocked)
        return out

    def step(
        self,
        ts: datetime,
        dt: float,
        *,
        hazard_multiplier: float = 1.0,
    ) -> tuple[list[Incident], list[Incident]]:
        """Advance incidents. Returns (new_incidents, updated_incidents)."""
        new: list[Incident] = []
        updated: list[Incident] = []

        # resolve / age existing
        for iid in list(self.active):
            ai = self.active[iid]
            ai.remaining_s -= dt
            if ai.remaining_s <= 0:
                ai.incident.status = IncidentStatus.RESOLVED
                updated.append(ai.incident)
                self.active.pop(iid)
            elif ai.remaining_s < 120 and ai.incident.status == IncidentStatus.ACTIVE:
                ai.incident.status = IncidentStatus.CLEARING
                updated.append(ai.incident)

        # maybe spawn a new one
        if self.rng.random() < BASE_HAZARD * hazard_multiplier:
            new.append(self._spawn(ts))

        return new, updated

    def _spawn(self, ts: datetime) -> Incident:
        self._seq += 1
        seg = self.rng.choice(list(self.net.segments.values()))
        itype = self.rng.choices(
            [
                IncidentType.ACCIDENT,
                IncidentType.BREAKDOWN,
                IncidentType.FLOOD,
                IncidentType.ROADWORK,
            ],
            weights=[0.4, 0.35, 0.1, 0.15],
        )[0]
        severity = self.rng.uniform(0.3, 1.0)
        duration = self.rng.uniform(300, 1800) * (1.5 if itype == IncidentType.ACCIDENT else 1.0)
        lat, lon = seg.geometry[len(seg.geometry) // 2]
        inc = Incident(
            id=f"INC-{self._seq}",
            ts=ts or utcnow(),
            type=itype,
            lat=lat,
            lon=lon,
            segment_id=seg.id,
            severity=round(severity, 2),
            segments_blocked=[seg.id] if severity > 0.6 else [],
            status=IncidentStatus.ACTIVE,
            description=f"{itype.value} on {seg.name}",
        )
        self.active[inc.id] = _ActiveIncident(incident=inc, remaining_s=duration)
        return inc
