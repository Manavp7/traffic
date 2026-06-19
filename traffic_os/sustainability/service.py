"""Sustainability engine: air quality, dynamic tolling, EV demand, carbon tracking."""

from __future__ import annotations

from traffic_os.common.config import Settings
from traffic_os.intelligence.current import current_metrics
from traffic_os.planning.economics import EconomicLossEngine, format_inr
from traffic_os.schemas import SegmentMetric, Weather
from traffic_os.simulation.network import RoadNetwork, load_network

# pricing
PRICE_BASE_INR = 20.0
PRICE_MAX_INR = 120.0
PRICE_CONGESTION_THRESHOLD = 40.0
DIVERSION_ELASTICITY = 0.0025  # share diverted per ₹ of average toll

# EV
EV_SHARE = 0.15
EV_KWH_PER_TRIP = 6.0

# AQI
AQI_BASE = 45.0


def aqi_category(aqi: float) -> str:
    if aqi <= 50:
        return "good"
    if aqi <= 100:
        return "satisfactory"
    if aqi <= 200:
        return "moderate"
    if aqi <= 300:
        return "poor"
    if aqi <= 400:
        return "very poor"
    return "severe"


class SustainabilityService:
    def __init__(self, storage) -> None:
        self.storage = storage
        self.settings: Settings = getattr(storage, "settings", None) or Settings(mode="dev")
        self.econ = EconomicLossEngine.from_settings(self.settings)
        self._net: RoadNetwork | None = None
        self._baseline_co2: float | None = None

    @property
    def net(self) -> RoadNetwork:
        if self._net is None or not self._net.segments:
            self._net = load_network(self.storage.db)
        return self._net

    def _metrics(self) -> dict[str, SegmentMetric]:
        return current_metrics(self.storage.db)

    def _avg_congestion(self, metrics) -> float:
        if not metrics:
            return 0.0
        return sum(m.congestion_score for m in metrics.values()) / len(metrics)

    # -- G1 air quality --------------------------------------------------- #
    def aqi(self) -> dict:
        metrics = self._metrics()
        avg = self._avg_congestion(metrics)
        weathers = self.storage.db.find("weather", Weather, order_by_ts=True, desc=True, limit=1)
        rain_clean = 0.85 if weathers and weathers[0].rain_mm > 5 else 1.0
        aqi = round(min(500.0, (AQI_BASE + avg * 2.2) * rain_clean), 0)
        # crude health-impact proxy: % of population at elevated risk
        affected = round(min(100.0, max(0.0, (aqi - 100) / 4.0)), 1)
        return {
            "aqi": aqi,
            "category": aqi_category(aqi),
            "avg_congestion": round(avg, 1),
            "health_impact_pct_at_risk": affected,
            "advisory": "limit outdoor activity" if aqi > 200 else "acceptable",
        }

    # -- G2 dynamic tolling ---------------------------------------------- #
    def pricing(self) -> dict:
        net = self.net
        metrics = self._metrics()
        prices: list[dict] = []
        revenue = 0.0
        for sid, m in metrics.items():
            if m.congestion_score < PRICE_CONGESTION_THRESHOLD or sid not in net.segments:
                continue
            price = round(PRICE_BASE_INR + m.congestion_score / 100.0 * PRICE_MAX_INR, 0)
            revenue += price * m.vehicle_count
            prices.append(
                {
                    "segment_id": sid,
                    "name": net.segments[sid].name,
                    "congestion": m.congestion_score,
                    "toll_inr": price,
                }
            )
        prices.sort(key=lambda p: float(p["toll_inr"]), reverse=True)
        avg_price = sum(float(p["toll_inr"]) for p in prices) / len(prices) if prices else 0.0
        diversion = round(min(0.4, avg_price * DIVERSION_ELASTICITY) * 100, 1)
        return {
            "priced_segments": len(prices),
            "avg_toll_inr": round(avg_price, 0),
            "est_revenue_per_hour_inr": round(revenue, 0),
            "est_revenue_human": format_inr(revenue * 24),
            "est_diversion_pct": diversion,
            "top": prices[:15],
        }

    # -- G3 EV charging demand ------------------------------------------- #
    def ev_demand(self, ev_share: float = EV_SHARE) -> dict:
        metrics = self._metrics()
        total_vehicles = sum(m.vehicle_count for m in metrics.values())
        ev_trips = total_vehicles * ev_share
        kwh = ev_trips * EV_KWH_PER_TRIP
        peak_kw = kwh * 0.4  # assume 40% charges within the peak hour
        return {
            "ev_share_pct": round(ev_share * 100, 0),
            "ev_vehicles": round(ev_trips, 0),
            "charging_demand_kwh": round(kwh, 0),
            "peak_grid_load_kw": round(peak_kw, 0),
            "grid_alert": peak_kw > 5000,
        }

    # -- G4 carbon ------------------------------------------------------- #
    def carbon(self, net_zero_target_kg: float = 50000.0) -> dict:
        metrics = self._metrics()
        impact = self.econ.city_impact(self.net, metrics)
        current = impact.co2_kg
        # baseline = emissions if everything were gridlocked (worst case reference)
        if self._baseline_co2 is None:
            self._baseline_co2 = max(current * 1.6, current + 1.0)
        saved = max(0.0, self._baseline_co2 - current)
        toward = round(min(100.0, (1 - current / max(self._baseline_co2, 1)) * 100), 1)
        return {
            "co2_kg_per_day": round(current, 0),
            "baseline_co2_kg_per_day": round(self._baseline_co2, 0),
            "co2_saved_kg_per_day": round(saved, 0),
            "net_zero_progress_pct": toward,
            "target_kg_per_day": net_zero_target_kg,
        }

    def summary(self) -> dict:
        return {
            "aqi": self.aqi(),
            "pricing": self.pricing(),
            "ev": self.ev_demand(),
            "carbon": self.carbon(),
        }
