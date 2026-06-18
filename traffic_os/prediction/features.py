"""Feature engineering for forecasting and accident-risk models.

Builds a tidy pandas frame from historical ``SegmentMetric`` + ``Weather`` series
with temporal, lag/rolling, weather and static (road) features.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from traffic_os.schemas import SegmentMetric, Weather
from traffic_os.simulation.history import _segment_importance
from traffic_os.simulation.network import RoadNetwork

LAGS = (1, 2, 3, 4)
ROLL = 4


def load_frame(storage, net: RoadNetwork) -> pd.DataFrame:
    """Load history into a DataFrame with engineered features (no target yet)."""
    metrics = storage.db.metrics_range(SegmentMetric)
    if not metrics:
        return pd.DataFrame()
    rows = [
        {
            "segment_id": m.segment_id,
            "ts": m.ts,
            "congestion": m.congestion_score,
            "speed": m.speed_kph,
            "density": m.density_pcu_per_km,
            "occupancy": m.occupancy_pct,
            "queue": m.queue_len_m,
        }
        for m in metrics
    ]
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.sort_values(["segment_id", "ts"]).reset_index(drop=True)

    # temporal
    hour = df["ts"].dt.hour + df["ts"].dt.minute / 60.0
    df["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    df["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    df["dow"] = df["ts"].dt.dayofweek
    df["is_weekend"] = (df["dow"] >= 5).astype(int)

    # weather merged by hourly timestamp
    weathers = storage.db.find("weather", Weather, limit=100000)
    if weathers:
        wdf = pd.DataFrame(
            [{"wts": w.ts, "capacity_factor": w.capacity_factor, "rain_mm": w.rain_mm}
             for w in weathers]
        )
        wdf["wts"] = pd.to_datetime(wdf["wts"], utc=True).dt.floor("h")
        wdf = wdf.drop_duplicates("wts")
        df["wts"] = df["ts"].dt.floor("h")
        df = df.merge(wdf, on="wts", how="left").drop(columns=["wts"])
    if "capacity_factor" not in df:
        df["capacity_factor"] = 1.0
        df["rain_mm"] = 0.0
    df["capacity_factor"] = df["capacity_factor"].fillna(1.0)
    df["rain_mm"] = df["rain_mm"].fillna(0.0)

    # static road features
    importance = _segment_importance(net)
    df["lanes"] = df["segment_id"].map(lambda s: net.segments[s].lanes if s in net.segments else 2)
    df["speed_limit"] = df["segment_id"].map(
        lambda s: net.segments[s].speed_limit_kph if s in net.segments else 50.0
    )
    df["importance"] = df["segment_id"].map(lambda s: importance.get(s, 0.3))

    # lag + rolling per segment
    g = df.groupby("segment_id")["congestion"]
    for lag in LAGS:
        df[f"lag_{lag}"] = g.shift(lag)
    df["roll_mean"] = g.shift(1).rolling(ROLL).mean().reset_index(level=0, drop=True)
    df["roll_std"] = g.shift(1).rolling(ROLL).std().reset_index(level=0, drop=True)
    return df


FORECAST_FEATURES = [
    "hour_sin", "hour_cos", "dow", "is_weekend",
    "capacity_factor", "rain_mm",
    "lanes", "speed_limit", "importance",
    "congestion", "speed", "density", "occupancy", "queue",
    *[f"lag_{lag}" for lag in LAGS],
    "roll_mean", "roll_std",
]


def make_supervised(df: pd.DataFrame, horizon_steps: int) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """Return (X, y, ts) for predicting congestion ``horizon_steps`` ahead."""
    df = df.copy()
    df["target"] = df.groupby("segment_id")["congestion"].shift(-horizon_steps)
    # seasonal-naive reference: value one day ago (history step = 15 min -> 96 steps)
    df = df.dropna(subset=[*FORECAST_FEATURES, "target"]).reset_index(drop=True)
    return df[FORECAST_FEATURES], df["target"], df["ts"]
