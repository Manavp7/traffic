"""ViolationService — runs rule-based detectors over tracks and persists results."""

from __future__ import annotations

from datetime import datetime

from traffic_os.common.logging import get_logger
from traffic_os.schemas import SignalState, Track, Violation
from traffic_os.simulation.network import RoadNetwork, load_network
from traffic_os.violations.detectors import (
    detect_illegal_parking,
    detect_red_light,
    detect_speeding,
    detect_wrong_side,
)

log = get_logger("violations")


class ViolationService:
    def __init__(self, storage) -> None:
        self.storage = storage
        self._net: RoadNetwork | None = None

    @property
    def net(self) -> RoadNetwork:
        if self._net is None or not self._net.segments:
            self._net = load_network(self.storage.db)
        return self._net

    def _build_is_green(self):
        """Approximate green-phase predicate from the latest signal states."""
        states = {s.signal_id: s for s in self.storage.db.find("signal_state", SignalState)}
        net = self.net
        green_segments: dict[str, set[str]] = {}
        for sig in net.signals.values():
            st = states.get(sig.id)
            if st is None:
                continue
            for ph in sig.phases:
                if ph.id == st.active_phase:
                    green_segments[sig.junction_id] = set(ph.movements)
                    break

        def is_green(segment_id: str, _ts: datetime) -> bool:
            seg = net.segments.get(segment_id)
            if seg is None:
                return True
            greens = green_segments.get(seg.to_junction)
            if greens is None:
                return True  # unsignalised or unknown -> not a red-light context
            return segment_id in greens

        return is_green

    def detect(self, tracks: list[Track] | None = None, *, persist: bool = True) -> list[Violation]:
        tracks = tracks if tracks is not None else self.storage.db.find("track", Track, limit=2000)
        net = self.net
        is_green = self._build_is_green()
        out: list[Violation] = []
        for tr in tracks:
            out.extend(detect_speeding(tr, net))
            out.extend(detect_wrong_side(tr, net))
            out.extend(detect_illegal_parking(tr, net))
            out.extend(detect_red_light(tr, net, is_green))
        if persist and out:
            self.storage.db.upsert_many("violation", out)
        log.info("Detected %d violations over %d tracks", len(out), len(tracks))
        return out

    def recent(self, limit: int = 100) -> list[Violation]:
        return self.storage.db.find(
            "violation", Violation, order_by_ts=True, desc=True, limit=limit
        )

    def counts_by_type(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for v in self.storage.db.find("violation", Violation, limit=5000):
            out[v.type.value] = out.get(v.type.value, 0) + 1
        return out
