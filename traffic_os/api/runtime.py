"""API runtime state: storage, simulation loop and the layer services."""

from __future__ import annotations

import asyncio
import contextlib

from traffic_os.common.logging import get_logger
from traffic_os.decision import DecisionService
from traffic_os.intelligence import IntelligenceService
from traffic_os.knowledge_graph import KnowledgeGraphService
from traffic_os.planning import PlanningService
from traffic_os.prediction import PredictionService
from traffic_os.recommendation import RecommendationEngine
from traffic_os.simulation import (
    SimulationEngine,
    build_network_from_settings,
    generate_history,
    load_network,
    save_network,
)
from traffic_os.storage import get_storage

log = get_logger("api.runtime")


class AppState:
    def __init__(self, storage=None, *, history_days: int = 7) -> None:
        self.storage = storage or get_storage()
        self.settings = self.storage.settings
        self._ensure_seeded(history_days)

        self.engine = SimulationEngine.from_storage(self.storage, self.settings)
        self.intelligence = IntelligenceService(self.storage)
        self.kg = KnowledgeGraphService(self.storage, self.intelligence)
        self.decision = DecisionService(self.storage)
        self.planning = PlanningService(self.storage)
        self.prediction = PredictionService(self.storage)
        self.recommendation = RecommendationEngine(
            self.storage, self.intelligence, kg=self.kg, prediction=self.prediction
        )
        from traffic_os.copilot import CopilotService

        self.copilot = CopilotService(
            self.storage, self.intelligence, kg=self.kg, prediction=self.prediction,
            planning=self.planning, recommendation=self.recommendation,
        )
        self._task: asyncio.Task | None = None
        self._stop = False
        self.tick_sleep_s = 1.0  # wall-clock seconds between simulated ticks

    def _ensure_seeded(self, history_days: int) -> None:
        if self.storage.db.count("road_segment") == 0:
            net = build_network_from_settings(self.settings)
            save_network(net, self.storage.db)
            log.info("Seeded network (%d segments)", len(net.segments))
        if self.storage.db.count("segment_metric") == 0:
            net = load_network(self.storage.db)
            log.info("Generating history for forecasting ...")
            generate_history(net, self.storage.db, days=history_days, step_min=15,
                             seed=self.settings.sim_seed)

    async def _loop(self) -> None:
        log.info("Live simulation loop started")
        while not self._stop:
            snap = self.engine.step_once()
            self.engine.persist_live(self.storage, snap)
            await self.storage.bus.publish("live.tick", self.engine.snapshot_message(snap))
            await asyncio.sleep(self.tick_sleep_s)

    async def start(self) -> None:
        self._stop = False
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stop = True
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task


_state: AppState | None = None


def get_state() -> AppState:
    global _state
    if _state is None:
        _state = AppState()
    return _state


def set_state(state: AppState) -> None:
    """Inject a pre-built state (used by tests)."""
    global _state
    _state = state
