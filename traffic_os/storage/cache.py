"""Cache adapters. Dev: in-process dict. Prod: Redis."""

from __future__ import annotations

import time
from typing import Any

from traffic_os.storage.ports import Cache


class MemoryCache(Cache):
    def __init__(self) -> None:
        self._store: dict[str, tuple[float | None, Any]] = {}

    def get(self, key: str) -> Any | None:
        item = self._store.get(key)
        if item is None:
            return None
        expiry, value = item
        if expiry is not None and time.time() > expiry:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any, ttl_s: int | None = None) -> None:
        expiry = time.time() + ttl_s if ttl_s else None
        self._store[key] = (expiry, value)
