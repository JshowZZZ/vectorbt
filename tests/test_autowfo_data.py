import numpy as np
import pandas as pd

from autowfo import data as d


def _make_ohlcv(index, base=100.0):
    close = pd.Series(base + np.arange(len(index), dtype=float), index=index)
    return pd.DataFrame(
        {
            "Open": close,
            "High": close * 1.01,
            "Low": close * 0.99,
            "Close": close,
            "Volume": 1000 + np.arange(len(index), dtype=float),
        },
        index=index,
    )


def _common_ctx_kwargs(cache_dir):
    return dict(
        timeframe="3m",
        data_days=10,
        base_symbol="BTC/USDT",
        trade_symbols=["ETH/BTC", "BNB/BTC"],
        exchange="binance",
        cache_dir=cache_dir,
        cache_format="csv",
        vol_lookbacks=[3],
        mom_lookbacks=[3],
        trade_mom_lookbacks=[3],
        rsi_window=3,
        bb_window=3,
        bb_alpha=2.0,
        atr_window=3,
        ma_pairs=[(3, 5)],
        obv_lookbacks=[3],
        volume_lookbacks=[3],
        roc_lookbacks=[3],
        cmf_lookbacks=[3],
        mfi_window=3,
        vroc_lookbacks=[3],
        ad_lookbacks=[3],
        cci_lookbacks=[3],
        willr_lookbacks=[3],
        adx_lookbacks=[3],
        trix_lookbacks=[3],
        dpo_lookbacks=[3],
        efi_lookbacks=[3],
        vwma_lookbacks=[3],
        ultosc_periods=(7, 14, 28),
        keltner_lookbacks=[3],
        donchian_lookbacks=[3],
        ppo_fast=12,
        ppo_slow=26,
        ppo_signal=9,
        chop_lookbacks=[3],
        init_cash_usdt=1000,
        capital_mode="shared",
    )


def test_normalize_index_sorts_and_deduplicates():
    index = pd.to_datetime(
        ["2024-01-01 00:00:00Z", "2024-01-01 01:00:00Z", "2024-01-01 01:00:00Z"]
    )
    df = pd.DataFrame({"Close": [1.0, 2.0, 3.0]}, index=index[::-1])
    got = d._normalize_index(df)

    assert got.index.is_monotonic_increasing
    assert len(got.index) == 2
    assert float(got.iloc[-1]["Close"]) == 2.0


def test_prepare_timeframe_context_characterization(tmp_path):
    index = pd.date_range("2024-01-01", periods=50, freq="h")
    base_df = _make_ohlcv(index, base=100.0)
    trade_df = _make_ohlcv(index, base=1.0)

    def loader(symbol, *_args, **_kwargs):
        return base_df if symbol == "BTC/USDT" else trade_df

    kwargs = _common_ctx_kwargs(str(tmp_path / "cache"))
    ctx = d._prepare_timeframe_context(**kwargs, load_or_update_symbol_fn=loader)

    assert ctx["trade_close"].shape[1] == 2
    assert ctx["total_days"] >= 1
    assert ctx["init_cash_btc"] > 0


def test_cache_csv_roundtrip(tmp_path):
    index = pd.date_range("2024-01-01", periods=10, freq="h")
    df = _make_ohlcv(index, base=100.0)
    cache_path = tmp_path / "sample.csv"

    d._write_cache(df, cache_path, "csv")
    loaded = d._read_cache(cache_path, "csv")

    pd.testing.assert_frame_equal(
        d._normalize_index(df),
        d._normalize_index(loaded),
        check_freq=False,
    )


def test_refresh_ohlcv_cache_builds_data_end_maps(tmp_path):
    index = pd.date_range("2024-01-01", periods=5, freq="h")
    df = _make_ohlcv(index, base=100.0)

    def loader(symbol, exchange, timeframe, start, end, cache_dir, cache_format):  # noqa: ARG001
        return df

    payload = d.refresh_ohlcv_cache(
        exchange="binance",
        timeframes=[{"timeframe": "1h", "days": 3}],
        symbols=["ETH/BTC"],
        base_symbol="BTC/USDT",
        cache_dir=str(tmp_path / "cache"),
        cache_format="csv",
        load_or_update_symbol_fn=loader,
    )

    expected_mark = d._format_data_end(index[-1])
    assert payload["timeframe_data_end"]["1h"] == expected_mark
    assert payload["errors"] == []
    assert payload["pair_data_end"] == [
        {"timeframe": "1h", "symbol": "BTC/USDT", "data_end": expected_mark},
        {"timeframe": "1h", "symbol": "ETH/BTC", "data_end": expected_mark},
    ]


def test_refresh_ohlcv_cache_keeps_partial_results_on_symbol_error(tmp_path):
    index = pd.date_range("2024-01-01", periods=5, freq="h")
    df = _make_ohlcv(index, base=100.0)

    def loader(symbol, exchange, timeframe, start, end, cache_dir, cache_format):  # noqa: ARG001
        if symbol == "ETH/BTC":
            raise RuntimeError("boom")
        return df

    payload = d.refresh_ohlcv_cache(
        exchange="binance",
        timeframes=[{"timeframe": "1h", "days": 3}],
        symbols=["ETH/BTC"],
        base_symbol="BTC/USDT",
        cache_dir=str(tmp_path / "cache"),
        cache_format="csv",
        load_or_update_symbol_fn=loader,
    )

    expected_mark = d._format_data_end(index[-1])
    assert payload["timeframe_data_end"]["1h"] == expected_mark
    assert payload["pair_data_end"] == [
        {"timeframe": "1h", "symbol": "BTC/USDT", "data_end": expected_mark},
    ]
    assert payload["errors"]
    assert "ETH/BTC" in payload["errors"][0]

