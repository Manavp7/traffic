"""e-Challan generation with a tamper-evident evidence locker.

Each challan stores its evidence (a JSON snapshot, or an image when available) in the
blob store, recording a **SHA-256 signature** and a **chain-of-custody** log so the
evidence is tamper-evident and audit-ready.
"""

from __future__ import annotations

import hashlib
import uuid

import orjson

from traffic_os.common.logging import get_logger
from traffic_os.common.timeutil import utcnow
from traffic_os.enforcement.anpr import SyntheticANPR
from traffic_os.schemas import Challan, Violation

log = get_logger("enforcement.challan")

FINES = {
    "speeding": 1000.0,
    "red_light": 1500.0,
    "wrong_side": 1500.0,
    "illegal_parking": 500.0,
    "no_helmet": 500.0,
    "no_seatbelt": 500.0,
    "mobile_use": 1000.0,
    "triple_riding": 1000.0,
    "zebra_violation": 500.0,
}


class ChallanService:
    def __init__(self, storage, anpr=None) -> None:
        self.storage = storage
        self.anpr = anpr or SyntheticANPR()

    def _store_evidence(self, challan_id: str, payload: dict) -> tuple[str, str]:
        data = orjson.dumps(payload)
        digest = hashlib.sha256(data).hexdigest()
        key = f"evidence/challan/{challan_id}.json"
        ref = self.storage.blob.put(key, data)
        return ref, digest

    def issue_for_violation(self, v: Violation, *, plate: str | None = None) -> Challan:
        cid = f"CH-{uuid.uuid4().hex[:10]}"
        plate = plate or self.anpr.recognize_track(v.vehicle_track_id)
        ts = utcnow()
        payload = {
            "challan_id": cid,
            "plate": plate,
            "violation_id": v.id,
            "violation_type": v.type.value,
            "ts": v.ts.isoformat(),
            "location": {"lat": v.lat, "lon": v.lon},
            "segment_id": v.segment_id,
            "detail": v.detail,
        }
        ref, digest = self._store_evidence(cid, payload)
        challan = Challan(
            id=cid,
            plate=plate,
            violation_type=v.type.value,
            ts=ts,
            lat=v.lat,
            lon=v.lon,
            segment_id=v.segment_id,
            vehicle_track_id=v.vehicle_track_id,
            fine_inr=FINES.get(v.type.value, 500.0),
            evidence_ref=ref,
            evidence_sha256=digest,
            status="issued",
            custody=[{"ts": ts.isoformat(), "actor": "anpr-system", "action": "captured+signed"}],
        )
        self.storage.db.upsert("challan", challan)
        return challan

    def issue_for_violations(self, violations: list[Violation]) -> list[Challan]:
        return [self.issue_for_violation(v) for v in violations]

    def verify_evidence(self, challan_id: str) -> bool:
        """Re-hash stored evidence and compare to the signature (tamper check)."""
        ch = self.storage.db.get("challan", challan_id, Challan)
        if ch is None or not ch.evidence_ref:
            return False
        key = ch.evidence_ref.replace("/blobs/", "")
        data = self.storage.blob.get(key)
        if data is None:
            return False
        return hashlib.sha256(data).hexdigest() == ch.evidence_sha256

    def set_status(self, challan_id: str, status: str, actor: str = "officer") -> Challan | None:
        ch = self.storage.db.get("challan", challan_id, Challan)
        if ch is None:
            return None
        ch.status = status
        ch.custody.append(
            {"ts": utcnow().isoformat(), "actor": actor, "action": f"status:{status}"}
        )
        self.storage.db.upsert("challan", ch)
        return ch

    def recent(self, limit: int = 100) -> list[Challan]:
        return self.storage.db.find("challan", Challan, order_by_ts=True, desc=True, limit=limit)

    def summary(self) -> dict:
        rows = self.storage.db.find("challan", Challan, limit=10000)
        total_fine = sum(c.fine_inr for c in rows)
        by_type: dict[str, int] = {}
        for c in rows:
            by_type[c.violation_type] = by_type.get(c.violation_type, 0) + 1
        paid = sum(1 for c in rows if c.status == "paid")
        return {
            "total": len(rows),
            "paid": paid,
            "total_fine_inr": round(total_fine, 1),
            "by_type": by_type,
        }
