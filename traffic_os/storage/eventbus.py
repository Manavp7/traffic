"""Event bus adapters. Dev: in-process asyncio fan-out. Prod: Redpanda/Kafka.

The dev bus keeps a bounded ring buffer per topic so late subscribers (e.g. a
WebSocket client connecting after simulation started) still receive recent state.
"""

from __future__ import annotations

import asyncio
from collections import deque
from typing import Any

from traffic_os.storage.ports import EventBus, Subscription


class _MemorySubscription(Subscription):
    def __init__(self, bus: MemoryEventBus, topic: str) -> None:
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._bus = bus
        self._topic = topic

    async def __aiter__(self):  # type: ignore[override]
        while True:
            yield await self._queue.get()

    def _push(self, message: dict[str, Any]) -> None:
        self._queue.put_nowait(message)

    def close(self) -> None:
        self._bus._unsubscribe(self._topic, self)


class MemoryEventBus(EventBus):
    def __init__(self, history: int = 200) -> None:
        self._subs: dict[str, list[_MemorySubscription]] = {}
        self._history: dict[str, deque[dict[str, Any]]] = {}
        self._history_size = history

    async def publish(self, topic: str, message: dict[str, Any]) -> None:
        self._history.setdefault(topic, deque(maxlen=self._history_size)).append(message)
        for sub in list(self._subs.get(topic, [])):
            sub._push(message)

    def subscribe(self, topic: str) -> _MemorySubscription:
        sub = _MemorySubscription(self, topic)
        self._subs.setdefault(topic, []).append(sub)
        # replay recent history so new subscribers are not empty-handed
        for msg in self._history.get(topic, []):
            sub._push(msg)
        return sub

    def latest(self, topic: str) -> dict[str, Any] | None:
        hist = self._history.get(topic)
        return hist[-1] if hist else None

    def _unsubscribe(self, topic: str, sub: _MemorySubscription) -> None:
        if topic in self._subs and sub in self._subs[topic]:
            self._subs[topic].remove(sub)
