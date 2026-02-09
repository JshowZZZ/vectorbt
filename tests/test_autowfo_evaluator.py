import pandas as pd

from scripts.autowfo import evaluator as autowfo_evaluator


def test_evaluator_coerces_missing_indicator_lookback(monkeypatch):
    idx = pd.date_range("2026-01-01", periods=8, freq="h")
    symbols = ["ETH/USDT"]
    true_mask = pd.Series(True, index=idx)

    ctx = {
        "vol_zscore_by_lb": {
            24: pd.Series(0.2, index=idx),
            28: pd.Series(0.3, index=idx),
        },
        "volume_zscore_by_lb": {
            24: pd.Series(0.2, index=idx),
            28: pd.Series(0.3, index=idx),
        },
        "trade_mom_by_lb": {
            3: pd.DataFrame({"ETH/USDT": [0.1] * len(idx)}, index=idx),
        },
        "trade_close": pd.DataFrame({"ETH/USDT": [100.0] * len(idx)}, index=idx),
        "init_cash_btc": 1.0,
    }

    runtime = {
        "ctx": ctx,
        "trade_symbols_tf": symbols,
        "timeframe": "1h",
        "data_days": 30,
        "exchange": "binance",
        "base_symbol": "BTC/USDT",
        "capital_mode": "shared",
        "fees": 0.001,
        "slippage_bps": 0.0,
        "spread_bps": 0.0,
        "funding_rate_daily": 0.0,
        "order_size_pct": 0.5,
        "max_concurrent_positions": 1,
        "init_cash_usdt": 1000.0,
        "wf_train_days": 120,
        "wf_test_days": 30,
        "wf_step_days": 30,
        "rsi_window": 14,
        "bar_hours": 1.0,
        "wf_slices": [],
        "config_sha256": "cfg",
        "data_fingerprint": "fp",
    }

    task = {
        "regime": {
            "regime_name": "trend_high",
            "regime_type": "trend",
            "vol_mode": "high",
            "rsi_pair": None,
        },
        "indicator_combo": ("volume_z",),
        "combo_params": {
            "volume_lookback": 32,
            "volume_z": 0.2,
        },
        "vol_lookback": 24,
        "vol_z": 0.1,
        "mom_lookback": 6,
        "trade_mom_lookback": 3,
        "tp_stop": 0.003,
        "sl_stop": 0.006,
        "max_hold": 2,
        "filter_name": "vol_mom_volume",
        "indicator_list": "volume_z",
    }

    monkeypatch.setattr(
        autowfo_evaluator.autowfo_engine,
        "_resolve_regime_signals",
        lambda **kwargs: (true_mask, true_mask, None, None),
    )
    monkeypatch.setattr(
        autowfo_evaluator.autowfo_engine,
        "_build_trade_mom_filters",
        lambda trade_mom: (trade_mom > -1e9, trade_mom < 1e9),
    )
    monkeypatch.setattr(
        autowfo_evaluator.autowfo_engine,
        "_compute_effective_costs",
        lambda **kwargs: (0.0, 0.0),
    )

    captured = {}

    def _fake_apply_indicator_combo(long_regime, short_regime, combo_keys, combo_params, combo_ctx):
        captured["volume_lookback"] = combo_params["volume_lookback"]
        return long_regime, short_regime, combo_params

    monkeypatch.setattr(
        autowfo_evaluator.autowfo_strategy,
        "_apply_indicator_combo",
        _fake_apply_indicator_combo,
    )
    monkeypatch.setattr(
        autowfo_evaluator.autowfo_portfolio,
        "_run_pf",
        lambda *args, **kwargs: object(),
    )
    monkeypatch.setattr(
        autowfo_evaluator.autowfo_metrics,
        "_calc_pf_series",
        lambda pf, tf_symbols, bar_hours: {
            "total_return_pct": pd.Series([1.0], index=tf_symbols),
            "total_profit": pd.Series([1.0], index=tf_symbols),
            "total_trades": pd.Series([10.0], index=tf_symbols),
            "win_rate_pct": pd.Series([50.0], index=tf_symbols),
            "avg_trade_pct": pd.Series([0.1], index=tf_symbols),
            "max_drawdown_pct": pd.Series([-5.0], index=tf_symbols),
            "position_coverage_pct": pd.Series([20.0], index=tf_symbols),
            "avg_hold_hours": pd.Series([2.0], index=tf_symbols),
        },
    )
    monkeypatch.setattr(
        autowfo_evaluator.autowfo_metrics,
        "_aggregate_metrics",
        lambda metrics: {
            "avg_total_return_pct": 1.0,
            "avg_total_trades": 10.0,
            "avg_win_rate_pct": 50.0,
            "avg_avg_trade_pct": 0.1,
            "avg_max_drawdown_pct": -5.0,
            "avg_position_coverage_pct": 20.0,
            "avg_hold_hours": 2.0,
        },
    )
    monkeypatch.setattr(
        autowfo_evaluator.autowfo_metrics,
        "_calc_pf_combo_metrics",
        lambda pf, bar_hours: {
            "total_return_pct": 1.0,
            "total_profit": 1.0,
            "total_trades": 10.0,
            "win_rate_pct": 50.0,
            "avg_trade_pct": 0.1,
            "max_drawdown_pct": -5.0,
            "position_coverage_pct": 20.0,
            "avg_hold_hours": 2.0,
        },
    )
    monkeypatch.setattr(
        autowfo_evaluator.autowfo_metrics,
        "_aggregate_oos_metrics",
        lambda rows: {
            "oos_avg_total_return_pct": 0.0,
            "oos_avg_win_rate_pct": 0.0,
            "oos_avg_avg_trade_pct": 0.0,
            "oos_avg_max_drawdown_pct": 0.0,
            "oos_avg_position_coverage_pct": 0.0,
            "oos_avg_total_trades": 0.0,
            "oos_min_total_trades": 0.0,
            "oos_avg_daily_trades": 0.0,
            "oos_avg_hold_hours": 0.0,
            "oos_segments": 0,
        },
    )

    result = autowfo_evaluator.evaluate_combo_task(task, runtime)
    assert captured["volume_lookback"] == 28
    assert result["variant_params"]["volume_lookback"] == 28
