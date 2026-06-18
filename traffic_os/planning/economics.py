"""Economic Loss Engine — turn congestion into money, fuel and CO2.

Government decision-makers respond to "₹X lakh/day", not "occupancy 72%". This
converts delay into vehicle-hours lost, litres of fuel burnt, CO2 emitted and a
rupee cost, using configurable value-of-time / fuel / emission factors.
"""

from __future__ import annotations

from dataclasses import dataclass

from traffic_os.common.config import Settings, get_settings
from traffic_os.common.timeutil import utcnow
from traffic_os.schemas import EconomicImpact, SegmentMetric
from traffic_os.simulation.network import RoadNetwork


@dataclass
class EconomicLossEngine:
    settings: Settings

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> EconomicLossEngine:
        return cls(settings or get_settings())

    def segment_rate(self, metric: SegmentMetric, seg) -> dict[str, float]:
        """Instantaneous loss *rate* for one segment (per hour)."""
        speed_ratio = min(metric.speed_kph / max(seg.speed_limit_kph, 1.0), 1.0)
        delay_fraction = max(0.0, 1.0 - speed_ratio)
        # vehicle-hours of delay accrued per hour = vehicles present * fraction of time lost
        delay_veh_h = metric.vehicle_count * delay_fraction
        fuel = delay_veh_h * self.settings.idle_fuel_litres_per_hour
        co2 = fuel * self.settings.co2_kg_per_litre
        cost = (
            delay_veh_h * self.settings.value_of_time_inr_per_hour
            + fuel * self.settings.fuel_price_inr_per_litre
        )
        return {"delay_veh_h": delay_veh_h, "fuel_litres": fuel, "co2_kg": co2, "cost_inr": cost}

    def city_impact(
        self,
        net: RoadNetwork,
        metrics: dict[str, SegmentMetric],
        *,
        window_h: float = 24.0,
    ) -> EconomicImpact:
        """Aggregate current loss rate across the city and project over ``window_h``."""
        agg = {"delay_veh_h": 0.0, "fuel_litres": 0.0, "co2_kg": 0.0, "cost_inr": 0.0}
        for sid, m in metrics.items():
            seg = net.segments.get(sid)
            if seg is None:
                continue
            r = self.segment_rate(m, seg)
            for k in agg:
                agg[k] += r[k]
        return EconomicImpact(
            scope="city",
            scope_id="city",
            ts=utcnow(),
            window_h=window_h,
            delay_veh_h=round(agg["delay_veh_h"] * window_h, 1),
            fuel_litres=round(agg["fuel_litres"] * window_h, 1),
            co2_kg=round(agg["co2_kg"] * window_h, 1),
            time_loss_h=round(agg["delay_veh_h"] * window_h, 1),
            cost_inr=round(agg["cost_inr"] * window_h, 1),
        )

    def segment_impacts(
        self,
        net: RoadNetwork,
        metrics: dict[str, SegmentMetric],
        *,
        window_h: float = 24.0,
        top_n: int | None = None,
    ) -> list[EconomicImpact]:
        out = []
        for sid, m in metrics.items():
            seg = net.segments.get(sid)
            if seg is None:
                continue
            r = self.segment_rate(m, seg)
            out.append(
                EconomicImpact(
                    scope="segment",
                    scope_id=sid,
                    ts=m.ts,
                    window_h=window_h,
                    delay_veh_h=round(r["delay_veh_h"] * window_h, 2),
                    fuel_litres=round(r["fuel_litres"] * window_h, 2),
                    co2_kg=round(r["co2_kg"] * window_h, 2),
                    time_loss_h=round(r["delay_veh_h"] * window_h, 2),
                    cost_inr=round(r["cost_inr"] * window_h, 2),
                )
            )
        out.sort(key=lambda e: e.cost_inr, reverse=True)
        return out[:top_n] if top_n else out


def format_inr(amount: float) -> str:
    """Indian numbering: lakh / crore."""
    if amount >= 1e7:
        return f"₹{amount / 1e7:.2f} crore"
    if amount >= 1e5:
        return f"₹{amount / 1e5:.2f} lakh"
    return f"₹{amount:,.0f}"
