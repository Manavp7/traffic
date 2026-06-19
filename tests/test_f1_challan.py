"""F1: ANPR + e-Challan + evidence locker."""

from __future__ import annotations

from datetime import datetime

from traffic_os.enforcement import FINES, ChallanService, plate_for_track
from traffic_os.schemas import Challan, Violation, ViolationType
from traffic_os.storage import memory_storage


def _violation(tid="V1", vtype=ViolationType.SPEEDING):
    return Violation(
        id="vio-1",
        ts=datetime(2025, 1, 1, 9, 0, 0),
        type=vtype,
        lat=12.97,
        lon=77.6,
        segment_id="S1",
        vehicle_track_id=tid,
        detail="62 km/h in 40",
    )


def test_plate_is_deterministic_and_realistic():
    p1 = plate_for_track("V1")
    p2 = plate_for_track("V1")
    assert p1 == p2
    assert len(p1) >= 8 and p1[:2].isalpha()


def test_issue_challan_with_signed_evidence():
    st = memory_storage()
    svc = ChallanService(st)
    ch = svc.issue_for_violation(_violation())
    assert isinstance(ch, Challan)
    assert ch.fine_inr == FINES["speeding"]
    assert ch.plate == plate_for_track("V1")
    assert ch.evidence_ref and ch.evidence_sha256
    assert ch.custody and ch.custody[0]["action"].startswith("captured")
    # persisted + retrievable
    assert st.db.get("challan", ch.id, Challan) is not None


def test_evidence_tamper_detection():
    st = memory_storage()
    svc = ChallanService(st)
    ch = svc.issue_for_violation(_violation())
    assert svc.verify_evidence(ch.id) is True
    # tamper with the stored evidence -> signature mismatch
    key = ch.evidence_ref.replace("/blobs/", "")
    st.blob.put(key, b'{"tampered": true}')
    assert svc.verify_evidence(ch.id) is False


def test_status_transition_and_summary():
    st = memory_storage()
    svc = ChallanService(st)
    c1 = svc.issue_for_violation(_violation("V1", ViolationType.RED_LIGHT))
    svc.issue_for_violation(_violation("V2", ViolationType.SPEEDING))
    svc.set_status(c1.id, "paid")
    summ = svc.summary()
    assert summ["total"] == 2
    assert summ["paid"] == 1
    assert summ["total_fine_inr"] == FINES["red_light"] + FINES["speeding"]
    assert summ["by_type"]["red_light"] == 1
