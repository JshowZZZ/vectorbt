"""Data access and context-building helpers extracted from the monolith.

AWF-000 step 2: keep behavior unchanged while making the module independently
importable and testable.
"""

import os
from datetime import datetime, timezone

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


def _format_data_end(ts):
    try:
        stamp = pd.Timestamp(ts)
    except Exception:
        return ""
    if pd.isna(stamp):
        return ""
    if stamp.tzinfo is not None:
        stamp = stamp.tz_convert("UTC").tz_localize(None)
    return stamp.strftime("%Y-%m-%d %H:%M:%S")


def refresh_ohlcv_cache(
    exchange,
    timeframes,
    symbols,
    base_symbol=None,
    cache_dir="artifacts/cache_ccxt",
    cache_format="csv",
    end="now UTC",
    load_or_update_symbol_fn=None,
):
    """Refresh cached OHLCV files and return per-timeframe latest data_end marks.

    This helper is lightweight orchestration around `_load_or_update_symbol` so it
    can be reused by control-plane periodic refresh and manual refresh hooks.
    """
    if load_or_update_symbol_fn is None:
        load_or_update_symbol_fn = _load_or_update_symbol

    normalized_timeframes = []
    if isinstance(timeframes, list):
        for item in timeframes:
            if not isinstance(item, dict):
                continue
            timeframe = str(item.get("timeframe", "")).strip()
            if not timeframe:
                continue
            try:
                days = int(item.get("days", 0))
            except Exception:
                days = 0
            if days <= 0:
                days = 1
            normalized_timeframes.append({"timeframe": timeframe, "days": days})

    symbol_list = []
    if base_symbol:
        base = str(base_symbol).strip()
        if base:
            symbol_list.append(base)
    if isinstance(symbols, (list, tuple)):
        for raw in symbols:
            sym = str(raw).strip()
            if sym and sym not in symbol_list:
                symbol_list.append(sym)

    pair_data_end = []
    timeframe_latest = {}
    errors = []

    for tf_entry in normalized_timeframes:
        timeframe = tf_entry["timeframe"]
        days = int(tf_entry["days"])
        start = f"{days} days ago UTC"
        timeframe_marks = []
        for symbol in symbol_list:
            try:
                df = load_or_update_symbol_fn(
                    symbol=symbol,
                    exchange=exchange,
                    timeframe=timeframe,
                    start=start,
                    end=end,
                    cache_dir=cache_dir,
                    cache_format=cache_format,
                )
            except Exception as exc:
                errors.append(f"{timeframe} {symbol}: {exc}")
                continue
            if df is None or getattr(df, "empty", True):
                continue
            try:
                last_ts = df.index.max()
            except Exception:
                continue
            if pd.isna(last_ts):
                continue
            mark = _format_data_end(last_ts)
            if not mark:
                continue
            pair_data_end.append(
                {
                    "timeframe": timeframe,
                    "symbol": symbol,
                    "data_end": mark,
                }
            )
            timeframe_marks.append(last_ts)
        if timeframe_marks:
            # Use the minimum timestamp across symbols as conservative freshness.
            timeframe_latest[timeframe] = _format_data_end(min(timeframe_marks))

    pair_data_end = sorted(
        pair_data_end,
        key=lambda item: (str(item.get("timeframe", "")), str(item.get("symbol", ""))),
    )
    return {
        "updated_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "exchange": exchange,
        "timeframe_data_end": timeframe_latest,
        "pair_data_end": pair_data_end,
        "errors": errors,
    }


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
    cci_lookbacks,
    willr_lookbacks,
    adx_lookbacks,
    trix_lookbacks,
    dpo_lookbacks,
    efi_lookbacks,
    vwma_lookbacks,
    ultosc_periods,
    keltner_lookbacks,
    donchian_lookbacks,
    ppo_fast,
    ppo_slow,
    ppo_signal,
    chop_lookbacks,
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

    # --- CCI (Commodity Channel Index) ---
    typical_price_cci = (btc_high + btc_low + btc_close) / 3
    cci_by_lb = {}
    for lb in cci_lookbacks:
        tp_sma = typical_price_cci.rolling(lb).mean()
        tp_mad = typical_price_cci.rolling(lb).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
        cci_by_lb[lb] = (typical_price_cci - tp_sma) / (0.015 * tp_mad.replace(0, np.nan))

    # --- Williams %R ---
    willr_by_lb = {}
    for lb in willr_lookbacks:
        hh = btc_high.rolling(lb).max()
        ll = btc_low.rolling(lb).min()
        denom = (hh - ll).replace(0, np.nan)
        willr_by_lb[lb] = ((hh - btc_close) / denom) * -100

    # --- ADX (Average Directional Index) ---
    adx_by_lb = {}
    for lb in adx_lookbacks:
        up_move = btc_high.diff()
        down_move = -btc_low.diff()
        plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
        minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
        tr = pd.concat([
            btc_high - btc_low,
            (btc_high - btc_close.shift(1)).abs(),
            (btc_low - btc_close.shift(1)).abs(),
        ], axis=1).max(axis=1)
        atr_adx = tr.ewm(span=lb, adjust=False).mean()
        plus_di = 100 * plus_dm.ewm(span=lb, adjust=False).mean() / atr_adx.replace(0, np.nan)
        minus_di = 100 * minus_dm.ewm(span=lb, adjust=False).mean() / atr_adx.replace(0, np.nan)
        dx = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan) * 100
        adx_by_lb[lb] = dx.ewm(span=lb, adjust=False).mean()

    # --- TRIX (Triple Exponential Average ROC) ---
    trix_by_lb = {}
    for lb in trix_lookbacks:
        ema1 = btc_close.ewm(span=lb, adjust=False).mean()
        ema2 = ema1.ewm(span=lb, adjust=False).mean()
        ema3 = ema2.ewm(span=lb, adjust=False).mean()
        trix_by_lb[lb] = ema3.pct_change() * 100

    # --- DPO (Detrended Price Oscillator) ---
    dpo_by_lb = {}
    for lb in dpo_lookbacks:
        shift_n = lb // 2 + 1
        sma_n = btc_close.rolling(lb).mean()
        dpo_by_lb[lb] = btc_close.shift(shift_n) - sma_n

    # --- Elder Force Index ---
    efi_by_lb = {}
    for lb in efi_lookbacks:
        raw_force = btc_close.diff() * btc_volume
        efi_by_lb[lb] = raw_force.ewm(span=lb, adjust=False).mean()

    # --- VWMA Trend (VWMA vs SMA) ---
    vwma_trend_by_lb = {}
    for lb in vwma_lookbacks:
        vwma = (btc_close * btc_volume).rolling(lb).sum() / btc_volume.rolling(lb).sum().replace(0, np.nan)
        sma = btc_close.rolling(lb).mean()
        vwma_trend_by_lb[lb] = (vwma > sma, vwma < sma)

    # --- Ultimate Oscillator ---
    bp = btc_close - pd.concat([btc_low, btc_close.shift(1)], axis=1).min(axis=1)
    tr_ult = pd.concat([
        btc_high - btc_low,
        (btc_high - btc_close.shift(1)).abs(),
        (btc_low - btc_close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    p1, p2, p3 = ultosc_periods
    avg1 = bp.rolling(p1).sum() / tr_ult.rolling(p1).sum().replace(0, np.nan)
    avg2 = bp.rolling(p2).sum() / tr_ult.rolling(p2).sum().replace(0, np.nan)
    avg3 = bp.rolling(p3).sum() / tr_ult.rolling(p3).sum().replace(0, np.nan)
    ultosc_series = 100 * (4 * avg1 + 2 * avg2 + avg3) / 7

    # --- Keltner Channel Position ---
    keltner_pos_by_lb = {}
    for lb in keltner_lookbacks:
        kelt_mid = btc_close.ewm(span=lb, adjust=False).mean()
        kelt_atr = vbt.ATR.run(btc_high, btc_low, btc_close, window=lb).atr
        kelt_upper = kelt_mid + 2 * kelt_atr
        kelt_lower = kelt_mid - 2 * kelt_atr
        kelt_range = (kelt_upper - kelt_lower).replace(0, np.nan)
        keltner_pos_by_lb[lb] = (btc_close - kelt_lower) / kelt_range

    # --- Donchian Channel Position ---
    donchian_pos_by_lb = {}
    for lb in donchian_lookbacks:
        don_high = btc_high.rolling(lb).max()
        don_low = btc_low.rolling(lb).min()
        don_range = (don_high - don_low).replace(0, np.nan)
        donchian_pos_by_lb[lb] = (btc_close - don_low) / don_range

    # --- PPO (Percentage Price Oscillator) ---
    ppo_fast_ema = btc_close.ewm(span=ppo_fast, adjust=False).mean()
    ppo_slow_ema = btc_close.ewm(span=ppo_slow, adjust=False).mean()
    ppo_line = (ppo_fast_ema - ppo_slow_ema) / ppo_slow_ema.replace(0, np.nan) * 100
    ppo_signal_line = ppo_line.ewm(span=ppo_signal, adjust=False).mean()
    ppo_hist_series = ppo_line - ppo_signal_line

    # --- Choppiness Index ---
    chop_by_lb = {}
    for lb in chop_lookbacks:
        chop_atr = vbt.ATR.run(btc_high, btc_low, btc_close, window=1).atr
        chop_atr_sum = chop_atr.rolling(lb).sum()
        chop_high = btc_high.rolling(lb).max()
        chop_low = btc_low.rolling(lb).min()
        chop_range = (chop_high - chop_low).replace(0, np.nan)
        chop_by_lb[lb] = 100 * np.log10(chop_atr_sum / chop_range) / np.log10(lb)

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
        "cci_by_lb": cci_by_lb,
        "willr_by_lb": willr_by_lb,
        "adx_by_lb": adx_by_lb,
        "trix_by_lb": trix_by_lb,
        "dpo_by_lb": dpo_by_lb,
        "efi_by_lb": efi_by_lb,
        "vwma_trend_by_lb": vwma_trend_by_lb,
        "ultosc_series": ultosc_series,
        "keltner_pos_by_lb": keltner_pos_by_lb,
        "donchian_pos_by_lb": donchian_pos_by_lb,
        "ppo_hist_series": ppo_hist_series,
        "chop_by_lb": chop_by_lb,
        "data_range": data_range,
    }

