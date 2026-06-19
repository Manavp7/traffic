"""Enumerations shared across Traffic-OS layers."""

from __future__ import annotations

from enum import Enum


class VehicleClass(str, Enum):
    CAR = "car"
    BUS = "bus"
    TRUCK = "truck"
    BIKE = "bike"  # motorcycle / two-wheeler
    AUTO = "auto"  # auto-rickshaw / three-wheeler
    PEDESTRIAN = "pedestrian"
    ANIMAL = "animal"

    @property
    def pcu(self) -> float:
        """Passenger Car Units — used for capacity/density normalisation."""
        return {
            VehicleClass.CAR: 1.0,
            VehicleClass.BUS: 3.0,
            VehicleClass.TRUCK: 3.0,
            VehicleClass.BIKE: 0.5,
            VehicleClass.AUTO: 0.75,
            VehicleClass.PEDESTRIAN: 0.0,
            VehicleClass.ANIMAL: 0.0,
        }[self]


class SignalMode(str, Enum):
    FIXED = "fixed"
    ADAPTIVE = "adaptive"
    PREEMPT = "preempt"  # emergency green corridor


class IncidentType(str, Enum):
    ACCIDENT = "accident"
    BREAKDOWN = "breakdown"
    HAZARD = "hazard"
    FLOOD = "flood"
    FIRE = "fire"
    ROADWORK = "roadwork"


class IncidentStatus(str, Enum):
    ACTIVE = "active"
    CLEARING = "clearing"
    RESOLVED = "resolved"


class CollisionKind(str, Enum):
    COLLISION = "collision"
    SUDDEN_STOP = "sudden_stop"
    ABNORMAL_MOTION = "abnormal_motion"


class ViolationType(str, Enum):
    WRONG_SIDE = "wrong_side"
    RED_LIGHT = "red_light"
    SPEEDING = "speeding"
    ILLEGAL_PARKING = "illegal_parking"
    # roadmap (vision-model based) — interfaces only:
    NO_HELMET = "no_helmet"
    NO_SEATBELT = "no_seatbelt"
    MOBILE_USE = "mobile_use"
    TRIPLE_RIDING = "triple_riding"
    ZEBRA_VIOLATION = "zebra_violation"


class EmergencyType(str, Enum):
    AMBULANCE = "ambulance"
    FIRE = "fire"
    POLICE = "police"
    DISASTER = "disaster"


class EventType(str, Enum):
    MATCH = "match"
    RALLY = "rally"
    CONCERT = "concert"
    FESTIVAL = "festival"


class ReportType(str, Enum):
    ACCIDENT = "accident"
    POTHOLE = "pothole"
    BLOCKAGE = "blockage"


class WeatherKind(str, Enum):
    CLEAR = "clear"
    RAIN = "rain"
    HEAVY_RAIN = "heavy_rain"
    FOG = "fog"
    FLOOD = "flood"


class ActionType(str, Enum):
    SIGNAL_RETIME = "signal_retime"
    DIVERT = "divert"
    OPEN_CORRIDOR = "open_corridor"
    CLOSE_ROAD = "close_road"
    ALERT = "alert"


class RoadHealthKind(str, Enum):
    POTHOLE = "pothole"
    CRACK = "crack"
    WATERLOGGING = "waterlogging"


class ScenarioOp(str, Enum):
    ADD_FLYOVER = "add_flyover"
    WIDEN_LANE = "widen_lane"
    CLOSE_ROAD = "close_road"
    RETIME_SIGNAL = "retime_signal"
