"""Blob store adapters. Dev: local filesystem. Prod: MinIO (S3)."""

from __future__ import annotations

from pathlib import Path

from traffic_os.storage.ports import BlobStore


class FsBlobStore(BlobStore):
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = self.root / key
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def put(self, key: str, data: bytes) -> str:
        self._path(key).write_bytes(data)
        return self.url(key)

    def get(self, key: str) -> bytes | None:
        p = self._path(key)
        return p.read_bytes() if p.exists() else None

    def url(self, key: str) -> str:
        return f"/blobs/{key}"
