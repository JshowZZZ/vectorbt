from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest


@pytest.mark.slow
def test_discovery_burnin_three_rounds(tmp_path, monkeypatch):
    pytest.importorskip("duckdb")
    vbt = pytest.importorskip("vectorbt")

    from scripts.autowfo import data_multi
    from scripts.autowfo.analytics import AnalyticsStore
    from scripts.autowfo.artifact_store import ArtifactStore
    from scripts.autowfo.discovery_loop import DiscoveryLoop
    from scripts.autowfo.experiment import Experiment
    from scripts.autowfo.experiment_runner import ExperimentRunner
    from scripts.autowfo.scheduler import ExperimentQueue, SchedulerConfig

    def _build_ohlcv(symbol: str, freq: str, bars: int, seed: int) -> pd.DataFrame:
        start = pd.Timestamp("2026-02-01 00:00:00", tz="UTC")
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
            1200.0 + (pd.RangeIndex(len(close)) % 60),
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

    btc_1h = _build_ohlcv("BTC", "1h", 500, seed=101)
    eth_4h = _build_ohlcv("ETH", "4h", 500, seed=202)

    source_dir = tmp_path / "source_parquet"
    source_dir.mkdir(parents=True, exist_ok=True)
    src_btc_1h = source_dir / "binance_btc-usdt_1h.parquet"
    src_eth_4h = source_dir / "binance_eth-usdt_4h.parquet"
    btc_1h.to_pickle(src_btc_1h)
    eth_4h.to_pickle(src_eth_4h)

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
    }

    def _mock_fetch_ohlcv_ccxt(asset, timeframe, start_ts, end_ts, exchange):
        _ = (start_ts, end_ts, exchange)
        return pd.read_pickle(source_map[(str(asset), str(timeframe))])

    monkeypatch.setattr(data_multi, "_fetch_ohlcv_ccxt", _mock_fetch_ohlcv_ccxt)

    class _FakeTrades:
        def count(self):
            return 12

        def win_rate(self):
            return 60.0

    sharpe_state = {"value": 1.0}

    class _FakePortfolio:
        def __init__(self, sharpe: float):
            self._sharpe = float(sharpe)
            self.trades = _FakeTrades()

        def sharpe_ratio(self):
            return self._sharpe

        def total_return(self):
            return 0.12

    monkeypatch.setattr(
        "scripts.autowfo.experiment_runner.vbt.Portfolio.from_signals",
        lambda *args, **kwargs: _FakePortfolio(sharpe_state["value"]),
    )

    artifacts_dir = tmp_path / "artifacts"
    experiments_root = artifacts_dir / "experiments"
    analytics = AnalyticsStore(artifacts_dir / "analytics.duckdb")
    queue = ExperimentQueue(
        queue_path=artifacts_dir / "scheduler_queue.json",
        config=SchedulerConfig(priority_order=["user_submitted", "discovery", "refine"], max_concurrent=1, schedule_cron=""),
    )

    pool_config = {
        "indicator_ids": ["RSI", "MACD", "BB", "EMA", "Volume"],
        "combo_size_range": [2, 2],
        "pruning": {"enabled": False},
        "default_trigger": {
            "asset": "BTC/USDT",
            "timeframe": "1h",
            "require_all": True,
        },
        "default_action": {
            "asset": "ETH/USDT",
            "timeframe": "4h",
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

    loop = DiscoveryLoop(
        pool_config=pool_config,
        scheduler=queue,
        analytics_store=analytics,
        experiments_root=experiments_root,
    )

    tick_summaries = []
    for round_idx, sharpe in enumerate((0.8, 1.1, 1.4), start=1):
        before_ids = set(queue.experiment_ids())
        tick = loop.tick()
        tick_summaries.append(tick)
        after_ids = set(queue.experiment_ids())

        if round_idx == 3:
            assert tick["enqueued"] == 0
            assert after_ids == before_ids

        item = queue.pop()
        assert item is not None

        exp_cfg = dict(item.get("experiment_config") or {})
        experiment = Experiment.from_dict(exp_cfg)
        exp_path = experiments_root / experiment.experiment_id / "config.json"
        exp_path.parent.mkdir(parents=True, exist_ok=True)
        experiment.save(exp_path)

        trigger_ohlcv, action_ohlcv = data_multi.load_experiment_data(
            experiment=experiment,
            start_date=str(eth_4h.index[0]),
            end_date=str(eth_4h.index[-1]),
            cache_dir=tmp_path / "ohlcv_cache",
        )

        sharpe_state["value"] = float(sharpe)
        store = ArtifactStore(experiment.experiment_id, base_dir=artifacts_dir)
        run_id = f"20260302_0{round_idx}0000"
        runner = ExperimentRunner(
            experiment=experiment,
            trigger_ohlcv=trigger_ohlcv,
            action_ohlcv=action_ohlcv,
            artifact_store=store,
            run_id=run_id,
        )
        result = runner.run()
        assert result.n_completed >= 1
        updated = analytics.update_from_run(experiment.experiment_id, result.run_id, store)
        assert updated >= 1

    leaderboard = analytics.query_indicator_leaderboard(limit=50)
    distinct_entries = set()
    for row in leaderboard:
        for key in ("trigger_indicators", "action_indicators"):
            value = row.get(key)
            if value is None:
                continue
            text = str(value)
            if text and text.lower() != "null":
                distinct_entries.add(text)
    assert len(distinct_entries) >= 2

    # verify queue-empty behavior after draining all remaining items
    while queue.pop() is not None:
        pass
    assert queue.pop() is None

    assert len(tick_summaries) == 3
    assert tick_summaries[0]["generated"] == 10
