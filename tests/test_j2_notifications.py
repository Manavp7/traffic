"""J2: citizen notifications + geofenced alerts."""

from __future__ import annotations

from datetime import datetime

from traffic_os.integrations.notify import NotificationService
from traffic_os.schemas import CitizenReport
from traffic_os.storage import memory_storage


def test_send_and_recent():
    st = memory_storage()
    svc = NotificationService(st)
    n = svc.send("+9199999", "Heavy congestion on MG Road")
    assert n.status == "sent"
    assert svc.recent()[0].message == "Heavy congestion on MG Road"


def test_geofence_targets_nearby_reports():
    st = memory_storage()
    # one report inside the fence, one far away
    st.db.upsert(
        "citizen_report",
        CitizenReport(id="R-near", ts=datetime.now(), type="pothole", lat=12.9000, lon=77.6000),
    )
    st.db.upsert(
        "citizen_report",
        CitizenReport(id="R-far", ts=datetime.now(), type="pothole", lat=12.9500, lon=77.6500),
    )
    svc = NotificationService(st)
    res = svc.geofence_alert(12.9001, 77.6001, 300.0, "Flooding ahead, avoid the area")
    assert res["recipients"] == 1  # only the nearby report
    assert res["broadcast_id"]
