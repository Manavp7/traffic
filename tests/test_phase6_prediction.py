"""Phase 6: forecasting + accident-risk tests."""

from __future__ import annotations

import pytest

pytest.importorskip("xgboost")
pytest.importorskip("sklearn")

from traffic_os.prediction import ForecastModel, PredictionService  # noqa: E402
from traffic_os.prediction.features import load_frame  # noqa: E402
from traffic_os.simulation import build_grid_network, generate_history, save_network  # noqa: E402
from traffic_os.storage import memory_storage  # noqa: E402


def _prepared(days=5, n=4):
    net = build_grid_network(n)
    st = memory_storage()
    save_network(net, st.db)
    generate_history(net, st.db, days=days, step_min=15, seed=11)
    return net, st


def test_feature_frame_built():
    net, st = _prepared(days=3)
    df = load_frame(st, net)
    assert not df.empty
    assert {"lag_1", "roll_mean", "hour_sin", "capacity_factor", "importance"} <= set(df.columns)


def test_forecast_beats_persistence_at_60min():
    net, st = _prepared(days=6)
    df = load_frame(st, net)
    fm = ForecastModel(60)
    bt = fm.backtest(df)
    # model should add skill over naive persistence at a 1h horizon
    assert bt.skill_vs_persistence > 0.0, bt
    assert 0 <= bt.mae <= 100


def test_prediction_service_forecast_and_risk():
    net, st = _prepared(days=6)
    svc = PredictionService(st)
    results = svc.train(horizons=(30, 60))
    assert set(results["forecast"].keys()) == {30, 60}
    assert results["accident_risk_auc"] >= 0.6  # must recover the latent hazard signal

    sid = next(iter(net.segments))
    f = svc.forecast(sid, 60)
    assert f is not None
    assert 0 <= f.predicted_congestion <= 100
    assert f.ci_low <= f.predicted_congestion <= f.ci_high
    assert f.ts_target > f.ts_made

    all_f = svc.forecast_all(60)
    assert len(all_f) == len(net.segments)
    assert st.db.count("forecast") == len(net.segments)


def test_accident_risk_outputs():
    from traffic_os.simulation import SimulationEngine

    net, st = _prepared(days=5)
    # add some live metrics for "now"
    eng = SimulationEngine(net)
    for _ in range(20):
        eng.persist(st, eng.step_once())
    svc = PredictionService(st)
    svc.train(horizons=(60,))
    risks = svc.accident_risk_all()
    assert risks
    assert all(0 <= r.risk_pct <= 100 for r in risks)
    top = svc.top_risk(5)
    assert len(top) <= 5
    assert top == sorted(top, key=lambda r: r.risk_pct, reverse=True)
