"""Traffic-OS API gateway (FastAPI) — exposes every layer + live WebSocket."""

from __future__ import annotations

import dataclasses
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from traffic_os.api.runtime import AppState, get_state
from traffic_os.common.logging import get_logger
from traffic_os.common.timeutil import utcnow
from traffic_os.schemas import (
    CameraFrameMetric,
    CitizenReport,
    CityEvent,
    EmergencyType,
    EmergencyVehicle,
    EnforcementZone,
    Incident,
    InfraScenario,
)

log = get_logger("api")


def _ser(obj: Any) -> Any:
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    if isinstance(obj, list):
        return [_ser(o) for o in obj]
    return obj


def st() -> AppState:
    return get_state()


# --------------------------------------------------------------------------- #
# auth + RBAC
# --------------------------------------------------------------------------- #
_PUBLIC_PATHS = {"/healthz", "/docs", "/openapi.json", "/redoc", "/ws"}


def check_api_key(request: Request, x_api_key: str | None = Header(default=None)) -> None:
    """Enforce an API key when one is configured (no-op in dev when unset)."""
    key = st().settings.api_key
    if key and request.url.path not in _PUBLIC_PATHS and x_api_key != key:
        raise HTTPException(status_code=401, detail="invalid or missing API key")


def get_role(x_role: str = Header(default="operator")) -> str:
    return x_role.lower()


def require_commissioner(role: str = Depends(get_role)) -> str:
    if role != "commissioner":
        raise HTTPException(status_code=403, detail="commissioner role required")
    return role


def audit(action: str, detail: dict, role: str = "system") -> None:
    from traffic_os.schemas import AuditLog

    st().storage.db.upsert(
        "audit_log",
        AuditLog(
            id=f"AUD-{uuid.uuid4().hex[:8]}", ts=utcnow(), role=role, action=action, detail=detail
        ),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    state = get_state()
    await state.start()
    log.info("Traffic-OS API ready (mode=%s)", state.settings.mode)
    yield
    await state.stop()


app = FastAPI(
    title="Traffic-OS",
    version="0.1.0",
    description="National Traffic Intelligence Operating System",
    lifespan=lifespan,
    dependencies=[Depends(check_api_key)],
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# health + network
# --------------------------------------------------------------------------- #
@app.get("/healthz")
def healthz():
    s = st()
    return {
        "status": "ok",
        "mode": s.settings.mode,
        "tick": s.engine.tick,
        "segments": s.storage.db.count("road_segment"),
    }


@app.get("/network")
def network():
    net = st().intelligence.net
    return {
        "junctions": [_ser(j) for j in net.junctions.values()],
        "segments": [_ser(sg) for sg in net.segments.values()],
        "signals": [_ser(sig) for sig in net.signals.values()],
    }


@app.get("/live")
def live():
    msg = st().storage.bus.latest("live.tick")
    return msg or {"tick": st().engine.tick, "metrics": [], "vehicles": [], "incidents": []}


@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    sub: Any = st().storage.bus.subscribe("live.tick")
    try:
        async for msg in sub:
            await websocket.send_json(msg)
    except WebSocketDisconnect:
        pass
    finally:
        if hasattr(sub, "close"):
            sub.close()


# --------------------------------------------------------------------------- #
# intelligence
# --------------------------------------------------------------------------- #
@app.get("/intelligence/summary")
def intel_summary():
    return st().intelligence.summary()


@app.get("/intelligence/hotspots")
def hotspots(n: int = 20):
    return _ser(st().intelligence.hotspots(top_n=n))


@app.get("/intelligence/bottlenecks")
def bottlenecks(n: int = 10):
    return _ser(st().intelligence.bottlenecks(top_n=n))


@app.get("/intelligence/travel-time")
def travel_time(origin: str, destination: str):
    est = st().intelligence.travel_time(origin, destination)
    if est is None:
        raise HTTPException(404, "no route")
    return _ser(est)


@app.get("/collisions")
def collisions():
    return _ser(st().intelligence.collisions())


@app.get("/analytics/timeseries")
def analytics_timeseries(segment: str | None = None, hours: int = 24):
    from traffic_os.intelligence.analytics import network_timeseries

    return network_timeseries(st().storage.db, segment_id=segment, hours=hours)


@app.get("/analytics/profile")
def analytics_profile():
    from traffic_os.intelligence.analytics import daily_profile, hourly_profile

    db = st().storage.db
    return {"hourly": hourly_profile(db), "daily": daily_profile(db)}


# --------------------------------------------------------------------------- #
# violations / incidents
# --------------------------------------------------------------------------- #
@app.get("/violations")
def violations():
    from traffic_os.violations import ViolationService

    svc = ViolationService(st().storage)
    svc.detect()
    return {"recent": _ser(svc.recent(100)), "counts": svc.counts_by_type()}


@app.get("/incidents")
def incidents():
    rows = st().storage.db.find("incident", Incident, order_by_ts=True, desc=True, limit=200)
    return _ser(rows)


@app.get("/alerts")
def alerts():
    """Operational alerts: active incidents, high accident-risk, severe congestion."""
    s = st()
    _rank = {"critical": 0, "high": 1, "medium": 2}
    out: list[dict] = []

    for inc in s.storage.db.find("incident", Incident, where={"status": "active"}):
        out.append(
            {
                "severity": "critical" if inc.severity > 0.7 else "high",
                "kind": "incident",
                "message": f"{inc.type.value.title()} on {inc.description or inc.segment_id}",
                "lat": inc.lat,
                "lon": inc.lon,
                "ts": inc.ts.isoformat(),
            }
        )

    for h in s.intelligence.hotspots(top_n=8):
        if h.congestion >= 75:
            out.append(
                {
                    "severity": "high",
                    "kind": "congestion",
                    "message": f"Severe congestion at {h.name} ({h.congestion:.0f}/100)",
                    "lat": h.lat,
                    "lon": h.lon,
                    "ts": None,
                }
            )

    for r in s.cache.get("risk", []):
        if r.get("risk_pct", 0) >= 70:
            out.append(
                {
                    "severity": "medium",
                    "kind": "risk",
                    "message": f"Accident risk {r['risk_pct']:.0f}% on {r['segment_id']}",
                    "lat": None,
                    "lon": None,
                    "ts": r.get("ts"),
                }
            )

    from traffic_os.schemas import Track

    tracks = s.storage.db.find("track", Track, limit=2000)
    for hit in s.watchlist.scan_tracks(tracks):
        out.append(
            {
                "severity": "critical",
                "kind": "watchlist",
                "message": f"Watchlisted vehicle {hit['plate']} ({hit['reason']}) detected",
                "lat": hit["lat"],
                "lon": hit["lon"],
                "ts": None,
            }
        )

    out.sort(key=lambda a: _rank.get(a["severity"], 9))
    return out


# --------------------------------------------------------------------------- #
# prediction
# --------------------------------------------------------------------------- #
@app.get("/forecast")
def forecast(horizon: int = 60, segment: str | None = None):
    pred = st().prediction
    if segment:
        f = pred.forecast(segment, horizon)
        if f is None:
            raise HTTPException(404, "no forecast")
        return _ser(f)
    return _ser(pred.forecast_all(horizon))


@app.get("/risk")
def risk(n: int = 10):
    s = st()
    cached = s.cache.get("risk")
    top = cached[:n] if cached is not None else _ser(s.prediction.top_risk(n))
    return {"top": top, "backtests": s.prediction.backtests}


# --------------------------------------------------------------------------- #
# decision: signals / emergency / disaster
# --------------------------------------------------------------------------- #
@app.get("/signals")
def signals():
    from traffic_os.schemas import SignalState

    s = st()
    states = s.storage.db.find("signal_state", SignalState)
    plans = s.decision.signal_plan()
    return {"states": _ser(states), "recommended_plan": _ser(plans)}


@app.get("/signals/evaluate")
def signals_evaluate():
    return st().decision.evaluate_signal_strategy(ticks=150, warmup=45)


@app.post("/signals/apply")
def signals_apply(role: str = Depends(require_commissioner)):
    """Apply an adaptive max-pressure plan to the live simulation right now."""
    plan = st().apply_signal_plan()
    audit("signals.apply", {"applied": len(plan)}, role)
    return {"applied": len(plan), "plan": plan}


class AutoSignalRequest(BaseModel):
    enabled: bool


@app.get("/signals/rl/evaluate")
def signals_rl_evaluate(episodes: int = 100, role: str = Depends(require_commissioner)):
    """Optional: train a single-junction DQN and compare vs fixed/max-pressure."""
    from traffic_os.decision.rl import train_and_evaluate

    res = train_and_evaluate(episodes=episodes)
    return res.__dict__


@app.post("/signals/auto")
def signals_auto(req: AutoSignalRequest, role: str = Depends(require_commissioner)):
    s = st()
    s.adaptive = req.enabled
    if req.enabled:
        s.apply_signal_plan()
    audit("signals.auto", {"enabled": req.enabled}, role)
    return {"adaptive": s.adaptive}


class EmergencyRequest(BaseModel):
    type: EmergencyType = EmergencyType.AMBULANCE
    lat: float
    lon: float
    dest_lat: float
    dest_lon: float


@app.post("/emergency")
def emergency(req: EmergencyRequest):
    ev = EmergencyVehicle(
        id="EV-req",
        type=req.type,
        lat=req.lat,
        lon=req.lon,
        dest_lat=req.dest_lat,
        dest_lon=req.dest_lon,
    )
    corridor = st().decision.emergency_corridor(ev)
    if corridor is None:
        raise HTTPException(404, "no corridor")
    return _ser(corridor)


class RerouteRequest(BaseModel):
    origin: str
    destination: str
    blocked: list[str]


@app.post("/disaster/reroute")
def disaster_reroute(req: RerouteRequest):
    return _ser(st().decision.reroute(req.origin, req.destination, set(req.blocked)))


# --------------------------------------------------------------------------- #
# strategic planning: economics + infra what-if
# --------------------------------------------------------------------------- #
@app.get("/economics")
def economics():
    p = st().planning
    return {"summary": p.economic_summary(), "breakdown": _ser(p.economic_breakdown(10))}


@app.post("/planning/scenario")
def planning_scenario(scenario: InfraScenario, role: str = Depends(require_commissioner)):
    result = st().planning.run_scenario(scenario)
    audit("planning.scenario", {"scenario": scenario.name}, role)
    return _ser(result)


@app.get("/planning/scenarios")
def planning_scenarios(role: str = Depends(require_commissioner)):
    from traffic_os.planning.scenario_library import ScenarioLibrary

    lib = ScenarioLibrary(st().storage)
    return lib.compare(lib.results())


class RoiRequest(BaseModel):
    build_cost_inr: float


@app.post("/planning/roi")
def planning_roi(req: RoiRequest, role: str = Depends(require_commissioner)):
    from traffic_os.planning.scenario_library import ScenarioLibrary

    lib = ScenarioLibrary(st().storage)
    results = lib.results()
    if not results:
        raise HTTPException(404, "no scenario results — run a scenario first")
    return lib.roi(results[-1], req.build_cost_inr)


# --------------------------------------------------------------------------- #
# recommendations
# --------------------------------------------------------------------------- #
@app.get("/intelligence/anomalies")
def intel_anomalies():
    from traffic_os.intelligence.anomaly import detect_anomalies

    return detect_anomalies(st().storage)


@app.get("/intelligence/kpis")
def intel_kpis():
    from traffic_os.intelligence.kpi import evaluate_kpis

    return evaluate_kpis(st().storage)


@app.get("/replay")
def replay(ts: str):
    from datetime import datetime

    from traffic_os.intelligence.kpi import replay_snapshot

    try:
        when = datetime.fromisoformat(ts)
    except ValueError as err:
        raise HTTPException(400, "ts must be ISO format") from err
    return replay_snapshot(st().storage, when)


@app.get("/signals/abtest")
def signals_abtest(runs: int = 4, role: str = Depends(require_commissioner)):
    from traffic_os.decision.abtest import ab_test

    s = st()
    return ab_test(s.storage, s.intelligence.net, runs=runs, ticks=120)


@app.get("/recommendations")
def recommendations(n: int = 12):
    cached = st().cache.get("recommendations")
    if cached is not None:
        return cached[:n]
    return _ser(st().recommendation.generate(max_recs=n))


# --------------------------------------------------------------------------- #
# knowledge graph
# --------------------------------------------------------------------------- #
@app.get("/kg/why")
def kg_why(junction: str):
    s = st()
    s.kg.sync()
    return s.kg.explain_junction(junction)


@app.get("/kg/stats")
def kg_stats():
    return st().kg.stats()


# --------------------------------------------------------------------------- #
# copilot
# --------------------------------------------------------------------------- #
class CopilotRequest(BaseModel):
    question: str


@app.post("/copilot")
def copilot(req: CopilotRequest):
    return st().copilot.ask(req.question)


@app.get("/copilot/health")
def copilot_health():
    return st().copilot.health()


@app.get("/audit")
def audit_log(role: str = Depends(require_commissioner)):
    from traffic_os.schemas import AuditLog

    rows = st().storage.db.find("audit_log", AuditLog, order_by_ts=True, desc=True, limit=200)
    return _ser(rows)


# --------------------------------------------------------------------------- #
# commissioner aggregate
# --------------------------------------------------------------------------- #
@app.get("/commissioner")
def commissioner(role: str = Depends(require_commissioner)):
    s = st()
    cache = s.cache
    return {
        "network": s.intelligence.summary(),
        "economics": cache.get("economics") or s.planning.economic_summary(),
        "recommendations": cache.get("recommendations", []),
        "top_hotspots": _ser(s.intelligence.hotspots(top_n=5)),
        "accident_risk": cache.get("risk", []),
        "forecast_avg": cache.get("forecast_avg", 0.0),
        "warmed": "updated_at" in cache,
    }


# --------------------------------------------------------------------------- #
# events / citizen reports / weather
# --------------------------------------------------------------------------- #
@app.get("/national")
def national(role: str = Depends(require_commissioner)):
    s = st()
    if s.national is None:
        return {"status": "warming", "cities": []}
    return s.national.national_summary()


@app.get("/sustainability")
def sustainability():
    return st().sustainability.summary()


@app.get("/sustainability/aqi")
def sustainability_aqi():
    return st().sustainability.aqi()


@app.get("/sustainability/pricing")
def sustainability_pricing():
    return st().sustainability.pricing()


@app.get("/parking")
def parking():
    return st().parking.status()


@app.get("/parking/nearest")
def parking_nearest(lat: float, lon: float, need: int = 1):
    res = st().parking.nearest_free(lat, lon, need=need)
    if res is None:
        raise HTTPException(404, "no free parking found")
    return res


@app.get("/planner")
def planner(origin: str, destination: str, accessible: bool = False):
    return st().planner.plan(origin, destination, accessible=accessible)


@app.post("/dispatch")
def dispatch(role: str = Depends(require_commissioner)):
    from traffic_os.decision.dispatch import DispatchService

    s = st()
    active = s.storage.db.find("incident", Incident, where={"status": "active"})
    results = DispatchService(s.storage).dispatch(active, s.intelligence.net)
    audit("dispatch", {"incidents": len(active)}, role)
    return [r.__dict__ for r in results]


class EvacuationRequest(BaseModel):
    zone_junctions: list[str]
    exit_junctions: list[str] | None = None
    population: int = 10000


@app.post("/evacuation")
def evacuation(req: EvacuationRequest, role: str = Depends(require_commissioner)):
    from traffic_os.decision.evacuation import nearest_exits, plan_evacuation

    net = st().intelligence.net
    exits = req.exit_junctions
    if not exits and req.zone_junctions:
        c = net.junctions[req.zone_junctions[0]]
        exits = nearest_exits(net, (c.lat, c.lon), k=3)
    return plan_evacuation(net, req.zone_junctions, exits or [], population=req.population)


class ConvoyRequest(BaseModel):
    lat: float
    lon: float
    dest_lat: float
    dest_lon: float


@app.post("/convoy")
def convoy(req: ConvoyRequest, role: str = Depends(require_commissioner)):
    from traffic_os.decision.convoy import plan_convoy

    s = st()
    return plan_convoy(s.intelligence.net, s.storage, req.lat, req.lon, req.dest_lat, req.dest_lon)


@app.get("/transit")
def transit():
    return st().transit.status()


@app.get("/freight")
def freight(n: int = 8):
    return st().freight.plan(n=n)


@app.get("/integrations/status")
def integrations_status():
    from traffic_os.integrations import get_weather_provider, provider_status

    s = st()
    return {
        "providers": provider_status(),
        "weather_now": get_weather_provider(s.storage).current(),
    }


@app.get("/events")
def events():
    return _ser(st().storage.db.find("city_event", CityEvent, limit=200))


@app.get("/reports")
def reports():
    return _ser(
        st().storage.db.find(
            "citizen_report", CitizenReport, order_by_ts=True, desc=True, limit=200
        )
    )


@app.post("/reports")
def create_report(report: CitizenReport):
    st().storage.db.upsert("citizen_report", report)
    return {"status": "received", "id": report.id}


# --------------------------------------------------------------------------- #
# edge AI ingest (Camera -> Edge node -> Command Center)
# --------------------------------------------------------------------------- #
@app.post("/ingest/camera")
def ingest_camera(metric: CameraFrameMetric):
    st().storage.db.upsert("camera_metric", metric)
    return {"status": "ok", "source_id": metric.source_id, "frame": metric.frame}


@app.get("/cameras")
def cameras():
    rows = st().storage.db.find(
        "camera_metric", CameraFrameMetric, order_by_ts=True, desc=True, limit=200
    )
    return _ser(rows)


class CameraRegisterRequest(BaseModel):
    id: str
    name: str
    source: str
    lat: float | None = None
    lon: float | None = None
    junction_id: str | None = None


@app.get("/cameras/registry")
def cameras_registry():
    from traffic_os.schemas import Camera

    return _ser(st().storage.db.find("camera", Camera, limit=500))


@app.post("/cameras/register")
def cameras_register(camera: CameraRegisterRequest, role: str = Depends(require_commissioner)):
    from traffic_os.schemas import Camera

    cam = Camera(**camera.model_dump())
    st().cameras.register(cam)
    audit("camera.register", {"id": cam.id, "source": cam.source}, role)
    return _ser(cam)


@app.post("/cameras/{camera_id}/ingest")
def cameras_ingest(camera_id: str, max_frames: int = 20, role: str = Depends(require_commissioner)):
    try:
        return st().cameras.ingest_once(camera_id, max_frames=max_frames)
    except KeyError as err:
        raise HTTPException(404, "camera not found") from err


@app.post("/enforcement/challans/issue")
def challans_issue(role: str = Depends(require_commissioner)):
    from traffic_os.violations import ViolationService

    s = st()
    violations = ViolationService(s.storage).detect()
    challans = s.challans.issue_for_violations(violations)
    audit("challan.issue", {"count": len(challans)}, role)
    return {"issued": len(challans), "challans": _ser(challans)}


@app.get("/enforcement/challans")
def challans_list():
    return _ser(st().challans.recent(100))


@app.get("/enforcement/challans/summary")
def challans_summary():
    return st().challans.summary()


@app.get("/enforcement/challans/{challan_id}/verify")
def challan_verify(challan_id: str):
    return {"challan_id": challan_id, "evidence_valid": st().challans.verify_evidence(challan_id)}


@app.post("/enforcement/challans/{challan_id}/status")
def challan_status(challan_id: str, status: str, role: str = Depends(require_commissioner)):
    ch = st().challans.set_status(challan_id, status, actor=role)
    if ch is None:
        raise HTTPException(404, "challan not found")
    return _ser(ch)


class WatchlistRequest(BaseModel):
    plate: str
    reason: str = "stolen"


@app.get("/enforcement/watchlist")
def watchlist_list():
    return _ser(st().watchlist.entries())


@app.post("/enforcement/watchlist")
def watchlist_add(req: WatchlistRequest, role: str = Depends(require_commissioner)):
    entry = st().watchlist.add(req.plate, req.reason)
    audit("watchlist.add", {"plate": req.plate, "reason": req.reason}, role)
    return _ser(entry)


@app.get("/enforcement/watchlist/scan")
def watchlist_scan():
    from traffic_os.schemas import Track

    s = st()
    tracks = s.storage.db.find("track", Track, limit=2000)
    return st().watchlist.scan_tracks(tracks)


@app.get("/enforcement/zones")
def zones_list():
    from traffic_os.schemas import EnforcementZone

    return _ser(st().storage.db.find("enforcement_zone", EnforcementZone, limit=1000))


@app.post("/enforcement/zones")
def zones_add(zone: EnforcementZone, role: str = Depends(require_commissioner)):
    st().zones.add_zone(zone)
    audit("zone.add", {"id": zone.id, "kind": zone.kind}, role)
    return _ser(zone)


@app.post("/enforcement/zones/enforce")
def zones_enforce(role: str = Depends(require_commissioner)):
    from traffic_os.violations import ViolationService

    s = st()
    violations = ViolationService(s.storage).detect()
    issued = s.zones.enforce(violations)
    audit("zone.enforce", {"issued": len(issued)}, role)
    return {"issued": len(issued), "challans": _ser(issued)}


@app.get("/safety/near-miss")
def safety_near_miss():
    from traffic_os.safety import detect_near_misses
    from traffic_os.schemas import Track

    tracks = st().storage.db.find("track", Track, limit=2000)
    return detect_near_misses(tracks)


@app.get("/safety/driver-scores")
def safety_driver_scores(n: int = 20):
    from traffic_os.safety import driver_scores
    from traffic_os.schemas import Track

    s = st()
    tracks = s.storage.db.find("track", Track, limit=2000)
    return driver_scores(tracks, s.intelligence.net)[:n]


@app.get("/road-health")
def road_health():
    from traffic_os.schemas import RoadHealthIssue

    rows = st().storage.db.find(
        "road_health", RoadHealthIssue, order_by_ts=True, desc=True, limit=500
    )
    return _ser(rows)
