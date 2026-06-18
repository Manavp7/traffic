"""PlanningService — Strategic Planning layer (digital twin + economics + what-if)."""

from __future__ import annotations

from traffic_os.common.config import Settings
from traffic_os.planning.economics import EconomicLossEngine, format_inr
from traffic_os.planning.infra_sim import run_scenario
from traffic_os.schemas import EconomicImpact, InfraScenario, ScenarioResult, SegmentMetric
from traffic_os.simulation.network import RoadNetwork, load_network


class PlanningService:
    def __init__(self, storage) -> None:
        self.storage = storage
        self.settings: Settings = getattr(storage, "settings", None) or Settings(mode="dev")
        self.econ = EconomicLossEngine.from_settings(self.settings)
        self._net: RoadNetwork | None = None

    @property
    def net(self) -> RoadNetwork:
        if self._net is None or not self._net.segments:
            self._net = load_network(self.storage.db)
        return self._net

    def _latest_metrics(self) -> dict[str, SegmentMetric]:
        from traffic_os.intelligence.current import current_metrics

        return current_metrics(self.storage.db)

    # -- economics -------------------------------------------------------- #
    def economic_impact(self, *, window_h: float = 24.0, persist: bool = True) -> EconomicImpact:
        impact = self.econ.city_impact(self.net, self._latest_metrics(), window_h=window_h)
        if persist:
            self.storage.db.upsert("economic_impact", impact)
        return impact

    def economic_breakdown(self, top_n: int = 10) -> list[EconomicImpact]:
        return self.econ.segment_impacts(self.net, self._latest_metrics(), top_n=top_n)

    def economic_summary(self) -> dict:
        impact = self.economic_impact(persist=False)
        return {
            "cost_inr": impact.cost_inr,
            "cost_human": format_inr(impact.cost_inr),
            "delay_veh_h": impact.delay_veh_h,
            "fuel_litres": impact.fuel_litres,
            "co2_kg": impact.co2_kg,
            "window_h": impact.window_h,
        }

    # -- infrastructure what-if ------------------------------------------ #
    def run_scenario(
        self, scenario: InfraScenario, *, persist: bool = True, ticks: int = 140
    ) -> ScenarioResult:
        result = run_scenario(self.net, scenario, self.settings, ticks=ticks)
        if persist:
            self.storage.db.upsert("infra_scenario", scenario)
            self.storage.db.upsert("scenario_result", result)
        return result
