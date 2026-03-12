from __future__ import annotations

import os
import threading
import time
from types import SimpleNamespace

import pandas as pd
import pytest

from scripts.autowfo import data_multi


def _make_ohlcv(start: str, periods: int, freq: str = "1h") -> pd.DataFrame:
    index = pd.date_range(start, periods=periods, freq=freq)
    close = pd.Series(100.0 + pd.RangeIndex(periods), index=index, dtype=float)
    return pd.DataFrame(
        {
            "open": close * 0.999,
            "high": close * 1.002,
            "low": close * 0.998,
            "close": close,
            "volume": pd.Series(1000.0, index=index, dtype=float),
        }
    )


@pytest.fixture(autouse=True)
def _mock_parquet_engine(monkeypatch):
    monkeypatch.setattr(data_multi, "_select_parquet_engine", lambda: "mock")

    def fake_read(path, engine):
        assert engine == "mock"
        return pd.read_pickle(path)

    def fake_write(df, path, engine):
        assert engine == "mock"
        tmp_path = path.with_suffix(f"{path.suffix}.tmp")
        df.to_pickle(tmp_path)
        os.replace(tmp_path, path)

    monkeypatch.setattr(data_multi, "_read_parquet", fake_read)
    monkeypatch.setattr(data_multi, "_write_parquet_atomic", fake_write)


def test_load_ohlcv_cache_miss_fetches_and_writes(tmp_path, monkeypatch):
    source = _make_ohlcv("2025-01-01", periods=12, freq="1h")
    calls = []

    def fake_fetch(asset, timeframe, start_ts, end_ts, exchange):
        calls.append((asset, timeframe, start_ts, end_ts, exchange))
        return source

    monkeypatch.setattr(data_multi, "_fetch_ohlcv", fake_fetch)

    out = data_multi.load_ohlcv(
        asset="BTC/USDT",
        timeframe="1h",
        start_date="2025-01-01",
        end_date="2025-01-01 05:00:00",
        cache_dir=tmp_path,
    )

    assert len(calls) == 1
    assert list(out.columns) == ["open", "high", "low", "close", "volume"]
    assert isinstance(out.index, pd.DatetimeIndex)
    assert out.index.min() >= pd.Timestamp("2025-01-01 00:00:00")
    assert out.index.max() <= pd.Timestamp("2025-01-01 05:00:00")
    assert (tmp_path / "binance_btc-usdt_1h.parquet").exists()


def test_load_ohlcv_cache_hit_does_not_fetch(tmp_path, monkeypatch):
    source = _make_ohlcv("2025-01-01", periods=10, freq="1h")

    def fake_fetch(*_args, **_kwargs):
        return source

    monkeypatch.setattr(data_multi, "_fetch_ohlcv", fake_fetch)
    data_multi.load_ohlcv(
        asset="BTC/USDT",
        timeframe="1h",
        start_date="2025-01-01",
        end_date="2025-01-01 08:00:00",
        cache_dir=tmp_path,
    )

    def should_not_fetch(*_args, **_kwargs):
        raise AssertionError("fetch should not be called on cache hit")

    monkeypatch.setattr(data_multi, "_fetch_ohlcv", should_not_fetch)
    out = data_multi.load_ohlcv(
        asset="BTC/USDT",
        timeframe="1h",
        start_date="2025-01-01 01:00:00",
        end_date="2025-01-01 07:00:00",
        cache_dir=tmp_path,
    )

    assert len(out) == 7
    assert out.index[0] == pd.Timestamp("2025-01-01 01:00:00")
    assert out.index[-1] == pd.Timestamp("2025-01-01 07:00:00")


def test_load_ohlcv_insufficient_cache_fetches_and_merges(tmp_path, monkeypatch):
    initial = _make_ohlcv("2025-01-01", periods=4, freq="1h")
    extended = _make_ohlcv("2025-01-01", periods=8, freq="1h")
    calls = []

    def fake_fetch(*_args, **_kwargs):
        calls.append(1)
        if len(calls) == 1:
            return initial
        return extended

    monkeypatch.setattr(data_multi, "_fetch_ohlcv", fake_fetch)

    data_multi.load_ohlcv(
        asset="BTC/USDT",
        timeframe="1h",
        start_date="2025-01-01",
        end_date="2025-01-01 03:00:00",
        cache_dir=tmp_path,
    )
    out = data_multi.load_ohlcv(
        asset="BTC/USDT",
        timeframe="1h",
        start_date="2025-01-01",
        end_date="2025-01-01 07:00:00",
        cache_dir=tmp_path,
    )

    assert len(calls) == 2
    assert len(out) == 8

    cached_df = pd.read_pickle(tmp_path / "binance_btc-usdt_1h.parquet")
    assert len(cached_df) == 8


def test_load_experiment_data_returns_trigger_and_action(tmp_path, monkeypatch):
    source = _make_ohlcv("2025-01-01", periods=6, freq="1h")
    calls = []

    def fake_load_ohlcv(asset, timeframe, start_date, end_date=None, exchange="binance", cache_dir="artifacts/ohlcv"):
        calls.append((asset, timeframe, start_date, end_date, exchange, cache_dir))
        return source.copy()

    monkeypatch.setattr(data_multi, "load_ohlcv", fake_load_ohlcv)

    experiment = SimpleNamespace(
        config={
            "trigger": {"asset": "BTC/USDT", "timeframe": "1h"},
            "action": {"asset": "ETH/USDT", "timeframe": "4h"},
        }
    )

    trigger_df, action_df = data_multi.load_experiment_data(
        experiment=experiment,
        start_date="2025-01-01",
        end_date="2025-01-02",
        cache_dir=tmp_path,
    )

    assert len(calls) == 2
    assert calls[0][0:2] == ("BTC/USDT", "1h")
    assert calls[1][0:2] == ("ETH/USDT", "4h")
    assert isinstance(trigger_df, pd.DataFrame)
    assert isinstance(action_df, pd.DataFrame)


def test_cache_info_lists_cached_files(tmp_path, monkeypatch):
    source = _make_ohlcv("2025-01-01", periods=5, freq="1h")

    def fake_fetch(*_args, **_kwargs):
        return source

    monkeypatch.setattr(data_multi, "_fetch_ohlcv", fake_fetch)

    data_multi.load_ohlcv(
        asset="BTC/USDT",
        timeframe="1h",
        start_date="2025-01-01",
        end_date="2025-01-01 04:00:00",
        cache_dir=tmp_path,
    )

    items = data_multi.cache_info(tmp_path)
    assert len(items) == 1
    row = items[0]
    assert row["file"] == "binance_btc-usdt_1h.parquet"
    assert row["asset"] == "btc-usdt"
    assert row["timeframe"] == "1h"
    assert row["rows"] == 5
    assert row["size_bytes"] > 0
    assert row["date_start"] == "2025-01-01T00:00:00"
    assert row["date_end"] == "2025-01-01T04:00:00"


def test_load_ohlcv_concurrent_calls_are_safe(tmp_path, monkeypatch):
    source = _make_ohlcv("2025-01-01", periods=12, freq="1h")
    fetch_count = {"value": 0}
    fetch_lock = threading.Lock()

    def fake_fetch(*_args, **_kwargs):
        with fetch_lock:
            fetch_count["value"] += 1
        time.sleep(0.15)
        return source

    monkeypatch.setattr(data_multi, "_fetch_ohlcv", fake_fetch)

    results = []
    errors = []

    def worker():
        try:
            df = data_multi.load_ohlcv(
                asset="BTC/USDT",
                timeframe="1h",
                start_date="2025-01-01",
                end_date="2025-01-01 10:00:00",
                cache_dir=tmp_path,
            )
            results.append(df)
        except Exception as exc:  # pragma: no cover - should not happen
            errors.append(exc)

    threads = [threading.Thread(target=worker), threading.Thread(target=worker)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    assert len(results) == 2
    pd.testing.assert_frame_equal(results[0], results[1])
    assert fetch_count["value"] == 1
    assert (tmp_path / "binance_btc-usdt_1h.parquet").exists()
