"""Infrastructure Planning Simulator — "what if we build/close/widen this?"

Applies scenario edits to a *copy* of the digital twin, re-runs the microsim under
identical demand, and reports KPI deltas (congestion, speed, throughput, ₹ cost).
This turns Traffic-OS from traffic management into city-planning software.
"""

from __future__ import annotations

from traffic_os.common.config import Settings, get_settings
from traffic_os.common.logging import get_logger
from traffic_os.planning.economics import EconomicLossEngine, format_inr
from traffic_os.schemas import InfraScenario, ScenarioOp, ScenarioResult, SegmentMetric
from traffic_os.simulation.network import RoadNetwork

log = get_logger("planning.infra")


def copy_network(net: RoadNetwork) -> RoadNetwork:
    new = RoadNetwork()
    new.junctions = {k: v.model_copy(deep=True) for k, v in net.junctions.items()}
    new.segments = {k: v.model_copy(deep=True) for k, v in net.segments.items()}
    new.signals = {k: v.model_copy(deep=True) for k, v in net.signals.items()}
    return new.finalize()


def apply_edits(net: RoadNetwork, scenario: InfraScenario) -> RoadNetwork:
    for edit in scenario.edits:
        if edit.op == ScenarioOp.ADD_FLYOVER and edit.target in net.segments:
            seg = net.segments[edit.target]
            seg.lanes += int(edit.params.get("lanes", 2))
            seg.speed_limit_kph = round(
                seg.speed_limit_kph * float(edit.params.get("speed_mult", 1.3)), 1
            )
        elif edit.op == ScenarioOp.WIDEN_LANE and edit.target in net.segments:
            net.segments[edit.target].lanes += int(edit.params.get("delta", 1))
        elif edit.op == ScenarioOp.CLOSE_ROAD and edit.target in net.segments:
            net.segments.pop(edit.target, None)
            for sig in net.signals.values():
                for ph in sig.phases:
                    if edit.target in ph.movements:
                        ph.movements.remove(edit.target)
        elif edit.op == ScenarioOp.RETIME_SIGNAL:
            rsig = net.signal_for_junction(edit.target)
            if rsig:
                for ph in rsig.phases:
                    if ph.id in edit.params:
                        ph.green_s = int(edit.params[ph.id])
    return net.finalize()


def _run_kpis(
    net: RoadNetwork,
    settings: Settings,
    *,
    ticks: int,
    warmup: int,
) -> dict[str, float]:
    from traffic_os.intelligence.congestion import DEFAULT_MODEL
    from traffic_os.simulation.engine import SimulationEngine

    eng = SimulationEngine(net, settings)
    cong, speed = [], []
    last: dict[str, SegmentMetric] = {}
    for t in range(ticks):
        snap = eng.step_once()
        last = {m.segment_id: m for m in snap.metrics}
        if t >= warmup:
            cong.append(sum(m.congestion_score for m in snap.metrics) / len(snap.metrics))
            speed.append(snap.mean_speed_kph)
    # authoritative congestion recompute on final snapshot
    for sid, m in last.items():
        seg = net.segments.get(sid)
        if seg:
            m.congestion_score = DEFAULT_MODEL.score(m, seg)
    econ = EconomicLossEngine.from_settings(settings).city_impact(net, last)
    return {
        "avg_congestion": round(sum(cong) / len(cong), 2) if cong else 0.0,
        "mean_speed_kph": round(sum(speed) / len(speed), 2) if speed else 0.0,
        "throughput": float(eng.cum_exited),
        "daily_cost_inr": econ.cost_inr,
    }


def run_scenario(
    net: RoadNetwork,
    scenario: InfraScenario,
    settings: Settings | None = None,
    *,
    ticks: int = 140,
    warmup: int = 40,
) -> ScenarioResult:
    settings = settings or get_settings()
    baseline = _run_kpis(copy_network(net), settings, ticks=ticks, warmup=warmup)
    scen_net = apply_edits(copy_network(net), scenario)
    scenario_kpis = _run_kpis(scen_net, settings, ticks=ticks, warmup=warmup)

    deltas = {k: round(scenario_kpis[k] - baseline[k], 2) for k in baseline}
    summary = _summarize(scenario, baseline, scenario_kpis, deltas)
    log.info("Scenario %s deltas: %s", scenario.name, deltas)
    return ScenarioResult(
        scenario_id=scenario.id,
        baseline_kpis=baseline,
        scenario_kpis=scenario_kpis,
        deltas=deltas,
        summary=summary,
    )


def _summarize(scenario, baseline, scen, deltas) -> str:
    cong_pct = (
        -deltas["avg_congestion"] / baseline["avg_congestion"] * 100
        if baseline["avg_congestion"]
        else 0.0
    )
    cost_delta = deltas["daily_cost_inr"]
    direction = "cuts" if cost_delta < 0 else "raises"
    cong_word = "reduces" if cong_pct >= 0 else "increases"
    return (
        f"{scenario.name}: {cong_word} average congestion by {abs(cong_pct):.1f}% "
        f"and {direction} economic cost by {format_inr(abs(cost_delta))}/day "
        f"(throughput {deltas['throughput']:+.0f} trips)."
    )
