"""J6: simulation calibration + edge store-and-forward buffer."""

from __future__ import annotations

from datetime import datetime

from traffic_os.edge import EdgeBuffer
from traffic_os.schemas import CameraFrameMetric
from traffic_os.simulation import build_grid_network, calibrate_demand


def _metric(i):
    return CameraFrameMetric(
        id=f"m{i}", source_id="cam", ts=datetime.now(), frame=i, total_vehicles=i
    )


def test_edge_buffer_store_and_forward():
    received = []
    buf = EdgeBuffer(received.append)
    buf.record(_metric(0))  # online -> delivered immediately
    assert len(received) == 1
    buf.set_online(False)
    buf.record(_metric(1))  # offline -> buffered
    buf.record(_metric(2))
    assert buf.pending == 2
    assert len(received) == 1
    flushed = buf.set_online(True)  # reconnect -> flush in order
    assert flushed == 2
    assert [m.id for m in received] == ["m0", "m1", "m2"]
    assert buf.pending == 0


def test_calibration_converges_toward_target():
    net = build_grid_network(5)
    target = 800
    result = calibrate_demand(net, target, ticks=40, warmup=15, iters=6)
    assert result["target_vehicles"] == target
    assert result["demand_scale"] > 0
    assert result["achieved_vehicles"] > 0
    # calibration should land within a reasonable band of the target
    assert result["error_pct"] <= 60.0
