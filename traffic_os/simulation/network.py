"""Road-network construction for the digital twin.

Two backends:
- ``build_grid_network``: a synthetic NxN grid (default; no network access needed).
- ``build_osm_network``: a real road network via osmnx (optional ``geo`` extra).

Both return a :class:`RoadNetwork` of Junctions, RoadSegments and Signals that the
microsimulator and every downstream layer consume.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from traffic_os.common.geo import bearing_deg, haversine_m
from traffic_os.common.logging import get_logger
from traffic_os.schemas import Junction, RoadSegment, Signal, SignalPhase

log = get_logger("sim.network")

# Reference centre (Bengaluru) for the synthetic grid.
CENTER_LAT = 12.9716
CENTER_LON = 77.5946
M_PER_DEG_LAT = 111_320.0


def _m_per_deg_lon(lat: float) -> float:
    return 111_320.0 * math.cos(math.radians(lat))


@dataclass
class RoadNetwork:
    junctions: dict[str, Junction] = field(default_factory=dict)
    segments: dict[str, RoadSegment] = field(default_factory=dict)
    signals: dict[str, Signal] = field(default_factory=dict)

    # adjacency helpers (built by ``finalize``)
    out_segments: dict[str, list[str]] = field(default_factory=dict)
    in_segments: dict[str, list[str]] = field(default_factory=dict)
    pair_to_segment: dict[tuple[str, str], str] = field(default_factory=dict)

    def finalize(self) -> RoadNetwork:
        self.out_segments = {j: [] for j in self.junctions}
        self.in_segments = {j: [] for j in self.junctions}
        self.pair_to_segment = {}
        for seg in self.segments.values():
            self.out_segments.setdefault(seg.from_junction, []).append(seg.id)
            self.in_segments.setdefault(seg.to_junction, []).append(seg.id)
            self.pair_to_segment[(seg.from_junction, seg.to_junction)] = seg.id
        return self

    def signal_for_junction(self, junction_id: str) -> Signal | None:
        for sig in self.signals.values():
            if sig.junction_id == junction_id:
                return sig
        return None


def _orientation(net_lat1, lon1, lat2, lon2) -> str:
    """Classify a segment as 'NS' or 'EW' by its bearing."""
    b = bearing_deg(net_lat1, lon1, lat2, lon2)
    # 0/180 ~ North-South, 90/270 ~ East-West
    if (45 <= b < 135) or (225 <= b < 315):
        return "EW"
    return "NS"


def build_grid_network(
    n: int = 6,
    spacing_m: float = 320.0,
    *,
    center_lat: float = CENTER_LAT,
    center_lon: float = CENTER_LON,
) -> RoadNetwork:
    """Build an ``n x n`` grid of signalised junctions with two-way roads."""
    net = RoadNetwork()
    dlat = spacing_m / M_PER_DEG_LAT
    dlon = spacing_m / _m_per_deg_lon(center_lat)
    half = (n - 1) / 2.0

    # Junctions
    coords: dict[str, tuple[float, float]] = {}
    for r in range(n):
        for c in range(n):
            jid = f"J{r}_{c}"
            lat = center_lat + (half - r) * dlat
            lon = center_lon + (c - half) * dlon
            # interior junctions are signalised
            interior = 0 < r < n - 1 and 0 < c < n - 1
            net.junctions[jid] = Junction(
                id=jid, name=f"Jn {r}-{c}", lat=lat, lon=lon, has_signal=interior
            )
            coords[jid] = (lat, lon)

    # Segments (both directions between 4-neighbours)
    main_roads = {0, n - 1, n // 2}  # rows/cols that are arterials (more lanes/faster)
    seg_no = 0

    def add_segment(a: str, b: str) -> None:
        nonlocal seg_no
        la, lo = coords[a]
        lb, lob = coords[b]
        length = haversine_m(la, lo, lb, lob)
        ra, ca = map(int, a[1:].split("_"))
        arterial = ra in main_roads or ca in main_roads
        seg = RoadSegment(
            id=f"S{seg_no}",
            name=f"{a}->{b}",
            from_junction=a,
            to_junction=b,
            length_m=round(length, 1),
            lanes=3 if arterial else 2,
            speed_limit_kph=60.0 if arterial else 40.0,
            one_way=True,
            geometry=[(la, lo), (lb, lob)],
        )
        net.segments[seg.id] = seg
        seg_no += 1

    for r in range(n):
        for c in range(n):
            jid = f"J{r}_{c}"
            if c + 1 < n:
                add_segment(jid, f"J{r}_{c+1}")
                add_segment(f"J{r}_{c+1}", jid)
            if r + 1 < n:
                add_segment(jid, f"J{r+1}_{c}")
                add_segment(f"J{r+1}_{c}", jid)

    net.finalize()
    _build_signals(net)
    log.info(
        "Built grid network: %d junctions, %d segments, %d signals",
        len(net.junctions),
        len(net.segments),
        len(net.signals),
    )
    return net


def _build_signals(net: RoadNetwork) -> None:
    """Create two-phase (NS / EW) fixed-timer signals for signalised junctions."""
    sig_no = 0
    for jid, jn in net.junctions.items():
        if not jn.has_signal:
            continue
        incoming = net.in_segments.get(jid, [])
        ns, ew = [], []
        for sid in incoming:
            seg = net.segments[sid]
            fj = net.junctions[seg.from_junction]
            tj = net.junctions[seg.to_junction]
            if _orientation(fj.lat, fj.lon, tj.lat, tj.lon) == "NS":
                ns.append(sid)
            else:
                ew.append(sid)
        phases = [
            SignalPhase(id=f"{jid}-NS", movements=ns, green_s=30, yellow_s=3, red_s=2),
            SignalPhase(id=f"{jid}-EW", movements=ew, green_s=30, yellow_s=3, red_s=2),
        ]
        sig = Signal(id=f"SIG{sig_no}", junction_id=jid, phases=phases)
        net.signals[sig.id] = sig
        sig_no += 1


def build_osm_network(place: str, cache_dir=None) -> RoadNetwork:
    """Build a network from OpenStreetMap via osmnx (requires the ``geo`` extra).

    The downloaded graph is cached to ``cache_dir/<slug>.graphml`` and reused on
    subsequent runs so the network is built once and works offline thereafter.
    """
    import re
    from pathlib import Path

    import osmnx as ox  # local import: optional dependency

    g = None
    cache_file = None
    if cache_dir is not None:
        cache_dir = Path(cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^a-z0-9]+", "-", place.lower()).strip("-")
        cache_file = cache_dir / f"{slug}.graphml"
        if cache_file.exists():
            log.info("Loading cached OSM network from %s", cache_file)
            g = ox.load_graphml(cache_file)

    if g is None:
        log.info("Downloading OSM drive network for %r ...", place)
        g = ox.graph_from_place(place, network_type="drive", simplify=True)
        if cache_file is not None:
            ox.save_graphml(g, cache_file)
            log.info("Cached OSM network to %s", cache_file)

    g = ox.project_graph(g, to_crs="epsg:4326")

    net = RoadNetwork()
    for node, data in g.nodes(data=True):
        jid = f"J{node}"
        net.junctions[jid] = Junction(
            id=jid, name=jid, lat=float(data["y"]), lon=float(data["x"]), has_signal=False
        )
    seg_no = 0
    for u, v, data in g.edges(data=True):
        a, b = f"J{u}", f"J{v}"
        if a not in net.junctions or b not in net.junctions:
            continue
        length = float(
            data.get(
                "length",
                haversine_m(
                    net.junctions[a].lat,
                    net.junctions[a].lon,
                    net.junctions[b].lat,
                    net.junctions[b].lon,
                ),
            )
        )
        lanes = data.get("lanes", 2)
        try:
            lanes = int(lanes[0]) if isinstance(lanes, list) else int(lanes)
        except (TypeError, ValueError):
            lanes = 2
        speed = data.get("maxspeed", 50)
        try:
            speed = (
                float(speed[0].split()[0])
                if isinstance(speed, list)
                else float(str(speed).split()[0])
            )
        except (TypeError, ValueError):
            speed = 50.0
        net.segments[f"S{seg_no}"] = RoadSegment(
            id=f"S{seg_no}",
            name=(
                data.get("name", f"{a}->{b}")
                if not isinstance(data.get("name"), list)
                else data["name"][0]
            ),
            from_junction=a,
            to_junction=b,
            length_m=round(length, 1),
            lanes=max(1, lanes),
            speed_limit_kph=speed,
            one_way=bool(data.get("oneway", False)),
            geometry=[
                (net.junctions[a].lat, net.junctions[a].lon),
                (net.junctions[b].lat, net.junctions[b].lon),
            ],
        )
        seg_no += 1

    net.finalize()
    # Heuristic: signalise high-degree junctions
    for jid in net.junctions:
        deg = len(net.in_segments.get(jid, [])) + len(net.out_segments.get(jid, []))
        if deg >= 6:
            net.junctions[jid].has_signal = True
    _build_signals(net)
    log.info(
        "Built OSM network: %d junctions, %d segments, %d signals",
        len(net.junctions),
        len(net.segments),
        len(net.signals),
    )
    return net


def save_network(net: RoadNetwork, db) -> None:
    """Persist the network into the document store (collections: junction/road_segment/signal)."""
    db.clear("junction")
    db.clear("road_segment")
    db.clear("signal")
    db.upsert_many("junction", list(net.junctions.values()))
    db.upsert_many("road_segment", list(net.segments.values()))
    db.upsert_many("signal", list(net.signals.values()))


def load_network(db) -> RoadNetwork:
    """Rebuild a :class:`RoadNetwork` from the document store."""
    net = RoadNetwork()
    for jn in db.find("junction", Junction):
        net.junctions[jn.id] = jn
    for seg in db.find("road_segment", RoadSegment):
        net.segments[seg.id] = seg
    for sig in db.find("signal", Signal):
        net.signals[sig.id] = sig
    return net.finalize()


def build_network_from_settings(settings) -> RoadNetwork:
    if settings.sim_use_osm:
        try:
            return build_osm_network(settings.sim_place, cache_dir=settings.data_dir / "osm")
        except Exception as exc:
            log.warning("OSM build failed (%s); falling back to synthetic grid", exc)
    return build_grid_network(settings.sim_grid_size)
