"""F3: enforcement zones + auto challan issuance."""

from __future__ import annotations

from datetime import datetime

from traffic_os.enforcement import ZoneService
from traffic_os.schemas import Challan, EnforcementZone, Violation, ViolationType
from traffic_os.storage import memory_storage


def _v(vtype, seg, tid):
    return Violation(
        id=f"v-{tid}",
        ts=datetime(2025, 1, 1, 9),
        type=vtype,
        lat=12.97,
        lon=77.6,
        segment_id=seg,
        vehicle_track_id=tid,
    )


def test_zone_auto_issues_matching_violation():
    st = memory_storage()
    svc = ZoneService(st)
    svc.add_zone(EnforcementZone(id="Z1", name="MG Rd cam", kind="red_light", segment_id="S5"))
    violations = [
        _v(ViolationType.RED_LIGHT, "S5", "A"),  # in zone, matching -> challan
        _v(ViolationType.RED_LIGHT, "S9", "B"),  # not in any zone -> ignored
        _v(ViolationType.SPEEDING, "S5", "C"),  # in zone but wrong kind -> ignored
    ]
    issued = svc.enforce(violations)
    assert len(issued) == 1
    assert issued[0].violation_type == "red_light"
    assert issued[0].vehicle_track_id == "A"
    # challan persisted with signed evidence
    stored = st.db.find("challan", Challan)
    assert len(stored) == 1 and stored[0].evidence_sha256


def test_speed_zone():
    st = memory_storage()
    svc = ZoneService(st)
    svc.add_zone(
        EnforcementZone(id="Z2", name="NH speed", kind="speed", segment_id="S1", speed_limit_kph=60)
    )
    issued = svc.enforce([_v(ViolationType.SPEEDING, "S1", "X")])
    assert len(issued) == 1 and issued[0].violation_type == "speeding"
