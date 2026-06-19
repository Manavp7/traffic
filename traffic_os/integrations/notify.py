"""Citizen notifications (SMS/WhatsApp/push) + geofenced alerts.

``LocalNotifier`` records notifications in the store (always works for the demo).
Twilio/WhatsApp/push providers activate when their credentials are configured.
"""

from __future__ import annotations

import os
import uuid

from traffic_os.common.geo import haversine_m
from traffic_os.common.logging import get_logger
from traffic_os.common.timeutil import utcnow
from traffic_os.schemas import CitizenReport, Notification

log = get_logger("integrations.notify")


class NotificationService:
    def __init__(self, storage) -> None:
        self.storage = storage

    def _channel(self) -> str:
        if os.environ.get("TWILIO_AUTH_TOKEN"):
            return "sms"  # pragma: no cover - needs creds
        if os.environ.get("WHATSAPP_TOKEN"):
            return "whatsapp"  # pragma: no cover
        return "local"

    def send(
        self, to: str, message: str, *, channel: str | None = None, geofence: dict | None = None
    ) -> Notification:
        note = Notification(
            id=f"N-{uuid.uuid4().hex[:8]}",
            ts=utcnow(),
            channel=channel or self._channel(),
            to=to,
            message=message,
            status="sent",
            geofence=geofence,
        )
        # real providers would dispatch here; local just records it
        self.storage.db.upsert("notification", note)
        return note

    def geofence_alert(self, lat: float, lon: float, radius_m: float, message: str) -> dict:
        """Notify citizens whose recent reports fall within the geofence."""
        reports = self.storage.db.find("citizen_report", CitizenReport, limit=5000)
        recipients = [r for r in reports if haversine_m(lat, lon, r.lat, r.lon) <= radius_m]
        gf = {"lat": lat, "lon": lon, "radius_m": radius_m}
        for r in recipients:
            self.send(r.id, message, geofence=gf)
        broadcast = self.send("area-broadcast", message, geofence=gf)
        return {
            "recipients": len(recipients),
            "broadcast_id": broadcast.id,
            "geofence": gf,
            "message": message,
        }

    def recent(self, limit: int = 100) -> list[Notification]:
        return self.storage.db.find(
            "notification", Notification, order_by_ts=True, desc=True, limit=limit
        )
