"""Signal controller for the digital twin.

Fixed-timer cycling by default, with hooks the Decision layer uses later:
- ``set_green_durations`` (adaptive signal intelligence), and
- ``preempt`` (emergency green corridors).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from traffic_os.schemas import SignalMode, SignalState
from traffic_os.simulation.network import RoadNetwork


@dataclass
class _SigRuntime:
    phase_index: int = 0
    elapsed_s: float = 0.0
    mode: SignalMode = SignalMode.FIXED
    green_override: dict[str, float] = field(default_factory=dict)  # phase_id -> green_s
    preempt_segments: set[str] = field(default_factory=set)
    preempt_remaining_s: float = 0.0


class SignalController:
    def __init__(self, net: RoadNetwork) -> None:
        self.net = net
        self.rt: dict[str, _SigRuntime] = {s: _SigRuntime() for s in net.signals}
        # junction -> signal id
        self._j2s = {sig.junction_id: sid for sid, sig in net.signals.items()}

    def _phase_total(self, sid: str, phase_index: int) -> float:
        sig = self.net.signals[sid]
        ph = sig.phases[phase_index]
        base = self.rt[sid].green_override.get(ph.id, ph.green_s)
        return base + ph.yellow_s

    def step(self, dt: float) -> None:
        for sid, rt in self.rt.items():
            if rt.preempt_remaining_s > 0:
                rt.preempt_remaining_s -= dt
                if rt.preempt_remaining_s <= 0:
                    rt.preempt_segments = set()
                    rt.mode = SignalMode.FIXED
                continue
            rt.elapsed_s += dt
            if rt.elapsed_s >= self._phase_total(sid, rt.phase_index):
                rt.elapsed_s = 0.0
                rt.phase_index = (rt.phase_index + 1) % len(self.net.signals[sid].phases)

    def green_segments(self, junction_id: str) -> set[str] | None:
        """Return green incoming segments, or ``None`` if junction is unsignalised."""
        sid = self._j2s.get(junction_id)
        if sid is None:
            return None  # unsignalised: free movement
        rt = self.rt[sid]
        if rt.preempt_remaining_s > 0:
            return set(rt.preempt_segments)
        sig = self.net.signals[sid]
        return set(sig.phases[rt.phase_index].movements)

    def set_green_durations(self, signal_id: str, durations: dict[str, float]) -> None:
        rt = self.rt.get(signal_id)
        if rt is not None:
            rt.green_override.update(durations)
            rt.mode = SignalMode.ADAPTIVE

    def preempt(self, signal_id: str, segments: set[str], duration_s: float) -> None:
        rt = self.rt.get(signal_id)
        if rt is not None:
            rt.preempt_segments = set(segments)
            rt.preempt_remaining_s = duration_s
            rt.mode = SignalMode.PREEMPT

    def preempt_junction(self, junction_id: str, segments: set[str], duration_s: float) -> None:
        sid = self._j2s.get(junction_id)
        if sid:
            self.preempt(sid, segments, duration_s)

    def states(self) -> list[SignalState]:
        out = []
        for sid, rt in self.rt.items():
            sig = self.net.signals[sid]
            ph = sig.phases[rt.phase_index]
            total = self._phase_total(sid, rt.phase_index)
            out.append(
                SignalState(
                    signal_id=sid,
                    active_phase=ph.id,
                    mode=rt.mode,
                    remaining_s=max(0.0, total - rt.elapsed_s),
                )
            )
        return out
