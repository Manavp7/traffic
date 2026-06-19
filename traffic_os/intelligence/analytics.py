"""Historical analytics — time series, diurnal/daily profiles, before/after deltas."""

from __future__ import annotations

import pandas as pd

from traffic_os.schemas import SegmentMetric


def _frame(db, segment_id: str | None = None) -> pd.DataFrame:
    rows = db.metrics_range(SegmentMetric, segment_id=segment_id)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(
        [{"ts": m.ts, "congestion": m.congestion_score, "speed": m.speed_kph} for m in rows]
    )
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df


def network_timeseries(db, *, segment_id: str | None = None, hours: int | None = 24) -> list[dict]:
    """Average congestion/speed over time (network-wide or for one segment)."""
    df = _frame(db, segment_id)
    if df.empty:
        return []
    if hours:
        cutoff = df["ts"].max() - pd.Timedelta(hours=hours)
        df = df[df["ts"] >= cutoff]
    g = (
        df.groupby("ts")
        .agg(congestion=("congestion", "mean"), speed=("speed", "mean"))
        .reset_index()
    )
    return [
        {"ts": ts.isoformat(), "congestion": round(c, 1), "speed": round(s, 1)}
        for ts, c, s in zip(g["ts"], g["congestion"], g["speed"], strict=False)
    ]


def hourly_profile(db) -> list[dict]:
    """Average congestion by hour-of-day (0..23) — the diurnal pattern."""
    df = _frame(db)
    if df.empty:
        return []
    df["hour"] = df["ts"].dt.hour
    g = df.groupby("hour")["congestion"].mean().reset_index()
    return [
        {"hour": int(h), "congestion": round(c, 1)}
        for h, c in zip(g["hour"], g["congestion"], strict=False)
    ]


def daily_profile(db) -> list[dict]:
    """Average congestion per calendar day."""
    df = _frame(db)
    if df.empty:
        return []
    df["date"] = df["ts"].dt.date.astype(str)
    g = df.groupby("date")["congestion"].mean().reset_index()
    return [
        {"date": d, "congestion": round(c, 1)}
        for d, c in zip(g["date"], g["congestion"], strict=False)
    ]
