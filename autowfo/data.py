"""Data access and context-building helpers extracted from the monolith.

AWF-000 step 2: keep behavior unchanged while making the module independently
importable and testable.
"""

import os
import re
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import vectorbt as vbt


_OPEN_INTEREST_HISTORY_TIMEFRAMES = {
    "5m",
    "15m",
    "30m",
    "1h",
    "2h",
    "4h",
    "6h",
    "12h",
    "1d",
}

_OPEN_INTEREST_PROVIDER_ALIASES = {
    "binance": "binanceusdm",
    "binanceusdm": "binanceusdm",
    "bybit": "bybit",
}

_BYBIT_OPEN_INTEREST_INTERVALS = {
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
}


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
    requested_start_ts = _coerce_utc_timestamp(start)
    requested_end_ts = _coerce_utc_timestamp(
        end,
        default=pd.Timestamp.now(tz="UTC").tz_convert(None),
    )
    if os.path.exists(cache_path):
        df = read_cache_fn(cache_path, cache_format)
        df = normalize_index_fn(df)
        first_ts = df.index.min()
        last_ts = df.index.max()
        try:
            step = pd.Timedelta(timeframe)
        except ValueError:
            step = pd.Timedelta("1h")
        if (
            requested_start_ts is not None
            and pd.notna(first_ts)
            and requested_start_ts < first_ts
        ):
            try:
                backfill_end = first_ts - step
                if requested_start_ts <= backfill_end:
                    old_df = download_symbol_ohlcv_fn(
                        symbol,
                        exchange,
                        timeframe,
                        start=_format_request_timestamp(requested_start_ts),
                        end=_format_request_timestamp(backfill_end),
                        show_progress=False,
                    )
                else:
                    old_df = pd.DataFrame()
            except Exception as exc:
                print(f"[warn] backfill failed for {symbol}, using cached history: {exc}")
                old_df = pd.DataFrame()
            if not old_df.empty:
                df = pd.concat([old_df, df], axis=0)
                df = df[~df.index.duplicated(keep="last")].sort_index()
                first_ts = df.index.min()
                last_ts = df.index.max()
                write_cache_fn(df, cache_path, cache_format)
        update_start = last_ts + step
        if update_start <= requested_end_ts:
            try:
                new_df = download_symbol_ohlcv_fn(
                    symbol,
                    exchange,
                    timeframe,
                    start=_format_request_timestamp(update_start),
                    end=_format_request_timestamp(requested_end_ts),
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
        df = download_symbol_ohlcv_fn(
            symbol,
            exchange,
            timeframe,
            _format_request_timestamp(requested_start_ts),
            _format_request_timestamp(requested_end_ts),
            show_progress=True,
        )
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


def _coerce_utc_timestamp(value, default=None):
    if value in (None, ""):
        return default
    if isinstance(value, pd.Timestamp):
        stamp = value
    else:
        text = str(value).strip()
        if not text:
            return default
        if text.lower() == "now utc":
            stamp = pd.Timestamp.now(tz="UTC")
        elif re.match(r"^\d+\s+days?\s+ago\s+utc$", text.lower()):
            days_n = int(text.split()[0])
            stamp = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days_n)
        else:
            stamp = pd.Timestamp(text)
    if stamp.tzinfo is not None:
        return stamp.tz_convert("UTC").tz_localize(None)
    return stamp


def _format_request_timestamp(ts):
    stamp = _coerce_utc_timestamp(ts)
    if stamp is None:
        return None
    return stamp.strftime("%Y-%m-%dT%H:%M:%S")


def _normalize_htf_resample_rule(value):
    key = str(value or "").strip().lower()
    if key == "8h":
        return "8h"
    if key in {"1d", "daily"}:
        return "1d"
    raise ValueError(f"unsupported HTF timeframe: {value}")


def _build_htf_trend_filters(close_series, base_index, htf_timeframes=None, htf_windows=None):
    timeframe_values = list(htf_timeframes or [])
    window_values = [int(value) for value in (htf_windows or []) if int(value) > 0]
    if close_series is None or close_series.empty or not timeframe_values or not window_values:
        return {}

    filters = {}
    for timeframe in timeframe_values:
        rule = _normalize_htf_resample_rule(timeframe)
        resampled_close = close_series.resample(rule).last().dropna()
        if resampled_close.empty:
            continue
        for window in window_values:
            ema = resampled_close.ewm(span=int(window), adjust=False).mean()
            long_gate = (resampled_close > ema).shift(1).astype("boolean")
            short_gate = (resampled_close < ema).shift(1).astype("boolean")
            long_gate = (
                long_gate.reindex(base_index, method="ffill").fillna(False).astype(bool)
            )
            short_gate = (
                short_gate.reindex(base_index, method="ffill").fillna(False).astype(bool)
            )
            filters[f"htf_trend:{str(timeframe).lower()}:{int(window)}"] = {
                "long": long_gate,
                "short": short_gate,
            }
    return filters


def _format_overlay_threshold(value):
    text = f"{float(value):.6f}".rstrip("0").rstrip(".")
    if text in {"", "-0"}:
        return "0"
    return text


def _normalize_open_interest_provider(value):
    key = str(value or "").strip().lower()
    return _OPEN_INTEREST_PROVIDER_ALIASES.get(key, "bybit")


def _perpetual_proxy_symbol(symbol, exchange="binanceusdm"):
    base = str(symbol or "").split("/", 1)[0].strip().upper()
    if not base:
        raise ValueError(f"invalid trade symbol for perpetual proxy: {symbol}")
    normalized_exchange = _OPEN_INTEREST_PROVIDER_ALIASES.get(
        str(exchange or "binanceusdm").strip().lower(),
        str(exchange or "binanceusdm").strip().lower(),
    )
    return normalized_exchange, f"{base}/USDT:USDT"


def _funding_proxy_symbol(symbol):
    return _perpetual_proxy_symbol(symbol)


def _normalize_open_interest_history_timeframe(value):
    key = str(value or "").strip().lower()
    if key in _OPEN_INTEREST_HISTORY_TIMEFRAMES:
        return key
    return "5m"


def _resolve_open_interest_history_request(provider, timeframe):
    normalized_provider = _normalize_open_interest_provider(provider)
    history_timeframe = _normalize_open_interest_history_timeframe(timeframe)
    if normalized_provider == "binanceusdm":
        return {
            "provider": normalized_provider,
            "download_timeframe": history_timeframe,
            "resample_rule": None,
        }
    if normalized_provider == "bybit":
        if history_timeframe in _BYBIT_OPEN_INTEREST_INTERVALS:
            return {
                "provider": normalized_provider,
                "download_timeframe": history_timeframe,
                "resample_rule": None,
            }
        target_delta = pd.Timedelta(history_timeframe)
        if (
            target_delta < pd.Timedelta("1d")
            and target_delta % pd.Timedelta("1h") == pd.Timedelta(0)
        ):
            return {
                "provider": normalized_provider,
                "download_timeframe": "1h",
                "resample_rule": history_timeframe,
            }
    raise ValueError(
        f"unsupported open interest provider/timeframe combination: {provider!r} / {timeframe!r}"
    )


def _resample_open_interest_history(history_df, rule):
    if history_df.empty or not rule:
        return history_df
    view = history_df.copy()
    view = view[~view.index.duplicated(keep="last")].sort_index()
    for column in ("openInterestAmount", "openInterestValue"):
        if column in view.columns:
            view[column] = pd.to_numeric(view[column], errors="coerce")
    resampled = view.resample(rule).last()
    if "openInterestAmount" in resampled.columns:
        resampled = resampled.dropna(subset=["openInterestAmount"])
    else:
        resampled = resampled.dropna(how="all")
    return resampled


def _download_funding_history(proxy_symbol, exchange, start_ts, end_ts):
    import ccxt  # type: ignore

    exchange_cls = getattr(ccxt, exchange, None)
    if exchange_cls is None:
        raise ValueError(f"unsupported funding exchange: {exchange!r}")

    ex = exchange_cls({"enableRateLimit": True})
    since_ms = int(start_ts.tz_localize("UTC").timestamp() * 1000)
    end_ms = int(end_ts.tz_localize("UTC").timestamp() * 1000)

    rows = []
    limit = 1000
    while True:
        batch = ex.fetch_funding_rate_history(proxy_symbol, since=since_ms, limit=limit)
        if not batch:
            break
        rows.extend(batch)
        last_ms = int(batch[-1].get("timestamp") or 0)
        next_since = last_ms + 1
        if next_since <= since_ms or next_since > end_ms:
            break
        since_ms = next_since
        if len(batch) < limit and last_ms >= end_ms:
            break

    if not rows:
        return pd.DataFrame(columns=["fundingRate"], index=pd.DatetimeIndex([]))

    out = pd.DataFrame(
        {
            "timestamp": [row.get("timestamp") for row in rows],
            "fundingRate": [row.get("fundingRate") for row in rows],
        }
    )
    out = out.dropna(subset=["timestamp"])
    timestamps = pd.to_datetime(
        pd.to_numeric(out.pop("timestamp"), errors="coerce"),
        unit="ms",
        utc=True,
    )
    out.index = pd.DatetimeIndex(timestamps).tz_convert(None)
    out = out[~out.index.duplicated(keep="last")].sort_index()
    out["fundingRate"] = pd.to_numeric(out["fundingRate"], errors="coerce")
    out = out.dropna(subset=["fundingRate"])
    return out.loc[(out.index >= start_ts) & (out.index <= end_ts)]


def _load_or_update_funding_history(symbol, start_ts, end_ts, cache_dir, cache_format):
    exchange, proxy_symbol = _perpetual_proxy_symbol(symbol)
    os.makedirs(cache_dir, exist_ok=True)
    cache_name = f"{exchange}_{proxy_symbol.replace('/', '-').replace(':', '-')}_funding.{cache_format}"
    cache_path = os.path.join(cache_dir, cache_name)

    cached = pd.DataFrame(columns=["fundingRate"], index=pd.DatetimeIndex([]))
    if os.path.exists(cache_path):
        cached = _read_cache(cache_path, cache_format)
        cached.index = pd.to_datetime(cached.index, utc=True).tz_convert(None)
        cached = cached[[col for col in cached.columns if col == "fundingRate"]]
        if "fundingRate" not in cached.columns:
            cached["fundingRate"] = np.nan
        cached = cached[~cached.index.duplicated(keep="last")].sort_index()

    if not cached.empty and cached.index.min() <= start_ts and cached.index.max() >= end_ts:
        return cached.loc[(cached.index >= start_ts) & (cached.index <= end_ts)]

    fetched = _download_funding_history(proxy_symbol, exchange, start_ts, end_ts)
    merged = fetched if cached.empty else pd.concat([cached, fetched], axis=0)
    merged = merged[~merged.index.duplicated(keep="last")].sort_index()
    _write_cache(merged, cache_path, cache_format)
    return merged.loc[(merged.index >= start_ts) & (merged.index <= end_ts)]


def _download_binance_open_interest_history(proxy_symbol, exchange, timeframe, start_ts, end_ts):
    import ccxt  # type: ignore

    exchange_cls = getattr(ccxt, exchange, None)
    if exchange_cls is None:
        raise ValueError(f"unsupported open interest exchange: {exchange!r}")

    history_timeframe = _normalize_open_interest_history_timeframe(timeframe)
    latest_available_start = pd.Timestamp.now(tz="UTC").tz_convert(None) - pd.Timedelta(days=31)
    if start_ts < latest_available_start:
        raise ValueError(
            "Binance open interest history only exposes the latest 1 month; "
            f"requested start {start_ts} is older than supported window {latest_available_start}"
        )
    ex = exchange_cls({"enableRateLimit": True})
    since_ms = int(start_ts.tz_localize("UTC").timestamp() * 1000)
    end_ms = int(end_ts.tz_localize("UTC").timestamp() * 1000)
    try:
        step_ms = max(int(pd.Timedelta(history_timeframe).total_seconds() * 1000), 1)
    except ValueError:
        step_ms = int(pd.Timedelta("5m").total_seconds() * 1000)

    rows = []
    limit = 500
    while True:
        batch = ex.fetch_open_interest_history(
            proxy_symbol,
            timeframe=history_timeframe,
            since=since_ms,
            limit=limit,
            params={"until": end_ms},
        )
        if not batch:
            break
        rows.extend(batch)
        last_ms = int(batch[-1].get("timestamp") or 0)
        next_since = last_ms + step_ms
        if next_since <= since_ms or next_since > end_ms:
            break
        since_ms = next_since
        if len(batch) < limit and last_ms >= end_ms:
            break

    if not rows:
        return pd.DataFrame(
            columns=["openInterestAmount", "openInterestValue"],
            index=pd.DatetimeIndex([]),
        )

    out = pd.DataFrame(
        {
            "timestamp": [row.get("timestamp") for row in rows],
            "openInterestAmount": [
                row.get("openInterestAmount", row.get("sumOpenInterest"))
                for row in rows
            ],
            "openInterestValue": [
                row.get("openInterestValue", row.get("sumOpenInterestValue"))
                for row in rows
            ],
        }
    )
    out = out.dropna(subset=["timestamp"])
    timestamps = pd.to_datetime(
        pd.to_numeric(out.pop("timestamp"), errors="coerce"),
        unit="ms",
        utc=True,
    )
    out.index = pd.DatetimeIndex(timestamps).tz_convert(None)
    out = out[~out.index.duplicated(keep="last")].sort_index()
    out["openInterestAmount"] = pd.to_numeric(out["openInterestAmount"], errors="coerce")
    out["openInterestValue"] = pd.to_numeric(out["openInterestValue"], errors="coerce")
    out = out.dropna(subset=["openInterestAmount"])
    return out.loc[(out.index >= start_ts) & (out.index <= end_ts)]


def _download_bybit_open_interest_history(proxy_symbol, exchange, timeframe, start_ts, end_ts):
    import ccxt  # type: ignore

    exchange_cls = getattr(ccxt, exchange, None)
    if exchange_cls is None:
        raise ValueError(f"unsupported open interest exchange: {exchange!r}")

    interval = _BYBIT_OPEN_INTEREST_INTERVALS.get(timeframe)
    if interval is None:
        raise ValueError(f"unsupported Bybit open interest timeframe: {timeframe!r}")

    ex = exchange_cls({"enableRateLimit": True})
    ex.load_markets()
    market = ex.market(proxy_symbol)
    request_method = getattr(ex, "publicGetV5MarketOpenInterest", None)
    if request_method is None:
        raise ValueError("Bybit exchange client is missing publicGetV5MarketOpenInterest")

    start_ms = int(start_ts.tz_localize("UTC").timestamp() * 1000)
    end_ms = int(end_ts.tz_localize("UTC").timestamp() * 1000)
    step_ms = max(int(pd.Timedelta(timeframe).total_seconds() * 1000), 1)
    batch_span_ms = step_ms * 199

    rows = []
    window_start_ms = start_ms
    while window_start_ms <= end_ms:
        window_end_ms = min(window_start_ms + batch_span_ms, end_ms)
        response = request_method(
            {
                "category": "linear" if market.get("linear") else "inverse",
                "symbol": market["id"],
                "intervalTime": interval,
                "startTime": str(window_start_ms),
                "endTime": str(window_end_ms),
                "limit": "200",
            }
        )
        batch = ((response or {}).get("result") or {}).get("list") or []
        if batch:
            rows.extend(batch)
        if window_end_ms >= end_ms:
            break
        next_window_start_ms = window_end_ms + step_ms
        if next_window_start_ms <= window_start_ms:
            break
        window_start_ms = next_window_start_ms

    if not rows:
        return pd.DataFrame(
            columns=["openInterestAmount", "openInterestValue"],
            index=pd.DatetimeIndex([]),
        )

    out = pd.DataFrame(
        {
            "timestamp": [row.get("timestamp") for row in rows],
            "openInterestAmount": [row.get("openInterest") for row in rows],
            "openInterestValue": [np.nan] * len(rows),
        }
    )
    out = out.dropna(subset=["timestamp"])
    timestamps = pd.to_datetime(
        pd.to_numeric(out.pop("timestamp"), errors="coerce"),
        unit="ms",
        utc=True,
    )
    out.index = pd.DatetimeIndex(timestamps).tz_convert(None)
    out = out[~out.index.duplicated(keep="last")].sort_index()
    out["openInterestAmount"] = pd.to_numeric(out["openInterestAmount"], errors="coerce")
    out["openInterestValue"] = pd.to_numeric(out["openInterestValue"], errors="coerce")
    out = out.dropna(subset=["openInterestAmount"])
    return out.loc[(out.index >= start_ts) & (out.index <= end_ts)]


def _download_open_interest_history(symbol, open_interest_provider, timeframe, start_ts, end_ts):
    request = _resolve_open_interest_history_request(open_interest_provider, timeframe)
    exchange, proxy_symbol = _perpetual_proxy_symbol(
        symbol,
        exchange=request["provider"],
    )
    download_timeframe = request["download_timeframe"]
    if exchange == "bybit":
        out = _download_bybit_open_interest_history(
            proxy_symbol,
            exchange,
            download_timeframe,
            start_ts,
            end_ts,
        )
    else:
        out = _download_binance_open_interest_history(
            proxy_symbol,
            exchange,
            download_timeframe,
            start_ts,
            end_ts,
        )
    resample_rule = request.get("resample_rule")
    if resample_rule:
        out = _resample_open_interest_history(out, resample_rule)
    return out.loc[(out.index >= start_ts) & (out.index <= end_ts)]


def _load_or_update_open_interest_history(
    symbol,
    timeframe,
    start_ts,
    end_ts,
    cache_dir,
    cache_format,
    open_interest_provider="bybit",
    read_cache_fn=None,
    write_cache_fn=None,
    download_open_interest_history_fn=None,
):
    if read_cache_fn is None:
        read_cache_fn = _read_cache
    if write_cache_fn is None:
        write_cache_fn = _write_cache
    if download_open_interest_history_fn is None:
        download_open_interest_history_fn = _download_open_interest_history

    provider = _normalize_open_interest_provider(open_interest_provider)
    exchange, proxy_symbol = _perpetual_proxy_symbol(symbol, exchange=provider)
    history_timeframe = _normalize_open_interest_history_timeframe(timeframe)
    os.makedirs(cache_dir, exist_ok=True)
    cache_name = (
        f"{exchange}_{proxy_symbol.replace('/', '-').replace(':', '-')}_"
        f"oi_{history_timeframe}.{cache_format}"
    )
    cache_path = os.path.join(cache_dir, cache_name)

    cached = pd.DataFrame(
        columns=["openInterestAmount", "openInterestValue"],
        index=pd.DatetimeIndex([]),
    )
    if os.path.exists(cache_path):
        cached = read_cache_fn(cache_path, cache_format)
        cached.index = pd.to_datetime(cached.index, utc=True).tz_convert(None)
        keep_cols = [
            col
            for col in cached.columns
            if col in {"openInterestAmount", "openInterestValue"}
        ]
        cached = cached[keep_cols]
        if "openInterestAmount" not in cached.columns:
            cached["openInterestAmount"] = np.nan
        if "openInterestValue" not in cached.columns:
            cached["openInterestValue"] = np.nan
        cached = cached[~cached.index.duplicated(keep="last")].sort_index()

    if not cached.empty and cached.index.min() <= start_ts and cached.index.max() >= end_ts:
        return cached.loc[(cached.index >= start_ts) & (cached.index <= end_ts)]

    fetched = download_open_interest_history_fn(
        symbol,
        provider,
        history_timeframe,
        start_ts,
        end_ts,
    )
    merged = fetched if cached.empty else pd.concat([cached, fetched], axis=0)
    merged = merged[~merged.index.duplicated(keep="last")].sort_index()
    write_cache_fn(merged, cache_path, cache_format)
    return merged.loc[(merged.index >= start_ts) & (merged.index <= end_ts)]


def _build_funding_gate_filters(
    trade_symbols,
    base_index,
    start_ts,
    end_ts,
    cache_dir,
    cache_format,
    long_thresholds=None,
    short_thresholds=None,
    load_funding_history_fn=None,
):
    long_values = [float(value) for value in (long_thresholds or []) if float(value) > 0]
    short_values = [float(value) for value in (short_thresholds or []) if float(value) < 0]
    if not trade_symbols or not long_values or not short_values:
        return {}
    if load_funding_history_fn is None:
        load_funding_history_fn = _load_or_update_funding_history

    funding_frame = pd.DataFrame(index=base_index)
    funding_cache_dir = os.path.join(cache_dir, "funding")
    for symbol in trade_symbols:
        funding_df = load_funding_history_fn(
            symbol,
            start_ts,
            end_ts,
            funding_cache_dir,
            cache_format,
        )
        if funding_df.empty or "fundingRate" not in funding_df.columns:
            raise RuntimeError(f"missing funding history for {symbol}")
        settled = funding_df["fundingRate"].shift(1)
        aligned = settled.reindex(base_index, method="ffill").fillna(0.0)
        funding_frame[symbol] = aligned.astype(float)

    filters = {}
    for long_threshold in sorted(set(long_values)):
        for short_threshold in sorted(set(short_values)):
            name = (
                f"funding_gate:{_format_overlay_threshold(long_threshold)}:"
                f"{_format_overlay_threshold(short_threshold)}"
            )
            filters[name] = {
                "long": (funding_frame <= float(long_threshold)).fillna(False),
                "short": (funding_frame >= float(short_threshold)).fillna(False),
            }
    return filters


def _resolve_requested_window(data_days, *, data_start=None, data_end=None):
    end_ts = _coerce_utc_timestamp(
        data_end,
        default=pd.Timestamp.now(tz="UTC").tz_convert(None),
    )
    try:
        days_n = int(data_days)
    except (TypeError, ValueError):
        days_n = 0
    if days_n <= 0:
        raise ValueError("data_days must be a positive integer")
    start_ts = _coerce_utc_timestamp(data_start)
    if start_ts is None:
        start_ts = end_ts - pd.Timedelta(days=days_n)
    if start_ts > end_ts:
        raise ValueError("requested data window start must be <= end")
    return {
        "start_ts": start_ts,
        "end_ts": end_ts,
        "start": _format_request_timestamp(start_ts),
        "end": _format_request_timestamp(end_ts),
    }


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
    htf_trend_timeframes=None,
    htf_trend_windows=None,
    funding_gate_long_thresholds=None,
    funding_gate_short_thresholds=None,
    oi_lookbacks=None,
    open_interest_provider="bybit",
    data_start=None,
    data_end=None,
    load_or_update_symbol_fn=None,
    load_funding_history_fn=None,
    load_open_interest_history_fn=None,
):
    if load_or_update_symbol_fn is None:
        load_or_update_symbol_fn = _load_or_update_symbol

    normalized_oi_lookbacks = []
    for value in oi_lookbacks or []:
        try:
            lookback = int(value)
        except (TypeError, ValueError):
            continue
        if lookback > 0:
            normalized_oi_lookbacks.append(lookback)
    oi_lookbacks = sorted(set(normalized_oi_lookbacks))
    if oi_lookbacks and load_open_interest_history_fn is None:
        normalized_open_interest_provider = _normalize_open_interest_provider(open_interest_provider)

        def load_open_interest_history_fn(
            symbol,
            timeframe,
            start_ts,
            end_ts,
            cache_dir,
            cache_format,
        ):
            return _load_or_update_open_interest_history(
                symbol,
                timeframe,
                start_ts,
                end_ts,
                cache_dir,
                cache_format,
                open_interest_provider=normalized_open_interest_provider,
            )

    use_explicit_window = data_start not in (None, "") or data_end not in (None, "")
    if use_explicit_window:
        requested_window = _resolve_requested_window(
            data_days,
            data_start=data_start,
            data_end=data_end,
        )
        start = requested_window["start"]
        end = requested_window["end"]
        requested_window_start = requested_window["start_ts"]
        requested_window_end = requested_window["end_ts"]
    else:
        start = f"{data_days} days ago UTC"
        end = "now UTC"
        requested_window_start = None
        requested_window_end = None
    all_symbols = [base_symbol] + trade_symbols
    symbol_data = {}
    for symbol in all_symbols:
        try:
            symbol_data[symbol] = load_or_update_symbol_fn(
                symbol, exchange, timeframe, start, end, cache_dir, cache_format
            )
        except Exception as exc:
            print(f"[warn] skip {symbol}: {exc}")

    if use_explicit_window:
        for symbol, df in list(symbol_data.items()):
            clipped = df.loc[(df.index >= requested_window_start) & (df.index <= requested_window_end)]
            symbol_data[symbol] = clipped
    else:
        # Keep the effective window close to requested `data_days` even when cache files
        # have grown older than the latest run configuration.
        try:
            latest_end = min(df.index.max() for df in symbol_data.values() if not df.empty)
            if pd.notna(latest_end):
                window_start = latest_end - pd.Timedelta(days=int(data_days))
                requested_window_start = window_start
                requested_window_end = latest_end
                for symbol, df in list(symbol_data.items()):
                    clipped = df.loc[df.index >= window_start]
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
    trade_high = high[trade_symbols]
    trade_low = low[trade_symbols]
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

    symbol_data_ranges = {}
    for symbol, df in symbol_data.items():
        if df.empty:
            continue
        symbol_data_ranges[symbol] = {
            "start": str(df.index[0]),
            "end": str(df.index[-1]),
            "rows": int(len(df.index)),
            "days": int(df.index.normalize().nunique()),
        }

    trade_close = trade_close.loc[common_index]
    trade_high = trade_high.loc[common_index]
    trade_low = trade_low.loc[common_index]
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
    trade_atr = vbt.ATR.run(trade_high, trade_low, trade_close, window=atr_window).atr
    if isinstance(trade_atr.columns, pd.MultiIndex):
        trade_atr.columns = trade_atr.columns.get_level_values(-1)
    trade_atr_ratio = trade_atr.divide(trade_close.replace(0, np.nan))

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

    oi_roc_by_lb = {}
    if oi_lookbacks:
        oi_history_df = load_open_interest_history_fn(
            base_symbol,
            timeframe,
            requested_window_start or trade_close.index.min(),
            requested_window_end or trade_close.index.max(),
            os.path.join(cache_dir, "open_interest"),
            cache_format,
        )
        if oi_history_df.empty or "openInterestAmount" not in oi_history_df.columns:
            raise RuntimeError(f"missing open interest history for {base_symbol}")
        oi_amount = pd.to_numeric(oi_history_df["openInterestAmount"], errors="coerce")
        oi_amount = oi_amount.replace([np.inf, -np.inf], np.nan)
        oi_amount = oi_amount[~oi_amount.index.duplicated(keep="last")].sort_index()
        oi_amount = oi_amount.reindex(trade_close.index, method="ffill")
        oi_roc_by_lb = {lb: oi_amount.pct_change(lb) for lb in oi_lookbacks}

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

    htf_trend_filters = _build_htf_trend_filters(
        btc_close,
        trade_close.index,
        htf_timeframes=htf_trend_timeframes,
        htf_windows=htf_trend_windows,
    )
    funding_gate_filters = _build_funding_gate_filters(
        trade_symbols,
        trade_close.index,
        requested_window_start or trade_close.index.min(),
        requested_window_end or trade_close.index.max(),
        cache_dir,
        cache_format,
        long_thresholds=funding_gate_long_thresholds,
        short_thresholds=funding_gate_short_thresholds,
        load_funding_history_fn=load_funding_history_fn,
    )

    data_range = f"{trade_close.index[0]} -> {trade_close.index[-1]}"
    overlap_diagnostics = {
        "requested_data_days": int(data_days),
        "requested_window_start": str(requested_window_start) if requested_window_start is not None else None,
        "requested_window_end": str(requested_window_end) if requested_window_end is not None else None,
        "realized_shared_start": str(common_index[0]),
        "realized_shared_end": str(common_index[-1]),
        "realized_shared_days": total_days,
        "requested_symbol_count": len(all_symbols) - 1,
        "available_trade_symbol_count": len(trade_symbols),
        "base_symbol": base_symbol,
        "open_interest_provider": (
            _normalize_open_interest_provider(open_interest_provider) if oi_lookbacks else None
        ),
        "trade_symbols": list(trade_symbols),
        "symbol_data_ranges": symbol_data_ranges,
    }

    return {
        "timeframe": timeframe,
        "data_days": data_days,
        "start": start,
        "end": end,
        "trade_symbols": trade_symbols,
        "trade_close": trade_close,
        "trade_high": trade_high,
        "trade_low": trade_low,
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
        "trade_atr_ratio": trade_atr_ratio,
        "ma_trend_by_pair": ma_trend_by_pair,
        "macd_hist_ratio_series": macd_hist_ratio_series,
        "stoch_k": stoch_k,
        "obv_roc_by_lb": obv_roc_by_lb,
        "oi_roc_by_lb": oi_roc_by_lb,
        "open_interest_provider": (
            _normalize_open_interest_provider(open_interest_provider) if oi_lookbacks else None
        ),
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
        "htf_trend_filters": htf_trend_filters,
        "funding_gate_filters": funding_gate_filters,
        "data_range": data_range,
        "overlap_diagnostics": overlap_diagnostics,
    }

