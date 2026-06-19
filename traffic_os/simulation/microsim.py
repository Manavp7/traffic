"""Mesoscopic traffic microsimulator (the heart of the digital twin).

Design: each road segment is a queue with a fundamental-diagram speed and a
signal/capacity-gated discharge. Vehicles are routed end-to-end on the graph, so
congestion, queues and bottlenecks emerge naturally. A subset of vehicles are
"probes" whose full trajectories are recorded as :class:`Track` objects — these
feed the violation and collision-detection layers (parity with real GPS/CV).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime

import networkx as nx

from traffic_os.common.geo import bearing_deg, interpolate
from traffic_os.common.logging import get_logger
from traffic_os.schemas import SegmentMetric, Track, TrackPoint, VehicleClass
from traffic_os.simulation.network import RoadNetwork
from traffic_os.simulation.signals import SignalController

log = get_logger("sim.micro")

JAM_DENSITY_PER_LANE = 150.0  # PCU/km/lane
SAT_FLOW_PER_LANE = 1800.0  # PCU/h/lane
MIN_SPEED_KPH = 4.0
VEH_SPACING_M = 7.0  # average jam spacing per PCU

_CLASS_WEIGHTS = [
    (VehicleClass.CAR, 0.45),
    (VehicleClass.BIKE, 0.30),
    (VehicleClass.AUTO, 0.13),
    (VehicleClass.BUS, 0.05),
    (VehicleClass.TRUCK, 0.07),
]


@dataclass
class Vehicle:
    id: str
    cls: VehicleClass
    route: list[str]
    idx: int = 0
    pos_m: float = 0.0
    speed_kph: float = 0.0
    is_probe: bool = False
    heading: float = 0.0

    @property
    def segment_id(self) -> str:
        return self.route[self.idx]


@dataclass
class SimStep:
    tick: int
    ts: datetime
    metrics: list[SegmentMetric]
    active_vehicles: int
    spawned: int
    exited: int
    probe_track_ids: list[str] = field(default_factory=list)


def diurnal_factor(hour_float: float) -> float:
    """Time-of-day demand multiplier with morning/evening peaks (0.15..1.0)."""
    import math

    morning = math.exp(-((hour_float - 9.0) ** 2) / (2 * 1.5**2))
    evening = math.exp(-((hour_float - 18.5) ** 2) / (2 * 1.8**2))
    midday = 0.45 * math.exp(-((hour_float - 13.0) ** 2) / (2 * 2.5**2))
    base = 0.12
    return base + 0.95 * max(morning, evening) + midday


class MicroSim:
    def __init__(
        self,
        net: RoadNetwork,
        signals: SignalController,
        *,
        seed: int = 42,
        demand_scale: float = 7.0,
        probe_ratio: float = 0.12,
        track_history: int = 40,
        directional_bias: float = 0.45,
    ) -> None:
        self.net = net
        self.signals = signals
        self.rng = random.Random(seed)
        self.demand_scale = demand_scale
        self.probe_ratio = probe_ratio
        self.track_history = track_history
        self.directional_bias = directional_bias

        self.vehicles: dict[str, Vehicle] = {}
        self.tracks: dict[str, Track] = {}
        self._veh_seq = 0

        self.graph = self._build_graph()
        self._route_cache: dict[tuple[str, str], list[str]] = {}
        self._junctions = list(net.junctions)
        self._central = self._central_junctions()
        self._art_src, self._art_dst = self._arterial_corridor()

    # -- graph / routing -------------------------------------------------- #
    def _build_graph(self) -> nx.DiGraph:
        g = nx.DiGraph()
        for seg in self.net.segments.values():
            # travel-time weight so routes prefer faster arterials
            tt = seg.length_m / max(seg.speed_limit_kph / 3.6, 1.0)
            g.add_edge(seg.from_junction, seg.to_junction, seg=seg.id, weight=tt)
        return g

    def _central_junctions(self) -> list[str]:
        """Junctions near the centroid — biased trip destinations (commercial core)."""
        lats = [j.lat for j in self.net.junctions.values()]
        lons = [j.lon for j in self.net.junctions.values()]
        clat, clon = sum(lats) / len(lats), sum(lons) / len(lons)
        ranked = sorted(
            self.net.junctions.values(),
            key=lambda j: (j.lat - clat) ** 2 + (j.lon - clon) ** 2,
        )
        k = max(1, len(ranked) // 6)
        return [j.id for j in ranked[:k]]

    def _arterial_corridor(self) -> tuple[list[str], list[str]]:
        """West/East endpoints of the central arterial row (grid only).

        Heavy west->east demand along this corridor creates the directional
        imbalance that adaptive signal control exploits. Empty for non-grid nets.
        """
        rows, cols = set(), set()
        for jid in self.net.junctions:
            if not jid.startswith("J") or "_" not in jid:
                return [], []
            try:
                r, c = (int(x) for x in jid[1:].split("_"))
            except ValueError:
                return [], []
            rows.add(r)
            cols.add(c)
        if not rows or not cols:
            return [], []
        mid = sorted(rows)[len(rows) // 2]
        maxc = max(cols)
        west = [f"J{mid}_{0}", f"J{mid}_{1}"]
        east = [f"J{mid}_{maxc}", f"J{mid}_{maxc - 1}"]
        west = [j for j in west if j in self.net.junctions]
        east = [j for j in east if j in self.net.junctions]
        return west, east

    def _route(self, src: str, dst: str) -> list[str]:
        key = (src, dst)
        if key in self._route_cache:
            return self._route_cache[key]
        try:
            nodes = nx.shortest_path(self.graph, src, dst, weight="weight")
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            self._route_cache[key] = []
            return []
        segs: list[str] = []
        for a, b in zip(nodes[:-1], nodes[1:], strict=False):
            sid = self.net.pair_to_segment.get((a, b))
            if sid is None:
                segs = []
                break
            segs.append(sid)
        self._route_cache[key] = segs
        return segs

    # -- demand ----------------------------------------------------------- #
    def _pick_class(self) -> VehicleClass:
        r = self.rng.random()
        acc = 0.0
        for cls, w in _CLASS_WEIGHTS:
            acc += w
            if r <= acc:
                return cls
        return VehicleClass.CAR

    def spawn(self, n: int) -> int:
        spawned = 0
        for _ in range(n):
            if self._art_src and self._art_dst and self.rng.random() < self.directional_bias:
                # heavy directional arterial flow (west -> east) — asymmetric load
                src = self.rng.choice(self._art_src)
                dst = self.rng.choice(self._art_dst)
            else:
                src = self.rng.choice(self._junctions)
                dst = (
                    self.rng.choice(self._central)
                    if self.rng.random() < 0.55
                    else self.rng.choice(self._junctions)
                )
            if src == dst:
                continue
            route = self._route(src, dst)
            if not route:
                continue
            self._veh_seq += 1
            vid = f"V{self._veh_seq}"
            is_probe = self.rng.random() < self.probe_ratio
            veh = Vehicle(id=vid, cls=self._pick_class(), route=route, is_probe=is_probe)
            self.vehicles[vid] = veh
            if is_probe:
                self.tracks[vid] = Track(
                    track_id=vid, source_id="sim", cls=veh.cls.value, segment_id=route[0]
                )
            spawned += 1
        return spawned

    # -- dynamics --------------------------------------------------------- #
    def _segment_pcu(self) -> dict[str, float]:
        load: dict[str, float] = dict.fromkeys(self.net.segments, 0.0)
        for veh in self.vehicles.values():
            load[veh.segment_id] += veh.cls.pcu
        return load

    def _segment_speed(self, seg_id: str, pcu: float) -> float:
        seg = self.net.segments[seg_id]
        length_km = max(seg.length_m / 1000.0, 1e-3)
        dens_per_lane = pcu / length_km / seg.lanes
        ratio = min(dens_per_lane / JAM_DENSITY_PER_LANE, 1.0)
        return max(seg.speed_limit_kph * (1.0 - ratio), MIN_SPEED_KPH)

    def step(
        self,
        tick: int,
        ts: datetime,
        dt: float,
        *,
        capacity_factor: float = 1.0,
        extra_demand: float = 0.0,
        blocked: set[str] | None = None,
    ) -> SimStep:
        blocked = blocked or set()
        self.signals.step(dt)

        # 1) demand
        hour = ts.hour + ts.minute / 60.0
        rate = self.demand_scale * diurnal_factor(hour) + extra_demand
        n_new = self._poisson(rate)
        spawned = self.spawn(n_new)

        # 2) movement
        pcu = self._segment_pcu()
        speeds = {s: self._segment_speed(s, pcu[s]) for s in self.net.segments}
        # per-tick discharge budget per segment (PCU) when gate open
        discharge_budget = {
            s: SAT_FLOW_PER_LANE / 3600.0 * seg.lanes * dt * capacity_factor
            for s, seg in self.net.segments.items()
        }
        jam_cap = {
            s: JAM_DENSITY_PER_LANE * seg.lanes * max(seg.length_m / 1000.0, 1e-3)
            for s, seg in self.net.segments.items()
        }

        exited = 0
        # process vehicles front-first within each segment for realistic discharge
        order = sorted(self.vehicles.values(), key=lambda v: v.pos_m, reverse=True)
        for veh in order:
            seg = self.net.segments[veh.segment_id]
            v_kph = speeds[veh.segment_id]
            veh.speed_kph = v_kph
            veh.pos_m += v_kph / 3.6 * dt
            if veh.pos_m < seg.length_m:
                continue
            # reached the downstream junction
            jn = seg.to_junction
            if veh.idx + 1 >= len(veh.route):
                self._remove(veh)
                exited += 1
                continue
            next_seg = veh.route[veh.idx + 1]
            green = self.signals.green_segments(jn)
            gate_open = green is None or veh.segment_id in green
            has_capacity = (
                discharge_budget[veh.segment_id] >= veh.cls.pcu
                and pcu[next_seg] + veh.cls.pcu <= jam_cap[next_seg]
                and next_seg not in blocked
                and veh.segment_id not in blocked
            )
            if gate_open and has_capacity:
                overflow = veh.pos_m - seg.length_m
                discharge_budget[veh.segment_id] -= veh.cls.pcu
                pcu[veh.segment_id] -= veh.cls.pcu
                pcu[next_seg] += veh.cls.pcu
                veh.idx += 1
                veh.pos_m = min(overflow, self.net.segments[next_seg].length_m)
            else:
                veh.pos_m = seg.length_m  # queue at stop line
                veh.speed_kph = 0.0

        # 3) metrics + probe tracks
        metrics = self._collect_metrics(ts, pcu, speeds)
        probe_ids = self._update_tracks(ts)

        return SimStep(
            tick=tick,
            ts=ts,
            metrics=metrics,
            active_vehicles=len(self.vehicles),
            spawned=spawned,
            exited=exited,
            probe_track_ids=probe_ids,
        )

    def _collect_metrics(
        self, ts: datetime, pcu: dict[str, float], speeds: dict[str, float]
    ) -> list[SegmentMetric]:
        counts: dict[str, int] = dict.fromkeys(self.net.segments, 0)
        queued: dict[str, int] = dict.fromkeys(self.net.segments, 0)
        for veh in self.vehicles.values():
            counts[veh.segment_id] += 1
            if veh.speed_kph <= MIN_SPEED_KPH + 0.1:
                queued[veh.segment_id] += 1

        out = []
        for sid, seg in self.net.segments.items():
            length_km = max(seg.length_m / 1000.0, 1e-3)
            dens = pcu[sid] / length_km / seg.lanes
            occ = min(dens / JAM_DENSITY_PER_LANE * 100.0, 100.0)
            speed = speeds[sid]
            queue_len = queued[sid] * VEH_SPACING_M / seg.lanes
            tt = seg.length_m / max(speed / 3.6, 0.5)
            out.append(
                SegmentMetric(
                    segment_id=sid,
                    ts=ts,
                    vehicle_count=counts[sid],
                    density_pcu_per_km=round(dens, 2),
                    speed_kph=round(speed, 2),
                    occupancy_pct=round(occ, 2),
                    queue_len_m=round(queue_len, 1),
                    congestion_score=round(
                        self._provisional_congestion(seg, speed, occ, queue_len), 1
                    ),
                    travel_time_s=round(tt, 1),
                )
            )
        return out

    @staticmethod
    def _provisional_congestion(seg, speed, occ, queue_len) -> float:
        """Provisional 0..100 score; the Intelligence layer recomputes authoritatively."""
        speed_deficit = max(0.0, 1.0 - speed / max(seg.speed_limit_kph, 1.0))
        q = min(queue_len / 200.0, 1.0)
        return min(100.0, 100.0 * (0.5 * speed_deficit + 0.3 * occ / 100.0 + 0.2 * q))

    def _update_tracks(self, ts: datetime) -> list[str]:
        ids = []
        for veh in self.vehicles.values():
            if not veh.is_probe:
                continue
            seg = self.net.segments[veh.segment_id]
            frac = min(veh.pos_m / max(seg.length_m, 1e-3), 1.0)
            (lat1, lon1), (lat2, lon2) = seg.geometry[0], seg.geometry[-1]
            lat, lon = interpolate(lat1, lon1, lat2, lon2, frac)
            heading = bearing_deg(lat1, lon1, lat2, lon2)
            tr = self.tracks.get(veh.id)
            if tr is None:
                tr = Track(track_id=veh.id, source_id="sim", cls=veh.cls.value)
                self.tracks[veh.id] = tr
            tr.segment_id = veh.segment_id
            tr.points.append(
                TrackPoint(ts=ts, lat=lat, lon=lon, speed_kph=veh.speed_kph, heading_deg=heading)
            )
            if len(tr.points) > self.track_history:
                tr.points = tr.points[-self.track_history :]
            ids.append(veh.id)
        return ids

    def _remove(self, veh: Vehicle) -> None:
        self.vehicles.pop(veh.id, None)

    def _poisson(self, lam: float) -> int:
        # Knuth's algorithm
        import math

        if lam <= 0:
            return 0
        ll = math.exp(-lam)
        k = 0
        p = 1.0
        while True:
            k += 1
            p *= self.rng.random()
            if p <= ll:
                return k - 1
