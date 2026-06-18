"""AI Recommendation Engine — the differentiator.

Most systems say "traffic is bad". This says *what to do*:
  - "Increase Signal A Phase EW by +18s" (signal retime),
  - "Divert Road B traffic via Road D" (divert),
  - "Open emergency corridor for AMB-1" (open corridor),
  - "Deploy patrol on Road C — accident risk 88%" (alert).

Each recommendation carries an expected effect, a confidence and a rationale linked
to the knowledge-graph cause, so operators understand *why*.
"""

from __future__ import annotations

from traffic_os.common.logging import get_logger
from traffic_os.common.timeutil import utcnow
from traffic_os.decision.adaptive_signal import compute_signal_plan
from traffic_os.decision.disaster import reroute_around
from traffic_os.schemas import ActionType, Incident, Recommendation
from traffic_os.simulation.network import RoadNetwork

log = get_logger("recommendation")

SEVERE_CONGESTION = 60.0
HIGH_RISK_PCT = 65.0
MIN_GREEN_DELTA = 5.0


class RecommendationEngine:
    def __init__(self, storage, intelligence, kg=None, prediction=None) -> None:
        self.storage = storage
        self.intelligence = intelligence
        self.kg = kg
        self.prediction = prediction

    @property
    def net(self) -> RoadNetwork:
        return self.intelligence.net

    def _rid(self, kind: str, target: str) -> str:
        return f"REC-{kind}-{target}"

    def _rationale_for_junction(self, junction_id: str) -> str:
        if self.kg is None:
            return ""
        try:
            factors = self.kg.why_congested(junction_id)
        except Exception:
            return ""
        if not factors:
            return ""
        return "; ".join(f.description for f in factors[:2])

    def generate(self, *, max_recs: int = 12, sync_kg: bool = True) -> list[Recommendation]:
        if sync_kg and self.kg is not None:
            try:
                self.kg.sync()
            except Exception as exc:  # pragma: no cover
                log.warning("KG sync failed: %s", exc)

        metrics = self.intelligence.latest_metrics()
        recs: list[Recommendation] = []
        recs += self._signal_recs(metrics)
        recs += self._bottleneck_divert_recs(metrics)
        recs += self._incident_recs()
        recs += self._risk_recs()

        # de-duplicate by (action_type, target), keep highest impact
        best: dict[tuple[str, str], Recommendation] = {}
        for r in recs:
            key = (r.action_type.value, r.target)
            if key not in best or r.impact_score > best[key].impact_score:
                best[key] = r
        out = sorted(best.values(), key=lambda r: r.impact_score, reverse=True)[:max_recs]
        if out:
            self.storage.db.clear("recommendation")
            self.storage.db.upsert_many("recommendation", out)
        log.info("Generated %d recommendations", len(out))
        return out

    # -- signal retiming --------------------------------------------------- #
    def _signal_recs(self, metrics) -> list[Recommendation]:
        out = []
        plans = compute_signal_plan(self.net, metrics)
        plan_by_junction = {p.junction_id: p for p in plans}
        for hs in self.intelligence.hotspots(top_n=8):
            if hs.congestion < SEVERE_CONGESTION:
                continue
            plan = plan_by_junction.get(hs.junction_id)
            if plan is None:
                continue
            # find the phase with the largest recommended increase
            cand = max(plan.phases, key=lambda pp: pp.green_s - pp.current_green_s)
            delta = cand.green_s - cand.current_green_s
            if delta < MIN_GREEN_DELTA:
                continue
            rationale = self._rationale_for_junction(hs.junction_id)
            out.append(
                Recommendation(
                    id=self._rid("SIG", hs.junction_id), ts=utcnow(),
                    trigger=f"Junction {hs.name} congested ({hs.congestion:.0f}/100)",
                    action_type=ActionType.SIGNAL_RETIME,
                    target=plan.signal_id,
                    params={"junction": hs.junction_id, "phase": cand.phase_id,
                            "green_s": cand.green_s, "delta_s": round(delta, 1)},
                    expected_effect=f"+{delta:.0f}s green on phase {cand.phase_id} to clear the busiest approach",
                    impact_score=round(hs.congestion + delta, 1),
                    confidence=0.75,
                    rationale=rationale or "High measured queue/density on this approach.",
                )
            )
        return out

    # -- divert around bottlenecks ---------------------------------------- #
    def _bottleneck_divert_recs(self, metrics) -> list[Recommendation]:
        out = []
        for bn in self.intelligence.bottlenecks(top_n=5):
            if bn.congestion < SEVERE_CONGESTION:
                continue
            seg = self.net.segments.get(bn.segment_id)
            if seg is None:
                continue
            rr = reroute_around(self.net, seg.from_junction, seg.to_junction,
                                {bn.segment_id}, metrics)
            if not rr.feasible or not rr.detour_route:
                continue
            out.append(
                Recommendation(
                    id=self._rid("DIV", bn.segment_id), ts=utcnow(),
                    trigger=f"Bottleneck on {bn.name} ({bn.speed_kph:.0f} km/h, queue {bn.congestion:.0f})",
                    action_type=ActionType.DIVERT,
                    target=bn.segment_id,
                    params={"detour": rr.detour_route, "extra_distance_m": rr.extra_distance_m},
                    expected_effect=f"Divert via {len(rr.detour_route)} alt segments (+{rr.extra_distance_m:.0f} m) to relieve the choke point",
                    impact_score=round(bn.score, 1),
                    confidence=0.65,
                    rationale=bn.explanation,
                )
            )
        return out

    # -- incident response ------------------------------------------------- #
    def _incident_recs(self) -> list[Recommendation]:
        out = []
        incidents = self.storage.db.find("incident", Incident, where={"status": "active"})
        for inc in incidents:
            if not inc.segments_blocked:
                continue
            seg = self.net.segments.get(inc.segment_id or "")
            if seg is None:
                continue
            rr = reroute_around(self.net, seg.from_junction, seg.to_junction,
                                set(inc.segments_blocked))
            detour = rr.detour_route if rr.feasible else []
            out.append(
                Recommendation(
                    id=self._rid("INC", inc.id), ts=utcnow(),
                    trigger=f"{inc.type.value.title()} blocking {seg.name}",
                    action_type=ActionType.DIVERT if detour else ActionType.ALERT,
                    target=inc.segment_id or seg.id,
                    params={"incident": inc.id, "detour": detour},
                    expected_effect=("Reroute around the blockage via alternate roads"
                                     if detour else "Alert drivers; clear the blockage urgently"),
                    impact_score=round(70 + inc.severity * 30, 1),
                    confidence=0.8,
                    rationale=f"{inc.description} (severity {inc.severity:.1f}).",
                )
            )
        return out

    # -- accident-risk alerts --------------------------------------------- #
    def _risk_recs(self) -> list[Recommendation]:
        if self.prediction is None:
            return []
        out = []
        try:
            top = self.prediction.top_risk(5)
        except Exception as exc:  # pragma: no cover
            log.warning("risk prediction unavailable: %s", exc)
            return []
        for risk in top:
            if risk.risk_pct < HIGH_RISK_PCT:
                continue
            seg = self.net.segments.get(risk.segment_id)
            name = seg.name if seg else risk.segment_id
            drivers = ", ".join(f"{k}={v}" for k, v in risk.drivers.items() if v)
            out.append(
                Recommendation(
                    id=self._rid("RISK", risk.segment_id), ts=utcnow(),
                    trigger=f"Accident risk {risk.risk_pct:.0f}% on {name}",
                    action_type=ActionType.ALERT,
                    target=risk.segment_id,
                    params={"risk_pct": risk.risk_pct, "drivers": risk.drivers},
                    expected_effect="Deploy patrol / lower speed limit / warn drivers to pre-empt a crash",
                    impact_score=round(risk.risk_pct, 1),
                    confidence=0.6,
                    rationale=f"Elevated risk drivers: {drivers}." if drivers else "Elevated accident risk.",
                )
            )
        return out
