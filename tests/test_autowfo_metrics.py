import numpy as np
import pandas as pd

from scripts import run_btc_regime_sweep as sweep
from scripts.autowfo import metrics as m


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
    assert got["oos_segments"] == 2


def test_calc_pf_combo_metrics_wrapper_matches_module():
    index = pd.date_range("2024-01-01", periods=30, freq="h")
    trade_close = pd.DataFrame({"ETH/BTC": np.linspace(1.0, 2.0, len(index))}, index=index)
    long_regime = pd.Series(True, index=index)
    short_regime = pd.Series(False, index=index)

    pf = sweep._run_pf(
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

    expected = m._calc_pf_combo_metrics(pf, bar_hours=1.0)
    actual = sweep._calc_pf_combo_metrics(pf, bar_hours=1.0)

    assert expected.keys() == actual.keys()
    for key in expected:
        if np.isnan(expected[key]) and np.isnan(actual[key]):
            continue
        assert np.isclose(expected[key], actual[key], equal_nan=True)
