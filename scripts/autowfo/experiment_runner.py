"""Experiment execution orchestrator for AUTOWFO."""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import vectorbt as vbt

from scripts.autowfo.artifact_store import ArtifactStore
from scripts.autowfo.experiment import Experiment
from scripts.autowfo.signal_composer import compose
from scripts.autowfo.split import _build_walk_forward_windows


@dataclass
class RunResult:
    run_id: str
    experiment_id: str
    n_combos: int
    n_completed: int
    n_errors: int
    best_oos_sharpe: float | None
    duration_seconds: float
    run_dir: Path


def _to_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, pd.DataFrame):
        if value.empty:
            return default
        return _to_float(value.iloc[0, 0], default=default)
    if isinstance(value, pd.Series):
        if value.empty:
            return default
        return _to_float(value.iloc[0], default=default)
    if isinstance(value, (list, tuple)):
        if not value:
            return default
        return _to_float(value[0], default=default)
    try:
        num = float(value)
    except Exception:
        return default
    if math.isnan(num) or math.isinf(num):
        return default
    return num


def _to_int(value: Any, default: int = 0) -> int:
    try:
        num = int(round(float(value)))
    except Exception:
        return default
    return max(0, num)


def _normalize_win_rate(value: float) -> float:
    win_rate = _to_float(value, default=0.0)
    if win_rate > 1.0 and win_rate <= 100.0:
        win_rate = win_rate / 100.0
    return max(0.0, min(1.0, win_rate))


def _normalize_sharpe(sharpe: float) -> float:
    score = (_to_float(sharpe, default=0.0) + 2.0) / 4.0
    return max(0.0, min(1.0, score))


def _compute_wf_score(oos_sharpe: float, oos_win_rate: float, oos_n_trades: int) -> float:
    return (
        0.5 * _normalize_sharpe(oos_sharpe)
        + 0.3 * _normalize_win_rate(oos_win_rate)
        + 0.2 * (math.log(max(0, int(oos_n_trades)) + 1) / 5.0)
    )


class ExperimentRunner:
    def __init__(
        self,
        experiment: Experiment,
        trigger_ohlcv: pd.DataFrame,
        action_ohlcv: pd.DataFrame,
        artifact_store: ArtifactStore,
        run_id: str | None = None,
        analytics_store: Any | None = None,
    ):
        self.experiment = experiment
        self.trigger_ohlcv = trigger_ohlcv
        self.action_ohlcv = action_ohlcv
        self.artifact_store = artifact_store
        self.run_id = run_id or datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        self.analytics_store = analytics_store

    @staticmethod
    def _build_combo_id(experiment_id: str, combo_params: dict) -> str:
        payload = json.dumps(combo_params, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        digest = hashlib.sha256(f"{experiment_id}|{payload}".encode("utf-8")).hexdigest()
        return digest[:16]

    def _indicator_and_condition_payload(self, combo_params: dict) -> tuple[str, str]:
        def _collect_indicators(prefix: str) -> list[str]:
            collected = []
            for key, value in combo_params.items():
                if not key.startswith(prefix):
                    continue
                if not isinstance(value, str):
                    continue
                name = value.strip()
                if not name:
                    continue
                collected.append((key, name))
            collected.sort(key=lambda item: item[0])
            ordered = []
            seen = set()
            for _, indicator in collected:
                if indicator in seen:
                    continue
                seen.add(indicator)
                ordered.append(indicator)
            return ordered

        side_payload = {
            key: value
            for key, value in combo_params.items()
            if key.startswith("trigger_") or key.startswith("action_")
        }
        indicator_params = {key: value for key, value in side_payload.items() if "operator" not in key}
        indicator_params["trigger_indicators"] = _collect_indicators("trigger_indicator")
        indicator_params["action_indicators"] = _collect_indicators("action_indicator")
        condition_params = {
            key: value
            for key, value in side_payload.items()
            if "operator" in key
            or any(marker in key for marker in ("threshold", "pct", "multiplier", "lookback", "reference"))
        }
        return (
            json.dumps(indicator_params, sort_keys=True, ensure_ascii=False),
            json.dumps(condition_params, sort_keys=True, ensure_ascii=False),
        )

    @staticmethod
    def _risk_payload(combo_params: dict) -> str:
        risk = {
            "risk_stoploss_pct": combo_params.get("risk_stoploss_pct"),
            "risk_take_profit_pct": combo_params.get("risk_take_profit_pct"),
            "risk_max_hold_bars": combo_params.get("risk_max_hold_bars"),
        }
        return json.dumps(risk, sort_keys=True, ensure_ascii=False)

    @staticmethod
    def _window_mask(index: pd.Index, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
        return (index > start) & (index <= end)

    def _build_test_windows(self, combo_params: dict) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
        windows = _build_walk_forward_windows(
            index=self.action_ohlcv.index,
            train_days=int(combo_params.get("wf_train_days", 90)),
            test_days=int(combo_params.get("wf_test_days", 30)),
            step_days=int(combo_params.get("wf_step_days", 30)),
            mode=None,
            valid_days=0,
        )
        if not windows:
            if self.action_ohlcv.empty:
                return []
            return [(self.action_ohlcv.index[0], self.action_ohlcv.index[-1])]
        return [(test_start, test_end) for _, _, _, _, test_start, test_end in windows]

    def _run_window_backtest(
        self,
        close_window: pd.Series,
        entry_long_window: pd.Series,
        entry_short_window: pd.Series,
        exit_long_window: pd.Series,
        exit_short_window: pd.Series,
        combo_params: dict,
    ) -> dict:
        if close_window.empty:
            return {
                "oos_sharpe": 0.0,
                "oos_win_rate": 0.0,
                "oos_n_trades": 0,
                "oos_total_return": 0.0,
            }

        stop_loss = abs(_to_float(combo_params.get("risk_stoploss_pct"), default=1.0)) / 100.0
        take_profit = _to_float(combo_params.get("risk_take_profit_pct"), default=1.0) / 100.0

        pf = vbt.Portfolio.from_signals(
            close=close_window,
            entries=entry_long_window,
            exits=exit_long_window,
            short_entries=entry_short_window,
            short_exits=exit_short_window,
            sl_stop=stop_loss,
            tp_stop=take_profit,
            init_cash=10000,
            fees=0.001,
        )
        n_trades = _to_int(pf.trades.count(), default=0)
        return {
            "oos_sharpe": _to_float(pf.sharpe_ratio(), default=0.0),
            "oos_win_rate": _normalize_win_rate(pf.trades.win_rate() if n_trades > 0 else 0.0),
            "oos_n_trades": n_trades,
            "oos_total_return": _to_float(pf.total_return(), default=0.0),
        }

    def _run_combo(self, combo_params: dict) -> dict:
        signals = compose(
            trigger_ohlcv=self.trigger_ohlcv,
            action_ohlcv=self.action_ohlcv,
            experiment=self.experiment,
            combo_params=combo_params,
        )

        windows = self._build_test_windows(combo_params)
        per_window = []
        for test_start, test_end in windows:
            mask = self._window_mask(self.action_ohlcv.index, start=test_start, end=test_end)
            if not bool(mask.any()):
                continue
            close_window = self.action_ohlcv.loc[mask, "close"]
            per_window.append(
                self._run_window_backtest(
                    close_window=close_window,
                    entry_long_window=signals.entry_long.loc[mask],
                    entry_short_window=signals.entry_short.loc[mask],
                    exit_long_window=signals.exit_long.loc[mask],
                    exit_short_window=signals.exit_short.loc[mask],
                    combo_params=combo_params,
                )
            )

        if not per_window:
            per_window = [
                {
                    "oos_sharpe": 0.0,
                    "oos_win_rate": 0.0,
                    "oos_n_trades": 0,
                    "oos_total_return": 0.0,
                }
            ]

        oos_sharpe = float(sum(item["oos_sharpe"] for item in per_window) / len(per_window))
        oos_win_rate = float(sum(item["oos_win_rate"] for item in per_window) / len(per_window))
        oos_n_trades = int(sum(int(item["oos_n_trades"]) for item in per_window))
        oos_total_return = float(sum(item["oos_total_return"] for item in per_window) / len(per_window))
        wf_score = _compute_wf_score(oos_sharpe=oos_sharpe, oos_win_rate=oos_win_rate, oos_n_trades=oos_n_trades)

        indicator_params, condition_params = self._indicator_and_condition_payload(combo_params)
        return {
            "combo_id": self._build_combo_id(self.experiment.experiment_id, combo_params),
            "experiment_id": self.experiment.experiment_id,
            "run_id": self.run_id,
            "direction": str(combo_params.get("direction", "long")),
            "trigger_asset": str(self.experiment.config.get("trigger", {}).get("asset", "")),
            "action_asset": str(self.experiment.config.get("action", {}).get("asset", "")),
            "indicator_params": indicator_params,
            "condition_params": condition_params,
            "risk_params": self._risk_payload(combo_params),
            "oos_sharpe": oos_sharpe,
            "oos_win_rate": oos_win_rate,
            "oos_n_trades": oos_n_trades,
            "oos_total_return": oos_total_return,
            "wf_score": wf_score,
            "created_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        }

    @staticmethod
    def _insert_combo_row(conn, row: dict) -> None:
        conn.execute(
            """
            INSERT INTO combo_results (
                combo_id, experiment_id, run_id, direction,
                trigger_asset, action_asset,
                indicator_params, condition_params, risk_params,
                oos_sharpe, oos_win_rate, oos_n_trades, oos_total_return,
                wf_score, created_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["combo_id"],
                row["experiment_id"],
                row["run_id"],
                row["direction"],
                row["trigger_asset"],
                row["action_asset"],
                row["indicator_params"],
                row["condition_params"],
                row["risk_params"],
                row["oos_sharpe"],
                row["oos_win_rate"],
                row["oos_n_trades"],
                row["oos_total_return"],
                row["wf_score"],
                row["created_utc"],
            ),
        )

    @staticmethod
    def _emit_progress(progress_fn, payload: dict) -> None:
        if progress_fn is None:
            return
        try:
            progress_fn(payload)
        except TypeError:
            progress_fn(payload["completed"], payload["total"])

    def run(self, progress_fn=None) -> RunResult:
        started = time.perf_counter()
        combo_grid = self.experiment.expand_grid()
        n_combos = len(combo_grid)

        run_dir = self.artifact_store.init_run(self.run_id)
        conn = self.artifact_store.init_results_db(self.run_id)

        n_completed = 0
        n_errors = 0
        best_oos_sharpe = None

        try:
            for idx, combo_params in enumerate(combo_grid, start=1):
                try:
                    combo_row = self._run_combo(combo_params)
                    self._insert_combo_row(conn, combo_row)
                    conn.commit()
                    n_completed += 1
                    sharpe_val = _to_float(combo_row.get("oos_sharpe"), default=0.0)
                    if best_oos_sharpe is None or sharpe_val > best_oos_sharpe:
                        best_oos_sharpe = sharpe_val
                except Exception:
                    n_errors += 1
                finally:
                    self._emit_progress(
                        progress_fn,
                        {
                            "run_id": self.run_id,
                            "completed": idx,
                            "total": n_combos,
                            "n_completed": n_completed,
                            "n_errors": n_errors,
                        },
                    )
        finally:
            conn.close()

        duration = time.perf_counter() - started
        result = RunResult(
            run_id=self.run_id,
            experiment_id=self.experiment.experiment_id,
            n_combos=n_combos,
            n_completed=n_completed,
            n_errors=n_errors,
            best_oos_sharpe=best_oos_sharpe,
            duration_seconds=float(duration),
            run_dir=run_dir,
        )
        self.artifact_store.write_run_meta(
            self.run_id,
            {
                **asdict(result),
                "run_dir": str(result.run_dir),
            },
        )
        if self.analytics_store is not None:
            try:
                self.analytics_store.update_from_run(
                    self.experiment.experiment_id,
                    self.run_id,
                    self.artifact_store,
                )
            except Exception:
                pass
        return result
