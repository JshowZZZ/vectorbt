from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest


@pytest.mark.slow
def test_real_data_smoke_runner_to_analytics(tmp_path, monkeypatch):
    pytest.importorskip("duckdb")
    vbt = pytest.importorskip("vectorbt")

    from autowfo import data_multi
    from autowfo.analytics import AnalyticsStore
    from autowfo.artifact_store import ArtifactStore
    from autowfo.experiment import Experiment
    from autowfo.experiment_runner import ExperimentRunner

    start = pd.Timestamp("2026-01-01 00:00:00", tz="UTC")
    end = start + pd.Timedelta(hours=499)
    close = (
        vbt.GBMData.download("BTC", start=start, end=end, freq="1h", seed=7)
        .get()
        .tz_convert(None)
        .iloc[:500]
    )
    open_ = close.shift(1).fillna(close.iloc[0])
    high = pd.concat([open_, close], axis=1).max(axis=1) * 1.02
    low = pd.concat([open_, close], axis=1).min(axis=1) * 0.98
    volume = pd.Series(
        1000.0 + (pd.RangeIndex(len(close)) % 50),
        index=close.index,
        dtype=float,
    )
    ohlcv = pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
        index=close.index,
    )

    source_parquet = tmp_path / "btc_1h_source.parquet"
    ohlcv.to_pickle(source_parquet)

    # Keep the test independent of optional pyarrow/fastparquet runtime.
    monkeypatch.setattr(data_multi, "_select_parquet_engine", lambda: "mock")
    monkeypatch.setattr(data_multi, "_read_parquet", lambda path, engine: pd.read_pickle(path))

    def _mock_write_parquet_atomic(df: pd.DataFrame, path: Path, engine: str) -> None:
        _ = engine
        tmp_path_local = path.with_suffix(".tmp")
        df.to_pickle(tmp_path_local)
        os.replace(tmp_path_local, path)

    monkeypatch.setattr(data_multi, "_write_parquet_atomic", _mock_write_parquet_atomic)

    fetch_calls = {"count": 0}

    def _mock_fetch_ohlcv_ccxt(asset, timeframe, start_ts, end_ts, exchange):
        _ = (asset, timeframe, start_ts, end_ts, exchange)
        fetch_calls["count"] += 1
        return pd.read_pickle(source_parquet)

    monkeypatch.setattr(data_multi, "_fetch_ohlcv_ccxt", _mock_fetch_ohlcv_ccxt)

    loaded = data_multi.load_ohlcv(
        asset="BTC/USDT",
        timeframe="1h",
        start_date=str(close.index[0]),
        end_date=str(close.index[-1]),
        exchange="binance",
        cache_dir=tmp_path / "ohlcv_cache",
    )
    assert fetch_calls["count"] == 1
    assert len(loaded) == 500

    experiment = Experiment.from_dict(
        {
            "experiment_id": "exp_real_data_smoke",
            "mode": "hypothesis",
            "trigger": {
                "asset": "BTC/USDT",
                "timeframe": "1h",
                "indicators": ["RSI"],
                "conditions": {
                    "RSI": {
                        "operator": "below",
                        "param_name": "rsi_period",
                        "param_values": [14],
                        "threshold_values": [58],
                    }
                },
                "require_all": True,
            },
            "action": {
                "asset": "BTC/USDT",
                "timeframe": "1h",
                "indicators": ["BB"],
                "conditions": {
                    "BB": {
                        "operator": "near_lower",
                        "bb_period_values": [20],
                        "bb_std_values": [2.0],
                        "pct_values": [0.85],
                    }
                },
                "require_all": True,
                "direction": "long",
            },
            "risk": {
                "stoploss_pct_values": [-2],
                "take_profit_pct_values": [2],
                "max_hold_bars_values": [24],
            },
            "wf": {"train_days": 30, "test_days": 10, "step_days": 10},
        }
    )

    artifacts_dir = tmp_path / "artifacts"
    store = ArtifactStore(experiment.experiment_id, base_dir=artifacts_dir)
    runner = ExperimentRunner(
        experiment=experiment,
        trigger_ohlcv=loaded,
        action_ohlcv=loaded,
        artifact_store=store,
        run_id="20260301_120000",
    )
    run_result = runner.run()

    assert run_result.n_completed >= 1
    rows = store.query_run_results(run_id=run_result.run_id, limit=10)
    assert len(rows) >= 1

    analytics_store = AnalyticsStore(artifacts_dir / "analytics.duckdb")
    updated_rows = analytics_store.update_from_run(experiment.experiment_id, run_result.run_id, store)
    assert updated_rows >= 1
    leaderboard = analytics_store.query_indicator_leaderboard(limit=20)
    assert len(leaderboard) >= 1

