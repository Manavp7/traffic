"""Stolen / blacklist vehicle watchlist with live plate matching."""

from __future__ import annotations

from traffic_os.common.logging import get_logger
from traffic_os.enforcement.anpr import plate_for_track
from traffic_os.schemas import Track, WatchlistEntry

log = get_logger("enforcement.watchlist")


class WatchlistService:
    def __init__(self, storage) -> None:
        self.storage = storage

    def add(self, plate: str, reason: str = "stolen") -> WatchlistEntry:
        entry = WatchlistEntry(id=plate.upper(), plate=plate.upper(), reason=reason)
        self.storage.db.upsert("watchlist", entry)
        return entry

    def remove(self, plate: str) -> None:
        entry = self.storage.db.get("watchlist", plate.upper(), WatchlistEntry)
        if entry:
            entry.active = False
            self.storage.db.upsert("watchlist", entry)

    def entries(self) -> list[WatchlistEntry]:
        return [
            e for e in self.storage.db.find("watchlist", WatchlistEntry, limit=10000) if e.active
        ]

    def is_listed(self, plate: str) -> WatchlistEntry | None:
        e = self.storage.db.get("watchlist", plate.upper(), WatchlistEntry)
        return e if e and e.active else None

    def scan_tracks(self, tracks: list[Track]) -> list[dict]:
        """Match live track plates against the watchlist; return hits as alerts."""
        listed = {e.plate: e for e in self.entries()}
        hits = []
        for tr in tracks:
            plate = plate_for_track(tr.track_id)
            entry = listed.get(plate)
            if entry is None:
                continue
            last = tr.points[-1] if tr.points else None
            hits.append(
                {
                    "plate": plate,
                    "reason": entry.reason,
                    "track_id": tr.track_id,
                    "lat": last.lat if last else None,
                    "lon": last.lon if last else None,
                }
            )
        return hits
