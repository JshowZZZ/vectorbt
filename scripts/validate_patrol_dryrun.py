"""Developer dry-run validation for scheduler patrol loop."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import pandas as pd

from autowfo.commands.core_patrol import _append_patrol_log
from autowfo.commands.cron import _run_scheduler_patrol_cycle
from scripts.autowfo import data_multi
from scripts.autowfo.analytics import AnalyticsStore
from scripts.autowfo import experiment_runner as experiment_runner_mod


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_ohlcv(bars: int = 500) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=bars, freq="1h", tz="UTC").tz_convert(None)
    close = pd.Series(100.0 + pd.RangeIndex(bars) * 0.05, index=index, dtype=float)
    open_ = close.shift(1).fillna(close.iloc[0])
    high = pd.concat([open_, close], axis=1).max(axis=1) * 1.01
    low = pd.concat([open_, close], axis=1).min(axis=1) * 0.99
    volume = pd.Series(2000.0 + (pd.RangeIndex(bars) % 100), index=index, dtype=float)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=index)


class _FakeTrades:
    @staticmethod
    def count():
        return 12

    @staticmethod
    def win_rate():
        return 60.0


class _FakePortfolio:
    def __init__(self, sharpe: float = 1.1):
        self._sharpe = float(sharpe)
        self.trades = _FakeTrades()

    def sharpe_ratio(self):
        return self._sharpe

    @staticmethod
    def total_return():
        return 0.12


class _CliAdapter:
    @staticmethod
    def _utc_now_iso() -> str:
        return _utc_now_iso()

    @staticmethod
    def _load_config(path: Path):
        return json.loads(path.read_text(encoding="utf-8-sig"))


def _round_pool(indicators: list[str]) -> dict:
    return {
        "indicator_ids": indicators,
        "combo_sizes": [2],
        "pruning": {"enabled": False},
        "default_trigger": {"asset": "BTC/USDT", "timeframe": "1h", "require_all": True},
        "default_action": {
            "asset": "BTC/USDT",
            "timeframe": "1h",
            "require_all": True,
            "direction": "long",
        },
        "default_risk": {
            "stoploss_pct_values": [-2],
            "take_profit_pct_values": [3],
            "max_hold_bars_values": [24],
        },
        "default_wf": {"train_days": 30, "test_days": 10, "step_days": 10},
    }


def _patch_data_layer(source_path: Path) -> tuple[Callable[[], None], dict]:
    originals = {
        "_select_parquet_engine": data_multi._select_parquet_engine,
        "_read_parquet": data_multi._read_parquet,
        "_write_parquet_atomic": data_multi._write_parquet_atomic,
        "_fetch_ohlcv_ccxt": data_multi._fetch_ohlcv_ccxt,
        "portfolio_from_signals": experiment_runner_mod.vbt.Portfolio.from_signals,
    }

    def _restore() -> None:
        data_multi._select_parquet_engine = originals["_select_parquet_engine"]
        data_multi._read_parquet = originals["_read_parquet"]
        data_multi._write_parquet_atomic = originals["_write_parquet_atomic"]
        data_multi._fetch_ohlcv_ccxt = originals["_fetch_ohlcv_ccxt"]
        experiment_runner_mod.vbt.Portfolio.from_signals = originals["portfolio_from_signals"]

    data_multi._select_parquet_engine = lambda: "mock"
    data_multi._read_parquet = lambda path, engine: pd.read_pickle(path)

    def _write_atomic(df: pd.DataFrame, path: Path, engine: str) -> None:
        _ = engine
        tmp = path.with_suffix(".tmp")
        df.to_pickle(tmp)
        os.replace(tmp, path)

    data_multi._write_parquet_atomic = _write_atomic
    data_multi._fetch_ohlcv_ccxt = lambda asset, timeframe, start_ts, end_ts, exchange: pd.read_pickle(source_path)
    experiment_runner_mod.vbt.Portfolio.from_signals = lambda *args, **kwargs: _FakePortfolio()
    return _restore, originals


def run_patrol_dryrun(workdir: Path, rounds: int = 3) -> dict:
    root = Path(workdir).resolve()
    repo_root = Path(__file__).resolve().parents[1]
    if (root / "artifacts").resolve() == (repo_root / "artifacts").resolve():
        raise ValueError("dry-run cannot write to production artifacts directory")
    root.mkdir(parents=True, exist_ok=True)

    artifacts_dir = root / "artifacts"
    source_dir = root / "source_parquet"
    source_dir.mkdir(parents=True, exist_ok=True)
    source_path = source_dir / "binance_btc-usdt_1h.parquet"
    _build_ohlcv().to_pickle(source_path)

    _write_json(
        artifacts_dir / "scheduler.json",
        {
            "priority_order": ["user_submitted", "discovery", "refine"],
            "max_concurrent": 1,
            "schedule_cron": "0 0 * * *",
            "max_runs_per_patrol": 5,
        },
    )
    _write_json(artifacts_dir / "scheduler_queue.json", {"version": 1, "next_seq": 1, "items": [], "updated_utc": ""})

    round_pools = [
        _round_pool(["RSI", "MACD", "BB"]),
        _round_pool(["RSI", "EMA", "Volume"]),
        _round_pool(["MACD", "EMA", "Volume"]),
    ]
    if rounds != 3:
        raise ValueError("dry-run currently expects rounds=3")

    restore, _ = _patch_data_layer(source_path)
    original_query_indicator_leaderboard = AnalyticsStore.query_indicator_leaderboard
    AnalyticsStore.query_indicator_leaderboard = lambda self, limit=20: []
    analytics = AnalyticsStore(artifacts_dir / "analytics.duckdb")
    cli_impl = _CliAdapter()
    prev_total_combos = 0
    round_rows = []
    try:
        for idx in range(rounds):
            _write_json(artifacts_dir / "pool_config.json", round_pools[idx])
            cycle_result = _run_scheduler_patrol_cycle(
                cwd=root,
                cli_impl=cli_impl,
                schedule_cron="0 0 * * *",
                max_runs_per_patrol=5,
            )
            growth = analytics.query_analytics_growth()
            _append_patrol_log(root, cycle_result)

            tick = cycle_result.get("discovery_tick") or {}
            tick_enqueued = int(tick.get("enqueued", 0) or 0)
            runs_executed = int(cycle_result.get("scheduler_runs_processed", 0) or 0)
            queue_remaining = int(cycle_result.get("queue_remaining", 0) or 0)
            total_runs = int(growth.get("total_runs", 0) or 0)
            total_combos = int(growth.get("total_combos", 0) or 0)
            if tick_enqueued <= 0:
                raise RuntimeError(f"round {idx + 1}: expected queue depth increase")
            if runs_executed <= 0:
                raise RuntimeError(f"round {idx + 1}: expected at least one executed run")
            if queue_remaining != 0:
                raise RuntimeError(f"round {idx + 1}: queue must be drained")
            if total_combos <= prev_total_combos:
                raise RuntimeError(f"round {idx + 1}: analytics growth did not increase")
            prev_total_combos = total_combos
            round_rows.append(
                {
                    "round": idx + 1,
                    "tick_generated": int(tick.get("generated", 0) or 0),
                    "tick_enqueued": tick_enqueued,
                    "runs_executed": runs_executed,
                    "queue_remaining": queue_remaining,
                    "growth_total_runs": total_runs,
                    "growth_total_combos": total_combos,
                }
            )
    finally:
        AnalyticsStore.query_indicator_leaderboard = original_query_indicator_leaderboard
        restore()

    patrol_log_path = artifacts_dir / "patrol_log.ndjson"
    lines = [line for line in patrol_log_path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    if len(lines) != rounds:
        raise RuntimeError(f"patrol_log lines mismatch: expected {rounds}, got {len(lines)}")
    required_keys = {"utc", "tick_generated", "tick_enqueued", "runs_executed", "runs_errors", "queue_remaining"}
    parsed_lines = []
    for line in lines:
        payload = json.loads(line)
        if not required_keys.issubset(set(payload.keys())):
            raise RuntimeError("patrol_log schema mismatch")
        parsed_lines.append(payload)

    summary = {
        "ok": True,
        "workdir": str(root),
        "rounds": round_rows,
        "patrol_log_lines": len(parsed_lines),
        "patrol_log_schema_keys": sorted(required_keys),
    }
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run scheduler patrol dry-run validation")
    parser.add_argument("--workdir", default="", help="Working directory for dry-run artifacts")
    parser.add_argument("--rounds", type=int, default=3, help="Number of patrol rounds (must be 3)")
    parser.add_argument("--summary-out", default="", help="Optional path to write JSON summary")
    args = parser.parse_args(argv)

    if str(args.workdir or "").strip():
        workdir = Path(args.workdir).resolve()
    else:
        workdir = Path(tempfile.mkdtemp(prefix="autowfo_patrol_dryrun_")).resolve()

    summary = run_patrol_dryrun(workdir=workdir, rounds=int(args.rounds))
    out_path = Path(args.summary_out).resolve() if str(args.summary_out or "").strip() else workdir / "patrol_dryrun_summary.json"
    _write_json(out_path, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
