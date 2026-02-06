"""Data access and context-building helpers extracted from the monolith.

AWF-000 step 2: keep behavior unchanged while making the module independently
importable and testable.
"""

import os

import numpy as np
import pandas as pd
import vectorbt as vbt


def _normalize_index(df):
    view = df.copy()
    view.index = pd.to_datetime(view.index, utc=True).tz_convert(None)
    view = view[~view.index.duplicated(keep="last")].sort_index()
    return view


def _has_parquet_engine():
    try:
        import pyarrow  # noqa: F401

        return True
    except Exception:
        try:
            import fastparquet  # noqa: F401

            return True
        except Exception:
            return False


def _fetch_top_trade_symbols(exchange, limit=10, fallback=None):
    fallback = list(fallback or [])
    try:
        import ccxt  # type: ignore
    except Exception:
        return fallback[:limit]
    try:
        exchange_cls = getattr(ccxt, exchange, None)
        if exchange_cls is None:
            return fallback[:limit]
        ex = exchange_cls({"enableRateLimit": True})
        tickers = ex.fetch_tickers()
        pairs = []
        for symbol, data in tickers.items():
            if not symbol.endswith("/BTC"):
                continue
            if any(flag in symbol for flag in ("UP/", "DOWN/", "BULL/", "BEAR/")):
                continue
            vol = data.get("quoteVolume")
            if vol is None:
                vol = data.get("baseVolume")
            if vol is None:
                continue
            pairs.append((symbol, float(vol)))
        pairs.sort(key=lambda x: x[1], reverse=True)
        symbols = [sym for sym, _ in pairs[: max(limit, 10)]]
        return symbols[:limit] if symbols else fallback[:limit]
    except Exception as exc:
        print(f"[warn] failed to fetch top symbols: {exc}")
        return fallback[:limit]


def _read_cache(path, cache_format):
    if cache_format == "parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path, index_col=0, parse_dates=True)


def _write_cache(df, path, cache_format):
    if cache_format == "parquet":
        df.to_parquet(path, index=True)
    else:
        df.to_csv(path, index=True)


def _download_symbol_ohlcv(
    symbol,
    exchange,
    timeframe,
    start,
    end,
    show_progress,
    normalize_index_fn=None,
):
    if normalize_index_fn is None:
        normalize_index_fn = _normalize_index
    data = vbt.CCXTData.download(
        symbol,
        exchange=exchange,
        timeframe=timeframe,
        start=start,
        end=end,
        show_progress=show_progress,
        config={"enableRateLimit": True},
    )
    open_ = data.get("Open")
    high = data.get("High")
    low = data.get("Low")
    close = data.get("Close")
    volume = data.get("Volume")
    df = pd.concat([open_, high, low, close, volume], axis=1)
    df.columns = ["Open", "High", "Low", "Close", "Volume"]
    return normalize_index_fn(df)


def _load_or_update_symbol(
    symbol,
    exchange,
    timeframe,
    start,
    end,
    cache_dir,
    cache_format,
    read_cache_fn=None,
    write_cache_fn=None,
    download_symbol_ohlcv_fn=None,
    normalize_index_fn=None,
):
    if read_cache_fn is None:
        read_cache_fn = _read_cache
    if write_cache_fn is None:
        write_cache_fn = _write_cache
    if download_symbol_ohlcv_fn is None:
        download_symbol_ohlcv_fn = _download_symbol_ohlcv
    if normalize_index_fn is None:
        normalize_index_fn = _normalize_index

    os.makedirs(cache_dir, exist_ok=True)
    cache_name = f"{exchange}_{symbol.replace('/', '-')}_{timeframe}.{cache_format}"
    cache_path = os.path.join(cache_dir, cache_name)
    if os.path.exists(cache_path):
        df = read_cache_fn(cache_path, cache_format)
        df = normalize_index_fn(df)
        last_ts = df.index.max()
        try:
            step = pd.Timedelta(timeframe)
        except ValueError:
            step = pd.Timedelta("1h")
        update_start = last_ts + step
        now_ts = pd.Timestamp.now(tz="UTC").tz_convert(None)
        if update_start < now_ts:
            try:
                new_df = download_symbol_ohlcv_fn(
                    symbol,
                    exchange,
                    timeframe,
                    start=update_start.isoformat(),
                    end=end,
                    show_progress=False,
                )
            except Exception as exc:
                print(f"[warn] update failed for {symbol}, using cached data: {exc}")
                return df
            if not new_df.empty:
                df = pd.concat([df, new_df], axis=0)
                df = df[~df.index.duplicated(keep="last")].sort_index()
                write_cache_fn(df, cache_path, cache_format)
    else:
        df = download_symbol_ohlcv_fn(symbol, exchange, timeframe, start, end, show_progress=True)
        write_cache_fn(df, cache_path, cache_format)
    return df


def _prepare_timeframe_context(
    timeframe,
    data_days,
    base_symbol,
    trade_symbols,
    exchange,
    cache_dir,
    cache_format,
    vol_lookbacks,
    mom_lookbacks,
    trade_mom_lookbacks,
    rsi_window,
    bb_window,
    bb_alpha,
    atr_window,
    ma_pairs,
    obv_lookbacks,
    volume_lookbacks,
    roc_lookbacks,
    cmf_lookbacks,
    mfi_window,
    vroc_lookbacks,
    ad_lookbacks,
    init_cash_usdt,
    capital_mode,
    load_or_update_symbol_fn=None,
):
    if load_or_update_symbol_fn is None:
        load_or_update_symbol_fn = _load_or_update_symbol

    start = f"{data_days} days ago UTC"
    end = "now UTC"
    all_symbols = [base_symbol] + trade_symbols
    symbol_data = {}
    for symbol in all_symbols:
        try:
            symbol_data[symbol] = load_or_update_symbol_fn(
                symbol, exchange, timeframe, start, end, cache_dir, cache_format
            )
        except Exception as exc:
            print(f"[warn] skip {symbol}: {exc}")

    # Keep the effective window close to requested `data_days` even when cache files
    # have grown older than the latest run configuration.
    try:
        latest_end = min(df.index.max() for df in symbol_data.values() if not df.empty)
        if pd.notna(latest_end):
            window_start = latest_end - pd.Timedelta(days=int(data_days))
            for symbol, df in list(symbol_data.items()):
                clipped = df.loc[df.index >= window_start]
                if not clipped.empty:
                    symbol_data[symbol] = clipped
    except Exception:
        pass

    if base_symbol not in symbol_data:
        raise RuntimeError(f"Base symbol not available: {base_symbol}")
    trade_symbols = [symbol for symbol in trade_symbols if symbol in symbol_data]
    if not trade_symbols:
        raise RuntimeError("No trade symbols available after data download.")

    close = pd.DataFrame({symbol: df["Close"] for symbol, df in symbol_data.items()})
    high = pd.DataFrame({symbol: df["High"] for symbol, df in symbol_data.items()})
    low = pd.DataFrame({symbol: df["Low"] for symbol, df in symbol_data.items()})
    volume = pd.DataFrame({symbol: df["Volume"] for symbol, df in symbol_data.items()})

    btc_close = close[base_symbol]
    trade_close = close[trade_symbols]
    trade_close = trade_close.dropna(axis=1, how="all")
    trade_symbols = list(trade_close.columns)
    btc_high = high[base_symbol]
    btc_low = low[base_symbol]
    btc_volume = volume[base_symbol]

    if trade_close.empty or btc_close.empty:
        raise RuntimeError("No overlapping data after download.")

    index_sets = [
        trade_close.dropna().index,
        btc_close.dropna().index,
        btc_high.dropna().index,
        btc_low.dropna().index,
        btc_volume.dropna().index,
    ]
    common_index = index_sets[0]
    for idx in index_sets[1:]:
        common_index = common_index.intersection(idx)

    if common_index.empty:
        raise RuntimeError("No overlapping timestamps after alignment.")

    trade_close = trade_close.loc[common_index]
    btc_close = btc_close.loc[common_index]
    btc_high = btc_high.loc[common_index]
    btc_low = btc_low.loc[common_index]
    btc_volume = btc_volume.loc[common_index]

    total_days = int(trade_close.index.normalize().nunique())
    init_cash_btc = init_cash_usdt / float(btc_close.iloc[0])
    if str(capital_mode).lower() == "per_symbol":
        init_cash_btc = np.repeat(init_cash_btc, len(trade_symbols))

    vol_zscore_by_lb = {}
    btc_ret = btc_close.pct_change()
    for lb in vol_lookbacks:
        vol = btc_ret.rolling(lb).std()
        vol_zscore_by_lb[lb] = (vol - vol.rolling(lb).mean()) / vol.rolling(lb).std()

    mom_by_lb = {lb: btc_close.pct_change(lb) for lb in mom_lookbacks}
    trade_mom_by_lb = {lb: trade_close.pct_change(lb) for lb in trade_mom_lookbacks}
    rsi_series = vbt.RSI.run(btc_close, window=rsi_window).rsi
    bbands = vbt.BBANDS.run(btc_close, window=bb_window, alpha=bb_alpha)
    bb_width = bbands.bandwidth
    bb_upper = bbands.upper
    bb_lower = bbands.lower
    atr = vbt.ATR.run(btc_high, btc_low, btc_close, window=atr_window).atr
    atr_ratio = atr / btc_close

    ma_trend_by_pair = {}
    for fast, slow in ma_pairs:
        ma_fast = vbt.MA.run(btc_close, window=fast).ma
        ma_slow = vbt.MA.run(btc_close, window=slow).ma
        ma_trend_by_pair[(fast, slow)] = (ma_fast > ma_slow, ma_fast < ma_slow)

    macd = vbt.MACD.run(btc_close)
    macd_hist_ratio_series = macd.hist / btc_close

    stoch_k = vbt.STOCH.run(btc_high, btc_low, btc_close).percent_k

    obv = vbt.OBV.run(btc_close, btc_volume).obv
    obv_roc_by_lb = {lb: obv.pct_change(lb) for lb in obv_lookbacks}

    volume_zscore_by_lb = {}
    vol_ret = btc_volume.pct_change()
    for lb in volume_lookbacks:
        vol_std = vol_ret.rolling(lb).std()
        volume_zscore_by_lb[lb] = (vol_ret - vol_ret.rolling(lb).mean()) / vol_std

    roc_by_lb = {lb: btc_close.pct_change(lb) for lb in roc_lookbacks}

    typical_price = (btc_high + btc_low + btc_close) / 3
    raw_money_flow = typical_price * btc_volume
    pos_flow = raw_money_flow.where(typical_price > typical_price.shift(1), 0.0)
    neg_flow = raw_money_flow.where(typical_price < typical_price.shift(1), 0.0)
    mfi_by_window = {}
    if mfi_window:
        pos_sum = pos_flow.rolling(mfi_window).sum()
        neg_sum = neg_flow.rolling(mfi_window).sum()
        mfi = 100 - (100 / (1 + pos_sum / neg_sum.replace(0, np.nan)))
        mfi_by_window[mfi_window] = mfi

    mfm = ((btc_close - btc_low) - (btc_high - btc_close)) / (btc_high - btc_low)
    mfm = mfm.replace([np.inf, -np.inf], 0.0).fillna(0.0)
    mfv = mfm * btc_volume
    cmf_by_window = {}
    for lb in cmf_lookbacks:
        denom = btc_volume.rolling(lb).sum()
        cmf_by_window[lb] = mfv.rolling(lb).sum() / denom.replace(0, np.nan)

    vroc_by_lb = {lb: btc_volume.pct_change(lb) for lb in vroc_lookbacks}

    ad_line = mfv.cumsum()
    ad_roc_by_lb = {lb: ad_line.pct_change(lb) for lb in ad_lookbacks}

    data_range = f"{trade_close.index[0]} -> {trade_close.index[-1]}"

    return {
        "timeframe": timeframe,
        "data_days": data_days,
        "start": start,
        "end": end,
        "trade_symbols": trade_symbols,
        "trade_close": trade_close,
        "btc_close": btc_close,
        "btc_high": btc_high,
        "btc_low": btc_low,
        "btc_volume": btc_volume,
        "total_days": total_days,
        "init_cash_btc": init_cash_btc,
        "vol_zscore_by_lb": vol_zscore_by_lb,
        "mom_by_lb": mom_by_lb,
        "trade_mom_by_lb": trade_mom_by_lb,
        "rsi_series": rsi_series,
        "bb_width": bb_width,
        "bb_upper": bb_upper,
        "bb_lower": bb_lower,
        "atr_ratio": atr_ratio,
        "ma_trend_by_pair": ma_trend_by_pair,
        "macd_hist_ratio_series": macd_hist_ratio_series,
        "stoch_k": stoch_k,
        "obv_roc_by_lb": obv_roc_by_lb,
        "volume_zscore_by_lb": volume_zscore_by_lb,
        "roc_by_lb": roc_by_lb,
        "cmf_by_window": cmf_by_window,
        "mfi_by_window": mfi_by_window,
        "mfi_window": mfi_window,
        "vroc_by_lb": vroc_by_lb,
        "ad_roc_by_lb": ad_roc_by_lb,
        "data_range": data_range,
    }
