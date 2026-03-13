import copy

import numpy as np
import pandas as pd

from autowfo import evaluator as ev
from autowfo import parallel as pr


def _normalize_for_compare(value):
    if isinstance(value, float) and np.isnan(value):
        return "NaN"
    if isinstance(value, dict):
        return {k: _normalize_for_compare(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize_for_compare(v) for v in value]
    return value


def _build_runtime_and_tasks():
    index = pd.date_range("2024-01-01", periods=48, freq="h")
    close = pd.Series(np.linspace(1.0, 2.0, len(index)), index=index)
    trade_close = pd.DataFrame({"ETH/BTC": close}, index=index)

    ctx = {
        "trade_close": trade_close,
        "init_cash_btc": 1.0,
        "total_days": int(trade_close.index.normalize().nunique()),
        "vol_zscore_by_lb": {24: pd.Series(1.0, index=index)},
        "mom_by_lb": {6: pd.Series(1.0, index=index)},
        "trade_mom_by_lb": {3: pd.DataFrame({"ETH/BTC": 1.0}, index=index)},
        "rsi_series": pd.Series(60.0, index=index),
        "btc_close": pd.Series(100.0, index=index),
        "bb_lower": pd.Series(99.0, index=index),
        "bb_upper": pd.Series(101.0, index=index),
    }

    runtime = {
        "ctx": ctx,
        "trade_symbols_tf": ["ETH/BTC"],
        "timeframe": "1h",
        "data_days": 2,
        "exchange": "binance",
        "base_symbol": "BTC/USDT",
        "capital_mode": "shared",
        "fees": 0.0,
        "slippage_bps": 0.0,
        "spread_bps": 0.0,
        "funding_rate_daily": 0.0,
        "order_size_pct": 1.0,
        "max_concurrent_positions": 1,
        "init_cash_usdt": 1000.0,
        "wf_train_days": 120,
        "wf_test_days": 30,
        "wf_step_days": 30,
        "rsi_window": 14,
        "bar_hours": 1.0,
        "wf_slices": [],
        "config_sha256": "cfg_hash",
        "data_fingerprint": "data_hash",
    }

    base_task = {
        "regime": {"regime_name": "trend_high", "regime_type": "trend", "vol_mode": "high"},
        "indicator_combo": ("rsi",),
        "filter_name": "rsi",
        "indicator_list": "rsi",
        "vol_lookback": 24,
        "vol_z": 0.8,
        "mom_lookback": 6,
        "trade_mom_lookback": 3,
        "tp_stop": 0.003,
        "sl_stop": 0.006,
        "max_hold": 2,
    }
    task1 = copy.deepcopy(base_task)
    task1["combo_key"] = "task_1"
    task1["combo_params"] = {"rsi_long": 55, "rsi_short": 45}

    task2 = copy.deepcopy(base_task)
    task2["combo_key"] = "task_2"
    task2["combo_params"] = {"rsi_long": 60, "rsi_short": 40}
    return runtime, [task1, task2]


def test_parallel_combo_results_match_sequential_bit_identical():
    runtime, tasks = _build_runtime_and_tasks()
    expected = [ev.evaluate_combo_task(task, runtime) for task in tasks]
    got = list(pr._run_combo_tasks(tasks, runtime, max_workers=3))
    assert _normalize_for_compare(got) == _normalize_for_compare(expected)
    assert len(got) == len(tasks)

