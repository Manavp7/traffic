"""DecisionService — adaptive signals, emergency corridors, disaster reroute."""

from __future__ import annotations

from traffic_os.common.config import Settings
from traffic_os.common.logging import get_logger
from traffic_os.decision.adaptive_signal import (
    SignalPlan,
    compute_signal_plan,
    plan_to_overrides,
)
from traffic_os.decision.disaster import Reroute, reroute_around
from traffic_os.decision.emergency import plan_corridor
from traffic_os.schemas import EmergencyVehicle, GreenCorridor, SegmentMetric
from traffic_os.simulation.network import RoadNetwork, load_network

log = get_logger("decision")


class DecisionService:
    def __init__(self, storage) -> None:
        self.storage = storage
        self._net: RoadNetwork | None = None

    @property
    def net(self) -> RoadNetwork:
        if self._net is None or not self._net.segments:
            self._net = load_network(self.storage.db)
        return self._net

    def _latest_metrics(self) -> dict[str, SegmentMetric]:
        return {m.segment_id: m for m in self.storage.db.latest_per_segment(SegmentMetric)}

    # -- adaptive signals ------------------------------------------------- #
    def signal_plan(self, metrics: dict[str, SegmentMetric] | None = None) -> list[SignalPlan]:
        return compute_signal_plan(self.net, metrics or self._latest_metrics())

    def evaluate_signal_strategy(
        self,
        *,
        ticks: int = 180,
        warmup: int = 50,
        update_every: int = 20,
        demand_scale: float | None = None,
        directional_bias: float = 0.85,
    ) -> dict:
        """Compare fixed-timer vs adaptive control on an oversaturated arterial peak.

        Adaptive max-pressure control adds most value when demand is directionally
        imbalanced (a congested arterial against light cross-streets) — the realistic
        peak-hour case — so we evaluate on exactly that scenario.
        """
        from traffic_os.simulation.engine import SimulationEngine

        net = self.net
        base = getattr(self.storage, "settings", None) or Settings(mode="dev")
        settings = base.model_copy(
            update={"sim_demand_scale": demand_scale} if demand_scale else {}
        )

        def run(adaptive: bool) -> tuple[int, float]:
            eng = SimulationEngine(net, settings)
            eng.micro.directional_bias = directional_bias
            speed_samples: list[float] = []
            for t in range(ticks):
                snap = eng.step_once()
                if adaptive and t % update_every == 0:
                    metrics = {m.segment_id: m for m in snap.metrics}
                    overrides = plan_to_overrides(compute_signal_plan(net, metrics))
                    for sig_id, durations in overrides.items():
                        eng.signals.set_green_durations(sig_id, durations)
                if t >= warmup:
                    speed_samples.append(snap.mean_speed_kph)
            mean_speed = sum(speed_samples) / len(speed_samples) if speed_samples else 0.0
            return eng.cum_exited, round(mean_speed, 2)

        # Throughput (trips completed) + mean speed are the real KPIs; average road
        # occupancy is misleading because throttling inflow lowers it artificially.
        fixed_throughput, fixed_speed = run(adaptive=False)
        adaptive_throughput, adaptive_speed = run(adaptive=True)
        thru_gain = (
            (adaptive_throughput - fixed_throughput) / fixed_throughput * 100.0
            if fixed_throughput
            else 0.0
        )
        speed_gain = (adaptive_speed - fixed_speed) / fixed_speed * 100.0 if fixed_speed else 0.0
        result = {
            "fixed_throughput": fixed_throughput,
            "adaptive_throughput": adaptive_throughput,
            "throughput_gain_pct": round(thru_gain, 2),
            "fixed_mean_speed_kph": fixed_speed,
            "adaptive_mean_speed_kph": adaptive_speed,
            "speed_gain_pct": round(speed_gain, 2),
            "improvement_pct": round(thru_gain, 2),
            "ticks": ticks,
        }
        log.info("Signal strategy eval: %s", result)
        return result

    # -- emergency -------------------------------------------------------- #
    def emergency_corridor(
        self, ev: EmergencyVehicle, *, blocked: set[str] | None = None, persist: bool = True
    ) -> GreenCorridor | None:
        corridor = plan_corridor(self.net, self._latest_metrics(), ev, blocked=blocked)
        if corridor and persist:
            self.storage.db.upsert("green_corridor", corridor)
        return corridor

    # -- disaster reroute ------------------------------------------------- #
    def reroute(self, origin: str, destination: str, blocked: set[str]) -> Reroute:
        return reroute_around(self.net, origin, destination, blocked, self._latest_metrics())
