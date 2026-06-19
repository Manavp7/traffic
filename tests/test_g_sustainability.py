"""Wave G: sustainability — AQI, pricing, EV demand, carbon."""

from __future__ import annotations

from traffic_os.simulation import SimulationEngine, build_grid_network, save_network
from traffic_os.storage import memory_storage
from traffic_os.sustainability import SustainabilityService
from traffic_os.sustainability.service import aqi_category


def _city(demand=90, ticks=30):
    net = build_grid_network(5)
    st = memory_storage()
    save_network(net, st.db)
    st.settings.sim_demand_scale = demand
    eng = SimulationEngine(net, st.settings)
    for _ in range(ticks):
        eng.persist_live(st, eng.step_once())
    return st


def test_aqi_category_thresholds():
    assert aqi_category(30) == "good"
    assert aqi_category(150) == "moderate"
    assert aqi_category(450) == "severe"


def test_aqi_and_carbon():
    svc = SustainabilityService(_city())
    aqi = svc.aqi()
    assert 0 <= aqi["aqi"] <= 500
    assert aqi["category"]
    carbon = svc.carbon()
    assert carbon["co2_kg_per_day"] >= 0
    assert carbon["co2_saved_kg_per_day"] >= 0
    assert 0 <= carbon["net_zero_progress_pct"] <= 100


def test_pricing_and_ev():
    svc = SustainabilityService(_city(demand=120))
    pricing = svc.pricing()
    assert pricing["priced_segments"] >= 0
    assert "est_revenue_human" in pricing
    assert 0 <= pricing["est_diversion_pct"] <= 40
    ev = svc.ev_demand()
    assert ev["charging_demand_kwh"] >= 0
    assert ev["peak_grid_load_kw"] >= 0


def test_summary_has_all_sections():
    svc = SustainabilityService(_city())
    s = svc.summary()
    assert set(s.keys()) == {"aqi", "pricing", "ev", "carbon"}
