"""Accident-risk prediction.

Upgrades incident handling from reactive ("accident happened") to predictive
("accident likely, risk = 91%"). Drivers: rainfall, speeding, density and
historical accident propensity.

NOTE: no public accident-labelled dataset is bundled, so training labels are drawn
from a documented latent-hazard function of the real feature columns; the model
must then *recover* that signal (reported via held-out ROC-AUC). On a real
deployment this is swapped for logged accident records — the pipeline is identical.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from traffic_os.common.logging import get_logger
from traffic_os.simulation.microsim import JAM_DENSITY_PER_LANE

log = get_logger("prediction.risk")

RISK_FEATURES = [
    "rain_norm", "density_norm", "speed_ratio", "occupancy_norm", "peak", "importance"
]


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def _build(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame()
    out["rain_norm"] = np.clip(df["rain_mm"] / 50.0, 0, 1)
    out["density_norm"] = np.clip(df["density"] / JAM_DENSITY_PER_LANE, 0, 1)
    out["speed_ratio"] = np.clip(df["speed"] / df["speed_limit"].clip(lower=1), 0, 2)
    out["occupancy_norm"] = np.clip(df["occupancy"] / 100.0, 0, 1)
    hour = df["hour_sin"]  # proxy; peak captured below
    out["peak"] = (np.abs(df["hour_cos"]) < 0.5).astype(float)  # mid-morning/evening-ish
    out["importance"] = df["importance"]
    out["_hour_sin"] = hour
    return out


def _latent_label(feat: pd.DataFrame, rng: np.random.Generator) -> np.ndarray:
    logit = (
        -3.2
        + 2.6 * feat["density_norm"]
        + 2.2 * feat["rain_norm"]
        + 1.1 * feat["occupancy_norm"]
        + 0.7 * feat["peak"]
        + 0.6 * feat["importance"]
        - 1.0 * np.clip(feat["speed_ratio"] - 0.5, 0, None)
    )
    p = _sigmoid(logit.values)
    return (rng.random(len(p)) < p).astype(int)


@dataclass
class RiskModel:
    auc: float = 0.0
    positive_rate: float = 0.0

    def __post_init__(self):
        from typing import Any

        self.model: Any = None

    def _new_model(self):
        from xgboost import XGBClassifier

        return XGBClassifier(
            n_estimators=160, max_depth=5, learning_rate=0.1,
            subsample=0.9, colsample_bytree=0.9, n_jobs=4, random_state=7,
            eval_metric="logloss",
        )

    def train(self, df: pd.DataFrame, seed: int = 7) -> RiskModel:
        from sklearn.metrics import roc_auc_score

        feat = _build(df)
        rng = np.random.default_rng(seed)
        y = _latent_label(feat, rng)
        X = feat[RISK_FEATURES]
        n = len(X)
        split = int(n * 0.8)
        self.model = self._new_model()
        self.model.fit(X.iloc[:split], y[:split])
        if y[split:].sum() > 0 and y[split:].sum() < len(y[split:]):
            proba = self.model.predict_proba(X.iloc[split:])[:, 1]
            self.auc = round(float(roc_auc_score(y[split:], proba)), 3)
        self.positive_rate = round(float(y.mean()), 3)
        log.info("Accident-risk model trained: AUC=%.3f pos_rate=%.3f", self.auc, self.positive_rate)
        return self

    def predict_pct(self, feat_row: dict) -> tuple[float, dict[str, float]]:
        if self.model is None:
            raise RuntimeError("risk model not trained")
        x = np.array([[feat_row[f] for f in RISK_FEATURES]], dtype=float)
        p = float(self.model.predict_proba(x)[0, 1])
        drivers = {
            "rain": round(feat_row["rain_norm"], 3),
            "density": round(feat_row["density_norm"], 3),
            "speeding": round(max(0.0, feat_row["speed_ratio"] - 1.0), 3),
            "occupancy": round(feat_row["occupancy_norm"], 3),
        }
        return round(p * 100.0, 1), drivers

    @staticmethod
    def features_from_metric(metric, seg, weather) -> dict:
        rain = weather.rain_mm if weather else 0.0
        return {
            "rain_norm": min(rain / 50.0, 1.0),
            "density_norm": min(metric.density_pcu_per_km / JAM_DENSITY_PER_LANE, 1.0),
            "speed_ratio": min(metric.speed_kph / max(seg.speed_limit_kph, 1), 2.0),
            "occupancy_norm": min(metric.occupancy_pct / 100.0, 1.0),
            "peak": 1.0 if 7 <= metric.ts.hour <= 10 or 17 <= metric.ts.hour <= 20 else 0.0,
            "importance": 0.5,
        }
