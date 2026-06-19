"""Calibrate simulation demand to match a target on-network vehicle count.

In production this is calibrated against real loop-detector / camera counts; here we
fit the ``sim_demand_scale`` so the twin reproduces an observed vehicle population.
"""

from __future__ import annotations

from traffic_os.common.config import Settings
from traffic_os.common.logging import get_logger
from traffic_os.simulation.network import RoadNetwork

log = get_logger("sim.calibration")


def _measure(net: RoadNetwork, demand: float, ticks: int, warmup: int) -> float:
    from traffic_os.simulation.engine import SimulationEngine

    eng = SimulationEngine(net, Settings(mode="dev", sim_demand_scale=demand))
    samples = []
    for t in range(ticks):
        snap = eng.step_once()
        if t >= warmup:
            samples.append(snap.active_vehicles)
    return sum(samples) / len(samples) if samples else 0.0


def calibrate_demand(
    net: RoadNetwork,
    target_vehicles: int,
    *,
    ticks: int = 60,
    warmup: int = 25,
    iters: int = 6,
    start_demand: float = 40.0,
) -> dict:
    """Proportionally adjust demand until mean active vehicles ~ target."""
    demand = start_demand
    achieved = _measure(net, demand, ticks, warmup)
    history = [(round(demand, 1), round(achieved, 0))]
    for _ in range(iters):
        if achieved <= 1:
            demand *= 2
        else:
            ratio = target_vehicles / achieved
            demand = max(1.0, min(400.0, demand * (0.5 + 0.5 * ratio)))  # damped step
        achieved = _measure(net, demand, ticks, warmup)
        history.append((round(demand, 1), round(achieved, 0)))
        if abs(achieved - target_vehicles) <= 0.1 * target_vehicles:
            break
    err = abs(achieved - target_vehicles) / max(target_vehicles, 1)
    log.info(
        "Calibrated demand=%.1f -> %.0f vehicles (target %d, err %.0f%%)",
        demand,
        achieved,
        target_vehicles,
        err * 100,
    )
    return {
        "demand_scale": round(demand, 1),
        "achieved_vehicles": round(achieved, 0),
        "target_vehicles": target_vehicles,
        "error_pct": round(err * 100, 1),
        "history": history,
    }
