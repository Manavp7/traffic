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


class RedisCache(Cache):
    """Production cache backed by Redis (values JSON-serialised)."""

    def __init__(self, url: str) -> None:
        import redis  # optional dependency

        self.client = redis.Redis.from_url(url)

    def get(self, key: str) -> Any | None:
        import orjson

        raw = self.client.get(key)
        return orjson.loads(raw) if raw else None

    def set(self, key: str, value: Any, ttl_s: int | None = None) -> None:
        import orjson

        data = orjson.dumps(value)
        if ttl_s:
            self.client.setex(key, ttl_s, data)
        else:
            self.client.set(key, data)
