"""Wave H: smart parking, multimodal planner, dispatch, evacuation, convoy."""

from __future__ import annotations

from datetime import datetime

from traffic_os.decision import (
    DispatchService,
    nearest_exits,
    plan_convoy,
    plan_evacuation,
)
from traffic_os.mobility import ParkingService, TransitService, TripPlanner
from traffic_os.schemas import Incident, IncidentStatus, IncidentType
from traffic_os.simulation import SimulationEngine, build_grid_network, save_network
from traffic_os.storage import memory_storage


def _city(demand=70, ticks=20):
    net = build_grid_network(5)
    st = memory_storage()
    save_network(net, st.db)
    st.settings.sim_demand_scale = demand
    eng = SimulationEngine(net, st.settings)
    for _ in range(ticks):
        eng.persist_live(st, eng.step_once())
    return net, st


def test_smart_parking():
    net, st = _city()
    svc = ParkingService(st)
    svc.seed_lots(6)
    status = svc.status()
    assert len(status) == 6
    assert all(0 <= s["occupancy_pct"] <= 100 for s in status)
    nearest = svc.nearest_free(net.junctions["J0_0"].lat, net.junctions["J0_0"].lon)
    assert nearest is not None and nearest["available"] >= 1


def test_multimodal_planner():
    net, st = _city()
    transit = TransitService(st)
    transit.build_routes(4)
    plan = TripPlanner(st, transit).plan("J0_0", "J4_4")
    assert plan["options"], "expected at least a car option"
    assert plan["recommended"]
    modes = {o["mode"] for o in plan["options"]}
    assert "car" in modes


def test_incident_auto_dispatch():
    net, st = _city()
    inc = Incident(
        id="I1",
        ts=datetime(2025, 1, 1, 9),
        type=IncidentType.ACCIDENT,
        lat=net.junctions["J2_2"].lat,
        lon=net.junctions["J2_2"].lon,
        segment_id="S1",
        severity=0.8,
        status=IncidentStatus.ACTIVE,
    )
    results = DispatchService(st).dispatch([inc], net)
    assert len(results) == 1
    assert results[0].unit_id is not None
    assert results[0].note == "dispatched"


def test_disaster_evacuation():
    net, st = _city()
    zone = ["J2_2", "J2_3"]
    c = net.junctions["J2_2"]
    exits = nearest_exits(net, (c.lat, c.lon), k=3)
    plan = plan_evacuation(net, zone, exits, population=4000, exit_capacity=3000)
    assert plan["evacuated"] > 0
    assert plan["assignments"]
    assert plan["evacuated"] <= plan["population"]


def test_vip_convoy_green_wave():
    net, st = _city()
    a, b = net.junctions["J0_0"], net.junctions["J4_4"]
    plan = plan_convoy(net, st, a.lat, a.lon, b.lat, b.lon)
    assert plan["feasible"]
    assert plan["route_segments"]
    assert plan["eta_s"] > 0
    # green wave times are monotonically increasing along the route
    times = [g["green_at_s"] for g in plan["green_wave"]]
    assert times == sorted(times)
