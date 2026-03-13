from __future__ import annotations

import math
import sqlite3

import pandas as pd

from autowfo.artifact_store import ArtifactStore
from autowfo.experiment import Experiment
from autowfo.experiment_runner import (
    ExperimentRunner,
    RunResult,
    _compute_wf_score,
)
from autowfo.signal_composer import SignalResult


def _make_ohlcv(n_bars: int = 24 * 25, freq: str = "1h") -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=n_bars, freq=freq)
    close = pd.Series(100.0 + pd.RangeIndex(n_bars) * 0.05, index=index, dtype=float)
    return pd.DataFrame(
        {
            "open": close * 0.999,
            "high": close * 1.003,
            "low": close * 0.997,
            "close": close,
            "volume": pd.Series(1000.0, index=index, dtype=float),
        }
    )


def _experiment_config(direction: str = "both") -> dict:
    return {
        "experiment_id": "exp_runner_phase21_v1",
        "mode": "hypothesis",
        "trigger": {
            "asset": "BTC/USDT",
            "timeframe": "1h",
            "indicators": ["Volume"],
            "conditions": {
                "Volume": {
                    "operator": "above_avg",
                    "vol_period_values": [2],
                    "multiplier_values": [0.5],
                }
            },
            "require_all": True,
        },
        "action": {
            "asset": "ETH/USDT",
            "timeframe": "1h",
            "indicators": ["Volume"],
            "conditions": {
                "Volume": {
                    "operator": "above_avg",
                    "vol_period_values": [2],
                    "multiplier_values": [0.5],
                }
            },
            "require_all": True,
            "direction": direction,
        },
        "risk": {
            "stoploss_pct_values": [-2],
            "take_profit_pct_values": [4],
            "max_hold_bars_values": [24],
        },
        "wf": {
            "train_days": 7,
            "test_days": 2,
            "step_days": 2,
        },
    }


def _fake_compose(trigger_ohlcv, action_ohlcv, experiment, combo_params):
    _ = (trigger_ohlcv, experiment)
    index = action_ohlcv.index
    base_signal = pd.Series([i % 10 == 0 for i in range(len(index))], index=index, dtype=bool)
    false_signal = pd.Series(False, index=index, dtype=bool)
    direction = combo_params.get("direction", "long")
    if direction == "short":
        return SignalResult(
            entry_long=false_signal,
            entry_short=base_signal,
            exit_long=false_signal.copy(),
            exit_short=false_signal.copy(),
        )
    return SignalResult(
        entry_long=base_signal,
        entry_short=false_signal,
        exit_long=false_signal.copy(),
        exit_short=false_signal.copy(),
    )


def _fake_window_metrics(
    self,
    close_window,
    entry_long_window,
    entry_short_window,
    exit_long_window,
    exit_short_window,
    combo_params,
):
    _ = (self, close_window, entry_long_window, entry_short_window, exit_long_window, exit_short_window, combo_params)
    return {
        "oos_sharpe": 1.0,
        "oos_win_rate": 0.5,
        "oos_n_trades": 10,
        "oos_total_return": 0.12,
    }


def _make_runner(
    tmp_path,
    direction: str = "both",
    run_id: str = "20260227_010101",
    analytics_store=None,
):
    experiment = Experiment.from_dict(_experiment_config(direction=direction))
    trigger_ohlcv = _make_ohlcv()
    action_ohlcv = _make_ohlcv()
    store = ArtifactStore(experiment.experiment_id, base_dir=tmp_path / "artifacts")
    runner = ExperimentRunner(
        experiment=experiment,
        trigger_ohlcv=trigger_ohlcv,
        action_ohlcv=action_ohlcv,
        artifact_store=store,
        run_id=run_id,
        analytics_store=analytics_store,
    )
    return experiment, store, runner


def test_run_returns_runresult_and_inserts_rows(tmp_path, monkeypatch):
    experiment, store, runner = _make_runner(tmp_path, direction="both")
    monkeypatch.setattr("autowfo.experiment_runner.compose", _fake_compose)
    monkeypatch.setattr(ExperimentRunner, "_run_window_backtest", _fake_window_metrics)

    result = runner.run()

    assert isinstance(result, RunResult)
    assert result.n_combos == len(experiment.expand_grid())
    assert result.n_completed == result.n_combos
    assert result.n_errors == 0

    conn = sqlite3.connect(store.get_run_db_path(result.run_id))
    try:
        row_count = conn.execute("SELECT COUNT(*) FROM combo_results").fetchone()[0]
        assert row_count == result.n_combos
    finally:
        conn.close()


def test_combo_id_is_deterministic():
    params_a = {"direction": "long", "x": 1, "y": 2}
    params_b = {"y": 2, "x": 1, "direction": "long"}
    combo_a = ExperimentRunner._build_combo_id("exp1", params_a)
    combo_b = ExperimentRunner._build_combo_id("exp1", params_b)
    assert combo_a == combo_b
    assert len(combo_a) == 16


def test_wf_score_formula_matches_spec():
    expected = 0.5 * ((1.0 + 2.0) / 4.0) + 0.3 * 0.5 + 0.2 * (math.log(11) / 5.0)
    assert _compute_wf_score(1.0, 0.5, 10) == expected


def test_progress_callback_called(tmp_path, monkeypatch):
    experiment, _store, runner = _make_runner(tmp_path, direction="both")
    monkeypatch.setattr("autowfo.experiment_runner.compose", _fake_compose)
    monkeypatch.setattr(ExperimentRunner, "_run_window_backtest", _fake_window_metrics)

    progress_calls = []
    runner.run(progress_fn=lambda payload: progress_calls.append(payload))

    assert len(progress_calls) == len(experiment.expand_grid())
    assert progress_calls[-1]["completed"] == len(experiment.expand_grid())


def test_combo_error_isolation(tmp_path, monkeypatch):
    experiment, store, runner = _make_runner(tmp_path, direction="both")

    call_state = {"count": 0}

    def fake_run_combo(self, combo_params):
        call_state["count"] += 1
        if call_state["count"] == 1:
            raise RuntimeError("boom")
        return {
            "combo_id": self._build_combo_id(self.experiment.experiment_id, combo_params),
            "experiment_id": self.experiment.experiment_id,
            "run_id": self.run_id,
            "direction": combo_params.get("direction", "long"),
            "trigger_asset": "BTC/USDT",
            "action_asset": "ETH/USDT",
            "indicator_params": "{}",
            "condition_params": "{}",
            "risk_params": "{}",
            "oos_sharpe": 0.1,
            "oos_win_rate": 0.2,
            "oos_n_trades": 1,
            "oos_total_return": 0.01,
            "wf_score": 0.1,
            "created_utc": "2026-02-27T00:00:00+00:00",
        }

    monkeypatch.setattr(ExperimentRunner, "_run_combo", fake_run_combo)
    result = runner.run()

    assert result.n_combos == len(experiment.expand_grid())
    assert result.n_errors == 1
    assert result.n_completed == result.n_combos - 1

    conn = sqlite3.connect(store.get_run_db_path(result.run_id))
    try:
        row_count = conn.execute("SELECT COUNT(*) FROM combo_results").fetchone()[0]
        assert row_count == result.n_combos - 1
    finally:
        conn.close()


def test_run_writes_run_meta(tmp_path, monkeypatch):
    _experiment, store, runner = _make_runner(tmp_path, direction="long", run_id="20260227_020202")
    monkeypatch.setattr("autowfo.experiment_runner.compose", _fake_compose)
    monkeypatch.setattr(ExperimentRunner, "_run_window_backtest", _fake_window_metrics)

    result = runner.run()
    meta = store.read_run_meta(result.run_id)

    assert meta["run_id"] == "20260227_020202"
    assert meta["n_combos"] == result.n_combos
    assert meta["n_completed"] == result.n_completed
    assert meta["n_errors"] == result.n_errors


def test_run_calls_analytics_hook_when_provided(tmp_path, monkeypatch):
    class DummyAnalyticsStore:
        def __init__(self):
            self.calls = []

        def update_from_run(self, experiment_id, run_id, artifact_store):
            self.calls.append((experiment_id, run_id, artifact_store))

    analytics = DummyAnalyticsStore()
    experiment, store, runner = _make_runner(
        tmp_path,
        direction="long",
        run_id="20260227_040404",
        analytics_store=analytics,
    )
    monkeypatch.setattr("autowfo.experiment_runner.compose", _fake_compose)
    monkeypatch.setattr(ExperimentRunner, "_run_window_backtest", _fake_window_metrics)

    result = runner.run()

    assert isinstance(result, RunResult)
    assert len(analytics.calls) == 1
    call = analytics.calls[0]
    assert call[0] == experiment.experiment_id
    assert call[1] == "20260227_040404"
    assert call[2] is store


def test_analytics_hook_failure_does_not_break_run(tmp_path, monkeypatch):
    class FailingAnalyticsStore:
        def update_from_run(self, experiment_id, run_id, artifact_store):
            _ = (experiment_id, run_id, artifact_store)
            raise RuntimeError("analytics failed")

    _experiment, _store, runner = _make_runner(
        tmp_path,
        direction="long",
        run_id="20260227_050505",
        analytics_store=FailingAnalyticsStore(),
    )
    monkeypatch.setattr("autowfo.experiment_runner.compose", _fake_compose)
    monkeypatch.setattr(ExperimentRunner, "_run_window_backtest", _fake_window_metrics)

    result = runner.run()
    assert isinstance(result, RunResult)
    assert result.n_errors == 0

