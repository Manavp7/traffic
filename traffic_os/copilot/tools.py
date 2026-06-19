"""Typed Copilot tools — data-grounded functions over the Traffic-OS services.

Each tool returns a structured dict plus a natural-language ``answer``. The same
tools back both the LLM (function-calling) and the deterministic fallback router,
so answers are always grounded in real system data.
"""

from __future__ import annotations

import contextlib
import re
from datetime import timedelta

from traffic_os.common.timeutil import utcnow
from traffic_os.intelligence.congestion import level
from traffic_os.schemas import Incident, IncidentType

JUNCTION_RE = re.compile(r"\bJ\d+_\d+\b")
SEGMENT_RE = re.compile(r"\bS\d+\b")


class CopilotTools:
    def __init__(
        self, storage, intelligence, kg=None, prediction=None, planning=None, recommendation=None
    ):
        self.storage = storage
        self.intel = intelligence
        self.kg = kg
        self.prediction = prediction
        self.planning = planning
        self.recommendation = recommendation

    # -- helpers ---------------------------------------------------------- #
    def _worst_junction_id(self) -> str | None:
        spots = self.intel.hotspots(top_n=1)
        return spots[0].junction_id if spots else None

    # -- tools ------------------------------------------------------------ #
    def why_congested(self, junction: str | None = None) -> dict:
        junction = junction or self._worst_junction_id()
        if junction is None:
            return {"answer": "No live traffic data available yet.", "data": {}}
        if self.kg is not None:
            with contextlib.suppress(Exception):
                self.kg.sync()
            expl = self.kg.explain_junction(junction)
            causes = expl.get("causes", [])
            if causes:
                lines = "; ".join(c["description"] for c in causes[:3])
                ans = f"{expl.get('name', junction)} is congested because: {lines}."
            else:
                ans = f"{expl.get('name', junction)} has no standout cause — it's general peak demand."
            return {"answer": ans, "data": expl}
        return {"answer": f"Junction {junction} congestion details unavailable.", "data": {}}

    def worst_junction(self) -> dict:
        spots = self.intel.hotspots(top_n=3)
        bns = self.intel.bottlenecks(top_n=1)
        if not spots:
            return {"answer": "No congestion data yet.", "data": {}}
        top = spots[0]
        ans = (
            f"The worst junction is {top.name} ({top.congestion:.0f}/100, {level(top.congestion)})."
        )
        if bns:
            ans += f" Root bottleneck: {bns[0].name} — {bns[0].explanation}"
        return {
            "answer": ans,
            "data": {
                "hotspots": [vars(s) for s in spots],
                "bottleneck": vars(bns[0]) if bns else None,
            },
        }

    def top_hotspots(self, n: int = 5) -> dict:
        spots = self.intel.hotspots(top_n=n)
        if not spots:
            return {"answer": "No congestion data yet.", "data": {}}
        lines = ", ".join(f"{s.name} ({s.congestion:.0f})" for s in spots)
        return {
            "answer": f"Top {len(spots)} congestion points: {lines}.",
            "data": {"hotspots": [vars(s) for s in spots]},
        }

    def accidents_count(self, period: str = "month") -> dict:
        days = {"today": 1, "day": 1, "week": 7, "month": 30, "year": 365}.get(period, 30)
        cutoff = utcnow() - timedelta(days=days)
        incidents = self.storage.db.find("incident", Incident, limit=10000)
        accidents = [
            i
            for i in incidents
            if i.type == IncidentType.ACCIDENT and i.ts.replace(tzinfo=cutoff.tzinfo) >= cutoff
        ]
        return {
            "answer": f"There have been {len(accidents)} accidents in the last {period}.",
            "data": {"count": len(accidents), "period": period},
        }

    def forecast(self, horizon_min: int = 60) -> dict:
        if self.prediction is None:
            return {"answer": "Forecasting model is not loaded.", "data": {}}
        try:
            forecasts = self.prediction.forecast_all(horizon_min, persist=False)
        except Exception as exc:
            return {"answer": f"Forecast unavailable: {exc}", "data": {}}
        if not forecasts:
            return {"answer": "No forecast available.", "data": {}}
        avg = sum(f.predicted_congestion for f in forecasts) / len(forecasts)
        severe = sum(1 for f in forecasts if f.predicted_congestion >= 75)
        worst = max(forecasts, key=lambda f: f.predicted_congestion)
        ans = (
            f"In {horizon_min} min, average congestion is forecast at {avg:.0f}/100 "
            f"with {severe} severe segment(s); worst is {worst.segment_id} "
            f"({worst.predicted_congestion:.0f})."
        )
        return {
            "answer": ans,
            "data": {"avg": round(avg, 1), "severe": severe, "worst_segment": worst.segment_id},
        }

    def accident_risk(self) -> dict:
        if self.prediction is None:
            return {"answer": "Accident-risk model is not loaded.", "data": {}}
        top = self.prediction.top_risk(5)
        if not top:
            return {"answer": "No accident-risk data.", "data": {}}
        lines = ", ".join(f"{r.segment_id} ({r.risk_pct:.0f}%)" for r in top)
        return {
            "answer": f"Highest accident-risk roads: {lines}.",
            "data": {"top": [r.model_dump() for r in top]},
        }

    def economic_cost(self) -> dict:
        if self.planning is None:
            return {"answer": "Economic engine is not loaded.", "data": {}}
        summ = self.planning.economic_summary()
        ans = (
            f"Today's estimated congestion cost is {summ['cost_human']} "
            f"({summ['delay_veh_h']:.0f} vehicle-hours lost, "
            f"{summ['fuel_litres']:.0f} L fuel, {summ['co2_kg']:.0f} kg CO2)."
        )
        return {"answer": ans, "data": summ}

    def recommend_actions(self, junction: str | None = None) -> dict:
        if self.recommendation is None:
            return {"answer": "Recommendation engine is not loaded.", "data": {}}
        recs = self.recommendation.generate(max_recs=5)
        if junction:
            recs = [r for r in recs if r.params.get("junction") == junction] or recs
        if not recs:
            return {"answer": "No actions needed right now — traffic is flowing.", "data": {}}
        lines = " ".join(
            f"({i + 1}) {r.expected_effect} [{r.action_type.value} @ {r.target}]."
            for i, r in enumerate(recs[:3])
        )
        return {
            "answer": f"Recommended actions: {lines}",
            "data": {"recommendations": [r.model_dump() for r in recs[:5]]},
        }

    def network_summary(self) -> dict:
        s = self.intel.summary()
        cost = self.planning.economic_summary()["cost_human"] if self.planning else "n/a"
        ans = (
            f"Network average congestion is {s.get('avg_congestion', 0):.0f}/100 "
            f"({s.get('level', 'n/a')}), {s.get('severe', 0)} severe segments. "
            f"Estimated daily cost: {cost}."
        )
        return {"answer": ans, "data": s}


def extract_junction(text: str) -> str | None:
    m = JUNCTION_RE.search(text)
    return m.group(0) if m else None


def extract_period(text: str) -> str:
    for p in ("today", "week", "month", "year"):
        if p in text:
            return p
    return "month"
