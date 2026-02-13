import numpy as np
import pandas as pd

from scripts.autowfo import metrics as m
from scripts.autowfo import portfolio as p


def test_timeframe_to_hours_characterization():
    assert m._timeframe_to_hours("3m") == 0.05
    assert m._timeframe_to_hours("2h") == 2.0
    assert m._timeframe_to_hours("2d") == 48.0
    assert np.isnan(m._timeframe_to_hours("bad"))


def test_aggregate_oos_metrics_characterization():
    rows = [
        {
            "avg_total_return_pct": 10.0,
            "avg_win_rate_pct": 50.0,
            "avg_avg_trade_pct": 1.0,
            "avg_max_drawdown_pct": -5.0,
            "avg_position_coverage_pct": 40.0,
            "avg_total_trades": 20.0,
            "min_total_trades": 15.0,
            "avg_daily_trades": 2.0,
            "avg_hold_hours": 4.0,
        },
        {
            "avg_total_return_pct": 20.0,
            "avg_win_rate_pct": 60.0,
            "avg_avg_trade_pct": 2.0,
            "avg_max_drawdown_pct": -4.0,
            "avg_position_coverage_pct": 50.0,
            "avg_total_trades": 30.0,
            "min_total_trades": 12.0,
            "avg_daily_trades": 3.0,
            "avg_hold_hours": 5.0,
        },
    ]
    got = m._aggregate_oos_metrics(rows)
    assert got["oos_avg_total_return_pct"] == 15.0
    assert got["oos_min_total_trades"] == 12.0
    assert got["oos_avg_daily_trades"] == 2.5
    assert got["oos_return_std"] == 5.0
    assert got["oos_positive_segment_ratio"] == 1.0
    assert got["oos_sharpe_like"] == 3.0
    assert got["oos_low_trade_segment_ratio"] == 1.0
    assert np.isclose(got["oos_low_trade_penalty"], 0.55)
    assert got["oos_segments"] == 2


def test_aggregate_oos_metrics_empty_includes_contract_fields():
    got = m._aggregate_oos_metrics([])
    assert set(got.keys()) == set(m.OOS_AGGREGATE_METRIC_FIELDS)
    assert np.isnan(got["oos_avg_daily_trades"])
    assert np.isnan(got["oos_sharpe_like"])
    assert got["oos_segments"] == 0


def test_calc_pf_combo_metrics_characterization():
    index = pd.date_range("2024-01-01", periods=30, freq="h")
    trade_close = pd.DataFrame({"ETH/BTC": np.linspace(1.0, 2.0, len(index))}, index=index)
    long_regime = pd.Series(True, index=index)
    short_regime = pd.Series(False, index=index)

    pf = p._run_pf(
        trade_close,
        long_regime,
        short_regime,
        max_hold=2,
        fees=0.0,
        sl_stop=None,
        tp_stop=None,
        freq="1h",
        slippage=0.0,
        init_cash=1.0,
        size=1.0,
        size_type="percent",
        cash_sharing=True,
        lock_cash=True,
        allow_partial=False,
        max_positions=None,
    )

    metrics = m._calc_pf_combo_metrics(pf, bar_hours=1.0)
    assert metrics["total_trades"] > 0
    assert np.isfinite(metrics["total_return_pct"])


def test_metric_field_constants_loaded_from_contract():
    assert m.IS_SERIES_METRIC_FIELDS == (
        "total_return_pct",
        "total_profit",
        "total_trades",
        "win_rate_pct",
        "avg_trade_pct",
        "max_drawdown_pct",
        "position_coverage_pct",
        "avg_hold_hours",
    )
    assert m.COMBO_METRIC_FIELDS == m.IS_SERIES_METRIC_FIELDS
    assert m.IS_AGGREGATE_METRIC_FIELDS == (
        "avg_total_return_pct",
        "avg_win_rate_pct",
        "avg_avg_trade_pct",
        "avg_max_drawdown_pct",
        "avg_position_coverage_pct",
        "avg_total_trades",
        "min_total_trades",
        "avg_hold_hours",
    )
    assert m.OOS_AGGREGATE_METRIC_FIELDS == (
        "oos_avg_total_return_pct",
        "oos_avg_win_rate_pct",
        "oos_avg_avg_trade_pct",
        "oos_avg_max_drawdown_pct",
        "oos_avg_position_coverage_pct",
        "oos_avg_total_trades",
        "oos_min_total_trades",
        "oos_avg_daily_trades",
        "oos_avg_hold_hours",
        "oos_return_std",
        "oos_positive_segment_ratio",
        "oos_sharpe_like",
        "oos_low_trade_segment_ratio",
        "oos_low_trade_penalty",
        "oos_segments",
    )
