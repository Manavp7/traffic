"""Multi-city / national rollout.

Each city is an isolated context (its own in-memory storage + simulation engine +
intelligence/economics services). The ``NationalService`` warms several cities and
aggregates their KPIs into a national rollup — demonstrating tenant isolation and a
country-level command view on top of the same Traffic-OS stack.
"""

from __future__ import annotations

from dataclasses import dataclass

from traffic_os.common.config import Settings
from traffic_os.common.logging import get_logger
from traffic_os.intelligence import IntelligenceService
from traffic_os.planning import PlanningService
from traffic_os.planning.economics import format_inr
from traffic_os.simulation import SimulationEngine, build_grid_network, save_network
from traffic_os.storage import memory_storage

log = get_logger("national")

# (city_id, display name, grid size, demand scale)
DEFAULT_CITIES = [
    ("blr", "Bengaluru", 6, 80.0),
    ("del", "Delhi", 5, 95.0),
    ("mum", "Mumbai", 5, 90.0),
]


@dataclass
class CityContext:
    id: str
    name: str
    storage: object
    engine: SimulationEngine
    intelligence: IntelligenceService
    planning: PlanningService


class NationalService:
    def __init__(self, specs=DEFAULT_CITIES, *, warm_ticks: int = 25) -> None:
        self.cities: list[CityContext] = []
        for cid, name, grid, demand in specs:
            st = memory_storage()
            st.settings.sim_demand_scale = demand
            net = build_grid_network(grid)
            save_network(net, st.db)
            eng = SimulationEngine(net, Settings(mode="dev", sim_demand_scale=demand))
            for _ in range(warm_ticks):
                eng.persist_live(st, eng.step_once())
            self.cities.append(
                CityContext(cid, name, st, eng, IntelligenceService(st), PlanningService(st))
            )
        log.info("National service warmed %d cities", len(self.cities))

    def step_all(self, ticks: int = 1) -> None:
        for c in self.cities:
            for _ in range(ticks):
                c.engine.persist_live(c.storage, c.engine.step_once())

    def city_summaries(self) -> list[dict]:
        out = []
        for c in self.cities:
            summ = c.intelligence.summary()
            econ = c.planning.economic_summary()
            out.append(
                {
                    "id": c.id,
                    "name": c.name,
                    "avg_congestion": summ.get("avg_congestion", 0.0),
                    "level": summ.get("level", "n/a"),
                    "severe": summ.get("severe", 0),
                    "segments": summ.get("segments", 0),
                    "cost_inr": econ["cost_inr"],
                    "cost_human": econ["cost_human"],
                    "active_vehicles": c.engine.cum_exited,
                }
            )
        return out

    def national_summary(self) -> dict:
        cities = self.city_summaries()
        total_cost = sum(c["cost_inr"] for c in cities)
        total_seg = sum(c["segments"] for c in cities) or 1
        wavg = sum(c["avg_congestion"] * c["segments"] for c in cities) / total_seg
        return {
            "cities": cities,
            "national_cost_inr": round(total_cost, 1),
            "national_cost_human": format_inr(total_cost),
            "national_avg_congestion": round(wavg, 1),
            "total_severe": sum(c["severe"] for c in cities),
            "city_count": len(cities),
        }
