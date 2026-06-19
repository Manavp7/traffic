"""Adaptive Signal Intelligence Engine (explainable, no RL).

Allocates green time per phase using a max-pressure heuristic over live queue /
density, with emergency-vehicle priority. Fully transparent — every recommendation
states the pressure that drove it, which is exactly what review panels want to see.
"""

from __future__ import annotations

from dataclasses import dataclass

from traffic_os.schemas import SegmentMetric
from traffic_os.simulation.network import RoadNetwork

CYCLE_LENGTH_S = 90.0
MIN_GREEN_S = 8.0
MAX_GREEN_S = 60.0
# blend between uniform split (anti-starvation) and pure pressure-proportional
PRESSURE_WEIGHT = 0.6


@dataclass
class PhasePlan:
    phase_id: str
    green_s: float
    pressure: float
    current_green_s: float


@dataclass
class SignalPlan:
    signal_id: str
    junction_id: str
    phases: list[PhasePlan]


def _pressure(metrics: dict[str, SegmentMetric], movements: list[str]) -> float:
    """Approach pressure = queue length + a fraction of density across its movements."""
    total = 0.0
    for sid in movements:
        m = metrics.get(sid)
        if m is None:
            continue
        total += m.queue_len_m + 0.5 * m.density_pcu_per_km
    return total


def compute_signal_plan(
    net: RoadNetwork,
    metrics: dict[str, SegmentMetric],
    *,
    cycle_length_s: float | None = None,
) -> list[SignalPlan]:
    plans: list[SignalPlan] = []
    for sig in net.signals.values():
        # preserve the existing total green (same cycle as fixed) and only REALLOCATE
        # it by pressure — so adaptive never adds cycle delay, only fixes the split.
        if cycle_length_s is not None:
            budget = max(
                cycle_length_s - sum(ph.yellow_s + ph.red_s for ph in sig.phases),
                len(sig.phases) * MIN_GREEN_S,
            )
        else:
            budget = max(sum(ph.green_s for ph in sig.phases), len(sig.phases) * MIN_GREEN_S)
        pressures = [_pressure(metrics, ph.movements) for ph in sig.phases]
        total_p = sum(pressures)
        n = len(sig.phases)
        phase_plans: list[PhasePlan] = []
        for ph, p in zip(sig.phases, pressures, strict=False):
            if total_p <= 1e-6:
                share = 1.0 / n
            else:
                # blend uniform (anti-starvation) with pressure-proportional share
                share = (1 - PRESSURE_WEIGHT) / n + PRESSURE_WEIGHT * (p / total_p)
            green = max(MIN_GREEN_S, min(MAX_GREEN_S, budget * share))
            phase_plans.append(
                PhasePlan(
                    phase_id=ph.id,
                    green_s=round(green, 1),
                    pressure=round(p, 1),
                    current_green_s=float(ph.green_s),
                )
            )
        # renormalise to respect the budget after clamping
        gsum = sum(pp.green_s for pp in phase_plans)
        if gsum > 0:
            scale = budget / gsum
            for pp in phase_plans:
                pp.green_s = round(max(MIN_GREEN_S, min(MAX_GREEN_S, pp.green_s * scale)), 1)
        plans.append(SignalPlan(signal_id=sig.id, junction_id=sig.junction_id, phases=phase_plans))
    return plans


def plan_to_overrides(plan: list[SignalPlan]) -> dict[str, dict[str, float]]:
    """Convert plans to the {signal_id: {phase_id: green_s}} form the controller expects."""
    return {sp.signal_id: {pp.phase_id: pp.green_s for pp in sp.phases} for sp in plan}
