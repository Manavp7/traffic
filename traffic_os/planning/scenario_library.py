"""Scenario library — persist/compare infrastructure what-if results + ROI/payback."""

from __future__ import annotations

from traffic_os.schemas import InfraScenario, ScenarioResult


class ScenarioLibrary:
    def __init__(self, storage) -> None:
        self.storage = storage

    def save(self, scenario: InfraScenario, result: ScenarioResult) -> None:
        self.storage.db.upsert("infra_scenario", scenario)
        # ScenarioResult has no id -> the store auto-assigns one, building a run history
        self.storage.db.upsert("scenario_result", result)

    def results(self) -> list[ScenarioResult]:
        return self.storage.db.find("scenario_result", ScenarioResult, limit=500)

    def roi(self, result: ScenarioResult, build_cost_inr: float) -> dict:
        """Payback from daily economic-cost savings (negative cost delta = saving)."""
        daily_saving = -result.deltas.get("daily_cost_inr", 0.0)
        payback_days = (build_cost_inr / daily_saving) if daily_saving > 0 else None
        return {
            "scenario_id": result.scenario_id,
            "build_cost_inr": build_cost_inr,
            "daily_saving_inr": round(daily_saving, 1),
            "annual_saving_inr": round(daily_saving * 365, 1),
            "payback_days": round(payback_days, 0) if payback_days else None,
            "payback_years": round(payback_days / 365, 2) if payback_days else None,
            "worthwhile": bool(payback_days and payback_days < 365 * 10),
        }

    def compare(self, results: list[ScenarioResult]) -> list[dict]:
        rows = []
        for r in results:
            rows.append(
                {
                    "scenario_id": r.scenario_id,
                    "summary": r.summary,
                    "congestion_delta": r.deltas.get("avg_congestion"),
                    "throughput_delta": r.deltas.get("throughput"),
                    "daily_cost_delta_inr": r.deltas.get("daily_cost_inr"),
                }
            )
        rows.sort(key=lambda x: x.get("daily_cost_delta_inr") or 0.0)
        return rows
