import datetime as dt
import itertools
import os
import time
import json
import csv
import sqlite3

import numpy as np
import pandas as pd
import vectorbt as vbt

from scripts.autowfo import data as autowfo_data
from scripts.autowfo import artifacts as autowfo_artifacts
from scripts.autowfo import engine as autowfo_engine
from scripts.autowfo import metrics as autowfo_metrics
from scripts.autowfo import portfolio as autowfo_portfolio
from scripts.autowfo import ranking as autowfo_ranking
from scripts.autowfo import report as autowfo_report
from scripts.autowfo import search as autowfo_search
from scripts.autowfo import split as autowfo_split
from scripts.autowfo import strategy as autowfo_strategy

from scripts.autowfo.constants import (
    FILTER_NAME_MAP,
    INDICATOR_LABELS,
    INDICATOR_META,
    INDICATOR_PARAM_FIELDS,
    LABELS,
    REGIME_NAME_MAP,
    REGIME_TYPE_MAP,
    _html_entity,
    _u,
)


def _indicator_combo_label(combo_keys):
    return autowfo_report._indicator_combo_label(combo_keys, INDICATOR_META)


def _format_indicator_list(value):
    return autowfo_report._format_indicator_list(value, INDICATOR_META)


def _df_to_html(df, columns, label_map):
    return autowfo_report._df_to_html(
        df,
        columns,
        label_map,
        FILTER_NAME_MAP,
        REGIME_NAME_MAP,
        REGIME_TYPE_MAP,
        format_indicator_list_fn=_format_indicator_list,
    )


def _normalize_index(df):
    return autowfo_data._normalize_index(df)


def _format_duration(seconds):
    return autowfo_report._format_duration(seconds)


def _timeframe_to_hours(timeframe):
    return autowfo_metrics._timeframe_to_hours(timeframe)


COMBO_KEY_FIELDS = [
    "timeframe",
    "data_days",
    "exchange",
    "base_symbol",
    "trade_symbols_key",
    "capital_mode",
    "fees",
    "slippage_bps",
    "spread_bps",
    "funding_rate_daily",
    "order_size_pct",
    "max_concurrent_positions",
    "init_cash_usdt",
    "wf_train_days",
    "wf_test_days",
    "wf_step_days",
    "data_start",
    "data_end",
    "regime_name",
    "regime_type",
    "vol_mode",
    "regime_rsi_long",
    "regime_rsi_short",
    "filter_name",
    "indicator_list",
    "indicator_count",
    "vol_lookback",
    "vol_z",
    "mom_lookback",
    "trade_mom_lookback",
    "tp_stop",
    "sl_stop",
    "max_hold",
    "rsi_window",
    "rsi_long",
    "rsi_short",
    "bb_width",
    "atr_ratio",
    "ma_fast",
    "ma_slow",
    "macd_hist_ratio",
    "stoch_long",
    "stoch_short",
    "obv_lookback",
    "volume_lookback",
    "volume_z",
    "roc_lookback",
    "roc_threshold",
    "mfi_long",
    "mfi_short",
    "cmf_lookback",
    "cmf_threshold",
    "vroc_lookback",
    "vroc_threshold",
    "ad_lookback",
]

COMBO_RESULT_FIELDS = COMBO_KEY_FIELDS + [
    "avg_total_return_pct",
    "avg_win_rate_pct",
    "avg_avg_trade_pct",
    "avg_max_drawdown_pct",
    "avg_position_coverage_pct",
    "avg_total_trades",
    "min_total_trades",
    "avg_daily_trades",
    "avg_hold_hours",
    "sym_avg_total_return_pct",
    "sym_avg_win_rate_pct",
    "sym_avg_avg_trade_pct",
    "sym_avg_max_drawdown_pct",
    "sym_avg_position_coverage_pct",
    "sym_avg_total_trades",
    "sym_min_total_trades",
    "sym_avg_daily_trades",
    "sym_avg_hold_hours",
    "oos_avg_total_return_pct",
    "oos_avg_win_rate_pct",
    "oos_avg_avg_trade_pct",
    "oos_avg_max_drawdown_pct",
    "oos_avg_position_coverage_pct",
    "oos_avg_total_trades",
    "oos_min_total_trades",
    "oos_avg_daily_trades",
    "oos_avg_hold_hours",
    "oos_segments",
]

SYMBOL_RESULT_FIELDS = [
    "timeframe",
    "data_days",
    "exchange",
    "base_symbol",
    "trade_symbols_key",
    "capital_mode",
    "fees",
    "order_size_pct",
    "max_concurrent_positions",
    "init_cash_usdt",
    "wf_train_days",
    "wf_test_days",
    "wf_step_days",
    "data_start",
    "data_end",
    "symbol",
    "regime_name",
    "regime_type",
    "vol_mode",
    "regime_rsi_long",
    "regime_rsi_short",
    "filter_name",
    "indicator_list",
    "indicator_count",
    "vol_lookback",
    "vol_z",
    "mom_lookback",
    "trade_mom_lookback",
    "tp_stop",
    "sl_stop",
    "max_hold",
    "rsi_window",
    "rsi_long",
    "rsi_short",
    "bb_width",
    "atr_ratio",
    "ma_fast",
    "ma_slow",
    "macd_hist_ratio",
    "stoch_long",
    "stoch_short",
    "obv_lookback",
    "volume_lookback",
    "volume_z",
    "roc_lookback",
    "roc_threshold",
    "mfi_long",
    "mfi_short",
    "cmf_lookback",
    "cmf_threshold",
    "vroc_lookback",
    "vroc_threshold",
    "ad_lookback",
    "total_return_pct",
    "total_profit",
    "total_trades",
    "win_rate_pct",
    "avg_trade_pct",
    "max_drawdown_pct",
    "position_coverage_pct",
    "avg_hold_hours",
]

STRICT_CONFIG_FIELDS = [
    "exchange",
    "base_symbol",
    "trade_symbols_key",
    "capital_mode",
    "fees",
    "order_size_pct",
    "max_concurrent_positions",
    "init_cash_usdt",
    "wf_train_days",
    "wf_test_days",
    "wf_step_days",
    "data_start",
    "data_end",
]


def _normalize_key_value(value):
    return autowfo_search._normalize_key_value(value)


def _combo_key_from_dict(values):
    return autowfo_search._combo_key_from_dict(values, COMBO_KEY_FIELDS)


def _safe_int(value, default):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return default
    return int(value)


def _safe_float(value, default):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return default
    return float(value)


def _pick_series_from_map(series_map, key, default_key=None):
    return autowfo_strategy._pick_series_from_map(series_map, key, default_key=default_key)


def _coerce_indicator_params(combo_keys, params, ctx):
    return autowfo_strategy._coerce_indicator_params(combo_keys, params, ctx)


def _has_all_config_fields(values):
    for field in STRICT_CONFIG_FIELDS:
        val = values.get(field)
        if val is None:
            return False
        if isinstance(val, float) and np.isnan(val):
            return False
        if isinstance(val, str) and not val:
            return False
    return True


def _ensure_csv_schema(path, columns):
    return autowfo_artifacts._ensure_csv_schema(path, columns)


def _append_rows(path, rows, columns):
    return autowfo_artifacts._append_rows(path, rows, columns)


def _ensure_db_schema(db_path, table, columns, indexes=None):
    return autowfo_artifacts._ensure_db_schema(db_path, table, columns, indexes=indexes)


def _append_db_rows(db_path, table, rows, columns):
    return autowfo_artifacts._append_db_rows(
        db_path,
        table,
        rows,
        columns,
        normalize_key_value_fn=_normalize_key_value,
    )


def _write_status(status_json_path, status_html_path, payload):
    return autowfo_artifacts._write_status(
        status_json_path=status_json_path,
        status_html_path=status_html_path,
        payload=payload,
        labels=LABELS,
    )


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
):
    return autowfo_data._prepare_timeframe_context(
        timeframe=timeframe,
        data_days=data_days,
        base_symbol=base_symbol,
        trade_symbols=trade_symbols,
        exchange=exchange,
        cache_dir=cache_dir,
        cache_format=cache_format,
        vol_lookbacks=vol_lookbacks,
        mom_lookbacks=mom_lookbacks,
        trade_mom_lookbacks=trade_mom_lookbacks,
        rsi_window=rsi_window,
        bb_window=bb_window,
        bb_alpha=bb_alpha,
        atr_window=atr_window,
        ma_pairs=ma_pairs,
        obv_lookbacks=obv_lookbacks,
        volume_lookbacks=volume_lookbacks,
        roc_lookbacks=roc_lookbacks,
        cmf_lookbacks=cmf_lookbacks,
        mfi_window=mfi_window,
        vroc_lookbacks=vroc_lookbacks,
        ad_lookbacks=ad_lookbacks,
        init_cash_usdt=init_cash_usdt,
        capital_mode=capital_mode,
        load_or_update_symbol_fn=_load_or_update_symbol,
    )


def _has_parquet_engine():
    return autowfo_data._has_parquet_engine()


def _fetch_top_trade_symbols(exchange, limit=10, fallback=None):
    return autowfo_data._fetch_top_trade_symbols(exchange=exchange, limit=limit, fallback=fallback)


def _read_cache(path, cache_format):
    return autowfo_data._read_cache(path, cache_format)


def _write_cache(df, path, cache_format):
    return autowfo_data._write_cache(df, path, cache_format)


def _download_symbol_ohlcv(symbol, exchange, timeframe, start, end, show_progress):
    return autowfo_data._download_symbol_ohlcv(
        symbol=symbol,
        exchange=exchange,
        timeframe=timeframe,
        start=start,
        end=end,
        show_progress=show_progress,
        normalize_index_fn=_normalize_index,
    )


def _load_or_update_symbol(symbol, exchange, timeframe, start, end, cache_dir, cache_format):
    return autowfo_data._load_or_update_symbol(
        symbol=symbol,
        exchange=exchange,
        timeframe=timeframe,
        start=start,
        end=end,
        cache_dir=cache_dir,
        cache_format=cache_format,
        read_cache_fn=_read_cache,
        write_cache_fn=_write_cache,
        download_symbol_ohlcv_fn=_download_symbol_ohlcv,
        normalize_index_fn=_normalize_index,
    )


def _build_walk_forward_slices(index, train_days, test_days, step_days):
    return autowfo_split._build_walk_forward_slices(index, train_days, test_days, step_days)


def _as_series(value, index):
    return autowfo_metrics._as_series(value, index)


def _as_scalar(value):
    return autowfo_metrics._as_scalar(value)


def _calc_pf_series(pf, symbols, bar_hours):
    return autowfo_metrics._calc_pf_series(pf, symbols, bar_hours)


def _calc_pf_combo_metrics(pf, bar_hours):
    return autowfo_metrics._calc_pf_combo_metrics(pf, bar_hours)


def _plot_portfolio(pf, plot_symbol):
    return autowfo_report._plot_portfolio(pf, plot_symbol)


def _aggregate_metrics(series_metrics):
    return autowfo_metrics._aggregate_metrics(series_metrics)


def _aggregate_oos_metrics(oos_rows):
    return autowfo_metrics._aggregate_oos_metrics(oos_rows)


def _choose_score_col(df, preferred="oos_avg_total_return_pct", fallback="avg_total_return_pct"):
    return autowfo_ranking._choose_score_col(df, preferred=preferred, fallback=fallback)


def _sort_by_score(
    df,
    preferred="oos_avg_total_return_pct",
    fallback="avg_total_return_pct",
    tie_break_avg_hold=True,
):
    return autowfo_ranking._sort_by_score(
        df,
        preferred=preferred,
        fallback=fallback,
        tie_break_avg_hold=tie_break_avg_hold,
    )


def _top_by_score(
    df,
    top_n,
    preferred="oos_avg_total_return_pct",
    fallback="avg_total_return_pct",
    tie_break_avg_hold=True,
):
    return autowfo_ranking._top_by_score(
        df,
        top_n=top_n,
        preferred=preferred,
        fallback=fallback,
        tie_break_avg_hold=tie_break_avg_hold,
    )


def _build_indicator_param_options_coarse():
    return autowfo_strategy._build_indicator_param_options_coarse()


def _expand_float(base, step, min_value=None, max_value=None):
    return autowfo_strategy._expand_float(
        base,
        step,
        min_value=min_value,
        max_value=max_value,
    )


def _expand_int(base, step, min_value=1):
    return autowfo_strategy._expand_int(base, step, min_value=min_value)


def _expand_lookback_list(values, step, min_value=2):
    return autowfo_strategy._expand_lookback_list(values, step, min_value=min_value)


def _expand_pair(base_long, base_short, step, min_value=0, max_value=100):
    return autowfo_strategy._expand_pair(
        base_long,
        base_short,
        step,
        min_value=min_value,
        max_value=max_value,
    )


def _indicator_defaults(options):
    return autowfo_strategy._indicator_defaults(options)


def _refine_indicator_params(ind_key, base_row, steps, defaults):
    return autowfo_strategy._refine_indicator_params(ind_key, base_row, steps, defaults)


def _iter_indicator_param_combos(combo_keys, param_options):
    yield from autowfo_strategy._iter_indicator_param_combos(combo_keys, param_options)


def _apply_indicator_combo(long_regime, short_regime, combo_keys, combo_params, ctx):
    return autowfo_strategy._apply_indicator_combo(
        long_regime,
        short_regime,
        combo_keys,
        combo_params,
        ctx,
    )


def _run_pf(
    trade_close,
    long_regime,
    short_regime,
    max_hold,
    fees,
    sl_stop,
    tp_stop,
    freq,
    slippage=None,
    long_filter=None,
    short_filter=None,
    init_cash=None,
    size=None,
    size_type=None,
    cash_sharing=None,
    lock_cash=None,
    allow_partial=None,
    max_positions=None,
    long_scores=None,
    short_scores=None,
):
    return autowfo_portfolio._run_pf(
        trade_close=trade_close,
        long_regime=long_regime,
        short_regime=short_regime,
        max_hold=max_hold,
        fees=fees,
        sl_stop=sl_stop,
        tp_stop=tp_stop,
        freq=freq,
        slippage=slippage,
        long_filter=long_filter,
        short_filter=short_filter,
        init_cash=init_cash,
        size=size,
        size_type=size_type,
        cash_sharing=cash_sharing,
        lock_cash=lock_cash,
        allow_partial=allow_partial,
        max_positions=max_positions,
        long_scores=long_scores,
        short_scores=short_scores,
    )


def main():
    base_symbol = "BTC/USDT"
    exchange = "binance"
    fallback_trade_symbols = [
        "ETH/BTC",
        "BNB/BTC",
        "ADA/BTC",
        "XRP/BTC",
        "SOL/BTC",
        "DOGE/BTC",
        "DOT/BTC",
        "LINK/BTC",
        "LTC/BTC",
        "AVAX/BTC",
    ]
    default_trade_symbols = _fetch_top_trade_symbols(
        exchange, limit=10, fallback=fallback_trade_symbols
    )
    out_dir = "artifacts"
    os.makedirs(out_dir, exist_ok=True)

    default_config = autowfo_engine._load_runtime_config(
        out_dir,
        env_mode=os.getenv("VBT_SWEEP_MODE"),
    )
    search_mode = autowfo_engine._normalize_search_mode(default_config.get("search_mode", "combo"))
    timeframe_configs = default_config["timeframes"]
    combo_sizes = default_config["combo_sizes"]
    combo_seed = int(default_config.get("combo_seed", 42))
    combo_segment_start = int(default_config.get("combo_segment_start", 0))
    combo_segment_size = default_config.get("combo_segment_size")
    combo_group_fields = default_config.get("combo_group_fields", ["indicator_list", "regime_name", "vol_mode"])
    trade_symbols = autowfo_engine._normalize_trade_symbols(
        default_config.get("trade_symbols", default_trade_symbols),
        base_symbol=base_symbol,
        default_trade_symbols=default_trade_symbols,
    )

    wf_train_days = autowfo_engine._safe_positive_config_int(default_config, "wf_train_days", 120)
    wf_test_days = autowfo_engine._safe_positive_config_int(default_config, "wf_test_days", 30)
    wf_step_days = autowfo_engine._safe_positive_config_int(default_config, "wf_step_days", 30)

    vol_lookbacks = [24]
    vol_zs = [0.8]
    mom_lookbacks = [6, 12]
    trade_mom_lookbacks = [3]
    tp_stops = [0.003, 0.005]
    sl_stops = [0.006, 0.01]
    max_holds = [2, 4]

    rsi_window = 14
    rsi_revert_pairs = [(30, 70), (35, 65), (40, 60)]
    bb_window = 20
    bb_alpha = 2
    atr_window = 14
    base_ma_pairs = [(10, 30), (20, 50)]
    ma_pairs = autowfo_engine._build_ma_pairs(base_ma_pairs)
    lookback_refine_step = 4
    obv_lookbacks = _expand_lookback_list([12, 24], lookback_refine_step)
    volume_lookbacks = _expand_lookback_list([12, 24], lookback_refine_step)
    roc_lookbacks = _expand_lookback_list([6, 12], lookback_refine_step)
    cmf_lookbacks = _expand_lookback_list([20, 30], lookback_refine_step)
    mfi_window = 14
    vroc_lookbacks = _expand_lookback_list([12, 24], lookback_refine_step)
    ad_lookbacks = _expand_lookback_list([20, 40], lookback_refine_step)

    fees = 0.001
    slippage_bps = float(default_config.get("slippage_bps", 0.0) or 0.0)
    spread_bps = float(default_config.get("spread_bps", 0.0) or 0.0)
    funding_rate_daily = float(default_config.get("funding_rate_daily", 0.0) or 0.0)
    capital_mode = str(default_config.get("capital_mode", "shared") or "shared").lower()
    if capital_mode not in {"shared", "per_symbol"}:
        capital_mode = "shared"
    init_cash_usdt = float(default_config.get("init_cash_usdt", 1000) or 1000)
    order_size_pct = float(default_config.get("order_size_pct", 0.5) or 0.5)
    if order_size_pct > 1:
        order_size_pct = order_size_pct / 100.0
    if order_size_pct <= 0:
        order_size_pct = 0.5
    max_concurrent_positions = int(default_config.get("max_concurrent_positions", 2) or 2)
    cache_dir = os.path.join(out_dir, "cache_ccxt")
    cache_format = "parquet" if _has_parquet_engine() else "csv"
    run_id = dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    timestamp_utc = dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    # Minimum average daily trades across all symbols.
    # User requirement: >= 5 trades per day.
    min_avg_daily_trades_target = 5
    min_oos_trades_target = 1
    top_n_fine = int(default_config.get("top_n_refine", 50))
    history_rows = 20
    leaderboard_path = os.path.join(out_dir, "leaderboard.csv")
    status_json_path = os.path.join(out_dir, "run_status.json")
    status_html_path = os.path.join(out_dir, "run_status.html")
    db_path = os.path.join(out_dir, "results.db")
    control_path = os.path.join(out_dir, "run_control.json")
    if not os.path.exists(control_path):
        with open(control_path, "w", encoding="utf-8") as f:
            json.dump({"paused": False}, f, ensure_ascii=False, indent=2)

    combo_path = os.path.join(out_dir, "param_sweep_combo_summary.csv")
    per_symbol_path = os.path.join(out_dir, "param_sweep_symbol_summary.csv")
    existing_combo_df = pd.read_csv(combo_path, low_memory=False) if os.path.exists(combo_path) else pd.DataFrame()
    existing_symbol_df = pd.read_csv(per_symbol_path, low_memory=False) if os.path.exists(per_symbol_path) else pd.DataFrame()
    _ensure_csv_schema(combo_path, COMBO_RESULT_FIELDS)
    _ensure_csv_schema(per_symbol_path, SYMBOL_RESULT_FIELDS)
    _ensure_db_schema(
        db_path,
        "combo_summary",
        COMBO_RESULT_FIELDS,
        indexes=[("idx_combo_timeframe", ["timeframe"])],
    )
    _ensure_db_schema(
        db_path,
        "symbol_summary",
        SYMBOL_RESULT_FIELDS,
        indexes=[
            ("idx_symbol_timeframe", ["timeframe"]),
            ("idx_symbol_symbol", ["symbol"]),
        ],
    )
    if os.path.exists(combo_path):
        existing_combo_df = pd.read_csv(combo_path, low_memory=False)
    if os.path.exists(per_symbol_path):
        existing_symbol_df = pd.read_csv(per_symbol_path, low_memory=False)
    if "timeframe" not in existing_combo_df.columns and not existing_combo_df.empty:
        existing_combo_df["timeframe"] = "1h"
    if "data_days" not in existing_combo_df.columns and not existing_combo_df.empty:
        existing_combo_df["data_days"] = np.nan
    if "timeframe" not in existing_symbol_df.columns and not existing_symbol_df.empty:
        existing_symbol_df["timeframe"] = "1h"
    if "data_days" not in existing_symbol_df.columns and not existing_symbol_df.empty:
        existing_symbol_df["data_days"] = np.nan
    if not existing_combo_df.empty:
        for field in COMBO_KEY_FIELDS:
            if field not in existing_combo_df.columns:
                existing_combo_df[field] = np.nan
    indicator_param_options = _build_indicator_param_options_coarse()
    indicator_defaults = _indicator_defaults(indicator_param_options)
    indicator_keys = list(INDICATOR_META.keys())
    combo_keys_all = []
    for size in combo_sizes:
        combo_keys_all.extend(list(itertools.combinations(indicator_keys, size)))
    rng = np.random.default_rng(combo_seed)
    rng.shuffle(combo_keys_all)
    if combo_segment_size:
        combo_keys_all = combo_keys_all[combo_segment_start: combo_segment_start + int(combo_segment_size)]

    regime_variants = autowfo_engine._build_regime_variants(rsi_revert_pairs)

    # scanning logic (multi-timeframe, incremental, two-space)
    regime_lookup = {regime["regime_name"]: regime for regime in regime_variants}
    timeframe_days_map = {cfg["timeframe"]: cfg["days"] for cfg in timeframe_configs}

    def count_coarse_combos():
        return autowfo_engine._count_coarse_combos(
            regime_variants=regime_variants,
            indicator_param_options=indicator_param_options,
            combo_keys_all=combo_keys_all,
            mom_lookbacks=mom_lookbacks,
            vol_lookbacks=vol_lookbacks,
            vol_zs=vol_zs,
            trade_mom_lookbacks=trade_mom_lookbacks,
            tp_stops=tp_stops,
            sl_stops=sl_stops,
            max_holds=max_holds,
        )

    total_combos = count_coarse_combos() * len(timeframe_configs) if search_mode == "combo" else 0
    done = 0
    skipped = 0
    start_ts = time.time()
    last_progress_ts = 0.0
    progress_every = 25
    progress_min_seconds = 5

    def emit_progress(stage="running", force=False):
        nonlocal last_progress_ts, done, skipped, total_combos
        now = time.time()
        if not force and done > 0:
            if (done % progress_every != 0) and (now - last_progress_ts < progress_min_seconds):
                return
        elapsed = now - start_ts
        eta = (elapsed / done * (total_combos - done)) if done > 0 else None
        payload = {
            "run_id": run_id,
            "stage": stage,
            "total": total_combos,
            "done": done,
            "remaining": max(total_combos - done, 0),
            "skipped": skipped,
            "percent": round(done / total_combos * 100, 2) if total_combos else 0,
            "elapsed": _format_duration(elapsed),
            "eta": _format_duration(eta) if eta is not None else "",
            "updated": dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        }
        _write_status(status_json_path, status_html_path, payload)
        print(
            f"[{stage}] {done}/{total_combos} ({payload['percent']}%) "
            f"skipped {skipped} elapsed {payload['elapsed']} eta {payload['eta']}",
            flush=True,
        )
        last_progress_ts = now

    def _read_control():
        try:
            with open(control_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"paused": False}

    def _wait_if_paused(stage_label):
        while True:
            control = _read_control()
            if not control.get("paused"):
                return
            emit_progress(stage=f"{stage_label} paused", force=True)
            time.sleep(2)

    def _checkpoint(force=False):
        nonlocal last_checkpoint_ts, last_checkpoint_done
        if not pending_combo_rows and not pending_symbol_rows:
            return
        now = time.time()
        if not force:
            if done - last_checkpoint_done < checkpoint_every and (now - last_checkpoint_ts) < checkpoint_min_seconds:
                return
        _append_rows(combo_path, pending_combo_rows, COMBO_RESULT_FIELDS)
        _append_rows(per_symbol_path, pending_symbol_rows, SYMBOL_RESULT_FIELDS)
        try:
            _append_db_rows(db_path, "combo_summary", pending_combo_rows, COMBO_RESULT_FIELDS)
            _append_db_rows(db_path, "symbol_summary", pending_symbol_rows, SYMBOL_RESULT_FIELDS)
        except Exception as exc:
            print(f"[warn] db write failed: {exc}")
        pending_combo_rows.clear()
        pending_symbol_rows.clear()
        last_checkpoint_ts = now
        last_checkpoint_done = done

    emit_progress(stage="running", force=True)

    seen_keys = set()
    if not existing_combo_df.empty:
        for _, row in existing_combo_df.iterrows():
            row_dict = row.to_dict()
            if not _has_all_config_fields(row_dict):
                continue
            seen_keys.add(_combo_key_from_dict(row_dict))

    pending_combo_rows = []
    pending_symbol_rows = []
    timeframe_ranges = []
    last_checkpoint_ts = time.time()
    last_checkpoint_done = 0
    checkpoint_every = 200
    checkpoint_min_seconds = 30

    def apply_quality_filters(df):
        return autowfo_engine._apply_quality_filters(
            df,
            min_avg_daily_trades_target=min_avg_daily_trades_target,
            min_oos_trades_target=min_oos_trades_target,
        )

    for tf_cfg in timeframe_configs:
        timeframe = tf_cfg["timeframe"]
        data_days = tf_cfg["days"]
        stage_prefix = f"{timeframe}"
        bar_hours = _timeframe_to_hours(timeframe)
        try:
            ctx = _prepare_timeframe_context(
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
            )
        except Exception as exc:
            if search_mode == "combo":
                total_combos = max(total_combos - count_coarse_combos(), done)
            emit_progress(stage=f"{stage_prefix} skipped", force=True)
            print(f"[warn] timeframe {timeframe} skipped: {exc}")
            continue

        trade_symbols_tf = ctx["trade_symbols"]
        plot_symbol_tf = trade_symbols_tf[0]
        timeframe_ranges.append(f"{timeframe} ({data_days}d): {ctx['data_range']}")
        wf_slices = _build_walk_forward_slices(
            ctx["trade_close"].index, wf_train_days, wf_test_days, wf_step_days
        )
        if not wf_slices:
            required_days = wf_train_days + wf_test_days
            print(
                f"[warn] timeframe {timeframe} has no walk-forward segments: "
                f"available_days={ctx['total_days']} required_days>={required_days}. "
                "OOS metrics will be empty."
            )

        def eval_combo(
            regime,
            indicator_combo,
            combo_params,
            vol_lookback,
            vol_z,
            mom_lookback,
            trade_mom_lookback,
            tp_stop,
            sl_stop,
            max_hold,
            stage,
        ):
            nonlocal done, skipped
            _wait_if_paused(stage)
            indicator_list = ",".join(indicator_combo)
            filter_name = _indicator_combo_label(indicator_combo)
            param_payload = {field: combo_params.get(field) for field in INDICATOR_PARAM_FIELDS}
            combo_key = _combo_key_from_dict({
                "timeframe": timeframe,
                "data_days": data_days,
                "exchange": exchange,
                "base_symbol": base_symbol,
                "trade_symbols_key": ",".join(trade_symbols_tf),
                "capital_mode": capital_mode,
                "fees": fees,
                "slippage_bps": slippage_bps,
                "spread_bps": spread_bps,
                "funding_rate_daily": funding_rate_daily,
                "order_size_pct": order_size_pct,
                "max_concurrent_positions": max_concurrent_positions,
                "init_cash_usdt": init_cash_usdt,
                "wf_train_days": wf_train_days,
                "wf_test_days": wf_test_days,
                "wf_step_days": wf_step_days,
                "data_start": str(ctx["trade_close"].index[0]),
                "data_end": str(ctx["trade_close"].index[-1]),
                "regime_name": regime["regime_name"],
                "regime_type": regime["regime_type"],
                "vol_mode": regime["vol_mode"],
                "regime_rsi_long": regime.get("rsi_pair", (None, None))[0] if regime["regime_type"] == "rsi_revert" else None,
                "regime_rsi_short": regime.get("rsi_pair", (None, None))[1] if regime["regime_type"] == "rsi_revert" else None,
                "filter_name": filter_name,
                "indicator_list": indicator_list,
                "indicator_count": len(indicator_combo),
                "vol_lookback": vol_lookback if regime["vol_mode"] != "any" else None,
                "vol_z": vol_z if regime["vol_mode"] != "any" else None,
                "mom_lookback": mom_lookback if regime["regime_type"] == "trend" else None,
                "trade_mom_lookback": trade_mom_lookback,
                "tp_stop": tp_stop,
                "sl_stop": sl_stop,
                "max_hold": max_hold,
                "rsi_window": rsi_window if "rsi" in indicator_combo else None,
                "rsi_long": param_payload["rsi_long"],
                "rsi_short": param_payload["rsi_short"],
                "bb_width": param_payload["bb_width"],
                "atr_ratio": param_payload["atr_ratio"],
                "ma_fast": param_payload["ma_fast"],
                "ma_slow": param_payload["ma_slow"],
                "macd_hist_ratio": param_payload["macd_hist_ratio"],
                "stoch_long": param_payload["stoch_long"],
                "stoch_short": param_payload["stoch_short"],
                "obv_lookback": param_payload["obv_lookback"],
                "volume_lookback": param_payload["volume_lookback"],
                "volume_z": param_payload["volume_z"],
                "roc_lookback": param_payload["roc_lookback"],
                "roc_threshold": param_payload["roc_threshold"],
                "mfi_long": param_payload["mfi_long"],
                "mfi_short": param_payload["mfi_short"],
                "cmf_lookback": param_payload["cmf_lookback"],
                "cmf_threshold": param_payload["cmf_threshold"],
                "vroc_lookback": param_payload["vroc_lookback"],
                "vroc_threshold": param_payload["vroc_threshold"],
                "ad_lookback": param_payload["ad_lookback"],
            })
            if combo_key in seen_keys:
                skipped += 1
                done += 1
                emit_progress(stage=stage)
                return

            vol_zscore = ctx["vol_zscore_by_lb"][vol_lookback]
            if regime["vol_mode"] == "high":
                vol_cond = vol_zscore > vol_z
            elif regime["vol_mode"] == "low":
                vol_cond = vol_zscore < -vol_z
            else:
                vol_cond = pd.Series(True, index=vol_zscore.index)

            if regime["regime_type"] == "trend":
                mom = ctx["mom_by_lb"][mom_lookback]
                long_regime = vol_cond & (mom > 0)
                short_regime = vol_cond & (mom < 0)
                regime_rsi_long = None
                regime_rsi_short = None
            elif regime["regime_type"] == "rsi_revert":
                regime_rsi_long, regime_rsi_short = regime["rsi_pair"]
                long_regime = vol_cond & (ctx["rsi_series"] < regime_rsi_long)
                short_regime = vol_cond & (ctx["rsi_series"] > regime_rsi_short)
            elif regime["regime_type"] == "bb_revert":
                regime_rsi_long = None
                regime_rsi_short = None
                long_regime = vol_cond & (ctx["btc_close"] < ctx["bb_lower"])
                short_regime = vol_cond & (ctx["btc_close"] > ctx["bb_upper"])
            else:
                regime_rsi_long = None
                regime_rsi_short = None
                long_regime = vol_cond & (ctx["btc_close"] > ctx["bb_upper"])
                short_regime = vol_cond & (ctx["btc_close"] < ctx["bb_lower"])

            trade_mom = ctx["trade_mom_by_lb"][trade_mom_lookback]
            long_filter = trade_mom > 0
            short_filter = trade_mom < 0

            effective_slippage = (slippage_bps + (spread_bps / 2.0)) / 10000.0
            funding_fee = funding_rate_daily * (max_hold * bar_hours / 24.0)
            effective_fees = fees + funding_fee

            long_regime_final, short_regime_final, variant_params = _apply_indicator_combo(
                long_regime,
                short_regime,
                indicator_combo,
                combo_params,
                ctx,
            )

            pf = _run_pf(
                ctx["trade_close"],
                long_regime_final,
                short_regime_final,
                max_hold,
                effective_fees,
                sl_stop,
                tp_stop,
                freq=timeframe,
                long_filter=long_filter,
                short_filter=short_filter,
                init_cash=ctx["init_cash_btc"],
                size=order_size_pct,
                size_type="percent",
                cash_sharing=(capital_mode == "shared"),
                lock_cash=True,
                allow_partial=False,
                max_positions=(max_concurrent_positions if capital_mode == "shared" else None),
                long_scores=trade_mom,
                short_scores=-trade_mom,
                slippage=effective_slippage,
            )

            metrics = _calc_pf_series(pf, trade_symbols_tf, bar_hours)
            sym_metrics = _aggregate_metrics(metrics)
            if capital_mode == "shared":
                combo_metrics = _calc_pf_combo_metrics(pf, bar_hours)
                avg_daily_trades = float(combo_metrics["total_trades"]) / max(ctx["total_days"], 1)
            else:
                combo_metrics = {
                    "total_return_pct": sym_metrics["avg_total_return_pct"],
                    "total_profit": np.nan,
                    "total_trades": sym_metrics["avg_total_trades"],
                    "win_rate_pct": sym_metrics["avg_win_rate_pct"],
                    "avg_trade_pct": sym_metrics["avg_avg_trade_pct"],
                    "max_drawdown_pct": sym_metrics["avg_max_drawdown_pct"],
                    "position_coverage_pct": sym_metrics["avg_position_coverage_pct"],
                    "avg_hold_hours": sym_metrics["avg_hold_hours"],
                }
                avg_daily_trades = float(sym_metrics["avg_total_trades"]) / max(ctx["total_days"], 1)

            oos_rows = []
            for test_start, test_end in wf_slices:
                segment_close = ctx["trade_close"].loc[test_start:test_end]
                if segment_close.empty:
                    continue
                segment_long = long_regime_final.loc[segment_close.index]
                segment_short = short_regime_final.loc[segment_close.index]
                segment_trade_mom = trade_mom.loc[segment_close.index]
                pf_test = _run_pf(
                    segment_close,
                    segment_long,
                    segment_short,
                    max_hold,
                    effective_fees,
                    sl_stop,
                    tp_stop,
                    freq=timeframe,
                    long_filter=segment_trade_mom > 0,
                    short_filter=segment_trade_mom < 0,
                    init_cash=ctx["init_cash_btc"],
                    size=order_size_pct,
                    size_type="percent",
                    cash_sharing=(capital_mode == "shared"),
                    lock_cash=True,
                    allow_partial=False,
                    max_positions=(max_concurrent_positions if capital_mode == "shared" else None),
                    long_scores=segment_trade_mom,
                    short_scores=-segment_trade_mom,
                    slippage=effective_slippage,
                )
                if capital_mode == "shared":
                    seg_combo_metrics = _calc_pf_combo_metrics(pf_test, bar_hours)
                else:
                    seg_series = _calc_pf_series(pf_test, trade_symbols_tf, bar_hours)
                    seg_agg = _aggregate_metrics(seg_series)
                    seg_combo_metrics = {
                        "total_return_pct": seg_agg["avg_total_return_pct"],
                        "total_profit": np.nan,
                        "total_trades": seg_agg["avg_total_trades"],
                        "win_rate_pct": seg_agg["avg_win_rate_pct"],
                        "avg_trade_pct": seg_agg["avg_avg_trade_pct"],
                        "max_drawdown_pct": seg_agg["avg_max_drawdown_pct"],
                        "position_coverage_pct": seg_agg["avg_position_coverage_pct"],
                        "avg_hold_hours": seg_agg["avg_hold_hours"],
                    }
                seg_row = {
                    "avg_total_return_pct": seg_combo_metrics["total_return_pct"],
                    "avg_win_rate_pct": seg_combo_metrics["win_rate_pct"],
                    "avg_avg_trade_pct": seg_combo_metrics["avg_trade_pct"],
                    "avg_max_drawdown_pct": seg_combo_metrics["max_drawdown_pct"],
                    "avg_position_coverage_pct": seg_combo_metrics["position_coverage_pct"],
                    "avg_total_trades": seg_combo_metrics["total_trades"],
                    "min_total_trades": seg_combo_metrics["total_trades"],
                    "avg_hold_hours": seg_combo_metrics["avg_hold_hours"],
                }
                segment_days = int(segment_close.index.normalize().nunique())
                seg_row["avg_daily_trades"] = float(seg_combo_metrics["total_trades"]) / max(segment_days, 1)
                oos_rows.append(seg_row)
            oos_metrics = _aggregate_oos_metrics(oos_rows)

            for symbol in trade_symbols_tf:
                pending_symbol_rows.append({
                    "timeframe": timeframe,
                    "data_days": data_days,
                    "exchange": exchange,
                    "base_symbol": base_symbol,
                    "trade_symbols_key": ",".join(trade_symbols_tf),
                    "capital_mode": capital_mode,
                    "fees": fees,
                    "order_size_pct": order_size_pct,
                    "max_concurrent_positions": max_concurrent_positions,
                    "init_cash_usdt": init_cash_usdt,
                    "wf_train_days": wf_train_days,
                    "wf_test_days": wf_test_days,
                    "wf_step_days": wf_step_days,
                    "data_start": str(ctx["trade_close"].index[0]),
                    "data_end": str(ctx["trade_close"].index[-1]),
                    "symbol": symbol,
                    "regime_name": regime["regime_name"],
                    "regime_type": regime["regime_type"],
                    "vol_mode": regime["vol_mode"],
                    "regime_rsi_long": regime_rsi_long,
                    "regime_rsi_short": regime_rsi_short,
                    "filter_name": filter_name,
                    "indicator_list": indicator_list,
                    "indicator_count": len(indicator_combo),
                    "vol_lookback": vol_lookback if regime["vol_mode"] != "any" else None,
                    "vol_z": vol_z if regime["vol_mode"] != "any" else None,
                    "mom_lookback": mom_lookback if regime["regime_type"] == "trend" else None,
                    "trade_mom_lookback": trade_mom_lookback,
                    "tp_stop": tp_stop,
                    "sl_stop": sl_stop,
                    "max_hold": max_hold,
                    "rsi_window": rsi_window if "rsi" in indicator_combo else None,
                    "rsi_long": variant_params["rsi_long"],
                    "rsi_short": variant_params["rsi_short"],
                    "bb_width": variant_params["bb_width"],
                    "atr_ratio": variant_params["atr_ratio"],
                    "ma_fast": variant_params["ma_fast"],
                    "ma_slow": variant_params["ma_slow"],
                    "macd_hist_ratio": variant_params["macd_hist_ratio"],
                    "stoch_long": variant_params["stoch_long"],
                    "stoch_short": variant_params["stoch_short"],
                    "obv_lookback": variant_params["obv_lookback"],
                    "volume_lookback": variant_params["volume_lookback"],
                    "volume_z": variant_params["volume_z"],
                    "roc_lookback": variant_params["roc_lookback"],
                    "roc_threshold": variant_params["roc_threshold"],
                    "mfi_long": variant_params["mfi_long"],
                    "mfi_short": variant_params["mfi_short"],
                    "cmf_lookback": variant_params["cmf_lookback"],
                    "cmf_threshold": variant_params["cmf_threshold"],
                    "vroc_lookback": variant_params["vroc_lookback"],
                    "vroc_threshold": variant_params["vroc_threshold"],
                    "ad_lookback": variant_params["ad_lookback"],
                    "total_return_pct": float(metrics["total_return_pct"][symbol]),
                    "total_profit": float(metrics["total_profit"][symbol]),
                    "total_trades": float(metrics["total_trades"][symbol]),
                    "win_rate_pct": float(metrics["win_rate_pct"][symbol]),
                    "avg_trade_pct": float(metrics["avg_trade_pct"][symbol]),
                    "max_drawdown_pct": float(metrics["max_drawdown_pct"][symbol]),
                    "position_coverage_pct": float(metrics["position_coverage_pct"][symbol]),
                    "avg_hold_hours": float(metrics["avg_hold_hours"][symbol]),
                })

            combo_row = {
                "timeframe": timeframe,
                "data_days": data_days,
                "exchange": exchange,
                "base_symbol": base_symbol,
                "trade_symbols_key": ",".join(trade_symbols_tf),
                "fees": fees,
                "slippage_bps": slippage_bps,
                "spread_bps": spread_bps,
                "funding_rate_daily": funding_rate_daily,
                "order_size_pct": order_size_pct,
                "max_concurrent_positions": max_concurrent_positions,
                "init_cash_usdt": init_cash_usdt,
                "wf_train_days": wf_train_days,
                "wf_test_days": wf_test_days,
                "wf_step_days": wf_step_days,
                "data_start": str(ctx["trade_close"].index[0]),
                "data_end": str(ctx["trade_close"].index[-1]),
                "regime_name": regime["regime_name"],
                "regime_type": regime["regime_type"],
                "vol_mode": regime["vol_mode"],
                "regime_rsi_long": regime_rsi_long,
                "regime_rsi_short": regime_rsi_short,
                "filter_name": filter_name,
                "indicator_list": indicator_list,
                "indicator_count": len(indicator_combo),
                "vol_lookback": vol_lookback if regime["vol_mode"] != "any" else None,
                "vol_z": vol_z if regime["vol_mode"] != "any" else None,
                "mom_lookback": mom_lookback if regime["regime_type"] == "trend" else None,
                "trade_mom_lookback": trade_mom_lookback,
                "tp_stop": tp_stop,
                "sl_stop": sl_stop,
                "max_hold": max_hold,
                "rsi_window": rsi_window if "rsi" in indicator_combo else None,
                "rsi_long": variant_params["rsi_long"],
                "rsi_short": variant_params["rsi_short"],
                "bb_width": variant_params["bb_width"],
                "atr_ratio": variant_params["atr_ratio"],
                "ma_fast": variant_params["ma_fast"],
                "ma_slow": variant_params["ma_slow"],
                "macd_hist_ratio": variant_params["macd_hist_ratio"],
                "stoch_long": variant_params["stoch_long"],
                "stoch_short": variant_params["stoch_short"],
                "obv_lookback": variant_params["obv_lookback"],
                "volume_lookback": variant_params["volume_lookback"],
                "volume_z": variant_params["volume_z"],
                "roc_lookback": variant_params["roc_lookback"],
                "roc_threshold": variant_params["roc_threshold"],
                "mfi_long": variant_params["mfi_long"],
                "mfi_short": variant_params["mfi_short"],
                "cmf_lookback": variant_params["cmf_lookback"],
                "cmf_threshold": variant_params["cmf_threshold"],
                "vroc_lookback": variant_params["vroc_lookback"],
                "vroc_threshold": variant_params["vroc_threshold"],
                "ad_lookback": variant_params["ad_lookback"],
                "avg_total_return_pct": combo_metrics["total_return_pct"],
                "avg_win_rate_pct": combo_metrics["win_rate_pct"],
                "avg_avg_trade_pct": combo_metrics["avg_trade_pct"],
                "avg_max_drawdown_pct": combo_metrics["max_drawdown_pct"],
                "avg_position_coverage_pct": combo_metrics["position_coverage_pct"],
                "avg_total_trades": combo_metrics["total_trades"],
                "min_total_trades": combo_metrics["total_trades"],
                "avg_daily_trades": avg_daily_trades,
                "avg_hold_hours": combo_metrics["avg_hold_hours"],
                "sym_avg_total_return_pct": sym_metrics["avg_total_return_pct"],
                "sym_avg_win_rate_pct": sym_metrics["avg_win_rate_pct"],
                "sym_avg_avg_trade_pct": sym_metrics["avg_avg_trade_pct"],
                "sym_avg_max_drawdown_pct": sym_metrics["avg_max_drawdown_pct"],
                "sym_avg_position_coverage_pct": sym_metrics["avg_position_coverage_pct"],
                "sym_avg_total_trades": sym_metrics["avg_total_trades"],
                "sym_min_total_trades": sym_metrics["min_total_trades"],
                "sym_avg_daily_trades": float(metrics["total_trades"].sum()) / max(ctx["total_days"], 1),
                "sym_avg_hold_hours": sym_metrics["avg_hold_hours"],
            }
            combo_row.update(oos_metrics)
            pending_combo_rows.append(combo_row)
            seen_keys.add(combo_key)
            done += 1
            emit_progress(stage=stage)
            _checkpoint()

        if search_mode == "combo":
            # Coarse pass: explore indicator combinations
            for regime in regime_variants:
                mom_iter = mom_lookbacks if regime["regime_type"] == "trend" else [mom_lookbacks[0]]
                for vol_lookback in vol_lookbacks:
                    for vol_z in vol_zs:
                        if regime["vol_mode"] == "any" and (
                            vol_lookback != vol_lookbacks[0] or vol_z != vol_zs[0]
                        ):
                            continue
                        for mom_lookback in mom_iter:
                            for trade_mom_lookback in trade_mom_lookbacks:
                                for tp_stop in tp_stops:
                                    for sl_stop in sl_stops:
                                        for max_hold in max_holds:
                                            for combo_keys in combo_keys_all:
                                                for combo_params in _iter_indicator_param_combos(combo_keys, indicator_param_options):
                                                    eval_combo(
                                                        regime,
                                                        combo_keys,
                                                        combo_params,
                                                        vol_lookback,
                                                        vol_z,
                                                        mom_lookback,
                                                        trade_mom_lookback,
                                                        tp_stop,
                                                        sl_stop,
                                                        max_hold,
                                                        stage=f"{stage_prefix} combo",
                                                    )

        if search_mode == "refine":
            tf_existing = existing_combo_df[existing_combo_df["timeframe"] == timeframe] if not existing_combo_df.empty else pd.DataFrame()
            tf_combo_df = tf_existing.copy()
            tf_filtered = apply_quality_filters(tf_combo_df)
            tf_sorted, _ = _sort_by_score(tf_filtered, tie_break_avg_hold=True)
            group_fields = [field for field in combo_group_fields if field in tf_sorted.columns]
            if group_fields:
                tf_sorted = tf_sorted.drop_duplicates(subset=group_fields)
            top_candidates = tf_sorted.head(top_n_fine)

            refine_steps = {
                "threshold_pair": 5,
                "lookback": 4,
                "ma_step": 5,
                "bb_width": 0.01,
                "atr_ratio": 0.001,
                "macd_hist_ratio": 0.0005,
                "roc_threshold": 0.005,
                "volume_z": 0.1,
                "cmf_threshold": 0.02,
                "vroc_threshold": 0.2,
                "tp_stop": 0.001,
                "sl_stop": 0.002,
            }

            fine_total = 0
            fine_targets = []
            for _, row in top_candidates.iterrows():
                indicator_list = row.get("indicator_list")
                if not indicator_list:
                    continue
                indicator_combo = tuple([v for v in str(indicator_list).split(",") if v])
                if not indicator_combo:
                    continue
                base_tp = _safe_float(row.get("tp_stop"), tp_stops[0])
                base_sl = _safe_float(row.get("sl_stop"), sl_stops[0])
                tp_candidates = _expand_float(base_tp, refine_steps["tp_stop"], min_value=0.0001)
                sl_candidates = _expand_float(base_sl, refine_steps["sl_stop"], min_value=0.0001)
                param_options = {
                    key: _refine_indicator_params(key, row, refine_steps, indicator_defaults)
                    for key in indicator_combo
                }
                indicator_count = int(np.prod([len(param_options.get(key, [{}])) for key in indicator_combo]))
                fine_total += indicator_count * max(len(tp_candidates), 1) * max(len(sl_candidates), 1)
                fine_targets.append((row, indicator_combo, tp_candidates, sl_candidates, param_options))

            if fine_total:
                total_combos += fine_total
                emit_progress(stage=f"{stage_prefix} refine", force=True)

            for row, indicator_combo, tp_candidates, sl_candidates, param_options in fine_targets:
                regime = regime_lookup.get(row.get("regime_name"), regime_variants[0])
                vol_lookback = _safe_int(row.get("vol_lookback"), vol_lookbacks[0])
                vol_z = _safe_float(row.get("vol_z"), vol_zs[0])
                mom_lookback = _safe_int(row.get("mom_lookback"), mom_lookbacks[0])
                trade_mom_lookback = _safe_int(row.get("trade_mom_lookback"), trade_mom_lookbacks[0])
                max_hold = _safe_int(row.get("max_hold"), max_holds[0])

                for tp_stop in tp_candidates:
                    for sl_stop in sl_candidates:
                        for combo_params in _iter_indicator_param_combos(indicator_combo, param_options):
                            eval_combo(
                                regime,
                                indicator_combo,
                                combo_params,
                                vol_lookback,
                                vol_z,
                                mom_lookback,
                                trade_mom_lookback,
                                tp_stop,
                                sl_stop,
                                max_hold,
                                stage=f"{stage_prefix} refine",
                            )

    _checkpoint(force=True)

    combo_df = pd.read_csv(combo_path, low_memory=False) if os.path.exists(combo_path) else pd.DataFrame()
    per_symbol_df = pd.read_csv(per_symbol_path, low_memory=False) if os.path.exists(per_symbol_path) else pd.DataFrame()

    combo_path_run = os.path.join(out_dir, f"param_sweep_combo_summary_{run_id}.csv")
    per_symbol_path_run = os.path.join(out_dir, f"param_sweep_symbol_summary_{run_id}.csv")
    if not combo_df.empty:
        combo_df.to_csv(combo_path_run, index=False)
    if not per_symbol_df.empty:
        per_symbol_df.to_csv(per_symbol_path_run, index=False)

    combo_df_current = combo_df
    if "timeframe" in combo_df.columns:
        valid_timeframes = {cfg["timeframe"] for cfg in timeframe_configs}
        tf_subset = combo_df[combo_df["timeframe"].isin(valid_timeframes)].copy()
        if not tf_subset.empty:
            combo_df_current = tf_subset
    if combo_df_current.empty:
        print("[warn] No valid combinations evaluated; check data download and filters.")
        return

    # Avoid picking low-activity strategies by requiring minimum average daily trades.
    min_avg_daily_trades_filter = min_avg_daily_trades_target
    filtered = apply_quality_filters(combo_df_current)
    if filtered.empty and "avg_daily_trades" in combo_df_current.columns:
        filtered = combo_df_current[combo_df_current["avg_daily_trades"] >= min_avg_daily_trades_filter].copy()
    if filtered.empty:
        min_avg_daily_trades_filter = 2
        filtered = combo_df_current[combo_df_current["avg_daily_trades"] >= min_avg_daily_trades_filter].copy()
    if filtered.empty:
        min_avg_daily_trades_filter = 0
        filtered = combo_df_current.copy()

    top10, _ = _top_by_score(filtered, top_n=10, tie_break_avg_hold=True)
    top10_path = os.path.join(out_dir, f"param_sweep_top10_{run_id}.csv")
    top10.to_csv(top10_path, index=False)

    best = top10.iloc[0].to_dict()
    best_timeframe = best.get("timeframe")
    if best_timeframe is None or (isinstance(best_timeframe, float) and np.isnan(best_timeframe)):
        best_timeframe = timeframe_configs[0]["timeframe"]
    best_timeframe = str(best_timeframe)
    if best_timeframe not in timeframe_days_map:
        best_timeframe = timeframe_configs[0]["timeframe"]
    best_data_days = _safe_int(
        best.get("data_days"),
        timeframe_days_map.get(best_timeframe, timeframe_configs[0]["days"]),
    )
    try:
        best_ctx = _prepare_timeframe_context(
            best_timeframe,
            best_data_days,
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
        )
    except Exception as exc:
        print(f"[warn] best report skipped: {exc}")
        return
    trade_close = best_ctx["trade_close"]
    btc_close = best_ctx["btc_close"]
    btc_high = best_ctx["btc_high"]
    btc_low = best_ctx["btc_low"]
    btc_volume = best_ctx["btc_volume"]
    trade_symbols = best_ctx["trade_symbols"]
    plot_symbol = trade_symbols[0]
    init_cash_btc = best_ctx["init_cash_btc"]
    vol_zscore_by_lb = best_ctx["vol_zscore_by_lb"]
    mom_by_lb = best_ctx["mom_by_lb"]
    trade_mom_by_lb = best_ctx["trade_mom_by_lb"]
    rsi_series = best_ctx["rsi_series"]
    bb_width = best_ctx["bb_width"]
    bb_upper = best_ctx["bb_upper"]
    bb_lower = best_ctx["bb_lower"]
    atr_ratio = best_ctx["atr_ratio"]
    ma_trend_by_pair = best_ctx["ma_trend_by_pair"]
    macd_hist_ratio_series = best_ctx["macd_hist_ratio_series"]
    stoch_k = best_ctx["stoch_k"]
    obv_roc_by_lb = best_ctx["obv_roc_by_lb"]
    volume_zscore_by_lb = best_ctx["volume_zscore_by_lb"]
    roc_by_lb = best_ctx["roc_by_lb"]
    cmf_by_window = best_ctx["cmf_by_window"]
    mfi_by_window = best_ctx["mfi_by_window"]
    mfi_window = best_ctx["mfi_window"]
    vroc_by_lb = best_ctx["vroc_by_lb"]
    ad_roc_by_lb = best_ctx["ad_roc_by_lb"]
    data_range = best_ctx["data_range"]
    scan_timeframes = "; ".join(timeframe_ranges) if timeframe_ranges else ""
    wf_slices = _build_walk_forward_slices(
        trade_close.index, wf_train_days, wf_test_days, wf_step_days
    )
    best_regime = {
        "regime_name": best.get("regime_name"),
        "regime_type": best.get("regime_type"),
        "vol_mode": best.get("vol_mode"),
        "regime_rsi_long": best.get("regime_rsi_long"),
        "regime_rsi_short": best.get("regime_rsi_short"),
    }
    indicator_list = best.get("indicator_list")
    if isinstance(indicator_list, float) and np.isnan(indicator_list):
        indicator_list = ""
    best_indicator_combo = tuple([v for v in str(indicator_list).split(",") if v]) if indicator_list else tuple()
    best_filter_name = best.get("filter_name") or _indicator_combo_label(best_indicator_combo)
    best_params = {}
    for field in INDICATOR_PARAM_FIELDS:
        value = best.get(field)
        best_params[field] = value if pd.notna(value) else None
    best_params = _coerce_indicator_params(best_indicator_combo, best_params, best_ctx)

    best_vol_lookback = int(best["vol_lookback"]) if pd.notna(best["vol_lookback"]) else vol_lookbacks[0]
    best_vol_z = float(best["vol_z"]) if pd.notna(best["vol_z"]) else vol_zs[0]
    best_mom_lookback = int(best["mom_lookback"]) if pd.notna(best["mom_lookback"]) else mom_lookbacks[0]
    best_trade_mom_lookback = int(best["trade_mom_lookback"])
    best_tp_stop = float(best["tp_stop"])
    best_sl_stop = float(best["sl_stop"])
    best_max_hold = int(best["max_hold"])

    vol_zscore, _ = _pick_series_from_map(vol_zscore_by_lb, best_vol_lookback, vol_lookbacks[0] if vol_lookbacks else None)
    if best_regime["vol_mode"] == "high":
        vol_cond = vol_zscore > best_vol_z
    elif best_regime["vol_mode"] == "low":
        vol_cond = vol_zscore < -best_vol_z
    else:
        vol_cond = pd.Series(True, index=vol_zscore.index)

    if best_regime["regime_type"] == "trend":
        mom, _ = _pick_series_from_map(mom_by_lb, best_mom_lookback, mom_lookbacks[0] if mom_lookbacks else None)
        long_regime = vol_cond & (mom > 0)
        short_regime = vol_cond & (mom < 0)
    elif best_regime["regime_type"] == "rsi_revert":
        long_regime = vol_cond & (rsi_series < best_regime["regime_rsi_long"])
        short_regime = vol_cond & (rsi_series > best_regime["regime_rsi_short"])
    elif best_regime["regime_type"] == "bb_revert":
        long_regime = vol_cond & (btc_close < bb_lower)
        short_regime = vol_cond & (btc_close > bb_upper)
    else:
        long_regime = vol_cond & (btc_close > bb_upper)
        short_regime = vol_cond & (btc_close < bb_lower)
    trade_mom, _ = _pick_series_from_map(
        trade_mom_by_lb,
        best_trade_mom_lookback,
        trade_mom_lookbacks[0] if trade_mom_lookbacks else None,
    )
    long_regime, short_regime, best_params = _apply_indicator_combo(
        long_regime,
        short_regime,
        best_indicator_combo,
        best_params,
        best_ctx,
    )

    best_bar_hours = _timeframe_to_hours(best_timeframe)
    best_effective_slippage = (slippage_bps + (spread_bps / 2.0)) / 10000.0
    best_funding_fee = funding_rate_daily * (best_max_hold * best_bar_hours / 24.0)
    best_effective_fees = fees + best_funding_fee

    best_pf = _run_pf(
        trade_close,
        long_regime,
        short_regime,
        best_max_hold,
        best_effective_fees,
        best_sl_stop,
        best_tp_stop,
        freq=best_timeframe,
        long_filter=trade_mom > 0,
        short_filter=trade_mom < 0,
        init_cash=init_cash_btc,
        size=order_size_pct,
        size_type="percent",
        cash_sharing=(capital_mode == "shared"),
        lock_cash=True,
        allow_partial=False,
        max_positions=(max_concurrent_positions if capital_mode == "shared" else None),
        long_scores=trade_mom,
        short_scores=-trade_mom,
        slippage=best_effective_slippage,
    )
    fig = _plot_portfolio(best_pf, plot_symbol)
    plot_html = fig.to_html(full_html=False, include_plotlyjs="cdn")

    best_metrics = _calc_pf_series(best_pf, trade_symbols, _timeframe_to_hours(best_timeframe))
    best_summary = pd.DataFrame({
        "symbol": trade_symbols,
        "total_return_pct": (best_metrics["total_return_pct"]).to_numpy(),
        "total_profit": best_metrics["total_profit"].to_numpy(),
        "total_trades": best_metrics["total_trades"].to_numpy(),
        "win_rate_pct": best_metrics["win_rate_pct"].to_numpy(),
        "avg_trade_pct": best_metrics["avg_trade_pct"].to_numpy(),
        "max_drawdown_pct": best_metrics["max_drawdown_pct"].to_numpy(),
        "position_coverage_pct": best_metrics["position_coverage_pct"].to_numpy(),
        "avg_hold_hours": best_metrics["avg_hold_hours"].to_numpy(),
    })

    report_params = pd.DataFrame([{
        "timeframe": best_timeframe,
        "data_days": best_data_days,
        "capital_mode": capital_mode,
        "regime_name": best_regime["regime_name"],
        "regime_type": best_regime["regime_type"],
        "vol_mode": best_regime["vol_mode"],
        "regime_rsi_long": best_regime["regime_rsi_long"],
        "regime_rsi_short": best_regime["regime_rsi_short"],
        "filter_name": best_filter_name,
        "indicator_list": indicator_list,
        "indicator_count": len(best_indicator_combo),
        "vol_lookback": best.get("vol_lookback"),
        "vol_z": best.get("vol_z"),
        "mom_lookback": best.get("mom_lookback"),
        "trade_mom_lookback": best_trade_mom_lookback,
        "tp_stop": best_tp_stop,
        "sl_stop": best_sl_stop,
        "max_hold": best_max_hold,
        "rsi_window": rsi_window if "rsi" in best_indicator_combo else None,
        "rsi_long": best_params["rsi_long"],
        "rsi_short": best_params["rsi_short"],
        "bb_width": best_params["bb_width"],
        "atr_ratio": best_params["atr_ratio"],
        "ma_fast": best_params["ma_fast"],
        "ma_slow": best_params["ma_slow"],
        "macd_hist_ratio": best_params["macd_hist_ratio"],
        "stoch_long": best_params["stoch_long"],
        "stoch_short": best_params["stoch_short"],
        "obv_lookback": best_params["obv_lookback"],
        "volume_lookback": best_params["volume_lookback"],
        "volume_z": best_params["volume_z"],
        "roc_lookback": best_params["roc_lookback"],
        "roc_threshold": best_params["roc_threshold"],
        "mfi_long": best_params["mfi_long"],
        "mfi_short": best_params["mfi_short"],
        "cmf_lookback": best_params["cmf_lookback"],
        "cmf_threshold": best_params["cmf_threshold"],
        "vroc_lookback": best_params["vroc_lookback"],
        "vroc_threshold": best_params["vroc_threshold"],
        "ad_lookback": best_params["ad_lookback"],
    }])

    oos_summary = pd.DataFrame([{
        "oos_segments": best.get("oos_segments"),
        "oos_avg_total_return_pct": best.get("oos_avg_total_return_pct"),
        "oos_avg_win_rate_pct": best.get("oos_avg_win_rate_pct"),
        "oos_avg_avg_trade_pct": best.get("oos_avg_avg_trade_pct"),
        "oos_avg_max_drawdown_pct": best.get("oos_avg_max_drawdown_pct"),
        "oos_avg_position_coverage_pct": best.get("oos_avg_position_coverage_pct"),
        "oos_avg_total_trades": best.get("oos_avg_total_trades"),
        "oos_min_total_trades": best.get("oos_min_total_trades"),
        "oos_avg_daily_trades": best.get("oos_avg_daily_trades"),
        "oos_avg_hold_hours": best.get("oos_avg_hold_hours"),
    }])

    top_columns = [
        "timeframe",
        "data_days",
        "regime_name",
        "regime_type",
        "vol_mode",
        "regime_rsi_long",
        "regime_rsi_short",
        "filter_name",
        "indicator_list",
        "indicator_count",
        "vol_lookback",
        "vol_z",
        "mom_lookback",
        "trade_mom_lookback",
        "tp_stop",
        "sl_stop",
        "max_hold",
        "rsi_window",
        "rsi_long",
        "rsi_short",
        "bb_width",
        "atr_ratio",
        "ma_fast",
        "ma_slow",
        "macd_hist_ratio",
        "stoch_long",
        "stoch_short",
        "obv_lookback",
        "volume_lookback",
        "volume_z",
        "roc_lookback",
        "roc_threshold",
        "mfi_long",
        "mfi_short",
        "cmf_lookback",
        "cmf_threshold",
        "vroc_lookback",
        "vroc_threshold",
        "ad_lookback",
        "avg_total_return_pct",
        "avg_daily_trades",
        "avg_hold_hours",
        "oos_avg_total_return_pct",
        "oos_avg_win_rate_pct",
        "oos_avg_avg_trade_pct",
        "oos_avg_max_drawdown_pct",
        "oos_avg_position_coverage_pct",
        "oos_avg_total_trades",
        "oos_min_total_trades",
        "oos_avg_daily_trades",
        "oos_avg_hold_hours",
        "oos_segments",
        "avg_win_rate_pct",
        "avg_avg_trade_pct",
        "avg_max_drawdown_pct",
        "avg_position_coverage_pct",
        "avg_total_trades",
        "min_total_trades",
    ]

    summary_columns = [
        "symbol",
        "total_return_pct",
        "total_profit",
        "total_trades",
        "position_coverage_pct",
        "win_rate_pct",
        "avg_trade_pct",
        "max_drawdown_pct",
        "avg_hold_hours",
    ]

    report_params_html = _df_to_html(report_params, list(report_params.columns), LABELS)
    oos_summary_html = _df_to_html(oos_summary, list(oos_summary.columns), LABELS)
    top10_html = _df_to_html(top10, top_columns, LABELS)
    summary_html = _df_to_html(best_summary, summary_columns, LABELS)

    # Persist this run into a simple leaderboard for long-term iteration.
    report_file_latest = f"btc_regime_{plot_symbol.replace('/', '-')}.html"
    report_file_run = f"btc_regime_{plot_symbol.replace('/', '-')}_{run_id}.html"
    report_path_latest = os.path.join(out_dir, report_file_latest)
    report_path_run = os.path.join(out_dir, report_file_run)

    leaderboard_row = {
        "run_id": run_id,
        "timestamp_utc": timestamp_utc,
        "plot_symbol": plot_symbol,
        "timeframe": best_timeframe,
        "data_days": best_data_days,
        "min_avg_daily_trades_target": min_avg_daily_trades_target,
        "min_avg_daily_trades_filter": min_avg_daily_trades_filter,
        "capital_mode": capital_mode,
        "init_cash_usdt": init_cash_usdt,
        "order_size_pct": order_size_pct,
        "max_concurrent_positions": max_concurrent_positions,
        "slippage_bps": slippage_bps,
        "spread_bps": spread_bps,
        "funding_rate_daily": funding_rate_daily,
        "wf_train_days": wf_train_days,
        "wf_test_days": wf_test_days,
        "wf_step_days": wf_step_days,
        "wf_segments": len(wf_slices),
        "regime_name": best.get("regime_name"),
        "regime_type": best.get("regime_type"),
        "vol_mode": best.get("vol_mode"),
        "regime_rsi_long": best.get("regime_rsi_long"),
        "regime_rsi_short": best.get("regime_rsi_short"),
        "filter_name": best.get("filter_name"),
        "indicator_list": best.get("indicator_list"),
        "indicator_count": best.get("indicator_count"),
        "vol_lookback": best.get("vol_lookback"),
        "vol_z": best.get("vol_z"),
        "mom_lookback": best.get("mom_lookback"),
        "trade_mom_lookback": best.get("trade_mom_lookback"),
        "tp_stop": best.get("tp_stop"),
        "sl_stop": best.get("sl_stop"),
        "max_hold": best.get("max_hold"),
        "rsi_window": best.get("rsi_window"),
        "rsi_long": best.get("rsi_long"),
        "rsi_short": best.get("rsi_short"),
        "bb_width": best.get("bb_width"),
        "atr_ratio": best.get("atr_ratio"),
        "ma_fast": best.get("ma_fast"),
        "ma_slow": best.get("ma_slow"),
        "macd_hist_ratio": best.get("macd_hist_ratio"),
        "stoch_long": best.get("stoch_long"),
        "stoch_short": best.get("stoch_short"),
        "obv_lookback": best.get("obv_lookback"),
        "volume_lookback": best.get("volume_lookback"),
        "volume_z": best.get("volume_z"),
        "roc_lookback": best.get("roc_lookback"),
        "roc_threshold": best.get("roc_threshold"),
        "mfi_long": best.get("mfi_long"),
        "mfi_short": best.get("mfi_short"),
        "cmf_lookback": best.get("cmf_lookback"),
        "cmf_threshold": best.get("cmf_threshold"),
        "vroc_lookback": best.get("vroc_lookback"),
        "vroc_threshold": best.get("vroc_threshold"),
        "ad_lookback": best.get("ad_lookback"),
        "avg_total_return_pct": best.get("avg_total_return_pct"),
        "avg_daily_trades": best.get("avg_daily_trades"),
        "avg_hold_hours": best.get("avg_hold_hours"),
        "avg_position_coverage_pct": best.get("avg_position_coverage_pct"),
        "avg_total_trades": best.get("avg_total_trades"),
        "min_total_trades": best.get("min_total_trades"),
        "oos_avg_total_return_pct": best.get("oos_avg_total_return_pct"),
        "oos_avg_win_rate_pct": best.get("oos_avg_win_rate_pct"),
        "oos_avg_avg_trade_pct": best.get("oos_avg_avg_trade_pct"),
        "oos_avg_max_drawdown_pct": best.get("oos_avg_max_drawdown_pct"),
        "oos_avg_position_coverage_pct": best.get("oos_avg_position_coverage_pct"),
        "oos_avg_total_trades": best.get("oos_avg_total_trades"),
        "oos_min_total_trades": best.get("oos_min_total_trades"),
        "oos_avg_daily_trades": best.get("oos_avg_daily_trades"),
        "oos_avg_hold_hours": best.get("oos_avg_hold_hours"),
        "oos_segments": best.get("oos_segments"),
        "report_file": report_file_run,
    }

    if os.path.exists(leaderboard_path):
        lb_df = pd.read_csv(leaderboard_path, low_memory=False)
        lb_df = pd.concat([lb_df, pd.DataFrame([leaderboard_row])], ignore_index=True)
    else:
        lb_df = pd.DataFrame([leaderboard_row])
    lb_df.to_csv(leaderboard_path, index=False)

    lb_view = lb_df.copy()
    if "report_file" in lb_view.columns:
        lb_view["report"] = lb_view["report_file"].apply(lambda x: f'<a href="{x}">{x}</a>' if x else "")
    else:
        lb_view["report"] = ""
    lb_cols = [
        "timestamp_utc",
        "run_id",
        "plot_symbol",
        "timeframe",
        "data_days",
        "min_avg_daily_trades_target",
        "min_avg_daily_trades_filter",
        "regime_name",
        "regime_type",
        "oos_avg_total_return_pct",
        "avg_total_return_pct",
        "avg_daily_trades",
        "oos_avg_daily_trades",
        "avg_total_trades",
        "avg_position_coverage_pct",
        "min_total_trades",
        "filter_name",
        "report",
    ]
    lb_recent = lb_view.sort_values("timestamp_utc", ascending=False).head(history_rows)
    lb_best, _ = _top_by_score(lb_view, top_n=history_rows, tie_break_avg_hold=False)
    lb_recent_html = _df_to_html(lb_recent.reindex(columns=lb_cols), lb_cols, LABELS)
    lb_best_html = _df_to_html(lb_best.reindex(columns=lb_cols), lb_cols, LABELS)

    scan_timeframes_html = (
        f"<div><strong>{LABELS['scan_timeframes']}:</strong> {scan_timeframes}</div>"
        if scan_timeframes
        else ""
    )

    html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>BTC Regime Backtest</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #111; }}
    h1, h2 {{ margin: 16px 0 8px; }}
    table {{ border-collapse: collapse; width: 100%; margin: 8px 0 16px; }}
    th, td {{ border: 1px solid #ddd; padding: 6px 8px; text-align: right; }}
    th {{ background: #f3f3f3; text-align: right; }}
    td:first-child, th:first-child {{ text-align: left; }}
    .meta {{ background: #fafafa; border: 1px solid #eee; padding: 12px; }}
  </style>
</head>
<body>
  <h1>{LABELS['report_title']}</h1>
    <div class="meta">
    <div><strong>{LABELS['data_range']}:</strong> {data_range}</div>
    <div><strong>{LABELS['timeframe']}:</strong> {best_timeframe}</div>
    <div><strong>{LABELS['data_days']}:</strong> {best_data_days}</div>
    {scan_timeframes_html}
    <div><strong>{LABELS['run_id']}:</strong> {run_id}</div>
    <div><strong>{LABELS['timestamp_utc']}:</strong> {timestamp_utc}</div>
    <div><strong>{LABELS['min_avg_daily_trades_target']}:</strong> {min_avg_daily_trades_target}</div>
    <div><strong>{LABELS['min_avg_daily_trades_filter']}:</strong> {min_avg_daily_trades_filter}</div>
    <div><strong>{LABELS['capital_mode']}:</strong> {capital_mode}</div>
    <div><strong>{LABELS['init_cash_usdt']}:</strong> {init_cash_usdt}</div>
    <div><strong>{LABELS['order_size_pct']}:</strong> {order_size_pct}</div>
    <div><strong>{LABELS['max_concurrent_positions']}:</strong> {max_concurrent_positions}</div>
    <div><strong>{LABELS['wf_train_days']}:</strong> {wf_train_days}</div>
    <div><strong>{LABELS['wf_test_days']}:</strong> {wf_test_days}</div>
    <div><strong>{LABELS['wf_step_days']}:</strong> {wf_step_days}</div>
    <div><strong>{LABELS['wf_segments']}:</strong> {len(wf_slices)}</div>
    <div><strong>{LABELS['base_symbol']}:</strong> {base_symbol}</div>
    <div><strong>{LABELS['trade_symbols']}:</strong> {', '.join(trade_symbols)}</div>
  </div>

  <h2>{LABELS['summary_title']}</h2>
  {summary_html}

  <h2>{LABELS['params_title']}</h2>
  {report_params_html}

  <h2>{LABELS['oos_summary_title']}</h2>
  {oos_summary_html}

  <h2>{LABELS['top_title']}</h2>
  {top10_html}

  <h2>{LABELS['history_title']}</h2>

  <h2>{LABELS['leaderboard_title']}</h2>
  {lb_best_html}

  <h2>{LABELS['recent_runs_title']}</h2>
  {lb_recent_html}

  <h2>{LABELS['chart_title']} ({plot_symbol})</h2>
  {plot_html}
</body>
</html>
"""

    with open(report_path_latest, "w", encoding="utf-8") as f:
        f.write(html)
    with open(report_path_run, "w", encoding="utf-8") as f:
        f.write(html)

    emit_progress(stage="complete", force=True)

    print("combo_summary", combo_path)
    print("per_symbol_summary", per_symbol_path)
    print("top10", top10_path)
    print("leaderboard", leaderboard_path)
    print("report_latest", report_path_latest)
    print("report_run", report_path_run)


if __name__ == "__main__":
    main()

