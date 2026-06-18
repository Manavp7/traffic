"""Live simulation engine — composes network, signals, microsim, incidents, weather, events.

Used by the CLI ``simulate`` command and the API's background loop. Advances a
simulated clock so diurnal demand patterns are visible during a short demo run.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from traffic_os.common.config import Settings, get_settings
from traffic_os.common.logging import get_logger
from traffic_os.common.timeutil import utcnow
from traffic_os.schemas import (
    CityEvent,
    Incident,
    SegmentMetric,
    SignalState,
    Track,
    Weather,
)
from traffic_os.simulation.events import event_demand, make_event
from traffic_os.simulation.incidents import IncidentManager
from traffic_os.simulation.microsim import MicroSim, SimStep
from traffic_os.simulation.network import (
    RoadNetwork,
    build_network_from_settings,
    load_network,
)
from traffic_os.simulation.signals import SignalController
from traffic_os.simulation.weather import weather_at

log = get_logger("sim.engine")


@dataclass
class LiveSnapshot:
    tick: int
    ts: datetime
    weather: Weather
    metrics: list[SegmentMetric]
    incidents: list[Incident]
    signal_states: list[SignalState]
    tracks: list[Track] = field(default_factory=list)
    active_vehicles: int = 0


class SimulationEngine:
    def __init__(
        self,
        net: RoadNetwork,
        settings: Settings | None = None,
        *,
        start: datetime | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.net = net
        self.signals = SignalController(net)
        self.micro = MicroSim(net, self.signals, seed=self.settings.sim_seed)
        self.incidents = IncidentManager(net, seed=self.settings.sim_seed + 1)
        self.dt = float(self.settings.sim_tick_seconds)
        # start clock at a busy morning hour so demos are lively
        self.ts = start or utcnow().replace(hour=9, minute=0, second=0, microsecond=0)
        self.tick = 0
        self._rng = self.micro.rng
        self.events: list[CityEvent] = []
        self._weather = weather_at(self.ts, self._rng)
        # one demo event a couple of hours out
        self.events.append(make_event(net, self.ts + timedelta(hours=2), self._rng))

    @classmethod
    def from_storage(cls, storage, settings: Settings | None = None) -> SimulationEngine:
        net = load_network(storage.db)
        if not net.segments:
            net = build_network_from_settings(settings or get_settings())
        return cls(net, settings)

    def step_once(self) -> LiveSnapshot:
        self.tick += 1
        self.ts += timedelta(seconds=self.dt)
        if self.tick % 12 == 0:  # refresh weather periodically
            self._weather = weather_at(self.ts, self._rng)

        blocked = self.incidents.blocked_segments()
        # higher hazard during rain & heavy demand
        hazard = 2.0 if self._weather.capacity_factor < 0.8 else 1.0
        new_inc, upd_inc = self.incidents.step(self.ts, self.dt, hazard_multiplier=hazard)

        extra = event_demand(self.events, self.ts)
        step: SimStep = self.micro.step(
            self.tick,
            self.ts,
            self.dt,
            capacity_factor=self._weather.capacity_factor,
            extra_demand=extra,
            blocked=blocked,
        )

        tracks = [
            self.micro.tracks[tid] for tid in step.probe_track_ids if tid in self.micro.tracks
        ]
        return LiveSnapshot(
            tick=self.tick,
            ts=self.ts,
            weather=self._weather,
            metrics=step.metrics,
            incidents=new_inc + upd_inc,
            signal_states=self.signals.states(),
            tracks=tracks,
            active_vehicles=step.active_vehicles,
        )

    def persist(self, storage, snap: LiveSnapshot) -> None:
        db = storage.db
        db.upsert_many("segment_metric", snap.metrics)
        if snap.incidents:
            db.upsert_many("incident", snap.incidents)
        db.upsert_many("signal_state", snap.signal_states)
        db.upsert("weather", snap.weather)
        if snap.tracks:
            db.upsert_many("track", snap.tracks)

    def snapshot_message(self, snap: LiveSnapshot) -> dict:
        """Compact live payload for the event bus / WebSocket."""
        vehicles = []
        for tr in snap.tracks:
            if tr.points:
                p = tr.points[-1]
                vehicles.append(
                    {
                        "id": tr.track_id,
                        "lat": p.lat,
                        "lon": p.lon,
                        "cls": tr.cls,
                        "speed": p.speed_kph,
                    }
                )
        return {
            "tick": snap.tick,
            "ts": snap.ts.isoformat(),
            "active_vehicles": snap.active_vehicles,
            "weather": snap.weather.kind.value,
            "metrics": [
                {"segment_id": m.segment_id, "congestion": m.congestion_score, "speed": m.speed_kph}
                for m in snap.metrics
            ],
            "vehicles": vehicles,
            "incidents": [
                {
                    "id": i.id,
                    "type": i.type.value,
                    "lat": i.lat,
                    "lon": i.lon,
                    "status": i.status.value,
                }
                for i in snap.incidents
            ],
        }

    async def run(
        self,
        storage,
        *,
        max_ticks: int | None = None,
        realtime: bool = False,
        persist_every: int = 1,
        on_snapshot=None,
    ) -> None:
        log.info("Simulation loop starting (max_ticks=%s, realtime=%s)", max_ticks, realtime)
        while max_ticks is None or self.tick < max_ticks:
            snap = self.step_once()
            if self.tick % persist_every == 0:
                self.persist(storage, snap)
            msg = self.snapshot_message(snap)
            await storage.bus.publish("live.tick", msg)
            if on_snapshot is not None:
                on_snapshot(snap)
            if realtime:
                await asyncio.sleep(self.dt)
            else:
                await asyncio.sleep(0)
        log.info("Simulation loop finished at tick %d", self.tick)
