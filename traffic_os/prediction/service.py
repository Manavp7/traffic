"""PredictionService — trains and serves forecasts + accident risk."""

from __future__ import annotations

from datetime import timedelta

import pandas as pd

from traffic_os.common.logging import get_logger
from traffic_os.prediction.accident_risk import RiskModel
from traffic_os.prediction.features import FORECAST_FEATURES, load_frame
from traffic_os.prediction.forecast import ForecastModel
from traffic_os.schemas import AccidentRisk, CityEvent, Forecast, SegmentMetric, Weather
from traffic_os.simulation.network import RoadNetwork, load_network

log = get_logger("prediction.service")

DEFAULT_HORIZONS = (15, 30, 60)


class PredictionService:
    def __init__(self, storage) -> None:
        self.storage = storage
        self._net: RoadNetwork | None = None
        self.frame: pd.DataFrame | None = None
        self.models: dict[int, ForecastModel] = {}
        self.risk = RiskModel()
        self.backtests: dict[int, dict] = {}

    @property
    def net(self) -> RoadNetwork:
        if self._net is None or not self._net.segments:
            self._net = load_network(self.storage.db)
        return self._net

    def train(self, horizons: tuple[int, ...] = DEFAULT_HORIZONS) -> dict:
        self.frame = load_frame(self.storage, self.net)
        if self.frame.empty:
            raise ValueError("no history to train on; run `history` first")
        results = {}
        for h in horizons:
            fm = ForecastModel(h)
            bt = fm.backtest(self.frame)
            fm.train(self.frame)
            self.models[h] = fm
            self.backtests[h] = bt.__dict__
            results[h] = bt.__dict__
        self.risk.train(self.frame)
        return {"forecast": results, "accident_risk_auc": self.risk.auc}

    # -- forecasting ------------------------------------------------------ #
    def _latest_rows(self) -> pd.DataFrame:
        assert self.frame is not None
        feat_ok = self.frame.dropna(subset=FORECAST_FEATURES)
        return feat_ok.sort_values("ts").groupby("segment_id").tail(1)

    def forecast(self, segment_id: str, horizon_min: int = 60) -> Forecast | None:
        if horizon_min not in self.models:
            self._ensure_trained()
        model = self.models.get(horizon_min)
        if model is None:
            return None
        rows = self._latest_rows()
        row = rows[rows["segment_id"] == segment_id]
        if row.empty:
            return None
        feat = row.iloc[0]
        pred, lo, hi = model.predict_row({f: float(feat[f]) for f in FORECAST_FEATURES})
        pred, lo, hi = self._event_adjust(segment_id, feat["ts"], pred, lo, hi, horizon_min)
        ts_made = pd.Timestamp(feat["ts"]).to_pydatetime()
        return Forecast(
            segment_id=segment_id,
            horizon_min=horizon_min,
            ts_made=ts_made,
            ts_target=ts_made + timedelta(minutes=horizon_min),
            predicted_congestion=round(pred, 1),
            ci_low=round(lo, 1),
            ci_high=round(hi, 1),
            model="xgboost",
        )

    def forecast_all(self, horizon_min: int = 60, *, persist: bool = True) -> list[Forecast]:
        if horizon_min not in self.models:
            self._ensure_trained()
        out = []
        for sid in self.net.segments:
            f = self.forecast(sid, horizon_min)
            if f is not None:
                out.append(f)
        if persist and out:
            self.storage.db.clear("forecast")
            self.storage.db.upsert_many("forecast", out)
        return out

    def _event_adjust(self, segment_id, ts, pred, lo, hi, horizon_min):
        """Bump forecast if an event near this segment's junction is active at target time."""
        seg = self.net.segments.get(segment_id)
        if seg is None:
            return pred, lo, hi
        target = pd.Timestamp(ts).to_pydatetime() + timedelta(minutes=horizon_min)
        events = self.storage.db.find("city_event", CityEvent, limit=200)
        for ev in events:
            near = ev.nearest_junction in (seg.from_junction, seg.to_junction)
            active = (
                ev.start - timedelta(hours=1) <= target.replace(tzinfo=ev.start.tzinfo) <= ev.end
            )
            if near and active:
                boost = min(25.0, ev.expected_attendance / 2000.0)
                return min(100, pred + boost), min(100, lo + boost), min(100, hi + boost)
        return pred, lo, hi

    # -- accident risk ---------------------------------------------------- #
    def accident_risk_all(self, *, persist: bool = True) -> list[AccidentRisk]:
        self._ensure_trained()
        weathers = self.storage.db.find("weather", Weather, order_by_ts=True, desc=True, limit=1)
        weather = weathers[0] if weathers else None
        latest = {m.segment_id: m for m in self.storage.db.latest_per_segment(SegmentMetric)}
        out = []
        for sid, m in latest.items():
            seg = self.net.segments.get(sid)
            if seg is None:
                continue
            feat = RiskModel.features_from_metric(m, seg, weather)
            pct, drivers = self.risk.predict_pct(feat)
            out.append(AccidentRisk(segment_id=sid, ts=m.ts, risk_pct=pct, drivers=drivers))
        if persist and out:
            self.storage.db.clear("accident_risk")
            self.storage.db.upsert_many("accident_risk", out)
        return out

    def top_risk(self, n: int = 10) -> list[AccidentRisk]:
        risks = self.accident_risk_all(persist=False)
        risks.sort(key=lambda r: r.risk_pct, reverse=True)
        return risks[:n]

    def _ensure_trained(self) -> None:
        if not self.models or self.frame is None:
            self.train()
