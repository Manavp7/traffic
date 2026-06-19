"""API runtime state: storage, simulation loop and the layer services."""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

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
        from traffic_os.edge import CameraManager
        from traffic_os.mobility import FreightService, TransitService

        self.cameras = CameraManager(self.storage)
        self.transit = TransitService(self.storage)
        self.freight = FreightService(self.storage)

        from traffic_os.enforcement import ChallanService, WatchlistService, ZoneService

        self.challans = ChallanService(self.storage)
        self.watchlist = WatchlistService(self.storage)
        self.zones = ZoneService(self.storage, self.challans)

        from traffic_os.copilot import CopilotService

        self.copilot = CopilotService(
            self.storage,
            self.intelligence,
            kg=self.kg,
            prediction=self.prediction,
            planning=self.planning,
            recommendation=self.recommendation,
        )
        self._task: asyncio.Task | None = None
        self._stop = False
        self.tick_sleep_s = 1.0  # wall-clock seconds between simulated ticks
        self.cache: dict = {}  # heavy analytics refreshed in the background
        self._refresh_interval_s = 12.0
        self.adaptive = False  # when True, the live loop re-applies adaptive signal plans
        self.national: Any = None  # NationalService, built lazily in the warmup thread

    def _ensure_seeded(self, history_days: int) -> None:
        if self.storage.db.count("road_segment") == 0:
            net = build_network_from_settings(self.settings)
            save_network(net, self.storage.db)
            log.info("Seeded network (%d segments)", len(net.segments))
        if self.storage.db.count("segment_metric") == 0:
            net = load_network(self.storage.db)
            log.info("Generating history for forecasting ...")
            generate_history(
                net, self.storage.db, days=history_days, step_min=15, seed=self.settings.sim_seed
            )

    def apply_signal_plan(self) -> list[dict]:
        """Compute an adaptive max-pressure plan from live metrics and apply it live."""
        from traffic_os.decision.adaptive_signal import compute_signal_plan, plan_to_overrides
        from traffic_os.intelligence.current import current_metrics

        metrics = current_metrics(self.storage.db)
        plan = compute_signal_plan(self.engine.net, metrics)
        for sid, durations in plan_to_overrides(plan).items():
            self.engine.signals.set_green_durations(sid, durations)
        return [
            {
                "signal_id": sp.signal_id,
                "junction_id": sp.junction_id,
                "phases": [
                    {
                        "phase_id": pp.phase_id,
                        "green_s": pp.green_s,
                        "current_green_s": pp.current_green_s,
                        "pressure": pp.pressure,
                    }
                    for pp in sp.phases
                ],
            }
            for sp in plan
        ]

    async def _loop(self) -> None:
        log.info("Live simulation loop started")
        while not self._stop:
            snap = self.engine.step_once()
            if self.adaptive and self.engine.tick % 6 == 0:
                self.apply_signal_plan()
            if self.national is not None and self.engine.tick % 3 == 0:
                self.national.step_all(1)
            self.engine.persist_live(self.storage, snap)
            await self.storage.bus.publish("live.tick", self.engine.snapshot_message(snap))
            await asyncio.sleep(self.tick_sleep_s)

    def _refresh_cache(self) -> None:
        """(Re)compute heavy analytics and cache them so the UI stays snappy."""
        import time

        try:
            if not self.prediction.models:
                self.prediction.train()
            recs = [r.model_dump(mode="json") for r in self.recommendation.generate()]
            risk = [r.model_dump(mode="json") for r in self.prediction.top_risk(8)]
            forecasts = self.prediction.forecast_all(60, persist=False)
            favg = (
                sum(f.predicted_congestion for f in forecasts) / len(forecasts)
                if forecasts
                else 0.0
            )
            self.cache = {
                "recommendations": recs,
                "risk": risk,
                "forecast_avg": round(favg, 1),
                "economics": self.planning.economic_summary(),
                "updated_at": time.time(),
            }
        except Exception as exc:  # pragma: no cover
            log.warning("Cache refresh failed: %s", exc)

    def _refresh_loop(self) -> None:
        import time

        log.info("Analytics warmup starting ...")
        self._refresh_cache()
        try:
            from traffic_os.national import NationalService

            self.national = NationalService()
        except Exception as exc:  # pragma: no cover
            log.warning("National service warmup failed: %s", exc)
        log.info("Analytics warmup complete")
        while not self._stop:
            time.sleep(self._refresh_interval_s)
            if self._stop:
                break
            self._refresh_cache()

    async def start(self) -> None:
        self._stop = False
        self._task = asyncio.create_task(self._loop())
        import threading

        threading.Thread(target=self._refresh_loop, daemon=True).start()

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
