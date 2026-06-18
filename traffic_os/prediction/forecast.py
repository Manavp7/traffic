"""Congestion forecasting (XGBoost) with confidence intervals + backtest baselines."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from traffic_os.common.logging import get_logger
from traffic_os.prediction.features import FORECAST_FEATURES, make_supervised

log = get_logger("prediction.forecast")

# history step is 15 min; horizon in minutes -> steps
HISTORY_STEP_MIN = 15


def horizon_to_steps(horizon_min: int) -> int:
    return max(1, round(horizon_min / HISTORY_STEP_MIN))


@dataclass
class BacktestResult:
    horizon_min: int
    mae: float
    mape: float
    persistence_mae: float
    skill_vs_persistence: float  # 1 - mae/persistence_mae (higher is better)
    n_test: int


class ForecastModel:
    def __init__(self, horizon_min: int = 60) -> None:
        self.horizon_min = horizon_min
        self.steps = horizon_to_steps(horizon_min)
        self.model: Any = None
        self.resid_std = 8.0

    def _new_model(self):
        from xgboost import XGBRegressor

        return XGBRegressor(
            n_estimators=200, max_depth=6, learning_rate=0.1,
            subsample=0.9, colsample_bytree=0.9, n_jobs=4,
            random_state=42, objective="reg:squarederror",
        )

    def train(self, df: pd.DataFrame) -> ForecastModel:
        X, y, _ = make_supervised(df, self.steps)
        if len(X) < 50:
            raise ValueError("not enough data to train forecast model")
        self.model = self._new_model()
        self.model.fit(X, y)
        pred = self.model.predict(X)
        self.resid_std = float(np.std(y - pred)) or 8.0
        log.info("Forecast model trained: horizon=%dmin rows=%d resid_std=%.2f",
                 self.horizon_min, len(X), self.resid_std)
        return self

    def backtest(self, df: pd.DataFrame, test_frac: float = 0.2) -> BacktestResult:
        X, y, ts = make_supervised(df, self.steps)
        order = np.argsort(ts.values)
        X, y = X.iloc[order].reset_index(drop=True), y.iloc[order].reset_index(drop=True)
        split = int(len(X) * (1 - test_frac))
        Xtr, Xte = X.iloc[:split], X.iloc[split:]
        ytr, yte = y.iloc[:split], y.iloc[split:]
        model = self._new_model()
        model.fit(Xtr, ytr)
        pred = model.predict(Xte)
        mae = float(np.mean(np.abs(pred - yte)))
        denom = np.clip(np.abs(yte.values), 5.0, None)
        mape = float(np.mean(np.abs(pred - yte.values) / denom) * 100)
        # persistence baseline: predict "current" congestion
        persist = Xte["congestion"].values
        persist_mae = float(np.mean(np.abs(persist - yte.values)))
        skill = 1 - mae / persist_mae if persist_mae else 0.0
        return BacktestResult(
            horizon_min=self.horizon_min, mae=round(mae, 2), mape=round(mape, 2),
            persistence_mae=round(persist_mae, 2), skill_vs_persistence=round(skill, 3),
            n_test=len(Xte),
        )

    def predict_row(self, feat: dict) -> tuple[float, float, float]:
        import numpy as np

        if self.model is None:
            raise RuntimeError("model not trained")
        x = np.array([[feat[f] for f in FORECAST_FEATURES]], dtype=float)
        pred = float(self.model.predict(x)[0])
        pred = max(0.0, min(100.0, pred))
        ci = 1.28 * self.resid_std  # ~80% interval
        return pred, max(0.0, pred - ci), min(100.0, pred + ci)
