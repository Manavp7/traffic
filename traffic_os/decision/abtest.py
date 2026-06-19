"""Signal-policy A/B testing with a significance estimate (Welch's t-test)."""

from __future__ import annotations

import math

from traffic_os.common.config import Settings
from traffic_os.decision.adaptive_signal import compute_signal_plan, plan_to_overrides


def _normal_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _welch(a: list[float], b: list[float]) -> tuple[float, float]:
    """Return (t_stat, two-tailed p approx via normal CDF)."""
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return 0.0, 1.0
    ma, mb = sum(a) / na, sum(b) / nb
    va = sum((x - ma) ** 2 for x in a) / (na - 1)
    vb = sum((x - mb) ** 2 for x in b) / (nb - 1)
    se = math.sqrt(va / na + vb / nb)
    if se == 0:
        return 0.0, 1.0
    t = (mb - ma) / se
    p = 2 * (1 - _normal_cdf(abs(t)))
    return t, p


def ab_test(
    storage,
    net,
    *,
    runs: int = 4,
    ticks: int = 120,
    warmup: int = 40,
    directional_bias: float = 0.85,
    demand_scale: float | None = None,
) -> dict:
    """Run fixed vs adaptive control over multiple seeds; compare throughput + significance."""
    from traffic_os.simulation.engine import SimulationEngine

    base = getattr(storage, "settings", None) or Settings(mode="dev")
    settings = base.model_copy(update={"sim_demand_scale": demand_scale} if demand_scale else {})

    def run(adaptive: bool, seed: int) -> int:
        s = settings.model_copy(update={"sim_seed": seed})
        eng = SimulationEngine(net, s)
        eng.micro.directional_bias = directional_bias
        for t in range(ticks):
            snap = eng.step_once()
            if adaptive and t % 6 == 0 and t >= warmup:
                for sid, dur in plan_to_overrides(
                    compute_signal_plan(net, {m.segment_id: m for m in snap.metrics})
                ).items():
                    eng.signals.set_green_durations(sid, dur)
        return eng.cum_exited

    fixed = [float(run(False, 100 + i)) for i in range(runs)]
    adaptive = [float(run(True, 100 + i)) for i in range(runs)]
    t, p = _welch(fixed, adaptive)
    mean_fixed = sum(fixed) / len(fixed)
    mean_adaptive = sum(adaptive) / len(adaptive)
    return {
        "runs": runs,
        "fixed_throughput_mean": round(mean_fixed, 1),
        "adaptive_throughput_mean": round(mean_adaptive, 1),
        "improvement_pct": (
            round((mean_adaptive - mean_fixed) / mean_fixed * 100, 2) if mean_fixed else 0.0
        ),
        "t_stat": round(t, 3),
        "p_value": round(p, 4),
        "significant": p < 0.05 and mean_adaptive > mean_fixed,
    }
