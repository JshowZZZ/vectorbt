"""Benchmark AUTOWFO combo evaluation: single worker vs 3 workers."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import time
from itertools import product
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.autowfo import parallel as autowfo_parallel
from scripts.autowfo import split as autowfo_split


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _normalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    if isinstance(value, tuple):
        return [_normalize(v) for v in value]
    if isinstance(value, np.generic):
        return _normalize(value.item())
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if value == 0.0:
            return 0.0
    return value


def _stable_json(value: Any) -> str:
    return json.dumps(_normalize(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _build_runtime(periods: int) -> Dict[str, Any]:
    index = pd.date_range("2024-01-01", periods=periods, freq="h")
    close_base = np.linspace(1.0, 2.0, periods)
    trade_close = pd.DataFrame(
        {
            "ETH/BTC": close_base,
            "BNB/BTC": close_base * 1.01,
            "SOL/BTC": close_base * 0.99,
        },
        index=index,
    )

    vol_signal = np.sin(np.linspace(0, 24, periods))
    mom_signal = np.cos(np.linspace(0, 20, periods))
    rsi_signal = 50 + 20 * np.sin(np.linspace(0, 25, periods))
    btc_close = pd.Series(np.linspace(100.0, 120.0, periods), index=index)

    ctx = {
        "trade_close": trade_close,
        "init_cash_btc": 1.0,
        "total_days": int(trade_close.index.normalize().nunique()),
        "vol_zscore_by_lb": {24: pd.Series(vol_signal, index=index)},
        "mom_by_lb": {6: pd.Series(mom_signal, index=index)},
        "trade_mom_by_lb": {
            3: pd.DataFrame(
                {
                    "ETH/BTC": mom_signal,
                    "BNB/BTC": mom_signal * 0.9,
                    "SOL/BTC": mom_signal * 1.1,
                },
                index=index,
            )
        },
        "rsi_series": pd.Series(rsi_signal, index=index),
        "btc_close": btc_close,
        "bb_lower": btc_close * 0.995,
        "bb_upper": btc_close * 1.005,
    }

    wf_slices = autowfo_split._build_walk_forward_slices(
        index=index,
        train_days=30,
        test_days=7,
        step_days=7,
    )

    return {
        "ctx": ctx,
        "trade_symbols_tf": ["ETH/BTC", "BNB/BTC", "SOL/BTC"],
        "timeframe": "1h",
        "data_days": 120,
        "exchange": "binance",
        "base_symbol": "BTC/USDT",
        "capital_mode": "shared",
        "fees": 0.001,
        "slippage_bps": 1.0,
        "spread_bps": 1.0,
        "funding_rate_daily": 0.0,
        "order_size_pct": 0.5,
        "max_concurrent_positions": 2,
        "init_cash_usdt": 1000.0,
        "wf_train_days": 30,
        "wf_test_days": 7,
        "wf_step_days": 7,
        "rsi_window": 14,
        "bar_hours": 1.0,
        "wf_slices": wf_slices,
        "config_sha256": "benchmark_config",
        "data_fingerprint": "benchmark_data",
    }


def _build_tasks(task_multiplier: int) -> List[Dict[str, Any]]:
    regimes = [
        {"regime_name": "trend_high", "regime_type": "trend", "vol_mode": "high"},
        {"regime_name": "trend_low", "regime_type": "trend", "vol_mode": "low"},
        {
            "regime_name": "rsi_revert_low",
            "regime_type": "rsi_revert",
            "vol_mode": "low",
            "rsi_pair": (35, 65),
        },
        {"regime_name": "bb_breakout_high", "regime_type": "bb_breakout", "vol_mode": "high"},
    ]
    rsi_params = [
        {"rsi_long": 52, "rsi_short": 48},
        {"rsi_long": 55, "rsi_short": 45},
        {"rsi_long": 58, "rsi_short": 42},
        {"rsi_long": 60, "rsi_short": 40},
    ]

    tasks: List[Dict[str, Any]] = []
    seq = 0
    for repeat_idx in range(task_multiplier):
        for regime, params, tp_stop, sl_stop, max_hold in product(
            regimes,
            rsi_params,
            [0.003, 0.004, 0.005],
            [0.006, 0.008],
            [2, 3],
        ):
            seq += 1
            tasks.append(
                {
                    "combo_key": f"bench_{repeat_idx}_{seq}",
                    "regime": dict(regime),
                    "indicator_combo": ("rsi",),
                    "combo_params": dict(params),
                    "filter_name": "rsi",
                    "indicator_list": "rsi",
                    "vol_lookback": 24,
                    "vol_z": 0.8,
                    "mom_lookback": 6,
                    "trade_mom_lookback": 3,
                    "tp_stop": float(tp_stop),
                    "sl_stop": float(sl_stop),
                    "max_hold": int(max_hold),
                }
            )
    return tasks


def _run_once(tasks: List[Dict[str, Any]], runtime: Dict[str, Any], max_workers: int) -> Tuple[float, List[Dict[str, Any]]]:
    start = time.perf_counter()
    results = list(autowfo_parallel._run_combo_tasks(tasks, runtime, max_workers=max_workers))
    elapsed = time.perf_counter() - start
    return elapsed, results


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark AUTOWFO parallel combo evaluation.")
    parser.add_argument("--periods", type=int, default=24 * 120, help="Synthetic hourly bars.")
    parser.add_argument("--task-multiplier", type=int, default=5, help="Multiplier for task set size.")
    parser.add_argument("--workers", type=int, default=3, help="Parallel workers to benchmark.")
    args = parser.parse_args()

    runtime = _build_runtime(periods=args.periods)
    tasks = _build_tasks(task_multiplier=args.task_multiplier)

    elapsed_single, results_single = _run_once(tasks, runtime, max_workers=1)
    elapsed_parallel, results_parallel = _run_once(tasks, runtime, max_workers=max(args.workers, 1))

    bit_identical = _stable_json(results_single) == _stable_json(results_parallel)
    speedup = elapsed_single / elapsed_parallel if elapsed_parallel > 0 else float("nan")

    timestamp = dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_dir = Path("artifacts") / "benchmarks"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"awf013_parallel_benchmark_{timestamp}.json"
    latest_path = out_dir / "awf013_parallel_benchmark_latest.json"
    payload = {
        "timestamp_utc": dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "task_count": len(tasks),
        "periods": args.periods,
        "task_multiplier": args.task_multiplier,
        "parallel_workers": max(args.workers, 1),
        "elapsed_single_sec": elapsed_single,
        "elapsed_parallel_sec": elapsed_parallel,
        "speedup": speedup,
        "bit_identical": bit_identical,
        "target_speedup": 2.5,
        "target_met": bool(bit_identical and speedup >= 2.5),
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    latest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[awf013-benchmark] tasks={len(tasks)} periods={args.periods}")
    print(f"[awf013-benchmark] single={elapsed_single:.4f}s parallel={elapsed_parallel:.4f}s")
    print(f"[awf013-benchmark] speedup={speedup:.4f} bit_identical={bit_identical}")
    print(f"[awf013-benchmark] target_met={payload['target_met']}")
    print(f"[awf013-benchmark] output={out_path.as_posix()}")


if __name__ == "__main__":
    main()
