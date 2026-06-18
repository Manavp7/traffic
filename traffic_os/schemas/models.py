"""Pydantic domain models — the shared contract across all Traffic-OS layers."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from traffic_os.common.timeutil import utcnow
from traffic_os.schemas.enums import (
    ActionType,
    CollisionKind,
    EmergencyType,
    EventType,
    IncidentStatus,
    IncidentType,
    ReportType,
    RoadHealthKind,
    ScenarioOp,
    SignalMode,
    ViolationType,
    WeatherKind,
)


# --------------------------------------------------------------------------- #
# Geometry / network
# --------------------------------------------------------------------------- #
class Junction(BaseModel):
    id: str
    name: str
    lat: float
    lon: float
    has_signal: bool = False


class RoadSegment(BaseModel):
    id: str
    name: str
    from_junction: str
    to_junction: str
    length_m: float
    lanes: int = 2
    speed_limit_kph: float = 50.0
    one_way: bool = True
    # polyline as [[lat, lon], ...] for map rendering
    geometry: list[tuple[float, float]] = Field(default_factory=list)

    @property
    def capacity_pcu_per_h(self) -> float:
        """Saturation flow ~1800 PCU/lane/h."""
        return 1800.0 * self.lanes


# --------------------------------------------------------------------------- #
# Signals
# --------------------------------------------------------------------------- #
class SignalPhase(BaseModel):
    id: str
    # segment ids that get green during this phase
    movements: list[str] = Field(default_factory=list)
    green_s: int = 30
    yellow_s: int = 3
    red_s: int = 2


class Signal(BaseModel):
    id: str
    junction_id: str
    phases: list[SignalPhase] = Field(default_factory=list)
    mode: SignalMode = SignalMode.FIXED


class SignalState(BaseModel):
    signal_id: str
    active_phase: str
    since: datetime = Field(default_factory=utcnow)
    mode: SignalMode = SignalMode.FIXED
    remaining_s: float = 0.0


# --------------------------------------------------------------------------- #
# Detections / tracks (perception output, normalised)
# --------------------------------------------------------------------------- #
class Detection(BaseModel):
    id: str
    source_id: str  # camera id or "sim"
    ts: datetime
    cls: str
    bbox: tuple[float, float, float, float] | None = None  # x1,y1,x2,y2 (camera)
    conf: float = 1.0
    lat: float | None = None
    lon: float | None = None


class TrackPoint(BaseModel):
    ts: datetime
    # geo coords for GPS/sim sources; may be absent for un-georegistered cameras
    lat: float | None = None
    lon: float | None = None
    # pixel coords for camera sources
    px: float | None = None
    py: float | None = None
    speed_kph: float = 0.0
    heading_deg: float = 0.0


class AuditLog(BaseModel):
    id: str
    ts: datetime
    role: str
    action: str
    detail: dict[str, Any] = Field(default_factory=dict)


class BusRoute(BaseModel):
    id: str
    name: str
    segments: list[str] = Field(default_factory=list)
    stops: list[str] = Field(default_factory=list)  # junction ids


class FreightTrip(BaseModel):
    id: str
    origin: str
    destination: str
    segments: list[str] = Field(default_factory=list)
    distance_m: float = 0.0
    eta_s: float = 0.0
    free_flow_s: float = 0.0
    fuel_litres: float = 0.0
    cost_inr: float = 0.0


class Camera(BaseModel):
    id: str
    name: str
    source: str  # RTSP URL or local video file path
    lat: float | None = None
    lon: float | None = None
    junction_id: str | None = None
    status: str = "registered"  # registered | online | offline


class RoadHealthIssue(BaseModel):
    id: str
    source_id: str
    ts: datetime
    kind: RoadHealthKind
    bbox: tuple[float, float, float, float] | None = None
    lat: float | None = None
    lon: float | None = None
    confidence: float = 0.5
    severity: float = 0.5  # 0..1
    method: str = "cv-heuristic"  # or "model:<name>"


class CameraFrameMetric(BaseModel):
    id: str
    source_id: str
    ts: datetime
    frame: int
    counts: dict[str, int] = Field(default_factory=dict)
    total_vehicles: int = 0
    occupancy_pct: float = 0.0
    queue_len_m: float = 0.0
    unique_tracks: int = 0


class Track(BaseModel):
    track_id: str
    source_id: str
    cls: str
    segment_id: str | None = None
    points: list[TrackPoint] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Time-series metrics
# --------------------------------------------------------------------------- #
class SegmentMetric(BaseModel):
    segment_id: str
    ts: datetime
    vehicle_count: int = 0
    density_pcu_per_km: float = 0.0
    speed_kph: float = 0.0
    occupancy_pct: float = 0.0
    queue_len_m: float = 0.0
    congestion_score: float = 0.0  # 0..100
    travel_time_s: float = 0.0


# --------------------------------------------------------------------------- #
# Incidents / collisions / violations
# --------------------------------------------------------------------------- #
class Incident(BaseModel):
    id: str
    ts: datetime
    type: IncidentType
    lat: float
    lon: float
    segment_id: str | None = None
    severity: float = 0.5  # 0..1
    segments_blocked: list[str] = Field(default_factory=list)
    status: IncidentStatus = IncidentStatus.ACTIVE
    description: str = ""


class CollisionEvent(BaseModel):
    id: str
    ts: datetime
    lat: float
    lon: float
    segment_id: str | None = None
    track_ids: list[str] = Field(default_factory=list)
    kind: CollisionKind = CollisionKind.COLLISION
    confidence: float = 0.5


class Violation(BaseModel):
    id: str
    ts: datetime
    type: ViolationType
    lat: float
    lon: float
    segment_id: str | None = None
    vehicle_track_id: str | None = None
    evidence_ref: str | None = None
    status: str = "open"
    detail: str = ""


# --------------------------------------------------------------------------- #
# Emergency
# --------------------------------------------------------------------------- #
class EmergencyVehicle(BaseModel):
    id: str
    type: EmergencyType
    lat: float
    lon: float
    dest_lat: float
    dest_lon: float


class GreenCorridor(BaseModel):
    id: str
    vehicle_id: str
    type: EmergencyType
    route_segments: list[str] = Field(default_factory=list)
    signals_preempted: list[str] = Field(default_factory=list)
    eta_s: float = 0.0
    baseline_eta_s: float = 0.0
    distance_m: float = 0.0


# --------------------------------------------------------------------------- #
# Weather / events / citizen reports
# --------------------------------------------------------------------------- #
class Weather(BaseModel):
    ts: datetime
    kind: WeatherKind = WeatherKind.CLEAR
    rain_mm: float = 0.0
    visibility_m: float = 10000.0
    # multiplier applied to free-flow capacity (1.0 = no impact)
    capacity_factor: float = 1.0


class CityEvent(BaseModel):
    id: str
    type: EventType
    name: str
    venue_lat: float
    venue_lon: float
    start: datetime
    end: datetime
    expected_attendance: int = 0
    nearest_junction: str | None = None


class CitizenReport(BaseModel):
    id: str
    ts: datetime
    type: ReportType
    lat: float
    lon: float
    photo_ref: str | None = None
    status: str = "new"
    note: str = ""


# --------------------------------------------------------------------------- #
# Prediction
# --------------------------------------------------------------------------- #
class Forecast(BaseModel):
    segment_id: str
    horizon_min: int
    ts_made: datetime
    ts_target: datetime
    predicted_congestion: float
    ci_low: float
    ci_high: float
    model: str = "xgboost"


class AccidentRisk(BaseModel):
    segment_id: str
    ts: datetime
    risk_pct: float  # 0..100
    drivers: dict[str, float] = Field(default_factory=dict)  # rain/speeding/density/history


# --------------------------------------------------------------------------- #
# Strategic planning / economics
# --------------------------------------------------------------------------- #
class EconomicImpact(BaseModel):
    scope: str  # "segment" | "junction" | "city"
    scope_id: str
    ts: datetime
    window_h: float = 24.0
    delay_veh_h: float = 0.0
    fuel_litres: float = 0.0
    co2_kg: float = 0.0
    time_loss_h: float = 0.0
    cost_inr: float = 0.0


class ScenarioEdit(BaseModel):
    op: ScenarioOp
    target: str  # segment id or junction id
    params: dict[str, Any] = Field(default_factory=dict)


class InfraScenario(BaseModel):
    id: str
    name: str
    edits: list[ScenarioEdit] = Field(default_factory=list)


class ScenarioResult(BaseModel):
    scenario_id: str
    baseline_kpis: dict[str, float]
    scenario_kpis: dict[str, float]
    deltas: dict[str, float]
    summary: str = ""


# --------------------------------------------------------------------------- #
# Recommendation (the differentiator: actions, not status)
# --------------------------------------------------------------------------- #
class Recommendation(BaseModel):
    id: str
    ts: datetime
    trigger: str
    action_type: ActionType
    target: str
    params: dict[str, Any] = Field(default_factory=dict)
    expected_effect: str = ""
    impact_score: float = 0.0  # for ranking
    confidence: float = 0.5
    rationale: str = ""
    status: str = "proposed"
