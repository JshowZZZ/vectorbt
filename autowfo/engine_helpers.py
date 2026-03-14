"""Engine helpers: config, schema, utility, progress/lifecycle."""

import copy
import itertools
import json
import os
import time

import numpy as np
import pandas as pd


DEFAULT_CONFIG = {
    "search_mode": "combo",
    "combo_sizes": [2, 3, 4],
    "combo_seed": 42,
    "max_workers": 1,
    "combo_segment_start": 0,
    "combo_segment_size": None,
    "timeframes": [{"timeframe": "3m", "days": 60}],
    "wf_train_days": 120,
    "wf_test_days": 30,
    "wf_step_days": 30,
    "wf_valid_days": 0,
    "wf_mode": "anchored",
    "min_avg_daily_trades_target": 5.0,
    "min_oos_trades_target": 1,
    "top_n_refine": 50,
    "ranking": {
        "mode": "composite",
        "low_trade_threshold": 30.0,
        "weights": {
            "return": 1.0,
            "stability": 1.0,
            "risk_adjust": 0.5,
            "drawdown_penalty": 1.0,
            "low_sample_penalty": 1.0,
        },
    },
    "combo_group_fields": ["indicator_list", "regime_name", "vol_mode"],
    "trade_symbols": ["ETH/BTC", "BNB/BTC", "SOL/BTC"],
    "capital_mode": "shared",
    "init_cash_usdt": 1000,
    "order_size_pct": 0.5,
    "max_concurrent_positions": 2,
    "slippage_bps": 2.0,
    "spread_bps": 2.0,
    "funding_rate_daily": 0.0,
    # AWF-108: checkpoint/progress tunables
    "checkpoint_every_n": 200,
    "progress_every_n": 25,
}


def _build_sweep_schema_fields(*, artifact_row_metadata_fields):
    combo_key_fields = [
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
        "wf_valid_days",
        "wf_mode",
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

    combo_result_fields = combo_key_fields + list(artifact_row_metadata_fields) + [
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
        "oos_return_std",
        "oos_positive_segment_ratio",
        "oos_sharpe_like",
        "oos_low_trade_segment_ratio",
        "oos_low_trade_penalty",
        "oos_segments",
    ]

    symbol_result_fields = [
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
        "wf_valid_days",
        "wf_mode",
        "data_start",
        "data_end",
        *list(artifact_row_metadata_fields),
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

    strict_config_fields = [
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
        "wf_valid_days",
        "wf_mode",
        "data_start",
        "data_end",
    ]

    return {
        "combo_key_fields": combo_key_fields,
        "combo_result_fields": combo_result_fields,
        "symbol_result_fields": symbol_result_fields,
        "strict_config_fields": strict_config_fields,
    }


def _load_runtime_config(out_dir, env_mode=None, config_path=None):
    config = copy.deepcopy(DEFAULT_CONFIG)
    resolved_config_path = config_path or os.path.join(out_dir, "sweep_config.json")
    if os.path.exists(resolved_config_path):
        try:
            # Accept UTF-8 files with or without BOM to avoid silent fallback to defaults.
            with open(resolved_config_path, "r", encoding="utf-8-sig") as f:
                override = json.load(f)
            for key, value in override.items():
                if isinstance(value, dict) and isinstance(config.get(key), dict):
                    merged = config[key].copy()
                    merged.update(value)
                    config[key] = merged
                else:
                    config[key] = value
        except Exception as exc:
            print(f"[warn] failed to load sweep_config.json: {exc}")
    if env_mode:
        config["search_mode"] = env_mode
    return config


def _ensure_control_file(control_path):
    if os.path.exists(control_path):
        return
    with open(control_path, "w", encoding="utf-8") as f:
        json.dump({"paused": False}, f, ensure_ascii=False, indent=2)


def _read_control(control_path):
    try:
        with open(control_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"paused": False}


def _normalize_search_mode(mode):
    search_mode = str(mode or "combo").lower()
    if search_mode not in {"combo", "refine"}:
        return "combo"
    return search_mode


def _normalize_trade_symbols(trade_symbols, base_symbol, default_trade_symbols):
    values = trade_symbols
    if isinstance(values, str):
        values = [s.strip() for s in values.split(",") if s.strip()]
    values = [s.strip() for s in values if s and str(s).strip()]
    values = [s for s in values if s != base_symbol]
    if not values:
        return list(default_trade_symbols)
    return values


def _safe_positive_config_int(config, name, default):
    try:
        value = int(config.get(name, default))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _safe_int(value, default):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return default
    return int(value)


def _safe_float(value, default):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return default
    return float(value)


def _has_all_config_fields(values, strict_fields):
    for field in strict_fields:
        val = values.get(field)
        if val is None:
            return False
        if isinstance(val, float) and np.isnan(val):
            return False
        if isinstance(val, str) and not val:
            return False
    return True


def _build_sweep_adapter_functions(
    *,
    combo_key_fields,
    strict_config_fields,
    indicator_meta,
    filter_name_map,
    regime_name_map,
    regime_type_map,
    combo_key_from_dict_impl_fn,
    indicator_combo_label_impl_fn,
    format_indicator_list_impl_fn,
    df_to_html_impl_fn,
):
    combo_key_fields_local = list(combo_key_fields)
    strict_config_fields_local = list(strict_config_fields)

    def _combo_key_from_dict(values):
        return combo_key_from_dict_impl_fn(values, combo_key_fields_local)

    def _indicator_combo_label(combo_keys):
        return indicator_combo_label_impl_fn(combo_keys, indicator_meta)

    def _format_indicator_list(value):
        return format_indicator_list_impl_fn(value, indicator_meta)

    def _df_to_html(df, columns, label_map):
        return df_to_html_impl_fn(
            df,
            columns,
            label_map,
            filter_name_map,
            regime_name_map,
            regime_type_map,
            format_indicator_list_fn=_format_indicator_list,
        )

    def _has_all_config_fields_for_sweep(values):
        return _has_all_config_fields(values, strict_config_fields_local)

    return {
        "combo_key_from_dict_fn": _combo_key_from_dict,
        "indicator_combo_label_fn": _indicator_combo_label,
        "format_indicator_list_fn": _format_indicator_list,
        "df_to_html_fn": _df_to_html,
        "has_all_config_fields_fn": _has_all_config_fields_for_sweep,
    }


def _resolve_runtime_settings(
    default_config,
    *,
    base_symbol,
    default_trade_symbols,
    normalize_split_mode_fn,
    resolve_ranking_config_fn,
):
    search_mode = _normalize_search_mode(default_config.get("search_mode", "combo"))
    timeframe_configs = default_config["timeframes"]
    combo_sizes = default_config["combo_sizes"]
    combo_seed = int(default_config.get("combo_seed", 42))
    max_workers = max(int(default_config.get("max_workers", 1) or 1), 1)
    combo_segment_start = int(default_config.get("combo_segment_start", 0))
    combo_segment_size = default_config.get("combo_segment_size")
    combo_group_fields = default_config.get(
        "combo_group_fields", ["indicator_list", "regime_name", "vol_mode"]
    )
    trade_symbols = _normalize_trade_symbols(
        default_config.get("trade_symbols", default_trade_symbols),
        base_symbol=base_symbol,
        default_trade_symbols=default_trade_symbols,
    )

    wf_train_days = _safe_positive_config_int(default_config, "wf_train_days", 120)
    wf_test_days = _safe_positive_config_int(default_config, "wf_test_days", 30)
    wf_step_days = _safe_positive_config_int(default_config, "wf_step_days", 30)
    wf_valid_days = int(default_config.get("wf_valid_days", 0) or 0)
    if wf_valid_days < 0:
        wf_valid_days = 0
    wf_mode = normalize_split_mode_fn(default_config.get("wf_mode", "anchored"))

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

    min_avg_daily_trades_target = float(
        default_config.get("min_avg_daily_trades_target", 5.0) or 5.0
    )
    if min_avg_daily_trades_target < 0:
        min_avg_daily_trades_target = 0.0
    min_oos_trades_target = int(default_config.get("min_oos_trades_target", 1) or 1)
    if min_oos_trades_target < 0:
        min_oos_trades_target = 0
    top_n_fine = int(default_config.get("top_n_refine", 50))
    ranking_config = resolve_ranking_config_fn(default_config.get("ranking"))
    pruning_config = default_config.get("pruning", None)

    return {
        "search_mode": search_mode,
        "timeframe_configs": timeframe_configs,
        "combo_sizes": combo_sizes,
        "combo_seed": combo_seed,
        "max_workers": max_workers,
        "combo_segment_start": combo_segment_start,
        "combo_segment_size": combo_segment_size,
        "combo_group_fields": combo_group_fields,
        "trade_symbols": trade_symbols,
        "wf_train_days": wf_train_days,
        "wf_test_days": wf_test_days,
        "wf_step_days": wf_step_days,
        "wf_valid_days": wf_valid_days,
        "wf_mode": wf_mode,
        "slippage_bps": slippage_bps,
        "spread_bps": spread_bps,
        "funding_rate_daily": funding_rate_daily,
        "capital_mode": capital_mode,
        "init_cash_usdt": init_cash_usdt,
        "order_size_pct": order_size_pct,
        "max_concurrent_positions": max_concurrent_positions,
        "min_avg_daily_trades_target": min_avg_daily_trades_target,
        "min_oos_trades_target": min_oos_trades_target,
        "top_n_fine": top_n_fine,
        "ranking_config": ranking_config,
        "pruning_config": pruning_config,
    }


def _build_ma_pairs(base_ma_pairs):
    return sorted(
        {
            (fast_val, slow_val)
            for base_fast, base_slow in base_ma_pairs
            for fast_val in (base_fast - 5, base_fast, base_fast + 5)
            for slow_val in (base_slow - 5, base_slow, base_slow + 5)
            if fast_val > 1 and slow_val > fast_val
        }
    )


def _build_regime_variants(rsi_revert_pairs):
    regime_variants = [
        {"regime_name": "trend_high", "regime_type": "trend", "vol_mode": "high", "rsi_pair": None},
        {"regime_name": "trend_low", "regime_type": "trend", "vol_mode": "low", "rsi_pair": None},
        {"regime_name": "trend_any", "regime_type": "trend", "vol_mode": "any", "rsi_pair": None},
    ]
    for rsi_pair in rsi_revert_pairs:
        regime_variants.append(
            {
                "regime_name": "rsi_revert_low",
                "regime_type": "rsi_revert",
                "vol_mode": "low",
                "rsi_pair": rsi_pair,
            }
        )
    for rsi_pair in rsi_revert_pairs:
        regime_variants.append(
            {
                "regime_name": "rsi_revert_high",
                "regime_type": "rsi_revert",
                "vol_mode": "high",
                "rsi_pair": rsi_pair,
            }
        )
    regime_variants.append(
        {
            "regime_name": "bb_revert_low",
            "regime_type": "bb_revert",
            "vol_mode": "low",
            "rsi_pair": None,
        }
    )
    regime_variants.append(
        {
            "regime_name": "bb_revert_high",
            "regime_type": "bb_revert",
            "vol_mode": "high",
            "rsi_pair": None,
        }
    )
    regime_variants.append(
        {
            "regime_name": "bb_breakout_high",
            "regime_type": "bb_breakout",
            "vol_mode": "high",
            "rsi_pair": None,
        }
    )
    return regime_variants


def _count_coarse_combos(
    regime_variants,
    indicator_param_options,
    combo_keys_all,
    mom_lookbacks,
    vol_lookbacks,
    vol_zs,
    trade_mom_lookbacks,
    tp_stops,
    sl_stops,
    max_holds,
):
    count = 0
    indicator_param_counts = {
        combo: int(np.prod([len(indicator_param_options.get(key, [{}])) for key in combo]))
        for combo in combo_keys_all
    }
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
                                    for combo in combo_keys_all:
                                        count += indicator_param_counts.get(combo, 1)
    return count


def _apply_quality_filters(df, min_avg_daily_trades_target, min_oos_trades_target):
    filtered = df.copy()
    if "avg_daily_trades" in filtered.columns:
        filtered = filtered[filtered["avg_daily_trades"] >= min_avg_daily_trades_target].copy()
    if not filtered.empty:
        if "oos_avg_total_return_pct" in filtered.columns:
            mask = (
                (filtered["oos_avg_total_return_pct"] > 0)
                & (filtered["oos_avg_avg_trade_pct"] > 0)
                & (filtered["oos_min_total_trades"] >= min_oos_trades_target)
            )
            if mask.any():
                filtered = filtered[mask].copy()
    return filtered


def _build_combo_keys(indicator_keys, combo_sizes, combo_seed, combo_segment_start=0, combo_segment_size=None):
    combo_keys_all = []
    for size in combo_sizes:
        combo_keys_all.extend(list(itertools.combinations(indicator_keys, size)))
    rng = np.random.default_rng(int(combo_seed))
    rng.shuffle(combo_keys_all)
    if combo_segment_size:
        start = int(combo_segment_start)
        end = start + int(combo_segment_size)
        combo_keys_all = combo_keys_all[start:end]
    return combo_keys_all


def _normalize_existing_results(existing_combo_df, existing_symbol_df, combo_key_fields):
    combo_df = existing_combo_df.copy()
    symbol_df = existing_symbol_df.copy()
    if "timeframe" not in combo_df.columns and not combo_df.empty:
        combo_df["timeframe"] = "1h"
    if "data_days" not in combo_df.columns and not combo_df.empty:
        combo_df["data_days"] = np.nan
    if "timeframe" not in symbol_df.columns and not symbol_df.empty:
        symbol_df["timeframe"] = "1h"
    if "data_days" not in symbol_df.columns and not symbol_df.empty:
        symbol_df["data_days"] = np.nan
    if not combo_df.empty:
        for field in combo_key_fields:
            if field not in combo_df.columns:
                combo_df[field] = np.nan
    return combo_df, symbol_df


def _strip_data_range_from_combo_key(combo_key):
    """Return combo_key with data_start/data_end parts removed.

    Used for cross-run seen_keys matching: OHLCV auto-refresh advances
    data_end on every run, so we strip data-range fields from the key
    before comparing against previously evaluated combos.
    """
    return "|".join(
        part for part in combo_key.split("|")
        if not (part.startswith("data_start=") or part.startswith("data_end="))
    )


# AWF-106b: Default values for combo_key fields that were added to the schema
# after significant CSV history was accumulated. Used by _build_seen_keys to
# fill None/NaN values so old rows still produce valid, matchable seen keys.
_SEEN_KEY_NULL_FIELD_DEFAULTS = {
    k: v
    for k, v in DEFAULT_CONFIG.items()
    if isinstance(v, (str, int, float)) and not isinstance(v, bool)
}


def _build_seen_keys(existing_combo_df, has_all_config_fields_fn, combo_key_from_dict_fn, null_fill_overrides=None):
    """Build seen-key sets from an existing combo DataFrame.

    Returns a dict with two sets:
      ``full``     -- keys that include all fields (including data_start/data_end)
      ``stripped`` -- keys with data_start/data_end removed, used for
                      cross-run skip decisions so that routine OHLCV refresh
                      (which advances data_end by N candles) does not
                      invalidate all seen_keys and force a full re-evaluation.

    Parameters
    ----------
    null_fill_overrides : dict, optional
        Extra key?alue pairs merged on top of ``_SEEN_KEY_NULL_FIELD_DEFAULTS``
        before filling NaN/None cells.  Use this to supply the *current*
        runtime config values (e.g. ``capital_mode``) so that rows written
        before a field was persisted to CSV still produce keys that match
        the runtime-generated keys.
    """
    if existing_combo_df.empty:
        return {"full": set(), "stripped": set()}
    # AWF-106d: merge caller-supplied overrides on top of built-in defaults so
    # that fields not yet written to CSV (e.g. capital_mode) are filled with
    # the *current* runtime value rather than a hardcoded default.
    effective_defaults = dict(_SEEN_KEY_NULL_FIELD_DEFAULTS)
    if null_fill_overrides:
        effective_defaults.update(null_fill_overrides)
    full_set = set()
    stripped_set = set()
    # AWF-108(b): use to_dict(orient='records') ??5-10x faster than iterrows()
    for row_dict in existing_combo_df.to_dict(orient="records"):
        # AWF-106b: fill None/NaN values with defaults so that rows written
        # before a new combo_key field was added (e.g., capital_mode,
        # wf_valid_days, wf_mode) still pass has_all_config_fields and produce
        # correct, matchable seen keys.
        filled = dict(row_dict)
        for field, default in effective_defaults.items():
            val = filled.get(field)
            if val is None or (isinstance(val, float) and np.isnan(val)):
                filled[field] = default
        if not has_all_config_fields_fn(filled):
            continue
        full_key = combo_key_from_dict_fn(filled)
        full_set.add(full_key)
        stripped_set.add(_strip_data_range_from_combo_key(full_key))
    return {"full": full_set, "stripped": stripped_set}


def _fallback_activity_filter(combo_df_current, min_avg_daily_trades_target, apply_quality_filters_fn):
    min_avg_daily_trades_filter = min_avg_daily_trades_target
    filtered = apply_quality_filters_fn(combo_df_current)
    has_avg_daily_trades = "avg_daily_trades" in combo_df_current.columns
    if filtered.empty and has_avg_daily_trades:
        filtered = combo_df_current[
            combo_df_current["avg_daily_trades"] >= min_avg_daily_trades_filter
        ].copy()
    if filtered.empty and has_avg_daily_trades:
        min_avg_daily_trades_filter = 2
        filtered = combo_df_current[
            combo_df_current["avg_daily_trades"] >= min_avg_daily_trades_filter
        ].copy()
    if filtered.empty:
        min_avg_daily_trades_filter = 0
        filtered = combo_df_current.copy()
    return filtered, min_avg_daily_trades_filter


def _should_emit_progress(
    done,
    force,
    last_progress_ts,
    now,
    progress_every,
    progress_min_seconds,
):
    if force:
        return True
    if done <= 0:
        return True
    if done % progress_every == 0:
        return True
    if (now - last_progress_ts) >= progress_min_seconds:
        return True
    return False


def _build_progress_payload(
    run_id,
    stage,
    total,
    done,
    skipped,
    elapsed_seconds,
    updated,
    format_duration_fn,
):
    eta_seconds = (elapsed_seconds / done * (total - done)) if done > 0 else None
    return {
        "run_id": run_id,
        "stage": stage,
        "total": total,
        "done": done,
        "remaining": max(total - done, 0),
        "skipped": skipped,
        "percent": round(done / total * 100, 2) if total else 0,
        "elapsed": format_duration_fn(elapsed_seconds),
        "eta": format_duration_fn(eta_seconds) if eta_seconds is not None else "",
        "updated": updated,
    }


def _should_checkpoint(
    done,
    force,
    last_checkpoint_done,
    last_checkpoint_ts,
    now,
    checkpoint_every,
    checkpoint_min_seconds,
):
    if force:
        return True
    if done - last_checkpoint_done >= checkpoint_every:
        return True
    if (now - last_checkpoint_ts) >= checkpoint_min_seconds:
        return True
    return False


def _checkpoint_pending_rows(
    *,
    done,
    force,
    last_checkpoint_done,
    last_checkpoint_ts,
    now,
    checkpoint_every,
    checkpoint_min_seconds,
    pending_combo_rows,
    pending_symbol_rows,
    combo_path,
    per_symbol_path,
    db_path,
    combo_result_fields,
    symbol_result_fields,
    should_checkpoint_fn,
    append_rows_fn,
    append_db_rows_fn,
    normalize_key_value_fn,
    warn_fn=print,
):
    if not pending_combo_rows and not pending_symbol_rows:
        return {
            "checkpointed": False,
            "last_checkpoint_done": last_checkpoint_done,
            "last_checkpoint_ts": last_checkpoint_ts,
        }

    if not should_checkpoint_fn(
        done=done,
        force=force,
        last_checkpoint_done=last_checkpoint_done,
        last_checkpoint_ts=last_checkpoint_ts,
        now=now,
        checkpoint_every=checkpoint_every,
        checkpoint_min_seconds=checkpoint_min_seconds,
    ):
        return {
            "checkpointed": False,
            "last_checkpoint_done": last_checkpoint_done,
            "last_checkpoint_ts": last_checkpoint_ts,
        }

    append_rows_fn(combo_path, pending_combo_rows, combo_result_fields)
    append_rows_fn(per_symbol_path, pending_symbol_rows, symbol_result_fields)
    try:
        append_db_rows_fn(
            db_path,
            "combo_summary",
            pending_combo_rows,
            combo_result_fields,
            normalize_key_value_fn=normalize_key_value_fn,
        )
        append_db_rows_fn(
            db_path,
            "symbol_summary",
            pending_symbol_rows,
            symbol_result_fields,
            normalize_key_value_fn=normalize_key_value_fn,
        )
    except Exception as exc:
        warn_fn(f"[warn] db write failed: {exc}")
    pending_combo_rows.clear()
    pending_symbol_rows.clear()

    return {
        "checkpointed": True,
        "last_checkpoint_done": done,
        "last_checkpoint_ts": now,
    }


def _build_run_lifecycle_callbacks(
    *,
    total_combos,
    run_id,
    status_json_path,
    status_html_path,
    labels,
    control_path,
    combo_path,
    per_symbol_path,
    db_path,
    combo_result_fields,
    symbol_result_fields,
    pending_combo_rows,
    pending_symbol_rows,
    format_duration_fn,
    write_status_fn,
    append_rows_fn,
    append_db_rows_fn,
    normalize_key_value_fn,
    now_fn,
    sleep_fn,
    build_updated_timestamp_fn,
    progress_every=25,
    progress_min_seconds=5,
    checkpoint_every=200,
    checkpoint_min_seconds=30,
    should_emit_progress_fn=_should_emit_progress,
    build_progress_payload_fn=_build_progress_payload,
    read_control_fn=_read_control,
    should_checkpoint_fn=_should_checkpoint,
    checkpoint_pending_rows_fn=_checkpoint_pending_rows,
    print_fn=print,
):
    state = {
        "total_combos": total_combos,
        "done": 0,
        "skipped": 0,
        "start_ts": now_fn(),
        "last_progress_ts": 0.0,
        "last_checkpoint_ts": now_fn(),
        "last_checkpoint_done": 0,
    }

    def emit_progress(stage="running", force=False):
        now = now_fn()
        if not should_emit_progress_fn(
            done=state["done"],
            force=force,
            last_progress_ts=state["last_progress_ts"],
            now=now,
            progress_every=progress_every,
            progress_min_seconds=progress_min_seconds,
        ):
            return
        payload = build_progress_payload_fn(
            run_id=run_id,
            stage=stage,
            total=state["total_combos"],
            done=state["done"],
            skipped=state["skipped"],
            elapsed_seconds=now - state["start_ts"],
            updated=build_updated_timestamp_fn(),
            format_duration_fn=format_duration_fn,
        )
        write_status_fn(status_json_path, status_html_path, payload, labels)
        print_fn(
            f"[{stage}] {state['done']}/{state['total_combos']} ({payload['percent']}%) "
            f"skipped {state['skipped']} elapsed {payload['elapsed']} eta {payload['eta']}",
            flush=True,
        )
        state["last_progress_ts"] = now

    def advance_progress_counts(done_delta, skipped_delta):
        state["done"] += done_delta
        state["skipped"] += skipped_delta

    def wait_if_paused(stage_label):
        while True:
            control = read_control_fn(control_path)
            if not control.get("paused"):
                return
            emit_progress(stage=f"{stage_label} paused", force=True)
            sleep_fn(2)

    def checkpoint(force=False):
        checkpoint_result = checkpoint_pending_rows_fn(
            done=state["done"],
            force=force,
            last_checkpoint_done=state["last_checkpoint_done"],
            last_checkpoint_ts=state["last_checkpoint_ts"],
            now=now_fn(),
            checkpoint_every=checkpoint_every,
            checkpoint_min_seconds=checkpoint_min_seconds,
            pending_combo_rows=pending_combo_rows,
            pending_symbol_rows=pending_symbol_rows,
            combo_path=combo_path,
            per_symbol_path=per_symbol_path,
            db_path=db_path,
            combo_result_fields=combo_result_fields,
            symbol_result_fields=symbol_result_fields,
            should_checkpoint_fn=should_checkpoint_fn,
            append_rows_fn=append_rows_fn,
            append_db_rows_fn=append_db_rows_fn,
            normalize_key_value_fn=normalize_key_value_fn,
        )
        state["last_checkpoint_done"] = checkpoint_result["last_checkpoint_done"]
        state["last_checkpoint_ts"] = checkpoint_result["last_checkpoint_ts"]
        return checkpoint_result

    def get_done():
        return state["done"]

    def get_total_combos():
        return state["total_combos"]

    def set_total_combos(value):
        state["total_combos"] = value

    return {
        "emit_progress_fn": emit_progress,
        "advance_progress_counts_fn": advance_progress_counts,
        "wait_if_paused_fn": wait_if_paused,
        "checkpoint_fn": checkpoint,
        "get_done_fn": get_done,
        "get_total_combos_fn": get_total_combos,
        "set_total_combos_fn": set_total_combos,
        "state": state,
    }

