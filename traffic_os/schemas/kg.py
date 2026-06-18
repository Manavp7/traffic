"""Knowledge-graph node/edge value types (backend-agnostic)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class KGNode(BaseModel):
    type: str  # Road, Junction, Signal, Vehicle, Violation, Accident, Weather, Event, Hotspot
    id: str
    props: dict[str, Any] = Field(default_factory=dict)


class KGEdge(BaseModel):
    type: str  # CONNECTS, CONTROLS, OCCURRED_ON, NEAR, DURING, CAUSED_BY, AFFECTS
    src_type: str
    src_id: str
    dst_type: str
    dst_id: str
    props: dict[str, Any] = Field(default_factory=dict)


class CausalFactor(BaseModel):
    """A single ranked cause returned by KG causal reasoning."""

    kind: str  # e.g. "road_closed", "signal_fault", "rainfall", "nearby_event", "bottleneck"
    description: str
    weight: float = 0.0  # contribution score
    node_type: str | None = None
    node_id: str | None = None
