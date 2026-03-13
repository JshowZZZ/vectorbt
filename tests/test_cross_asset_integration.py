from __future__ import annotations

import math
import os
from pathlib import Path

import pandas as pd
import pytest


@pytest.mark.slow
def test_cross_asset_integration_end_to_end(tmp_path, monkeypatch):
    pytest.importorskip("duckdb")
    vbt = pytest.importorskip("vectorbt")

    from autowfo import data_multi
    from autowfo.analytics import AnalyticsStore
    from autowfo.artifact_store import ArtifactStore
    from autowfo.experiment import Experiment
    from autowfo.experiment_runner import ExperimentRunner
    from autowfo.signal_composer import compose

    def _build_ohlcv(symbol: str, freq: str, bars: int, seed: int) -> pd.DataFrame:
        start = pd.Timestamp("2026-01-01 00:00:00", tz="UTC")
        if freq == "1h":
            end = start + pd.Timedelta(hours=bars - 1)
        elif freq == "4h":
            end = start + pd.Timedelta(hours=(bars - 1) * 4)
        else:
            raise ValueError(f"unsupported freq: {freq}")

        close = (
            vbt.GBMData.download(symbol, start=start, end=end, freq=freq, seed=seed)
            .get()
            .tz_convert(None)
            .iloc[:bars]
        )
        open_ = close.shift(1).fillna(close.iloc[0])
        high = pd.concat([open_, close], axis=1).max(axis=1) * 1.01
        low = pd.concat([open_, close], axis=1).min(axis=1) * 0.99
        volume = pd.Series(
            1000.0 + (pd.RangeIndex(len(close)) % 80),
            index=close.index,
            dtype=float,
        )
        return pd.DataFrame(
            {
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            },
            index=close.index,
        )

    btc_1h = _build_ohlcv("BTC", "1h", 500, seed=11)
    eth_4h = _build_ohlcv("ETH", "4h", 500, seed=22)
    bnb_1h = _build_ohlcv("BNB", "1h", 500, seed=33)

    source_dir = tmp_path / "source_parquet"
    source_dir.mkdir(parents=True, exist_ok=True)

    src_btc_1h = source_dir / "binance_btc-usdt_1h.parquet"
    src_eth_4h = source_dir / "binance_eth-usdt_4h.parquet"
    src_bnb_1h = source_dir / "binance_bnb-usdt_1h.parquet"
    btc_1h.to_pickle(src_btc_1h)
    eth_4h.to_pickle(src_eth_4h)
    bnb_1h.to_pickle(src_bnb_1h)

    monkeypatch.setattr(data_multi, "_select_parquet_engine", lambda: "mock")
    monkeypatch.setattr(data_multi, "_read_parquet", lambda path, engine: pd.read_pickle(path))

    def _mock_write_parquet_atomic(df: pd.DataFrame, path: Path, engine: str) -> None:
        _ = engine
        tmp_path_local = path.with_suffix(".tmp")
        df.to_pickle(tmp_path_local)
        os.replace(tmp_path_local, path)

    monkeypatch.setattr(data_multi, "_write_parquet_atomic", _mock_write_parquet_atomic)

    source_map = {
        ("BTC/USDT", "1h"): src_btc_1h,
        ("ETH/USDT", "4h"): src_eth_4h,
        ("BNB/USDT", "1h"): src_bnb_1h,
    }

    def _mock_fetch_ohlcv_ccxt(asset, timeframe, start_ts, end_ts, exchange):
        _ = (start_ts, end_ts, exchange)
        key = (str(asset), str(timeframe))
        return pd.read_pickle(source_map[key])

    monkeypatch.setattr(data_multi, "_fetch_ohlcv_ccxt", _mock_fetch_ohlcv_ccxt)

    experiment_1 = Experiment.from_dict(
        {
            "experiment_id": "exp_cross_asset_rsi_bb",
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
                        "threshold_values": [55],
                    }
                },
                "require_all": True,
            },
            "action": {
                "asset": "ETH/USDT",
                "timeframe": "4h",
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
                "direction": "both",
            },
            "risk": {
                "stoploss_pct_values": [-3],
                "take_profit_pct_values": [5],
                "max_hold_bars_values": [24],
            },
            "wf": {"train_days": 30, "test_days": 10, "step_days": 10},
        }
    )

    trigger_1, action_1 = data_multi.load_experiment_data(
        experiment=experiment_1,
        start_date=str(eth_4h.index[0]),
        end_date=str(eth_4h.index[-1]),
        cache_dir=tmp_path / "ohlcv_cache",
    )

    combo_1 = experiment_1.expand_grid()[0]
    signals_1 = compose(trigger_1, action_1, experiment_1, combo_1)
    assert not signals_1.entry_long.isna().any()
    assert not signals_1.entry_short.isna().any()
    assert not signals_1.exit_long.isna().any()
    assert not signals_1.exit_short.isna().any()

    artifacts_dir = tmp_path / "artifacts"
    store_1 = ArtifactStore(experiment_1.experiment_id, base_dir=artifacts_dir)
    runner_1 = ExperimentRunner(
        experiment=experiment_1,
        trigger_ohlcv=trigger_1,
        action_ohlcv=action_1,
        artifact_store=store_1,
        run_id="20260301_120000",
    )
    run_1 = runner_1.run()
    assert run_1.n_completed >= 1

    rows_1 = store_1.query_run_results(run_id=run_1.run_id, limit=50)
    assert len(rows_1) >= 1
    for row in rows_1:
        assert math.isfinite(float(row["oos_sharpe"]))

    experiment_2 = Experiment.from_dict(
        {
            "experiment_id": "exp_cross_asset_macd_ema",
            "mode": "hypothesis",
            "trigger": {
                "asset": "BNB/USDT",
                "timeframe": "1h",
                "indicators": ["MACD"],
                "conditions": {
                    "MACD": {
                        "operator": "above",
                        "macd_fast_values": [12],
                        "macd_slow_values": [26],
                        "macd_signal_values": [9],
                        "threshold_values": [0.0],
                    }
                },
                "require_all": True,
            },
            "action": {
                "asset": "ETH/USDT",
                "timeframe": "4h",
                "indicators": ["EMA"],
                "conditions": {
                    "EMA": {
                        "operator": "above",
                        "ema_period_values": [20],
                        "threshold_values": [0.0],
                    }
                },
                "require_all": True,
                "direction": "both",
            },
            "risk": {
                "stoploss_pct_values": [-3],
                "take_profit_pct_values": [5],
                "max_hold_bars_values": [24],
            },
            "wf": {"train_days": 30, "test_days": 10, "step_days": 10},
        }
    )

    trigger_2, action_2 = data_multi.load_experiment_data(
        experiment=experiment_2,
        start_date=str(eth_4h.index[0]),
        end_date=str(eth_4h.index[-1]),
        cache_dir=tmp_path / "ohlcv_cache",
    )

    store_2 = ArtifactStore(experiment_2.experiment_id, base_dir=artifacts_dir)
    runner_2 = ExperimentRunner(
        experiment=experiment_2,
        trigger_ohlcv=trigger_2,
        action_ohlcv=action_2,
        artifact_store=store_2,
        run_id="20260301_130000",
    )
    run_2 = runner_2.run()
    assert run_2.n_completed >= 1

    analytics = AnalyticsStore(artifacts_dir / "analytics.duckdb")
    updated_1 = analytics.update_from_run(experiment_1.experiment_id, run_1.run_id, store_1)
    updated_2 = analytics.update_from_run(experiment_2.experiment_id, run_2.run_id, store_2)
    assert updated_1 >= 1
    assert updated_2 >= 1

    comparison = analytics.query_experiment_comparison()
    assert len(comparison) == 2
    assert {row["experiment_id"] for row in comparison} == {
        "exp_cross_asset_rsi_bb",
        "exp_cross_asset_macd_ema",
    }
    assert comparison[0]["avg_oos_sharpe"] >= comparison[1]["avg_oos_sharpe"]

