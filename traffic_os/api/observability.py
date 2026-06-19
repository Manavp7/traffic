"""Lightweight, dependency-free observability: Prometheus metrics + rate limiting."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class Metrics:
    """Minimal Prometheus-compatible counter/gauge registry."""

    def __init__(self) -> None:
        self._counters: dict[tuple[str, tuple], float] = defaultdict(float)
        self._gauges: dict[str, float] = {}
        self._lock = threading.Lock()

    def inc(self, name: str, labels: dict | None = None, value: float = 1.0) -> None:
        key = (name, tuple(sorted((labels or {}).items())))
        with self._lock:
            self._counters[key] += value

    def set_gauge(self, name: str, value: float) -> None:
        with self._lock:
            self._gauges[name] = value

    def render(self) -> str:
        lines = []
        seen = set()
        for (name, labels), val in sorted(self._counters.items()):
            if name not in seen:
                lines.append(f"# TYPE {name} counter")
                seen.add(name)
            lbl = ",".join(f'{k}="{v}"' for k, v in labels)
            lines.append(f"{name}{{{lbl}}} {val}" if lbl else f"{name} {val}")
        for name, val in sorted(self._gauges.items()):
            lines.append(f"# TYPE {name} gauge")
            lines.append(f"{name} {val}")
        return "\n".join(lines) + "\n"


class RateLimiter:
    """Sliding-window per-client rate limiter (requests per minute)."""

    def __init__(self, per_min: int) -> None:
        self.per_min = per_min
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, client: str) -> bool:
        if self.per_min <= 0:
            return True
        now = time.time()
        with self._lock:
            dq = self._hits[client]
            while dq and now - dq[0] > 60:
                dq.popleft()
            if len(dq) >= self.per_min:
                return False
            dq.append(now)
            return True


METRICS = Metrics()
