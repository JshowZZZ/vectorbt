from __future__ import annotations

import sqlite3

import numpy as np
import pandas as pd

from scripts.autowfo.artifact_store import ArtifactStore
from scripts.autowfo.experiment import Experiment
from scripts.autowfo.experiment_runner import ExperimentRunner
from scripts.autowfo.signal_composer import compose


def _make_ohlcv(
    n_bars: int = 100,
    freq: str = "1h",
    trend: str = "flat",
    spike_indices: list[int] | None = None,
) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=n_bars, freq=freq)
    if trend == "flat":
        close = pd.Series(100.0, index=index, dtype=float)
    elif trend == "up":
        close = pd.Series(100.0 + np.arange(n_bars) * 0.5, index=index, dtype=float)
    elif trend == "down":
        close = pd.Series(100.0 - np.arange(n_bars) * 0.3, index=index, dtype=float)
    else:
        raise ValueError(f"unknown trend: {trend}")

    volume = pd.Series(1000.0, index=index, dtype=float)
    for idx in spike_indices or []:
        if 0 <= idx < n_bars:
            volume.iloc[idx] = 3000.0

    return pd.DataFrame(
        {
            "open": close * 0.999,
            "high": close * 1.005,
            "low": close * 0.995,
            "close": close,
            "volume": volume,
        }
    )


def _build_experiment(
    experiment_id: str,
    direction: str,
    trigger_timeframe: str = "1h",
    action_timeframe: str = "1h",
    trigger_multiplier: float = 1.2,
) -> Experiment:
    config = {
        "experiment_id": experiment_id,
        "mode": "hypothesis",
        "trigger": {
            "asset": "BTC/USDT",
            "timeframe": trigger_timeframe,
            "indicators": ["Volume"],
            "conditions": {
                "Volume": {
                    "operator": "above_avg",
                    "vol_period_values": [2],
                    "multiplier_values": [trigger_multiplier],
                }
            },
            "require_all": True,
        },
        "action": {
            "asset": "ETH/USDT",
            "timeframe": action_timeframe,
            "indicators": ["Volume"],
            "conditions": {
                "Volume": {
                    "operator": "above_avg",
                    "vol_period_values": [1],
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
    return Experiment.from_dict(config)


def _run_experiment(
    experiment: Experiment,
    trigger_ohlcv: pd.DataFrame,
    action_ohlcv: pd.DataFrame,
    tmp_path,
    run_id: str,
):
    store = ArtifactStore(experiment.experiment_id, base_dir=tmp_path / "artifacts")
    runner = ExperimentRunner(
        experiment=experiment,
        trigger_ohlcv=trigger_ohlcv,
        action_ohlcv=action_ohlcv,
        artifact_store=store,
        run_id=run_id,
    )
    result = runner.run()
    conn = sqlite3.connect(store.get_run_db_path(run_id))
    return result, conn


def test_both_directions_produce_rows(tmp_path):
    experiment = _build_experiment("exp_dual_both_v1", direction="both")
    trigger_ohlcv = _make_ohlcv(n_bars=24 * 12, freq="1h", trend="up", spike_indices=[20, 40, 60, 80])
    action_ohlcv = _make_ohlcv(n_bars=24 * 12, freq="1h", trend="up")

    grid = experiment.expand_grid()
    assert {row["direction"] for row in grid} == {"long", "short"}

    result, conn = _run_experiment(experiment, trigger_ohlcv, action_ohlcv, tmp_path, run_id="20260227_030001")
    try:
        directions = {row[0] for row in conn.execute("SELECT direction FROM combo_results").fetchall()}
        row_count = conn.execute("SELECT COUNT(*) FROM combo_results").fetchone()[0]
    finally:
        conn.close()

    assert result.n_combos == 2
    assert row_count == 2
    assert directions == {"long", "short"}


def test_long_only_experiment_stores_only_long(tmp_path):
    experiment = _build_experiment("exp_dual_long_v1", direction="long")
    trigger_ohlcv = _make_ohlcv(n_bars=24 * 12, freq="1h", trend="up", spike_indices=[12, 36, 72])
    action_ohlcv = _make_ohlcv(n_bars=24 * 12, freq="1h", trend="flat")

    result, conn = _run_experiment(experiment, trigger_ohlcv, action_ohlcv, tmp_path, run_id="20260227_030002")
    try:
        directions = {row[0] for row in conn.execute("SELECT direction FROM combo_results").fetchall()}
    finally:
        conn.close()

    assert result.n_combos == 1
    assert directions == {"long"}


def test_short_only_experiment_stores_only_short(tmp_path):
    experiment = _build_experiment("exp_dual_short_v1", direction="short")
    trigger_ohlcv = _make_ohlcv(n_bars=24 * 12, freq="1h", trend="down", spike_indices=[10, 30, 50, 70])
    action_ohlcv = _make_ohlcv(n_bars=24 * 12, freq="1h", trend="flat")

    result, conn = _run_experiment(experiment, trigger_ohlcv, action_ohlcv, tmp_path, run_id="20260227_030003")
    try:
        directions = {row[0] for row in conn.execute("SELECT direction FROM combo_results").fetchall()}
    finally:
        conn.close()

    assert result.n_combos == 1
    assert directions == {"short"}


def test_signal_asymmetry_entries_are_mutually_exclusive(tmp_path):
    experiment = _build_experiment("exp_dual_asym_v1", direction="both")
    trigger_ohlcv = _make_ohlcv(n_bars=24 * 12, freq="1h", trend="flat", spike_indices=[8, 24, 56])
    action_ohlcv = _make_ohlcv(n_bars=24 * 12, freq="1h", trend="flat")

    combos = experiment.expand_grid()
    long_combo = next(row for row in combos if row["direction"] == "long")
    short_combo = next(row for row in combos if row["direction"] == "short")

    long_sig = compose(trigger_ohlcv, action_ohlcv, experiment, long_combo)
    short_sig = compose(trigger_ohlcv, action_ohlcv, experiment, short_combo)

    assert not bool((long_sig.entry_long & long_sig.entry_short).any())
    assert not bool((short_sig.entry_long & short_sig.entry_short).any())
    assert bool(long_sig.entry_short.any()) is False
    assert bool(short_sig.entry_long.any()) is False


def test_cross_timeframe_alignment_with_both_directions(tmp_path):
    experiment = _build_experiment(
        "exp_dual_cross_tf_v1",
        direction="both",
        trigger_timeframe="1h",
        action_timeframe="4h",
    )
    trigger_ohlcv = _make_ohlcv(n_bars=24 * 12, freq="1h", trend="flat", spike_indices=[2, 6, 10, 50])
    action_ohlcv = _make_ohlcv(n_bars=6 * 12, freq="4h", trend="flat")

    combos = experiment.expand_grid()
    long_combo = next(row for row in combos if row["direction"] == "long")
    short_combo = next(row for row in combos if row["direction"] == "short")

    long_sig = compose(trigger_ohlcv, action_ohlcv, experiment, long_combo)
    short_sig = compose(trigger_ohlcv, action_ohlcv, experiment, short_combo)

    expected = [False, True, True, True, False]
    assert long_sig.entry_long.iloc[:5].tolist() == expected
    assert short_sig.entry_short.iloc[:5].tolist() == expected

    result, conn = _run_experiment(experiment, trigger_ohlcv, action_ohlcv, tmp_path, run_id="20260227_030004")
    try:
        directions = {row[0] for row in conn.execute("SELECT direction FROM combo_results").fetchall()}
    finally:
        conn.close()

    assert result.n_combos == 2
    assert directions == {"long", "short"}


def test_empty_signals_still_stored_with_zero_trades(tmp_path):
    experiment = _build_experiment("exp_dual_empty_v1", direction="both", trigger_multiplier=2.0)
    trigger_ohlcv = _make_ohlcv(n_bars=24 * 12, freq="1h", trend="flat", spike_indices=[])
    action_ohlcv = _make_ohlcv(n_bars=24 * 12, freq="1h", trend="flat")

    result, conn = _run_experiment(experiment, trigger_ohlcv, action_ohlcv, tmp_path, run_id="20260227_030005")
    try:
        rows = conn.execute("SELECT direction, oos_n_trades FROM combo_results ORDER BY direction").fetchall()
    finally:
        conn.close()

    assert result.n_combos == 2
    assert len(rows) == 2
    assert rows[0][1] == 0
    assert rows[1][1] == 0
