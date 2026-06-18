"""E16: public-transport + freight modules."""

from __future__ import annotations

from traffic_os.mobility import FreightService, TransitService
from traffic_os.simulation import SimulationEngine, build_grid_network, save_network
from traffic_os.storage import memory_storage


def _running_city(demand=70, ticks=25):
    net = build_grid_network(5)
    st = memory_storage()
    save_network(net, st.db)
    st.settings.sim_demand_scale = demand
    eng = SimulationEngine(net, st.settings)
    for _ in range(ticks):
        eng.persist_live(st, eng.step_once())
    return net, st


def test_transit_routes_and_status():
    net, st = _running_city()
    svc = TransitService(st)
    routes = svc.build_routes(n=4)
    assert routes, "expected bus routes"
    assert all(r.segments and r.stops for r in routes)
    status = svc.status()
    assert len(status) == len(routes)
    for s in status:
        assert s["current_min"] >= 0
        assert "on_time" in s
        assert 0 <= s["passenger_load_pct"] <= 100


def test_freight_plan():
    net, st = _running_city()
    svc = FreightService(st)
    plan = svc.plan(n=6, seed=1)
    assert plan["trucks"] > 0
    assert plan["total_distance_km"] > 0
    assert plan["total_fuel_litres"] > 0
    assert plan["total_cost_inr"] > 0
    # each trip's current ETA is >= free-flow time
    for t in plan["trips"]:
        assert t["eta_s"] >= t["free_flow_s"] - 1e-6
