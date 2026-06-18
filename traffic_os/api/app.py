"""Traffic-OS API gateway (FastAPI) — exposes every layer + live WebSocket."""

from __future__ import annotations

import dataclasses
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from traffic_os.api.runtime import AppState, get_state
from traffic_os.common.logging import get_logger
from traffic_os.schemas import (
    CameraFrameMetric,
    CitizenReport,
    CityEvent,
    EmergencyType,
    EmergencyVehicle,
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
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def st() -> AppState:
    return get_state()


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
def signals_apply():
    """Apply an adaptive max-pressure plan to the live simulation right now."""
    plan = st().apply_signal_plan()
    return {"applied": len(plan), "plan": plan}


class AutoSignalRequest(BaseModel):
    enabled: bool


@app.post("/signals/auto")
def signals_auto(req: AutoSignalRequest):
    s = st()
    s.adaptive = req.enabled
    if req.enabled:
        s.apply_signal_plan()
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
def planning_scenario(scenario: InfraScenario):
    return _ser(st().planning.run_scenario(scenario))


# --------------------------------------------------------------------------- #
# recommendations
# --------------------------------------------------------------------------- #
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


# --------------------------------------------------------------------------- #
# commissioner aggregate
# --------------------------------------------------------------------------- #
@app.get("/commissioner")
def commissioner():
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


@app.get("/road-health")
def road_health():
    from traffic_os.schemas import RoadHealthIssue

    rows = st().storage.db.find(
        "road_health", RoadHealthIssue, order_by_ts=True, desc=True, limit=500
    )
    return _ser(rows)
