"""Engine/orchestration helpers extracted from run_btc_regime_sweep monolith."""

import copy
import itertools
import json
import os

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


def _load_runtime_config(out_dir, env_mode=None):
    config = copy.deepcopy(DEFAULT_CONFIG)
    config_path = os.path.join(out_dir, "sweep_config.json")
    if os.path.exists(config_path):
        try:
            # Accept UTF-8 files with or without BOM to avoid silent fallback to defaults.
            with open(config_path, "r", encoding="utf-8-sig") as f:
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


def _build_seen_keys(existing_combo_df, has_all_config_fields_fn, combo_key_from_dict_fn):
    if existing_combo_df.empty:
        return set()
    seen_keys = set()
    for _, row in existing_combo_df.iterrows():
        row_dict = row.to_dict()
        if not has_all_config_fields_fn(row_dict):
            continue
        seen_keys.add(combo_key_from_dict_fn(row_dict))
    return seen_keys


def _iter_coarse_plan(
    regime_variants,
    mom_lookbacks,
    vol_lookbacks,
    vol_zs,
    trade_mom_lookbacks,
    tp_stops,
    sl_stops,
    max_holds,
    combo_keys_all,
    iter_indicator_param_combos_fn,
    indicator_param_options,
):
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
                                        for combo_params in iter_indicator_param_combos_fn(
                                            combo_keys, indicator_param_options
                                        ):
                                            yield (
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
                                            )


def _default_refine_steps():
    return {
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


def _build_refine_targets(
    top_candidates,
    tp_stops,
    sl_stops,
    indicator_defaults,
    refine_steps,
    expand_float_fn,
    safe_float_fn,
    refine_indicator_params_fn,
):
    fine_total = 0
    fine_targets = []
    for _, row in top_candidates.iterrows():
        indicator_list = row.get("indicator_list")
        if not indicator_list:
            continue
        indicator_combo = tuple([v for v in str(indicator_list).split(",") if v])
        if not indicator_combo:
            continue
        base_tp = safe_float_fn(row.get("tp_stop"), tp_stops[0])
        base_sl = safe_float_fn(row.get("sl_stop"), sl_stops[0])
        tp_candidates = expand_float_fn(base_tp, refine_steps["tp_stop"], min_value=0.0001)
        sl_candidates = expand_float_fn(base_sl, refine_steps["sl_stop"], min_value=0.0001)
        param_options = {
            key: refine_indicator_params_fn(key, row, refine_steps, indicator_defaults)
            for key in indicator_combo
        }
        indicator_count = int(np.prod([len(param_options.get(key, [{}])) for key in indicator_combo]))
        fine_total += indicator_count * max(len(tp_candidates), 1) * max(len(sl_candidates), 1)
        fine_targets.append((row, indicator_combo, tp_candidates, sl_candidates, param_options))
    return fine_total, fine_targets


def _run_search_for_timeframe(
    search_mode,
    stage_prefix,
    timeframe,
    regime_variants,
    regime_lookup,
    mom_lookbacks,
    vol_lookbacks,
    vol_zs,
    trade_mom_lookbacks,
    tp_stops,
    sl_stops,
    max_holds,
    combo_keys_all,
    iter_indicator_param_combos_fn,
    indicator_param_options,
    eval_combo_fn,
    existing_combo_df,
    apply_quality_filters_fn,
    sort_by_score_fn,
    combo_group_fields,
    top_n_fine,
    min_avg_daily_trades_target,
    indicator_defaults,
    expand_float_fn,
    safe_float_fn,
    refine_indicator_params_fn,
    safe_int_fn,
    on_refine_plan_fn=None,
):
    if search_mode == "combo":
        for (
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
        ) in _iter_coarse_plan(
            regime_variants=regime_variants,
            mom_lookbacks=mom_lookbacks,
            vol_lookbacks=vol_lookbacks,
            vol_zs=vol_zs,
            trade_mom_lookbacks=trade_mom_lookbacks,
            tp_stops=tp_stops,
            sl_stops=sl_stops,
            max_holds=max_holds,
            combo_keys_all=combo_keys_all,
            iter_indicator_param_combos_fn=iter_indicator_param_combos_fn,
            indicator_param_options=indicator_param_options,
        ):
            eval_combo_fn(
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
        return 0

    if search_mode != "refine":
        return 0

    tf_existing = (
        existing_combo_df[existing_combo_df["timeframe"] == timeframe]
        if not existing_combo_df.empty
        else pd.DataFrame()
    )
    tf_combo_df = tf_existing.copy()
    # Reuse the same activity fallback path as finalize stage so refine does not
    # silently collapse to 0 candidates on low-frequency windows.
    tf_filtered, _ = _fallback_activity_filter(
        combo_df_current=tf_combo_df,
        min_avg_daily_trades_target=min_avg_daily_trades_target,
        apply_quality_filters_fn=apply_quality_filters_fn,
    )
    tf_sorted, _ = sort_by_score_fn(tf_filtered, tie_break_avg_hold=True)
    group_fields = [field for field in combo_group_fields if field in tf_sorted.columns]
    if group_fields:
        tf_sorted = tf_sorted.drop_duplicates(subset=group_fields)
    top_candidates = tf_sorted.head(top_n_fine)

    refine_steps = _default_refine_steps()
    fine_total, fine_targets = _build_refine_targets(
        top_candidates=top_candidates,
        tp_stops=tp_stops,
        sl_stops=sl_stops,
        indicator_defaults=indicator_defaults,
        refine_steps=refine_steps,
        expand_float_fn=expand_float_fn,
        safe_float_fn=safe_float_fn,
        refine_indicator_params_fn=refine_indicator_params_fn,
    )
    if fine_total and on_refine_plan_fn is not None:
        on_refine_plan_fn(fine_total, f"{stage_prefix} refine")

    for row, indicator_combo, tp_candidates, sl_candidates, param_options in fine_targets:
        regime = regime_lookup.get(row.get("regime_name"), regime_variants[0])
        vol_lookback = safe_int_fn(row.get("vol_lookback"), vol_lookbacks[0])
        vol_z = safe_float_fn(row.get("vol_z"), vol_zs[0])
        mom_lookback = safe_int_fn(row.get("mom_lookback"), mom_lookbacks[0])
        trade_mom_lookback = safe_int_fn(row.get("trade_mom_lookback"), trade_mom_lookbacks[0])
        max_hold = safe_int_fn(row.get("max_hold"), max_holds[0])

        for tp_stop in tp_candidates:
            for sl_stop in sl_candidates:
                for combo_params in iter_indicator_param_combos_fn(indicator_combo, param_options):
                    eval_combo_fn(
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

    return fine_total


def _run_parallel_combo_search_for_timeframe(
    *,
    stage,
    regime_variants,
    mom_lookbacks,
    vol_lookbacks,
    vol_zs,
    trade_mom_lookbacks,
    tp_stops,
    sl_stops,
    max_holds,
    combo_keys_all,
    iter_indicator_param_combos_fn,
    indicator_param_options,
    build_combo_task_fn,
    seen_keys,
    runtime_eval,
    max_workers,
    run_combo_tasks_fn,
    append_eval_result_fn,
    emit_progress_fn,
    checkpoint_fn,
    on_progress_tick_fn=None,
):
    done = 0
    skipped = 0
    planned_keys = set()
    combo_tasks = []

    for (
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
    ) in _iter_coarse_plan(
        regime_variants=regime_variants,
        mom_lookbacks=mom_lookbacks,
        vol_lookbacks=vol_lookbacks,
        vol_zs=vol_zs,
        trade_mom_lookbacks=trade_mom_lookbacks,
        tp_stops=tp_stops,
        sl_stops=sl_stops,
        max_holds=max_holds,
        combo_keys_all=combo_keys_all,
        iter_indicator_param_combos_fn=iter_indicator_param_combos_fn,
        indicator_param_options=indicator_param_options,
    ):
        combo_key, task_payload = build_combo_task_fn(
            regime=regime,
            indicator_combo=combo_keys,
            combo_params=combo_params,
            vol_lookback=vol_lookback,
            vol_z=vol_z,
            mom_lookback=mom_lookback,
            trade_mom_lookback=trade_mom_lookback,
            tp_stop=tp_stop,
            sl_stop=sl_stop,
            max_hold=max_hold,
        )
        if combo_key in seen_keys or combo_key in planned_keys:
            skipped += 1
            done += 1
            if on_progress_tick_fn is not None:
                on_progress_tick_fn(done_delta=1, skipped_delta=1)
            emit_progress_fn(stage=stage)
            continue
        planned_keys.add(combo_key)
        combo_tasks.append(task_payload)

    for task_payload, result in zip(
        combo_tasks,
        run_combo_tasks_fn(combo_tasks, runtime_eval, max_workers=max_workers),
    ):
        append_eval_result_fn(result, task_payload)
        seen_keys.add(task_payload["combo_key"])
        done += 1
        if on_progress_tick_fn is not None:
            on_progress_tick_fn(done_delta=1, skipped_delta=0)
        emit_progress_fn(stage=stage)
        checkpoint_fn()

    return {"done": done, "skipped": skipped}


def _run_combo_eval_step(
    *,
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
    wait_if_paused_fn,
    build_combo_task_fn,
    seen_keys,
    evaluate_combo_task_fn,
    runtime_eval,
    append_eval_result_fn,
    emit_progress_fn,
    checkpoint_fn,
    on_progress_tick_fn=None,
):
    wait_if_paused_fn(stage)
    combo_key, task_payload = build_combo_task_fn(
        regime=regime,
        indicator_combo=indicator_combo,
        combo_params=combo_params,
        vol_lookback=vol_lookback,
        vol_z=vol_z,
        mom_lookback=mom_lookback,
        trade_mom_lookback=trade_mom_lookback,
        tp_stop=tp_stop,
        sl_stop=sl_stop,
        max_hold=max_hold,
    )
    if combo_key in seen_keys:
        if on_progress_tick_fn is not None:
            on_progress_tick_fn(done_delta=1, skipped_delta=1)
        emit_progress_fn(stage=stage)
        return {"skipped": True, "evaluated": False}

    result = evaluate_combo_task_fn(task_payload, runtime_eval)
    append_eval_result_fn(result, task_payload)
    seen_keys.add(combo_key)
    if on_progress_tick_fn is not None:
        on_progress_tick_fn(done_delta=1, skipped_delta=0)
    emit_progress_fn(stage=stage)
    checkpoint_fn()
    return {"skipped": False, "evaluated": True}


def _prepare_timeframe_runtime_or_skip(
    *,
    prepare_timeframe_runtime_fn,
    prepare_kwargs,
    search_mode,
    total_combos,
    done,
    count_coarse_combos_fn,
    stage_prefix,
    timeframe,
    emit_progress_fn,
    warn_fn=print,
):
    try:
        timeframe_runtime = prepare_timeframe_runtime_fn(**prepare_kwargs)
    except Exception as exc:
        adjusted_total_combos = total_combos
        if search_mode == "combo":
            adjusted_total_combos = max(total_combos - count_coarse_combos_fn(), done)
        emit_progress_fn(stage=f"{stage_prefix} skipped", force=True)
        warn_fn(f"[warn] timeframe {timeframe} skipped: {exc}")
        return {
            "ok": False,
            "timeframe_runtime": None,
            "total_combos": adjusted_total_combos,
        }
    return {
        "ok": True,
        "timeframe_runtime": timeframe_runtime,
        "total_combos": total_combos,
    }


def _build_prepare_timeframe_runtime_kwargs(
    *,
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
    wf_train_days,
    wf_test_days,
    wf_step_days,
    wf_mode,
    fees,
    slippage_bps,
    spread_bps,
    funding_rate_daily,
    order_size_pct,
    max_concurrent_positions,
    config_sha256,
    bar_hours,
    prepare_timeframe_context_fn,
    build_walk_forward_windows_fn,
    compute_data_fingerprint_fn,
):
    return {
        "timeframe": timeframe,
        "data_days": data_days,
        "base_symbol": base_symbol,
        "trade_symbols": trade_symbols,
        "exchange": exchange,
        "cache_dir": cache_dir,
        "cache_format": cache_format,
        "vol_lookbacks": vol_lookbacks,
        "mom_lookbacks": mom_lookbacks,
        "trade_mom_lookbacks": trade_mom_lookbacks,
        "rsi_window": rsi_window,
        "bb_window": bb_window,
        "bb_alpha": bb_alpha,
        "atr_window": atr_window,
        "ma_pairs": ma_pairs,
        "obv_lookbacks": obv_lookbacks,
        "volume_lookbacks": volume_lookbacks,
        "roc_lookbacks": roc_lookbacks,
        "cmf_lookbacks": cmf_lookbacks,
        "mfi_window": mfi_window,
        "vroc_lookbacks": vroc_lookbacks,
        "ad_lookbacks": ad_lookbacks,
        "init_cash_usdt": init_cash_usdt,
        "capital_mode": capital_mode,
        "wf_train_days": wf_train_days,
        "wf_test_days": wf_test_days,
        "wf_step_days": wf_step_days,
        "wf_mode": wf_mode,
        "fees": fees,
        "slippage_bps": slippage_bps,
        "spread_bps": spread_bps,
        "funding_rate_daily": funding_rate_daily,
        "order_size_pct": order_size_pct,
        "max_concurrent_positions": max_concurrent_positions,
        "config_sha256": config_sha256,
        "bar_hours": bar_hours,
        "prepare_timeframe_context_fn": prepare_timeframe_context_fn,
        "build_walk_forward_windows_fn": build_walk_forward_windows_fn,
        "compute_data_fingerprint_fn": compute_data_fingerprint_fn,
    }


def _build_prepare_timeframe_runtime_context(
    *,
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
    wf_train_days,
    wf_test_days,
    wf_step_days,
    wf_mode,
    fees,
    slippage_bps,
    spread_bps,
    funding_rate_daily,
    order_size_pct,
    max_concurrent_positions,
    config_sha256,
    prepare_timeframe_context_fn,
    build_walk_forward_windows_fn,
    compute_data_fingerprint_fn,
):
    return {
        "base_symbol": base_symbol,
        "trade_symbols": trade_symbols,
        "exchange": exchange,
        "cache_dir": cache_dir,
        "cache_format": cache_format,
        "vol_lookbacks": vol_lookbacks,
        "mom_lookbacks": mom_lookbacks,
        "trade_mom_lookbacks": trade_mom_lookbacks,
        "rsi_window": rsi_window,
        "bb_window": bb_window,
        "bb_alpha": bb_alpha,
        "atr_window": atr_window,
        "ma_pairs": ma_pairs,
        "obv_lookbacks": obv_lookbacks,
        "volume_lookbacks": volume_lookbacks,
        "roc_lookbacks": roc_lookbacks,
        "cmf_lookbacks": cmf_lookbacks,
        "mfi_window": mfi_window,
        "vroc_lookbacks": vroc_lookbacks,
        "ad_lookbacks": ad_lookbacks,
        "init_cash_usdt": init_cash_usdt,
        "capital_mode": capital_mode,
        "wf_train_days": wf_train_days,
        "wf_test_days": wf_test_days,
        "wf_step_days": wf_step_days,
        "wf_mode": wf_mode,
        "fees": fees,
        "slippage_bps": slippage_bps,
        "spread_bps": spread_bps,
        "funding_rate_daily": funding_rate_daily,
        "order_size_pct": order_size_pct,
        "max_concurrent_positions": max_concurrent_positions,
        "config_sha256": config_sha256,
        "prepare_timeframe_context_fn": prepare_timeframe_context_fn,
        "build_walk_forward_windows_fn": build_walk_forward_windows_fn,
        "compute_data_fingerprint_fn": compute_data_fingerprint_fn,
    }


def _build_shared_pipeline_runtime_context(
    *,
    base_symbol,
    trade_symbols,
    exchange,
    cache_dir,
    cache_format,
    vol_lookbacks,
    vol_zs,
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
    wf_train_days,
    wf_test_days,
    wf_step_days,
    wf_mode,
    indicator_param_fields,
    fees,
    slippage_bps,
    spread_bps,
    funding_rate_daily,
    order_size_pct,
    max_concurrent_positions,
    config_sha256,
    combo_seed=None,
):
    return {
        "base_symbol": base_symbol,
        "trade_symbols": trade_symbols,
        "exchange": exchange,
        "cache_dir": cache_dir,
        "cache_format": cache_format,
        "vol_lookbacks": vol_lookbacks,
        "vol_zs": vol_zs,
        "mom_lookbacks": mom_lookbacks,
        "trade_mom_lookbacks": trade_mom_lookbacks,
        "rsi_window": rsi_window,
        "bb_window": bb_window,
        "bb_alpha": bb_alpha,
        "atr_window": atr_window,
        "ma_pairs": ma_pairs,
        "obv_lookbacks": obv_lookbacks,
        "volume_lookbacks": volume_lookbacks,
        "roc_lookbacks": roc_lookbacks,
        "cmf_lookbacks": cmf_lookbacks,
        "mfi_window": mfi_window,
        "vroc_lookbacks": vroc_lookbacks,
        "ad_lookbacks": ad_lookbacks,
        "init_cash_usdt": init_cash_usdt,
        "capital_mode": capital_mode,
        "wf_train_days": wf_train_days,
        "wf_test_days": wf_test_days,
        "wf_step_days": wf_step_days,
        "wf_mode": wf_mode,
        "indicator_param_fields": indicator_param_fields,
        "fees": fees,
        "slippage_bps": slippage_bps,
        "spread_bps": spread_bps,
        "funding_rate_daily": funding_rate_daily,
        "order_size_pct": order_size_pct,
        "max_concurrent_positions": max_concurrent_positions,
        "config_sha256": config_sha256,
        "combo_seed": combo_seed,
    }


def _build_prepare_timeframe_runtime_context_from_shared(
    *,
    shared_pipeline_runtime_context,
    prepare_timeframe_context_fn,
    build_walk_forward_windows_fn,
    compute_data_fingerprint_fn,
):
    shared = dict(shared_pipeline_runtime_context)
    return _build_prepare_timeframe_runtime_context(
        base_symbol=shared["base_symbol"],
        trade_symbols=shared["trade_symbols"],
        exchange=shared["exchange"],
        cache_dir=shared["cache_dir"],
        cache_format=shared["cache_format"],
        vol_lookbacks=shared["vol_lookbacks"],
        mom_lookbacks=shared["mom_lookbacks"],
        trade_mom_lookbacks=shared["trade_mom_lookbacks"],
        rsi_window=shared["rsi_window"],
        bb_window=shared["bb_window"],
        bb_alpha=shared["bb_alpha"],
        atr_window=shared["atr_window"],
        ma_pairs=shared["ma_pairs"],
        obv_lookbacks=shared["obv_lookbacks"],
        volume_lookbacks=shared["volume_lookbacks"],
        roc_lookbacks=shared["roc_lookbacks"],
        cmf_lookbacks=shared["cmf_lookbacks"],
        mfi_window=shared["mfi_window"],
        vroc_lookbacks=shared["vroc_lookbacks"],
        ad_lookbacks=shared["ad_lookbacks"],
        init_cash_usdt=shared["init_cash_usdt"],
        capital_mode=shared["capital_mode"],
        wf_train_days=shared["wf_train_days"],
        wf_test_days=shared["wf_test_days"],
        wf_step_days=shared["wf_step_days"],
        wf_mode=shared["wf_mode"],
        fees=shared["fees"],
        slippage_bps=shared["slippage_bps"],
        spread_bps=shared["spread_bps"],
        funding_rate_daily=shared["funding_rate_daily"],
        order_size_pct=shared["order_size_pct"],
        max_concurrent_positions=shared["max_concurrent_positions"],
        config_sha256=shared["config_sha256"],
        prepare_timeframe_context_fn=prepare_timeframe_context_fn,
        build_walk_forward_windows_fn=build_walk_forward_windows_fn,
        compute_data_fingerprint_fn=compute_data_fingerprint_fn,
    )


def _build_prepare_timeframe_runtime_kwargs_from_context(
    *,
    timeframe,
    data_days,
    bar_hours,
    prepare_timeframe_runtime_context,
):
    context = dict(prepare_timeframe_runtime_context)
    return _build_prepare_timeframe_runtime_kwargs(
        timeframe=timeframe,
        data_days=data_days,
        bar_hours=bar_hours,
        **context,
    )


def _build_timeframe_ready_search_kwargs(
    *,
    timeframe,
    data_days,
    stage_prefix,
    timeframe_runtime,
    search_mode,
    max_workers,
    regime_variants,
    regime_lookup,
    mom_lookbacks,
    vol_lookbacks,
    vol_zs,
    trade_mom_lookbacks,
    tp_stops,
    sl_stops,
    max_holds,
    combo_keys_all,
    indicator_param_options,
    existing_combo_df,
    combo_group_fields,
    top_n_fine,
    min_avg_daily_trades_target,
    indicator_defaults,
    indicator_param_fields,
    exchange,
    base_symbol,
    capital_mode,
    fees,
    slippage_bps,
    spread_bps,
    funding_rate_daily,
    order_size_pct,
    max_concurrent_positions,
    init_cash_usdt,
    wf_train_days,
    wf_test_days,
    wf_step_days,
    wf_mode,
    rsi_window,
    config_sha256,
    seen_keys,
    pending_symbol_rows,
    pending_combo_rows,
    combo_key_from_dict_fn,
    indicator_combo_label_fn,
    iter_indicator_param_combos_fn,
    run_combo_tasks_fn,
    evaluate_combo_task_fn,
    wait_if_paused_fn,
    emit_progress_fn,
    checkpoint_fn,
    on_progress_tick_fn,
    apply_quality_filters_fn,
    sort_by_score_impl_fn,
    ranking_config,
    expand_float_fn,
    safe_float_fn,
    refine_indicator_params_fn,
    safe_int_fn,
):
    return {
        "timeframe": timeframe,
        "data_days": data_days,
        "stage_prefix": stage_prefix,
        "timeframe_runtime": timeframe_runtime,
        "search_mode": search_mode,
        "max_workers": max_workers,
        "regime_variants": regime_variants,
        "regime_lookup": regime_lookup,
        "mom_lookbacks": mom_lookbacks,
        "vol_lookbacks": vol_lookbacks,
        "vol_zs": vol_zs,
        "trade_mom_lookbacks": trade_mom_lookbacks,
        "tp_stops": tp_stops,
        "sl_stops": sl_stops,
        "max_holds": max_holds,
        "combo_keys_all": combo_keys_all,
        "indicator_param_options": indicator_param_options,
        "existing_combo_df": existing_combo_df,
        "combo_group_fields": combo_group_fields,
        "top_n_fine": top_n_fine,
        "min_avg_daily_trades_target": min_avg_daily_trades_target,
        "indicator_defaults": indicator_defaults,
        "indicator_param_fields": indicator_param_fields,
        "exchange": exchange,
        "base_symbol": base_symbol,
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
        "wf_mode": wf_mode,
        "rsi_window": rsi_window,
        "config_sha256": config_sha256,
        "seen_keys": seen_keys,
        "pending_symbol_rows": pending_symbol_rows,
        "pending_combo_rows": pending_combo_rows,
        "combo_key_from_dict_fn": combo_key_from_dict_fn,
        "indicator_combo_label_fn": indicator_combo_label_fn,
        "iter_indicator_param_combos_fn": iter_indicator_param_combos_fn,
        "run_combo_tasks_fn": run_combo_tasks_fn,
        "evaluate_combo_task_fn": evaluate_combo_task_fn,
        "wait_if_paused_fn": wait_if_paused_fn,
        "emit_progress_fn": emit_progress_fn,
        "checkpoint_fn": checkpoint_fn,
        "on_progress_tick_fn": on_progress_tick_fn,
        "apply_quality_filters_fn": apply_quality_filters_fn,
        "sort_by_score_fn": lambda df, tie_break_avg_hold=True: sort_by_score_impl_fn(
            df,
            tie_break_avg_hold=tie_break_avg_hold,
            ranking_config=ranking_config,
        ),
        "expand_float_fn": expand_float_fn,
        "safe_float_fn": safe_float_fn,
        "refine_indicator_params_fn": refine_indicator_params_fn,
        "safe_int_fn": safe_int_fn,
    }


def _build_timeframe_ready_search_context(
    *,
    search_mode,
    max_workers,
    regime_variants,
    regime_lookup,
    mom_lookbacks,
    vol_lookbacks,
    vol_zs,
    trade_mom_lookbacks,
    tp_stops,
    sl_stops,
    max_holds,
    combo_keys_all,
    indicator_param_options,
    existing_combo_df,
    combo_group_fields,
    top_n_fine,
    min_avg_daily_trades_target,
    indicator_defaults,
    indicator_param_fields,
    exchange,
    base_symbol,
    capital_mode,
    fees,
    slippage_bps,
    spread_bps,
    funding_rate_daily,
    order_size_pct,
    max_concurrent_positions,
    init_cash_usdt,
    wf_train_days,
    wf_test_days,
    wf_step_days,
    wf_mode,
    rsi_window,
    config_sha256,
    ranking_config,
    seen_keys,
    pending_symbol_rows,
    pending_combo_rows,
    combo_key_from_dict_fn,
    indicator_combo_label_fn,
    iter_indicator_param_combos_fn,
    run_combo_tasks_fn,
    evaluate_combo_task_fn,
    wait_if_paused_fn,
    emit_progress_fn,
    checkpoint_fn,
    on_progress_tick_fn,
    apply_quality_filters_fn,
    sort_by_score_impl_fn,
    expand_float_fn,
    safe_float_fn,
    refine_indicator_params_fn,
    safe_int_fn,
):
    return {
        "search_mode": search_mode,
        "max_workers": max_workers,
        "regime_variants": regime_variants,
        "regime_lookup": regime_lookup,
        "mom_lookbacks": mom_lookbacks,
        "vol_lookbacks": vol_lookbacks,
        "vol_zs": vol_zs,
        "trade_mom_lookbacks": trade_mom_lookbacks,
        "tp_stops": tp_stops,
        "sl_stops": sl_stops,
        "max_holds": max_holds,
        "combo_keys_all": combo_keys_all,
        "indicator_param_options": indicator_param_options,
        "existing_combo_df": existing_combo_df,
        "combo_group_fields": combo_group_fields,
        "top_n_fine": top_n_fine,
        "min_avg_daily_trades_target": min_avg_daily_trades_target,
        "indicator_defaults": indicator_defaults,
        "indicator_param_fields": indicator_param_fields,
        "exchange": exchange,
        "base_symbol": base_symbol,
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
        "wf_mode": wf_mode,
        "rsi_window": rsi_window,
        "config_sha256": config_sha256,
        "ranking_config": ranking_config,
        "seen_keys": seen_keys,
        "pending_symbol_rows": pending_symbol_rows,
        "pending_combo_rows": pending_combo_rows,
        "combo_key_from_dict_fn": combo_key_from_dict_fn,
        "indicator_combo_label_fn": indicator_combo_label_fn,
        "iter_indicator_param_combos_fn": iter_indicator_param_combos_fn,
        "run_combo_tasks_fn": run_combo_tasks_fn,
        "evaluate_combo_task_fn": evaluate_combo_task_fn,
        "wait_if_paused_fn": wait_if_paused_fn,
        "emit_progress_fn": emit_progress_fn,
        "checkpoint_fn": checkpoint_fn,
        "on_progress_tick_fn": on_progress_tick_fn,
        "apply_quality_filters_fn": apply_quality_filters_fn,
        "sort_by_score_impl_fn": sort_by_score_impl_fn,
        "expand_float_fn": expand_float_fn,
        "safe_float_fn": safe_float_fn,
        "refine_indicator_params_fn": refine_indicator_params_fn,
        "safe_int_fn": safe_int_fn,
    }


def _build_timeframe_ready_search_context_from_shared(
    *,
    shared_pipeline_runtime_context,
    search_mode,
    max_workers,
    regime_variants,
    regime_lookup,
    tp_stops,
    sl_stops,
    max_holds,
    combo_keys_all,
    indicator_param_options,
    existing_combo_df,
    combo_group_fields,
    top_n_fine,
    min_avg_daily_trades_target,
    indicator_defaults,
    ranking_config,
    seen_keys,
    pending_symbol_rows,
    pending_combo_rows,
    combo_key_from_dict_fn,
    indicator_combo_label_fn,
    iter_indicator_param_combos_fn,
    run_combo_tasks_fn,
    evaluate_combo_task_fn,
    wait_if_paused_fn,
    emit_progress_fn,
    checkpoint_fn,
    on_progress_tick_fn,
    apply_quality_filters_fn,
    sort_by_score_impl_fn,
    expand_float_fn,
    safe_float_fn,
    refine_indicator_params_fn,
    safe_int_fn,
):
    shared = dict(shared_pipeline_runtime_context)
    return _build_timeframe_ready_search_context(
        search_mode=search_mode,
        max_workers=max_workers,
        regime_variants=regime_variants,
        regime_lookup=regime_lookup,
        mom_lookbacks=shared["mom_lookbacks"],
        vol_lookbacks=shared["vol_lookbacks"],
        vol_zs=shared["vol_zs"],
        trade_mom_lookbacks=shared["trade_mom_lookbacks"],
        tp_stops=tp_stops,
        sl_stops=sl_stops,
        max_holds=max_holds,
        combo_keys_all=combo_keys_all,
        indicator_param_options=indicator_param_options,
        existing_combo_df=existing_combo_df,
        combo_group_fields=combo_group_fields,
        top_n_fine=top_n_fine,
        min_avg_daily_trades_target=min_avg_daily_trades_target,
        indicator_defaults=indicator_defaults,
        indicator_param_fields=shared["indicator_param_fields"],
        exchange=shared["exchange"],
        base_symbol=shared["base_symbol"],
        capital_mode=shared["capital_mode"],
        fees=shared["fees"],
        slippage_bps=shared["slippage_bps"],
        spread_bps=shared["spread_bps"],
        funding_rate_daily=shared["funding_rate_daily"],
        order_size_pct=shared["order_size_pct"],
        max_concurrent_positions=shared["max_concurrent_positions"],
        init_cash_usdt=shared["init_cash_usdt"],
        wf_train_days=shared["wf_train_days"],
        wf_test_days=shared["wf_test_days"],
        wf_step_days=shared["wf_step_days"],
        wf_mode=shared["wf_mode"],
        rsi_window=shared["rsi_window"],
        config_sha256=shared["config_sha256"],
        ranking_config=ranking_config,
        seen_keys=seen_keys,
        pending_symbol_rows=pending_symbol_rows,
        pending_combo_rows=pending_combo_rows,
        combo_key_from_dict_fn=combo_key_from_dict_fn,
        indicator_combo_label_fn=indicator_combo_label_fn,
        iter_indicator_param_combos_fn=iter_indicator_param_combos_fn,
        run_combo_tasks_fn=run_combo_tasks_fn,
        evaluate_combo_task_fn=evaluate_combo_task_fn,
        wait_if_paused_fn=wait_if_paused_fn,
        emit_progress_fn=emit_progress_fn,
        checkpoint_fn=checkpoint_fn,
        on_progress_tick_fn=on_progress_tick_fn,
        apply_quality_filters_fn=apply_quality_filters_fn,
        sort_by_score_impl_fn=sort_by_score_impl_fn,
        expand_float_fn=expand_float_fn,
        safe_float_fn=safe_float_fn,
        refine_indicator_params_fn=refine_indicator_params_fn,
        safe_int_fn=safe_int_fn,
    )


def _build_timeframe_ready_search_kwargs_from_context(
    *,
    timeframe,
    data_days,
    stage_prefix,
    timeframe_runtime,
    timeframe_ready_search_context,
):
    context = dict(timeframe_ready_search_context)
    return _build_timeframe_ready_search_kwargs(
        timeframe=timeframe,
        data_days=data_days,
        stage_prefix=stage_prefix,
        timeframe_runtime=timeframe_runtime,
        **context,
    )


def _run_timeframe_ready_search_with_refine_tracking(
    *,
    run_timeframe_ready_search_fn,
    run_timeframe_ready_search_kwargs,
    get_total_combos_fn,
    set_total_combos_fn,
    emit_progress_fn,
):
    def _on_refine_plan(fine_total, stage):
        set_total_combos_fn(get_total_combos_fn() + fine_total)
        emit_progress_fn(stage=stage, force=True)

    run_kwargs = dict(run_timeframe_ready_search_kwargs)
    run_kwargs["on_refine_plan_fn"] = _on_refine_plan
    run_timeframe_ready_search_fn(**run_kwargs)


def _build_timeframe_execution_callbacks(
    *,
    search_mode,
    count_coarse_combos_fn,
    emit_progress_fn,
    get_total_combos_fn,
    set_total_combos_fn,
    prepare_timeframe_runtime_context,
    prepare_timeframe_runtime_fn,
    timeframe_ready_search_context,
    run_timeframe_ready_search_fn,
    run_timeframe_ready_search_with_refine_tracking_fn,
    build_prepare_kwargs_from_context_fn=_build_prepare_timeframe_runtime_kwargs_from_context,
    prepare_runtime_or_skip_fn=_prepare_timeframe_runtime_or_skip,
    build_ready_kwargs_from_context_fn=_build_timeframe_ready_search_kwargs_from_context,
):
    def _prepare_runtime_attempt(*, timeframe, data_days, stage_prefix, bar_hours, done, total_combos):
        prepare_kwargs = build_prepare_kwargs_from_context_fn(
            timeframe=timeframe,
            data_days=data_days,
            bar_hours=bar_hours,
            prepare_timeframe_runtime_context=prepare_timeframe_runtime_context,
        )
        return prepare_runtime_or_skip_fn(
            prepare_timeframe_runtime_fn=prepare_timeframe_runtime_fn,
            prepare_kwargs=prepare_kwargs,
            search_mode=search_mode,
            total_combos=total_combos,
            done=done,
            count_coarse_combos_fn=count_coarse_combos_fn,
            stage_prefix=stage_prefix,
            timeframe=timeframe,
            emit_progress_fn=emit_progress_fn,
        )

    def _run_timeframe_body(*, timeframe, data_days, stage_prefix, bar_hours, timeframe_runtime):
        ready_search_kwargs = build_ready_kwargs_from_context_fn(
            timeframe=timeframe,
            data_days=data_days,
            stage_prefix=stage_prefix,
            timeframe_runtime=timeframe_runtime,
            timeframe_ready_search_context=timeframe_ready_search_context,
        )
        run_timeframe_ready_search_with_refine_tracking_fn(
            run_timeframe_ready_search_fn=run_timeframe_ready_search_fn,
            run_timeframe_ready_search_kwargs=ready_search_kwargs,
            get_total_combos_fn=get_total_combos_fn,
            set_total_combos_fn=set_total_combos_fn,
            emit_progress_fn=emit_progress_fn,
        )

    return {
        "prepare_runtime_attempt_fn": _prepare_runtime_attempt,
        "on_timeframe_ready_fn": _run_timeframe_body,
    }


def _run_timeframe_search_loop(
    *,
    timeframe_configs,
    wf_train_days,
    wf_test_days,
    prepare_runtime_attempt_fn,
    on_timeframe_ready_fn,
    get_done_fn,
    get_total_combos_fn,
    set_total_combos_fn,
    timeframe_to_hours_fn,
    warn_fn=print,
):
    timeframe_ranges = []
    timeframe_fingerprints = []

    for tf_cfg in timeframe_configs:
        timeframe = tf_cfg["timeframe"]
        data_days = tf_cfg["days"]
        stage_prefix = f"{timeframe}"
        bar_hours = timeframe_to_hours_fn(timeframe)
        runtime_attempt = prepare_runtime_attempt_fn(
            timeframe=timeframe,
            data_days=data_days,
            stage_prefix=stage_prefix,
            bar_hours=bar_hours,
            done=get_done_fn(),
            total_combos=get_total_combos_fn(),
        )
        set_total_combos_fn(runtime_attempt["total_combos"])
        if not runtime_attempt["ok"]:
            continue

        timeframe_runtime = runtime_attempt["timeframe_runtime"]
        ctx = timeframe_runtime["ctx"]
        timeframe_ranges.append(timeframe_runtime["timeframe_range"])
        timeframe_fingerprints.append(timeframe_runtime["timeframe_data_fingerprint"])

        wf_windows = timeframe_runtime["wf_windows"]
        if not wf_windows:
            required_days = wf_train_days + wf_test_days
            warn_fn(
                f"[warn] timeframe {timeframe} has no walk-forward segments: "
                f"available_days={ctx['total_days']} required_days>={required_days}. "
                "OOS metrics will be empty."
            )

        on_timeframe_ready_fn(
            timeframe=timeframe,
            data_days=data_days,
            stage_prefix=stage_prefix,
            bar_hours=bar_hours,
            timeframe_runtime=timeframe_runtime,
        )

    return {
        "timeframe_ranges": timeframe_ranges,
        "timeframe_fingerprints": timeframe_fingerprints,
    }


def _run_timeframe_ready_search(
    *,
    timeframe,
    data_days,
    stage_prefix,
    timeframe_runtime,
    search_mode,
    max_workers,
    regime_variants,
    regime_lookup,
    mom_lookbacks,
    vol_lookbacks,
    vol_zs,
    trade_mom_lookbacks,
    tp_stops,
    sl_stops,
    max_holds,
    combo_keys_all,
    indicator_param_options,
    existing_combo_df,
    combo_group_fields,
    top_n_fine,
    min_avg_daily_trades_target,
    indicator_defaults,
    indicator_param_fields,
    exchange,
    base_symbol,
    capital_mode,
    fees,
    slippage_bps,
    spread_bps,
    funding_rate_daily,
    order_size_pct,
    max_concurrent_positions,
    init_cash_usdt,
    wf_train_days,
    wf_test_days,
    wf_step_days,
    wf_mode,
    rsi_window,
    config_sha256,
    seen_keys,
    pending_symbol_rows,
    pending_combo_rows,
    combo_key_from_dict_fn,
    indicator_combo_label_fn,
    iter_indicator_param_combos_fn,
    run_combo_tasks_fn,
    evaluate_combo_task_fn,
    wait_if_paused_fn,
    emit_progress_fn,
    checkpoint_fn,
    on_progress_tick_fn,
    on_refine_plan_fn,
    apply_quality_filters_fn,
    sort_by_score_fn,
    expand_float_fn,
    safe_float_fn,
    refine_indicator_params_fn,
    safe_int_fn,
):
    ctx = timeframe_runtime["ctx"]
    trade_symbols_tf = timeframe_runtime["trade_symbols_tf"]
    timeframe_data_fingerprint = timeframe_runtime["timeframe_data_fingerprint"]
    runtime_eval = timeframe_runtime["runtime_eval"]

    def _build_combo_task(
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
    ):
        return _build_combo_task_payload(
            timeframe=timeframe,
            data_days=data_days,
            exchange=exchange,
            base_symbol=base_symbol,
            trade_symbols_tf=trade_symbols_tf,
            capital_mode=capital_mode,
            fees=fees,
            slippage_bps=slippage_bps,
            spread_bps=spread_bps,
            funding_rate_daily=funding_rate_daily,
            order_size_pct=order_size_pct,
            max_concurrent_positions=max_concurrent_positions,
            init_cash_usdt=init_cash_usdt,
            wf_train_days=wf_train_days,
            wf_test_days=wf_test_days,
            wf_step_days=wf_step_days,
            wf_mode=wf_mode,
            data_start=ctx["trade_close"].index[0],
            data_end=ctx["trade_close"].index[-1],
            regime=regime,
            indicator_combo=indicator_combo,
            combo_params=combo_params,
            vol_lookback=vol_lookback,
            vol_z=vol_z,
            mom_lookback=mom_lookback,
            trade_mom_lookback=trade_mom_lookback,
            tp_stop=tp_stop,
            sl_stop=sl_stop,
            max_hold=max_hold,
            rsi_window=rsi_window,
            indicator_param_fields=indicator_param_fields,
            combo_key_from_dict_fn=combo_key_from_dict_fn,
            indicator_combo_label_fn=indicator_combo_label_fn,
        )

    def _append_eval_result(result, task_meta):
        _append_eval_result_rows(
            result=result,
            task_meta=task_meta,
            timeframe=timeframe,
            data_days=data_days,
            exchange=exchange,
            base_symbol=base_symbol,
            trade_symbols_tf=trade_symbols_tf,
            capital_mode=capital_mode,
            fees=fees,
            slippage_bps=slippage_bps,
            spread_bps=spread_bps,
            funding_rate_daily=funding_rate_daily,
            order_size_pct=order_size_pct,
            max_concurrent_positions=max_concurrent_positions,
            init_cash_usdt=init_cash_usdt,
            wf_train_days=wf_train_days,
            wf_test_days=wf_test_days,
            wf_step_days=wf_step_days,
            wf_mode=wf_mode,
            data_start=ctx["trade_close"].index[0],
            data_end=ctx["trade_close"].index[-1],
            rsi_window=rsi_window,
            config_sha256=config_sha256,
            timeframe_data_fingerprint=timeframe_data_fingerprint,
            ctx_total_days=ctx["total_days"],
            pending_symbol_rows=pending_symbol_rows,
            pending_combo_rows=pending_combo_rows,
            build_symbol_row_fn=_build_symbol_row,
            build_combo_row_fn=_build_combo_row,
        )

    def _eval_combo(
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
        _run_combo_eval_step(
            regime=regime,
            indicator_combo=indicator_combo,
            combo_params=combo_params,
            vol_lookback=vol_lookback,
            vol_z=vol_z,
            mom_lookback=mom_lookback,
            trade_mom_lookback=trade_mom_lookback,
            tp_stop=tp_stop,
            sl_stop=sl_stop,
            max_hold=max_hold,
            stage=stage,
            wait_if_paused_fn=wait_if_paused_fn,
            build_combo_task_fn=_build_combo_task,
            seen_keys=seen_keys,
            evaluate_combo_task_fn=evaluate_combo_task_fn,
            runtime_eval=runtime_eval,
            append_eval_result_fn=_append_eval_result,
            emit_progress_fn=emit_progress_fn,
            checkpoint_fn=checkpoint_fn,
            on_progress_tick_fn=on_progress_tick_fn,
        )

    if search_mode == "combo" and max_workers > 1:
        stage = f"{stage_prefix} combo"
        _run_parallel_combo_search_for_timeframe(
            stage=stage,
            regime_variants=regime_variants,
            mom_lookbacks=mom_lookbacks,
            vol_lookbacks=vol_lookbacks,
            vol_zs=vol_zs,
            trade_mom_lookbacks=trade_mom_lookbacks,
            tp_stops=tp_stops,
            sl_stops=sl_stops,
            max_holds=max_holds,
            combo_keys_all=combo_keys_all,
            iter_indicator_param_combos_fn=iter_indicator_param_combos_fn,
            indicator_param_options=indicator_param_options,
            build_combo_task_fn=_build_combo_task,
            seen_keys=seen_keys,
            runtime_eval=runtime_eval,
            max_workers=max_workers,
            run_combo_tasks_fn=run_combo_tasks_fn,
            append_eval_result_fn=_append_eval_result,
            emit_progress_fn=emit_progress_fn,
            checkpoint_fn=checkpoint_fn,
            on_progress_tick_fn=on_progress_tick_fn,
        )
        return

    _run_search_for_timeframe(
        search_mode=search_mode,
        stage_prefix=stage_prefix,
        timeframe=timeframe,
        regime_variants=regime_variants,
        regime_lookup=regime_lookup,
        mom_lookbacks=mom_lookbacks,
        vol_lookbacks=vol_lookbacks,
        vol_zs=vol_zs,
        trade_mom_lookbacks=trade_mom_lookbacks,
        tp_stops=tp_stops,
        sl_stops=sl_stops,
        max_holds=max_holds,
        combo_keys_all=combo_keys_all,
        iter_indicator_param_combos_fn=iter_indicator_param_combos_fn,
        indicator_param_options=indicator_param_options,
        eval_combo_fn=_eval_combo,
        existing_combo_df=existing_combo_df,
        apply_quality_filters_fn=apply_quality_filters_fn,
        sort_by_score_fn=sort_by_score_fn,
        combo_group_fields=combo_group_fields,
        top_n_fine=top_n_fine,
        min_avg_daily_trades_target=min_avg_daily_trades_target,
        indicator_defaults=indicator_defaults,
        expand_float_fn=expand_float_fn,
        safe_float_fn=safe_float_fn,
        refine_indicator_params_fn=refine_indicator_params_fn,
        safe_int_fn=safe_int_fn,
        on_refine_plan_fn=on_refine_plan_fn,
    )


def _run_finalize_after_timeframe_loop(
    *,
    timeframe_loop_result,
    checkpoint_fn,
    run_finalize_pipeline_fn,
    finalize_kwargs,
):
    checkpoint_fn(force=True)
    run_kwargs = dict(finalize_kwargs)
    run_kwargs["timeframe_ranges"] = timeframe_loop_result["timeframe_ranges"]
    run_kwargs["timeframe_fingerprints"] = timeframe_loop_result["timeframe_fingerprints"]
    return run_finalize_pipeline_fn(**run_kwargs)


def _run_timeframe_search_and_finalize(
    *,
    timeframe_configs,
    wf_train_days,
    wf_test_days,
    prepare_runtime_attempt_fn,
    on_timeframe_ready_fn,
    get_done_fn,
    get_total_combos_fn,
    set_total_combos_fn,
    timeframe_to_hours_fn,
    finalize_pipeline_context,
    checkpoint_fn,
    run_finalize_pipeline_fn,
    run_timeframe_search_loop_fn=_run_timeframe_search_loop,
    build_finalize_pipeline_kwargs_from_context_fn=None,
    run_finalize_after_timeframe_loop_fn=_run_finalize_after_timeframe_loop,
):
    if build_finalize_pipeline_kwargs_from_context_fn is None:
        build_finalize_pipeline_kwargs_from_context_fn = _build_finalize_pipeline_kwargs_from_context

    timeframe_loop_result = run_timeframe_search_loop_fn(
        timeframe_configs=timeframe_configs,
        wf_train_days=wf_train_days,
        wf_test_days=wf_test_days,
        prepare_runtime_attempt_fn=prepare_runtime_attempt_fn,
        on_timeframe_ready_fn=on_timeframe_ready_fn,
        get_done_fn=get_done_fn,
        get_total_combos_fn=get_total_combos_fn,
        set_total_combos_fn=set_total_combos_fn,
        timeframe_to_hours_fn=timeframe_to_hours_fn,
    )
    finalize_kwargs = build_finalize_pipeline_kwargs_from_context_fn(
        finalize_pipeline_context=finalize_pipeline_context,
    )
    return run_finalize_after_timeframe_loop_fn(
        timeframe_loop_result=timeframe_loop_result,
        checkpoint_fn=checkpoint_fn,
        run_finalize_pipeline_fn=run_finalize_pipeline_fn,
        finalize_kwargs=finalize_kwargs,
    )


def _run_timeframe_pipeline(
    *,
    timeframe_configs,
    wf_train_days,
    wf_test_days,
    search_mode,
    count_coarse_combos_fn,
    emit_progress_fn,
    get_done_fn,
    get_total_combos_fn,
    set_total_combos_fn,
    prepare_timeframe_runtime_context,
    prepare_timeframe_runtime_fn,
    timeframe_ready_search_context,
    run_timeframe_ready_search_fn,
    run_timeframe_ready_search_with_refine_tracking_fn,
    timeframe_to_hours_fn,
    finalize_pipeline_context,
    checkpoint_fn,
    run_finalize_pipeline_fn,
    build_timeframe_execution_callbacks_fn=_build_timeframe_execution_callbacks,
    run_timeframe_search_and_finalize_fn=_run_timeframe_search_and_finalize,
):
    callbacks = build_timeframe_execution_callbacks_fn(
        search_mode=search_mode,
        count_coarse_combos_fn=count_coarse_combos_fn,
        emit_progress_fn=emit_progress_fn,
        get_total_combos_fn=get_total_combos_fn,
        set_total_combos_fn=set_total_combos_fn,
        prepare_timeframe_runtime_context=prepare_timeframe_runtime_context,
        prepare_timeframe_runtime_fn=prepare_timeframe_runtime_fn,
        timeframe_ready_search_context=timeframe_ready_search_context,
        run_timeframe_ready_search_fn=run_timeframe_ready_search_fn,
        run_timeframe_ready_search_with_refine_tracking_fn=(
            run_timeframe_ready_search_with_refine_tracking_fn
        ),
    )
    return run_timeframe_search_and_finalize_fn(
        timeframe_configs=timeframe_configs,
        wf_train_days=wf_train_days,
        wf_test_days=wf_test_days,
        prepare_runtime_attempt_fn=callbacks["prepare_runtime_attempt_fn"],
        on_timeframe_ready_fn=callbacks["on_timeframe_ready_fn"],
        get_done_fn=get_done_fn,
        get_total_combos_fn=get_total_combos_fn,
        set_total_combos_fn=set_total_combos_fn,
        timeframe_to_hours_fn=timeframe_to_hours_fn,
        finalize_pipeline_context=finalize_pipeline_context,
        checkpoint_fn=checkpoint_fn,
        run_finalize_pipeline_fn=run_finalize_pipeline_fn,
    )


def _handle_finalize_result(
    *,
    finalize_result,
    emit_progress_fn,
    print_fn=print,
):
    if not finalize_result.get("ok"):
        warning = finalize_result.get("warning")
        if warning:
            print_fn(warning)
        return False

    emit_progress_fn(stage="complete", force=True)
    for key, value in finalize_result.get("completion_outputs", {}).items():
        print_fn(key, value)
    return True


def _build_finalize_pipeline_kwargs(
    *,
    combo_path,
    per_symbol_path,
    out_dir,
    run_id,
    timeframe_configs,
    timeframe_days_map,
    safe_int_fn,
    min_avg_daily_trades_target,
    apply_quality_filters_fn,
    top_by_score_impl_fn,
    ranking_config,
    history_rows,
    base_symbol,
    trade_symbols,
    exchange,
    cache_dir,
    cache_format,
    vol_lookbacks,
    vol_zs,
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
    wf_train_days,
    wf_test_days,
    wf_step_days,
    wf_mode,
    indicator_param_fields,
    fees,
    slippage_bps,
    spread_bps,
    funding_rate_daily,
    order_size_pct,
    max_concurrent_positions,
    labels,
    config_sha256,
    timestamp_utc,
    leaderboard_path,
    run_metadata_path,
    run_metadata_path_run,
    registry_path,
    search_mode,
    config_path,
    prepare_timeframe_context_fn,
    indicator_combo_label_fn,
    coerce_indicator_params_fn,
    pick_series_from_map_fn,
    apply_indicator_combo_fn,
    timeframe_to_hours_fn,
    run_pf_fn,
    plot_portfolio_fn,
    calc_pf_series_fn,
    build_walk_forward_slices_fn,
    df_to_html_fn,
    combine_data_fingerprints_fn,
    write_run_metadata_fn,
    update_run_registry_fn,
    combo_seed=None,
):
    top_by_score_fn = lambda df, top_n, tie_break_avg_hold: top_by_score_impl_fn(
        df,
        top_n=top_n,
        tie_break_avg_hold=tie_break_avg_hold,
        ranking_config=ranking_config,
    )
    return {
        "combo_path": combo_path,
        "per_symbol_path": per_symbol_path,
        "out_dir": out_dir,
        "run_id": run_id,
        "timeframe_configs": timeframe_configs,
        "timeframe_days_map": timeframe_days_map,
        "safe_int_fn": safe_int_fn,
        "min_avg_daily_trades_target": min_avg_daily_trades_target,
        "apply_quality_filters_fn": apply_quality_filters_fn,
        "top_by_score_fn": top_by_score_fn,
        "history_rows": history_rows,
        "top_by_score_leaderboard_fn": top_by_score_fn,
        "base_symbol": base_symbol,
        "trade_symbols": trade_symbols,
        "exchange": exchange,
        "cache_dir": cache_dir,
        "cache_format": cache_format,
        "vol_lookbacks": vol_lookbacks,
        "vol_zs": vol_zs,
        "mom_lookbacks": mom_lookbacks,
        "trade_mom_lookbacks": trade_mom_lookbacks,
        "rsi_window": rsi_window,
        "bb_window": bb_window,
        "bb_alpha": bb_alpha,
        "atr_window": atr_window,
        "ma_pairs": ma_pairs,
        "obv_lookbacks": obv_lookbacks,
        "volume_lookbacks": volume_lookbacks,
        "roc_lookbacks": roc_lookbacks,
        "cmf_lookbacks": cmf_lookbacks,
        "mfi_window": mfi_window,
        "vroc_lookbacks": vroc_lookbacks,
        "ad_lookbacks": ad_lookbacks,
        "init_cash_usdt": init_cash_usdt,
        "capital_mode": capital_mode,
        "wf_train_days": wf_train_days,
        "wf_test_days": wf_test_days,
        "wf_step_days": wf_step_days,
        "wf_mode": wf_mode,
        "indicator_param_fields": indicator_param_fields,
        "fees": fees,
        "slippage_bps": slippage_bps,
        "spread_bps": spread_bps,
        "funding_rate_daily": funding_rate_daily,
        "order_size_pct": order_size_pct,
        "max_concurrent_positions": max_concurrent_positions,
        "labels": labels,
        "config_sha256": config_sha256,
        "combo_seed": combo_seed,
        "timestamp_utc": timestamp_utc,
        "ranking_config": ranking_config,
        "leaderboard_path": leaderboard_path,
        "run_metadata_path": run_metadata_path,
        "run_metadata_path_run": run_metadata_path_run,
        "registry_path": registry_path,
        "search_mode": search_mode,
        "config_path": config_path,
        "prepare_timeframe_context_fn": prepare_timeframe_context_fn,
        "indicator_combo_label_fn": indicator_combo_label_fn,
        "coerce_indicator_params_fn": coerce_indicator_params_fn,
        "pick_series_from_map_fn": pick_series_from_map_fn,
        "apply_indicator_combo_fn": apply_indicator_combo_fn,
        "timeframe_to_hours_fn": timeframe_to_hours_fn,
        "run_pf_fn": run_pf_fn,
        "plot_portfolio_fn": plot_portfolio_fn,
        "calc_pf_series_fn": calc_pf_series_fn,
        "build_walk_forward_slices_fn": build_walk_forward_slices_fn,
        "df_to_html_fn": df_to_html_fn,
        "combine_data_fingerprints_fn": combine_data_fingerprints_fn,
        "write_run_metadata_fn": write_run_metadata_fn,
        "update_run_registry_fn": update_run_registry_fn,
    }


def _build_finalize_pipeline_context(
    *,
    combo_path,
    per_symbol_path,
    out_dir,
    run_id,
    timeframe_configs,
    timeframe_days_map,
    safe_int_fn,
    min_avg_daily_trades_target,
    apply_quality_filters_fn,
    top_by_score_impl_fn,
    ranking_config,
    history_rows,
    base_symbol,
    trade_symbols,
    exchange,
    cache_dir,
    cache_format,
    vol_lookbacks,
    vol_zs,
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
    wf_train_days,
    wf_test_days,
    wf_step_days,
    wf_mode,
    indicator_param_fields,
    fees,
    slippage_bps,
    spread_bps,
    funding_rate_daily,
    order_size_pct,
    max_concurrent_positions,
    labels,
    config_sha256,
    timestamp_utc,
    leaderboard_path,
    run_metadata_path,
    run_metadata_path_run,
    registry_path,
    search_mode,
    config_path,
    prepare_timeframe_context_fn,
    indicator_combo_label_fn,
    coerce_indicator_params_fn,
    pick_series_from_map_fn,
    apply_indicator_combo_fn,
    timeframe_to_hours_fn,
    run_pf_fn,
    plot_portfolio_fn,
    calc_pf_series_fn,
    build_walk_forward_slices_fn,
    df_to_html_fn,
    combine_data_fingerprints_fn,
    write_run_metadata_fn,
    update_run_registry_fn,
    combo_seed=None,
):
    return {
        "combo_path": combo_path,
        "per_symbol_path": per_symbol_path,
        "out_dir": out_dir,
        "run_id": run_id,
        "timeframe_configs": timeframe_configs,
        "timeframe_days_map": timeframe_days_map,
        "safe_int_fn": safe_int_fn,
        "min_avg_daily_trades_target": min_avg_daily_trades_target,
        "apply_quality_filters_fn": apply_quality_filters_fn,
        "top_by_score_impl_fn": top_by_score_impl_fn,
        "ranking_config": ranking_config,
        "history_rows": history_rows,
        "base_symbol": base_symbol,
        "trade_symbols": trade_symbols,
        "exchange": exchange,
        "cache_dir": cache_dir,
        "cache_format": cache_format,
        "vol_lookbacks": vol_lookbacks,
        "vol_zs": vol_zs,
        "mom_lookbacks": mom_lookbacks,
        "trade_mom_lookbacks": trade_mom_lookbacks,
        "rsi_window": rsi_window,
        "bb_window": bb_window,
        "bb_alpha": bb_alpha,
        "atr_window": atr_window,
        "ma_pairs": ma_pairs,
        "obv_lookbacks": obv_lookbacks,
        "volume_lookbacks": volume_lookbacks,
        "roc_lookbacks": roc_lookbacks,
        "cmf_lookbacks": cmf_lookbacks,
        "mfi_window": mfi_window,
        "vroc_lookbacks": vroc_lookbacks,
        "ad_lookbacks": ad_lookbacks,
        "init_cash_usdt": init_cash_usdt,
        "capital_mode": capital_mode,
        "wf_train_days": wf_train_days,
        "wf_test_days": wf_test_days,
        "wf_step_days": wf_step_days,
        "wf_mode": wf_mode,
        "indicator_param_fields": indicator_param_fields,
        "fees": fees,
        "slippage_bps": slippage_bps,
        "spread_bps": spread_bps,
        "funding_rate_daily": funding_rate_daily,
        "order_size_pct": order_size_pct,
        "max_concurrent_positions": max_concurrent_positions,
        "labels": labels,
        "config_sha256": config_sha256,
        "combo_seed": combo_seed,
        "timestamp_utc": timestamp_utc,
        "leaderboard_path": leaderboard_path,
        "run_metadata_path": run_metadata_path,
        "run_metadata_path_run": run_metadata_path_run,
        "registry_path": registry_path,
        "search_mode": search_mode,
        "config_path": config_path,
        "prepare_timeframe_context_fn": prepare_timeframe_context_fn,
        "indicator_combo_label_fn": indicator_combo_label_fn,
        "coerce_indicator_params_fn": coerce_indicator_params_fn,
        "pick_series_from_map_fn": pick_series_from_map_fn,
        "apply_indicator_combo_fn": apply_indicator_combo_fn,
        "timeframe_to_hours_fn": timeframe_to_hours_fn,
        "run_pf_fn": run_pf_fn,
        "plot_portfolio_fn": plot_portfolio_fn,
        "calc_pf_series_fn": calc_pf_series_fn,
        "build_walk_forward_slices_fn": build_walk_forward_slices_fn,
        "df_to_html_fn": df_to_html_fn,
        "combine_data_fingerprints_fn": combine_data_fingerprints_fn,
        "write_run_metadata_fn": write_run_metadata_fn,
        "update_run_registry_fn": update_run_registry_fn,
    }


def _build_finalize_pipeline_context_from_shared(
    *,
    shared_pipeline_runtime_context,
    combo_path,
    per_symbol_path,
    out_dir,
    run_id,
    timeframe_configs,
    timeframe_days_map,
    safe_int_fn,
    min_avg_daily_trades_target,
    apply_quality_filters_fn,
    top_by_score_impl_fn,
    ranking_config,
    history_rows,
    labels,
    timestamp_utc,
    leaderboard_path,
    run_metadata_path,
    run_metadata_path_run,
    registry_path,
    search_mode,
    config_path,
    prepare_timeframe_context_fn,
    indicator_combo_label_fn,
    coerce_indicator_params_fn,
    pick_series_from_map_fn,
    apply_indicator_combo_fn,
    timeframe_to_hours_fn,
    run_pf_fn,
    plot_portfolio_fn,
    calc_pf_series_fn,
    build_walk_forward_slices_fn,
    df_to_html_fn,
    combine_data_fingerprints_fn,
    write_run_metadata_fn,
    update_run_registry_fn,
):
    shared = dict(shared_pipeline_runtime_context)
    return _build_finalize_pipeline_context(
        combo_path=combo_path,
        per_symbol_path=per_symbol_path,
        out_dir=out_dir,
        run_id=run_id,
        timeframe_configs=timeframe_configs,
        timeframe_days_map=timeframe_days_map,
        safe_int_fn=safe_int_fn,
        min_avg_daily_trades_target=min_avg_daily_trades_target,
        apply_quality_filters_fn=apply_quality_filters_fn,
        top_by_score_impl_fn=top_by_score_impl_fn,
        ranking_config=ranking_config,
        history_rows=history_rows,
        base_symbol=shared["base_symbol"],
        trade_symbols=shared["trade_symbols"],
        exchange=shared["exchange"],
        cache_dir=shared["cache_dir"],
        cache_format=shared["cache_format"],
        vol_lookbacks=shared["vol_lookbacks"],
        vol_zs=shared["vol_zs"],
        mom_lookbacks=shared["mom_lookbacks"],
        trade_mom_lookbacks=shared["trade_mom_lookbacks"],
        rsi_window=shared["rsi_window"],
        bb_window=shared["bb_window"],
        bb_alpha=shared["bb_alpha"],
        atr_window=shared["atr_window"],
        ma_pairs=shared["ma_pairs"],
        obv_lookbacks=shared["obv_lookbacks"],
        volume_lookbacks=shared["volume_lookbacks"],
        roc_lookbacks=shared["roc_lookbacks"],
        cmf_lookbacks=shared["cmf_lookbacks"],
        mfi_window=shared["mfi_window"],
        vroc_lookbacks=shared["vroc_lookbacks"],
        ad_lookbacks=shared["ad_lookbacks"],
        init_cash_usdt=shared["init_cash_usdt"],
        capital_mode=shared["capital_mode"],
        wf_train_days=shared["wf_train_days"],
        wf_test_days=shared["wf_test_days"],
        wf_step_days=shared["wf_step_days"],
        wf_mode=shared["wf_mode"],
        indicator_param_fields=shared["indicator_param_fields"],
        fees=shared["fees"],
        slippage_bps=shared["slippage_bps"],
        spread_bps=shared["spread_bps"],
        funding_rate_daily=shared["funding_rate_daily"],
        order_size_pct=shared["order_size_pct"],
        max_concurrent_positions=shared["max_concurrent_positions"],
        labels=labels,
        config_sha256=shared["config_sha256"],
        combo_seed=shared.get("combo_seed"),
        timestamp_utc=timestamp_utc,
        leaderboard_path=leaderboard_path,
        run_metadata_path=run_metadata_path,
        run_metadata_path_run=run_metadata_path_run,
        registry_path=registry_path,
        search_mode=search_mode,
        config_path=config_path,
        prepare_timeframe_context_fn=prepare_timeframe_context_fn,
        indicator_combo_label_fn=indicator_combo_label_fn,
        coerce_indicator_params_fn=coerce_indicator_params_fn,
        pick_series_from_map_fn=pick_series_from_map_fn,
        apply_indicator_combo_fn=apply_indicator_combo_fn,
        timeframe_to_hours_fn=timeframe_to_hours_fn,
        run_pf_fn=run_pf_fn,
        plot_portfolio_fn=plot_portfolio_fn,
        calc_pf_series_fn=calc_pf_series_fn,
        build_walk_forward_slices_fn=build_walk_forward_slices_fn,
        df_to_html_fn=df_to_html_fn,
        combine_data_fingerprints_fn=combine_data_fingerprints_fn,
        write_run_metadata_fn=write_run_metadata_fn,
        update_run_registry_fn=update_run_registry_fn,
    )


def _build_finalize_pipeline_kwargs_from_context(
    *,
    finalize_pipeline_context,
):
    context = dict(finalize_pipeline_context)
    return _build_finalize_pipeline_kwargs(**context)


def _prepare_timeframe_runtime(
    *,
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
    wf_train_days,
    wf_test_days,
    wf_step_days,
    wf_mode,
    fees,
    slippage_bps,
    spread_bps,
    funding_rate_daily,
    order_size_pct,
    max_concurrent_positions,
    config_sha256,
    bar_hours,
    prepare_timeframe_context_fn,
    build_walk_forward_windows_fn,
    compute_data_fingerprint_fn,
):
    ctx = prepare_timeframe_context_fn(
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
    )
    trade_symbols_tf = ctx["trade_symbols"]
    timeframe_range = f"{timeframe} ({data_days}d): {ctx['data_range']}"
    timeframe_data_fingerprint = compute_data_fingerprint_fn(
        {
            "exchange": exchange,
            "base_symbol": base_symbol,
            "trade_symbols": trade_symbols_tf,
            "timeframe": timeframe,
            "data_days": data_days,
            "data_start": str(ctx["trade_close"].index[0]),
            "data_end": str(ctx["trade_close"].index[-1]),
        }
    )
    wf_windows = build_walk_forward_windows_fn(
        ctx["trade_close"].index,
        wf_train_days,
        wf_test_days,
        wf_step_days,
        mode=wf_mode,
    )
    wf_slices = [(test_start, test_end) for _, _, test_start, test_end in wf_windows]
    runtime_eval = {
        "ctx": ctx,
        "trade_symbols_tf": trade_symbols_tf,
        "timeframe": timeframe,
        "data_days": data_days,
        "exchange": exchange,
        "base_symbol": base_symbol,
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
        "wf_mode": wf_mode,
        "rsi_window": rsi_window,
        "bar_hours": bar_hours,
        "wf_windows": wf_windows,
        "wf_slices": wf_slices,
        "config_sha256": config_sha256,
        "data_fingerprint": timeframe_data_fingerprint,
    }
    return {
        "ctx": ctx,
        "trade_symbols_tf": trade_symbols_tf,
        "timeframe_range": timeframe_range,
        "timeframe_data_fingerprint": timeframe_data_fingerprint,
        "wf_windows": wf_windows,
        "wf_slices": wf_slices,
        "runtime_eval": runtime_eval,
    }


def _build_combo_key_values(
    timeframe,
    data_days,
    exchange,
    base_symbol,
    trade_symbols_tf,
    capital_mode,
    fees,
    slippage_bps,
    spread_bps,
    funding_rate_daily,
    order_size_pct,
    max_concurrent_positions,
    init_cash_usdt,
    wf_train_days,
    wf_test_days,
    wf_step_days,
    data_start,
    data_end,
    regime,
    filter_name,
    indicator_list,
    indicator_combo,
    vol_lookback,
    vol_z,
    mom_lookback,
    trade_mom_lookback,
    tp_stop,
    sl_stop,
    max_hold,
    rsi_window,
    param_payload,
    wf_mode="anchored",
):
    return {
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
        "wf_mode": wf_mode,
        "data_start": str(data_start),
        "data_end": str(data_end),
        "regime_name": regime["regime_name"],
        "regime_type": regime["regime_type"],
        "vol_mode": regime["vol_mode"],
        "regime_rsi_long": regime.get("rsi_pair", (None, None))[0]
        if regime["regime_type"] == "rsi_revert"
        else None,
        "regime_rsi_short": regime.get("rsi_pair", (None, None))[1]
        if regime["regime_type"] == "rsi_revert"
        else None,
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
    }


def _build_combo_task_payload(
    *,
    timeframe,
    data_days,
    exchange,
    base_symbol,
    trade_symbols_tf,
    capital_mode,
    fees,
    slippage_bps,
    spread_bps,
    funding_rate_daily,
    order_size_pct,
    max_concurrent_positions,
    init_cash_usdt,
    wf_train_days,
    wf_test_days,
    wf_step_days,
    wf_mode,
    data_start,
    data_end,
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
    rsi_window,
    indicator_param_fields,
    combo_key_from_dict_fn,
    indicator_combo_label_fn,
):
    indicator_combo = tuple(indicator_combo)
    combo_params = dict(combo_params)
    indicator_list = ",".join(indicator_combo)
    filter_name = indicator_combo_label_fn(indicator_combo)
    param_payload = {field: combo_params.get(field) for field in indicator_param_fields}
    combo_key_values = _build_combo_key_values(
        timeframe=timeframe,
        data_days=data_days,
        exchange=exchange,
        base_symbol=base_symbol,
        trade_symbols_tf=trade_symbols_tf,
        capital_mode=capital_mode,
        fees=fees,
        slippage_bps=slippage_bps,
        spread_bps=spread_bps,
        funding_rate_daily=funding_rate_daily,
        order_size_pct=order_size_pct,
        max_concurrent_positions=max_concurrent_positions,
        init_cash_usdt=init_cash_usdt,
        wf_train_days=wf_train_days,
        wf_test_days=wf_test_days,
        wf_step_days=wf_step_days,
        wf_mode=wf_mode,
        data_start=data_start,
        data_end=data_end,
        regime=regime,
        filter_name=filter_name,
        indicator_list=indicator_list,
        indicator_combo=indicator_combo,
        vol_lookback=vol_lookback,
        vol_z=vol_z,
        mom_lookback=mom_lookback,
        trade_mom_lookback=trade_mom_lookback,
        tp_stop=tp_stop,
        sl_stop=sl_stop,
        max_hold=max_hold,
        rsi_window=rsi_window,
        param_payload=param_payload,
    )
    combo_key = combo_key_from_dict_fn(combo_key_values)
    task_payload = {
        "combo_key": combo_key,
        "regime": regime,
        "indicator_combo": indicator_combo,
        "combo_params": combo_params,
        "filter_name": filter_name,
        "indicator_list": indicator_list,
        "vol_lookback": vol_lookback,
        "vol_z": vol_z,
        "mom_lookback": mom_lookback,
        "trade_mom_lookback": trade_mom_lookback,
        "tp_stop": tp_stop,
        "sl_stop": sl_stop,
        "max_hold": max_hold,
    }
    return combo_key, task_payload


def _resolve_regime_signals(regime, vol_cond, ctx, mom_lookback):
    if regime["regime_type"] == "trend":
        mom = ctx["mom_by_lb"][mom_lookback]
        return vol_cond & (mom > 0), vol_cond & (mom < 0), None, None
    if regime["regime_type"] == "rsi_revert":
        regime_rsi_long, regime_rsi_short = regime["rsi_pair"]
        return (
            vol_cond & (ctx["rsi_series"] < regime_rsi_long),
            vol_cond & (ctx["rsi_series"] > regime_rsi_short),
            regime_rsi_long,
            regime_rsi_short,
        )
    if regime["regime_type"] == "bb_revert":
        return (
            vol_cond & (ctx["btc_close"] < ctx["bb_lower"]),
            vol_cond & (ctx["btc_close"] > ctx["bb_upper"]),
            None,
            None,
        )
    return (
        vol_cond & (ctx["btc_close"] > ctx["bb_upper"]),
        vol_cond & (ctx["btc_close"] < ctx["bb_lower"]),
        None,
        None,
    )


def _build_symbol_row(
    timeframe,
    data_days,
    exchange,
    base_symbol,
    trade_symbols_tf,
    capital_mode,
    fees,
    order_size_pct,
    max_concurrent_positions,
    init_cash_usdt,
    wf_train_days,
    wf_test_days,
    wf_step_days,
    data_start,
    data_end,
    symbol,
    regime,
    regime_rsi_long,
    regime_rsi_short,
    filter_name,
    indicator_list,
    indicator_combo,
    vol_lookback,
    vol_z,
    mom_lookback,
    trade_mom_lookback,
    tp_stop,
    sl_stop,
    max_hold,
    rsi_window,
    variant_params,
    metrics,
    wf_mode="anchored",
    config_sha256=None,
    data_fingerprint=None,
):
    return {
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
        "wf_mode": wf_mode,
        "data_start": str(data_start),
        "data_end": str(data_end),
        "config_sha256": config_sha256,
        "data_fingerprint": data_fingerprint,
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
    }


def _build_combo_row(
    timeframe,
    data_days,
    exchange,
    base_symbol,
    trade_symbols_tf,
    fees,
    slippage_bps,
    spread_bps,
    funding_rate_daily,
    order_size_pct,
    max_concurrent_positions,
    init_cash_usdt,
    wf_train_days,
    wf_test_days,
    wf_step_days,
    data_start,
    data_end,
    regime,
    regime_rsi_long,
    regime_rsi_short,
    filter_name,
    indicator_list,
    indicator_combo,
    vol_lookback,
    vol_z,
    mom_lookback,
    trade_mom_lookback,
    tp_stop,
    sl_stop,
    max_hold,
    rsi_window,
    variant_params,
    combo_metrics,
    sym_metrics,
    metrics,
    ctx_total_days,
    oos_metrics,
    wf_mode="anchored",
    config_sha256=None,
    data_fingerprint=None,
):
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
        "wf_mode": wf_mode,
        "data_start": str(data_start),
        "data_end": str(data_end),
        "config_sha256": config_sha256,
        "data_fingerprint": data_fingerprint,
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
        "avg_daily_trades": float(combo_metrics["total_trades"]) / max(ctx_total_days, 1),
        "avg_hold_hours": combo_metrics["avg_hold_hours"],
        "sym_avg_total_return_pct": sym_metrics["avg_total_return_pct"],
        "sym_avg_win_rate_pct": sym_metrics["avg_win_rate_pct"],
        "sym_avg_avg_trade_pct": sym_metrics["avg_avg_trade_pct"],
        "sym_avg_max_drawdown_pct": sym_metrics["avg_max_drawdown_pct"],
        "sym_avg_position_coverage_pct": sym_metrics["avg_position_coverage_pct"],
        "sym_avg_total_trades": sym_metrics["avg_total_trades"],
        "sym_min_total_trades": sym_metrics["min_total_trades"],
        "sym_avg_daily_trades": float(metrics["total_trades"].sum()) / max(ctx_total_days, 1),
        "sym_avg_hold_hours": sym_metrics["avg_hold_hours"],
    }
    combo_row.update(oos_metrics)
    return combo_row


def _append_eval_result_rows(
    *,
    result,
    task_meta,
    timeframe,
    data_days,
    exchange,
    base_symbol,
    trade_symbols_tf,
    capital_mode,
    fees,
    slippage_bps,
    spread_bps,
    funding_rate_daily,
    order_size_pct,
    max_concurrent_positions,
    init_cash_usdt,
    wf_train_days,
    wf_test_days,
    wf_step_days,
    wf_mode,
    data_start,
    data_end,
    rsi_window,
    config_sha256,
    timeframe_data_fingerprint,
    ctx_total_days,
    pending_symbol_rows,
    pending_combo_rows,
    build_symbol_row_fn,
    build_combo_row_fn,
):
    metrics_values = result.get("metrics_values")
    if not isinstance(metrics_values, dict):
        return False

    regime = task_meta["regime"]
    indicator_combo = tuple(task_meta["indicator_combo"])
    filter_name = task_meta["filter_name"]
    indicator_list = task_meta["indicator_list"]
    vol_lookback = task_meta["vol_lookback"]
    vol_z = task_meta["vol_z"]
    mom_lookback = task_meta["mom_lookback"]
    trade_mom_lookback = task_meta["trade_mom_lookback"]
    tp_stop = task_meta["tp_stop"]
    sl_stop = task_meta["sl_stop"]
    max_hold = task_meta["max_hold"]
    metrics = {name: pd.Series(values).reindex(trade_symbols_tf) for name, values in metrics_values.items()}
    variant_params = result["variant_params"]
    regime_rsi_long = result["regime_rsi_long"]
    regime_rsi_short = result["regime_rsi_short"]

    for symbol in trade_symbols_tf:
        pending_symbol_rows.append(
            build_symbol_row_fn(
                timeframe=timeframe,
                data_days=data_days,
                exchange=exchange,
                base_symbol=base_symbol,
                trade_symbols_tf=trade_symbols_tf,
                capital_mode=capital_mode,
                fees=fees,
                order_size_pct=order_size_pct,
                max_concurrent_positions=max_concurrent_positions,
                init_cash_usdt=init_cash_usdt,
                wf_train_days=wf_train_days,
                wf_test_days=wf_test_days,
                wf_step_days=wf_step_days,
                wf_mode=wf_mode,
                data_start=data_start,
                data_end=data_end,
                symbol=symbol,
                regime=regime,
                regime_rsi_long=regime_rsi_long,
                regime_rsi_short=regime_rsi_short,
                filter_name=filter_name,
                indicator_list=indicator_list,
                indicator_combo=indicator_combo,
                vol_lookback=vol_lookback,
                vol_z=vol_z,
                mom_lookback=mom_lookback,
                trade_mom_lookback=trade_mom_lookback,
                tp_stop=tp_stop,
                sl_stop=sl_stop,
                max_hold=max_hold,
                rsi_window=rsi_window,
                variant_params=variant_params,
                metrics=metrics,
                config_sha256=config_sha256,
                data_fingerprint=timeframe_data_fingerprint,
            )
        )

    combo_row = build_combo_row_fn(
        timeframe=timeframe,
        data_days=data_days,
        exchange=exchange,
        base_symbol=base_symbol,
        trade_symbols_tf=trade_symbols_tf,
        fees=fees,
        slippage_bps=slippage_bps,
        spread_bps=spread_bps,
        funding_rate_daily=funding_rate_daily,
        order_size_pct=order_size_pct,
        max_concurrent_positions=max_concurrent_positions,
        init_cash_usdt=init_cash_usdt,
        wf_train_days=wf_train_days,
        wf_test_days=wf_test_days,
        wf_step_days=wf_step_days,
        wf_mode=wf_mode,
        data_start=data_start,
        data_end=data_end,
        regime=regime,
        regime_rsi_long=regime_rsi_long,
        regime_rsi_short=regime_rsi_short,
        filter_name=filter_name,
        indicator_list=indicator_list,
        indicator_combo=indicator_combo,
        vol_lookback=vol_lookback,
        vol_z=vol_z,
        mom_lookback=mom_lookback,
        trade_mom_lookback=trade_mom_lookback,
        tp_stop=tp_stop,
        sl_stop=sl_stop,
        max_hold=max_hold,
        rsi_window=rsi_window,
        variant_params=variant_params,
        combo_metrics=result["combo_metrics"],
        sym_metrics=result["sym_metrics"],
        metrics=metrics,
        ctx_total_days=ctx_total_days,
        oos_metrics=result["oos_metrics"],
        config_sha256=config_sha256,
        data_fingerprint=timeframe_data_fingerprint,
    )
    pending_combo_rows.append(combo_row)
    return True


def _compute_effective_costs(fees, slippage_bps, spread_bps, funding_rate_daily, max_hold, bar_hours):
    effective_slippage = (slippage_bps + (spread_bps / 2.0)) / 10000.0
    funding_fee = funding_rate_daily * (max_hold * bar_hours / 24.0)
    effective_fees = fees + funding_fee
    return effective_fees, effective_slippage


def _build_trade_mom_filters(trade_mom):
    return trade_mom > 0, trade_mom < 0


def _load_result_frames(combo_path, per_symbol_path):
    combo_df = pd.read_csv(combo_path, low_memory=False) if os.path.exists(combo_path) else pd.DataFrame()
    per_symbol_df = (
        pd.read_csv(per_symbol_path, low_memory=False) if os.path.exists(per_symbol_path) else pd.DataFrame()
    )
    return combo_df, per_symbol_df


def _write_run_snapshot_files(combo_df, per_symbol_df, out_dir, run_id):
    combo_path_run = os.path.join(out_dir, f"param_sweep_combo_summary_{run_id}.csv")
    per_symbol_path_run = os.path.join(out_dir, f"param_sweep_symbol_summary_{run_id}.csv")
    if not combo_df.empty:
        combo_df.to_csv(combo_path_run, index=False)
    if not per_symbol_df.empty:
        per_symbol_df.to_csv(per_symbol_path_run, index=False)
    return combo_path_run, per_symbol_path_run


def _select_current_combo_df(combo_df, timeframe_configs):
    combo_df_current = combo_df
    if "timeframe" in combo_df.columns:
        valid_timeframes = {cfg["timeframe"] for cfg in timeframe_configs}
        tf_subset = combo_df[combo_df["timeframe"].isin(valid_timeframes)].copy()
        if not tf_subset.empty:
            combo_df_current = tf_subset
    return combo_df_current


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


def _pick_best_from_top(top_df, timeframe_configs, timeframe_days_map, safe_int_fn):
    best = top_df.iloc[0].to_dict()
    best_timeframe = best.get("timeframe")
    if best_timeframe is None or (isinstance(best_timeframe, float) and np.isnan(best_timeframe)):
        best_timeframe = timeframe_configs[0]["timeframe"]
    best_timeframe = str(best_timeframe)
    if best_timeframe not in timeframe_days_map:
        best_timeframe = timeframe_configs[0]["timeframe"]
    best_data_days = safe_int_fn(
        best.get("data_days"),
        timeframe_days_map.get(best_timeframe, timeframe_configs[0]["days"]),
    )
    return best, best_timeframe, best_data_days


def _build_leaderboard_row_payload(
    *,
    run_id,
    timestamp_utc,
    config_sha256,
    ranking_mode,
    plot_symbol,
    best_timeframe,
    best_data_days,
    min_avg_daily_trades_target,
    min_avg_daily_trades_filter,
    capital_mode,
    init_cash_usdt,
    order_size_pct,
    max_concurrent_positions,
    slippage_bps,
    spread_bps,
    funding_rate_daily,
    wf_train_days,
    wf_test_days,
    wf_step_days,
    wf_mode,
    wf_segments,
    best,
    report_file,
):
    return {
        "run_id": run_id,
        "timestamp_utc": timestamp_utc,
        "config_sha256": config_sha256,
        "data_fingerprint": best.get("data_fingerprint"),
        "ranking_mode": ranking_mode,
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
        "wf_mode": wf_mode,
        "wf_segments": wf_segments,
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
        "oos_return_std": best.get("oos_return_std"),
        "oos_positive_segment_ratio": best.get("oos_positive_segment_ratio"),
        "oos_sharpe_like": best.get("oos_sharpe_like"),
        "oos_low_trade_segment_ratio": best.get("oos_low_trade_segment_ratio"),
        "oos_low_trade_penalty": best.get("oos_low_trade_penalty"),
        "oos_segments": best.get("oos_segments"),
        "report_file": report_file,
    }


def _build_run_metadata_payload(
    *,
    run_id,
    timestamp_utc,
    search_mode,
    config_sha256,
    data_fingerprint,
    config_path,
    exchange,
    base_symbol,
    trade_symbols,
    timeframe_configs,
    wf_train_days,
    wf_test_days,
    wf_step_days,
    wf_mode,
    capital_mode,
    init_cash_usdt,
    ranking_config,
    combo_seed=None,
):
    return {
        "run_id": run_id,
        "timestamp_utc": timestamp_utc,
        "search_mode": search_mode,
        "config_sha256": config_sha256,
        "combo_seed": combo_seed,
        "data_fingerprint": data_fingerprint,
        "config_path": config_path,
        "exchange": exchange,
        "base_symbol": base_symbol,
        "trade_symbols": trade_symbols,
        "timeframes": timeframe_configs,
        "wf_train_days": wf_train_days,
        "wf_test_days": wf_test_days,
        "wf_step_days": wf_step_days,
        "wf_mode": wf_mode,
        "capital_mode": capital_mode,
        "init_cash_usdt": init_cash_usdt,
        "ranking": ranking_config,
    }


def _prepare_best_timeframe_context(
    *,
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
    prepare_timeframe_context_fn,
):
    try:
        ctx = prepare_timeframe_context_fn(
            timeframe=best_timeframe,
            data_days=best_data_days,
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
        )
        return {"ctx": ctx, "error": None}
    except Exception as exc:
        return {"ctx": None, "error": exc}


def _persist_run_metadata_and_registry(
    *,
    timeframe_fingerprints,
    run_id,
    timestamp_utc,
    search_mode,
    config_sha256,
    config_path,
    exchange,
    base_symbol,
    trade_symbols,
    timeframe_configs,
    wf_train_days,
    wf_test_days,
    wf_step_days,
    wf_mode,
    capital_mode,
    init_cash_usdt,
    ranking_config,
    run_metadata_path,
    run_metadata_path_run,
    registry_path,
    leaderboard_row,
    per_symbol_df,
    combine_data_fingerprints_fn,
    write_run_metadata_fn,
    update_run_registry_fn,
    combo_seed=None,
):
    run_data_fingerprint = combine_data_fingerprints_fn(timeframe_fingerprints)
    run_metadata_payload = _build_run_metadata_payload(
        run_id=run_id,
        timestamp_utc=timestamp_utc,
        search_mode=search_mode,
        config_sha256=config_sha256,
        combo_seed=combo_seed,
        data_fingerprint=run_data_fingerprint,
        config_path=config_path,
        exchange=exchange,
        base_symbol=base_symbol,
        trade_symbols=trade_symbols,
        timeframe_configs=timeframe_configs,
        wf_train_days=wf_train_days,
        wf_test_days=wf_test_days,
        wf_step_days=wf_step_days,
        wf_mode=wf_mode,
        capital_mode=capital_mode,
        init_cash_usdt=init_cash_usdt,
        ranking_config=ranking_config,
    )
    write_run_metadata_fn(run_metadata_path, run_metadata_payload)
    write_run_metadata_fn(run_metadata_path_run, run_metadata_payload)
    update_run_registry_fn(
        registry_path=registry_path,
        run_metadata=run_metadata_payload,
        best_row=leaderboard_row,
        per_symbol_df=per_symbol_df,
        updated_utc=timestamp_utc,
    )
    return {"run_data_fingerprint": run_data_fingerprint, "run_metadata_payload": run_metadata_payload}


def _build_completion_output_map(
    *,
    combo_path,
    per_symbol_path,
    top10_path,
    leaderboard_path,
    registry_path,
    run_metadata_path,
    run_metadata_path_run,
    report_path_latest,
    report_path_run,
):
    return {
        "combo_summary": combo_path,
        "per_symbol_summary": per_symbol_path,
        "top10": top10_path,
        "leaderboard": leaderboard_path,
        "run_registry": registry_path,
        "run_metadata": run_metadata_path,
        "run_metadata_run": run_metadata_path_run,
        "report_latest": report_path_latest,
        "report_run": report_path_run,
    }


def _run_finalize_pipeline(
    *,
    combo_path,
    per_symbol_path,
    out_dir,
    run_id,
    timeframe_configs,
    timeframe_days_map,
    safe_int_fn,
    min_avg_daily_trades_target,
    apply_quality_filters_fn,
    top_by_score_fn,
    history_rows,
    top_by_score_leaderboard_fn,
    base_symbol,
    trade_symbols,
    exchange,
    cache_dir,
    cache_format,
    vol_lookbacks,
    vol_zs,
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
    timeframe_ranges,
    wf_train_days,
    wf_test_days,
    wf_step_days,
    wf_mode,
    indicator_param_fields,
    fees,
    slippage_bps,
    spread_bps,
    funding_rate_daily,
    order_size_pct,
    max_concurrent_positions,
    labels,
    config_sha256,
    timestamp_utc,
    ranking_config,
    leaderboard_path,
    run_metadata_path,
    run_metadata_path_run,
    registry_path,
    timeframe_fingerprints,
    search_mode,
    config_path,
    per_symbol_df_for_registry=None,
    prepare_timeframe_context_fn=None,
    indicator_combo_label_fn=None,
    coerce_indicator_params_fn=None,
    pick_series_from_map_fn=None,
    apply_indicator_combo_fn=None,
    timeframe_to_hours_fn=None,
    run_pf_fn=None,
    plot_portfolio_fn=None,
    calc_pf_series_fn=None,
    build_walk_forward_slices_fn=None,
    df_to_html_fn=None,
    combine_data_fingerprints_fn=None,
    write_run_metadata_fn=None,
    update_run_registry_fn=None,
    combo_seed=None,
):
    combo_df, per_symbol_df = _load_result_frames(combo_path, per_symbol_path)
    _write_run_snapshot_files(combo_df, per_symbol_df, out_dir, run_id)

    combo_df_current = _select_current_combo_df(combo_df, timeframe_configs)
    if combo_df_current.empty:
        return {
            "ok": False,
            "warning": "[warn] No valid combinations evaluated; check data download and filters.",
        }

    filtered, min_avg_daily_trades_filter = _fallback_activity_filter(
        combo_df_current=combo_df_current,
        min_avg_daily_trades_target=min_avg_daily_trades_target,
        apply_quality_filters_fn=apply_quality_filters_fn,
    )

    top10, _ = top_by_score_fn(filtered, top_n=10, tie_break_avg_hold=True)
    top10_path = os.path.join(out_dir, f"param_sweep_top10_{run_id}.csv")
    top10.to_csv(top10_path, index=False)

    best, best_timeframe, best_data_days = _pick_best_from_top(
        top_df=top10,
        timeframe_configs=timeframe_configs,
        timeframe_days_map=timeframe_days_map,
        safe_int_fn=safe_int_fn,
    )

    best_ctx_result = _prepare_best_timeframe_context(
        best_timeframe=best_timeframe,
        best_data_days=best_data_days,
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
        prepare_timeframe_context_fn=prepare_timeframe_context_fn,
    )
    best_ctx = best_ctx_result["ctx"]
    if best_ctx is None:
        return {"ok": False, "warning": f"[warn] best report skipped: {best_ctx_result['error']}"}

    best_replay = _prepare_best_replay_payload(
        best=best,
        best_timeframe=best_timeframe,
        best_ctx=best_ctx,
        timeframe_ranges=timeframe_ranges,
        wf_train_days=wf_train_days,
        wf_test_days=wf_test_days,
        wf_step_days=wf_step_days,
        wf_mode=wf_mode,
        indicator_param_fields=indicator_param_fields,
        vol_lookbacks=vol_lookbacks,
        vol_zs=vol_zs,
        mom_lookbacks=mom_lookbacks,
        trade_mom_lookbacks=trade_mom_lookbacks,
        fees=fees,
        slippage_bps=slippage_bps,
        spread_bps=spread_bps,
        funding_rate_daily=funding_rate_daily,
        order_size_pct=order_size_pct,
        capital_mode=capital_mode,
        max_concurrent_positions=max_concurrent_positions,
        indicator_combo_label_fn=indicator_combo_label_fn,
        coerce_indicator_params_fn=coerce_indicator_params_fn,
        pick_series_from_map_fn=pick_series_from_map_fn,
        apply_indicator_combo_fn=apply_indicator_combo_fn,
        timeframe_to_hours_fn=timeframe_to_hours_fn,
        run_pf_fn=run_pf_fn,
        plot_portfolio_fn=plot_portfolio_fn,
        calc_pf_series_fn=calc_pf_series_fn,
        build_walk_forward_slices_fn=build_walk_forward_slices_fn,
    )

    trade_symbols_report = best_replay["trade_symbols"]
    plot_symbol = best_replay["plot_symbol"]
    data_range = best_replay["data_range"]
    scan_timeframes = best_replay["scan_timeframes"]
    wf_slices = best_replay["wf_slices"]
    best_regime = best_replay["best_regime"]
    indicator_list = best_replay["indicator_list"]
    best_indicator_combo = best_replay["best_indicator_combo"]
    best_filter_name = best_replay["best_filter_name"]
    best_params = best_replay["best_params"]
    best_trade_mom_lookback = best_replay["best_trade_mom_lookback"]
    best_tp_stop = best_replay["best_tp_stop"]
    best_sl_stop = best_replay["best_sl_stop"]
    best_max_hold = best_replay["best_max_hold"]
    best_summary = best_replay["best_summary"]
    plot_html = best_replay["plot_html"]

    report_params, oos_summary = _build_best_report_frames(
        best=best,
        best_timeframe=best_timeframe,
        best_data_days=best_data_days,
        capital_mode=capital_mode,
        wf_mode=wf_mode,
        best_regime=best_regime,
        best_filter_name=best_filter_name,
        indicator_list=indicator_list,
        best_indicator_combo=best_indicator_combo,
        best_trade_mom_lookback=best_trade_mom_lookback,
        best_tp_stop=best_tp_stop,
        best_sl_stop=best_sl_stop,
        best_max_hold=best_max_hold,
        rsi_window=rsi_window,
        best_params=best_params,
    )

    report_tables = _build_report_table_html_sections(
        report_params=report_params,
        oos_summary=oos_summary,
        top10=top10,
        best_summary=best_summary,
        label_map=labels,
        df_to_html_fn=df_to_html_fn,
    )
    report_params_html = report_tables["report_params_html"]
    oos_summary_html = report_tables["oos_summary_html"]
    top10_html = report_tables["top10_html"]
    summary_html = report_tables["summary_html"]

    report_paths = _build_report_file_paths(out_dir=out_dir, plot_symbol=plot_symbol, run_id=run_id)
    report_file_run = report_paths["report_file_run"]
    report_path_latest = report_paths["report_path_latest"]
    report_path_run = report_paths["report_path_run"]

    leaderboard_row = _build_leaderboard_row_payload(
        run_id=run_id,
        timestamp_utc=timestamp_utc,
        config_sha256=config_sha256,
        ranking_mode=ranking_config.get("mode"),
        plot_symbol=plot_symbol,
        best_timeframe=best_timeframe,
        best_data_days=best_data_days,
        min_avg_daily_trades_target=min_avg_daily_trades_target,
        min_avg_daily_trades_filter=min_avg_daily_trades_filter,
        capital_mode=capital_mode,
        init_cash_usdt=init_cash_usdt,
        order_size_pct=order_size_pct,
        max_concurrent_positions=max_concurrent_positions,
        slippage_bps=slippage_bps,
        spread_bps=spread_bps,
        funding_rate_daily=funding_rate_daily,
        wf_train_days=wf_train_days,
        wf_test_days=wf_test_days,
        wf_step_days=wf_step_days,
        wf_mode=wf_mode,
        wf_segments=len(wf_slices),
        best=best,
        report_file=report_file_run,
    )

    lb_df = _append_leaderboard_row(leaderboard_path=leaderboard_path, leaderboard_row=leaderboard_row)
    _, lb_recent, lb_best = _build_leaderboard_views(
        lb_df=lb_df,
        history_rows=history_rows,
        top_by_score_fn=top_by_score_leaderboard_fn,
    )
    lb_report = _build_leaderboard_report_html(
        lb_recent=lb_recent,
        lb_best=lb_best,
        label_map=labels,
        df_to_html_fn=df_to_html_fn,
    )
    lb_recent_html = lb_report["lb_recent_html"]
    lb_best_html = lb_report["lb_best_html"]

    html = _build_report_html(
        labels=labels,
        data_range=data_range,
        best_timeframe=best_timeframe,
        best_data_days=best_data_days,
        scan_timeframes=scan_timeframes,
        run_id=run_id,
        timestamp_utc=timestamp_utc,
        min_avg_daily_trades_target=min_avg_daily_trades_target,
        min_avg_daily_trades_filter=min_avg_daily_trades_filter,
        capital_mode=capital_mode,
        init_cash_usdt=init_cash_usdt,
        order_size_pct=order_size_pct,
        max_concurrent_positions=max_concurrent_positions,
        wf_train_days=wf_train_days,
        wf_test_days=wf_test_days,
        wf_step_days=wf_step_days,
        wf_mode=wf_mode,
        wf_segments=len(wf_slices),
        base_symbol=base_symbol,
        trade_symbols=trade_symbols_report,
        summary_html=summary_html,
        report_params_html=report_params_html,
        oos_summary_html=oos_summary_html,
        top10_html=top10_html,
        lb_best_html=lb_best_html,
        lb_recent_html=lb_recent_html,
        plot_symbol=plot_symbol,
        plot_html=plot_html,
    )
    _write_report_files(report_path_latest=report_path_latest, report_path_run=report_path_run, html=html)

    _persist_run_metadata_and_registry(
        timeframe_fingerprints=timeframe_fingerprints,
        run_id=run_id,
        timestamp_utc=timestamp_utc,
        search_mode=search_mode,
        config_sha256=config_sha256,
        combo_seed=combo_seed,
        config_path=config_path,
        exchange=exchange,
        base_symbol=base_symbol,
        trade_symbols=trade_symbols_report,
        timeframe_configs=timeframe_configs,
        wf_train_days=wf_train_days,
        wf_test_days=wf_test_days,
        wf_step_days=wf_step_days,
        wf_mode=wf_mode,
        capital_mode=capital_mode,
        init_cash_usdt=init_cash_usdt,
        ranking_config=ranking_config,
        run_metadata_path=run_metadata_path,
        run_metadata_path_run=run_metadata_path_run,
        registry_path=registry_path,
        leaderboard_row=leaderboard_row,
        per_symbol_df=per_symbol_df if per_symbol_df_for_registry is None else per_symbol_df_for_registry,
        combine_data_fingerprints_fn=combine_data_fingerprints_fn,
        write_run_metadata_fn=write_run_metadata_fn,
        update_run_registry_fn=update_run_registry_fn,
    )

    completion_outputs = _build_completion_output_map(
        combo_path=combo_path,
        per_symbol_path=per_symbol_path,
        top10_path=top10_path,
        leaderboard_path=leaderboard_path,
        registry_path=registry_path,
        run_metadata_path=run_metadata_path,
        run_metadata_path_run=run_metadata_path_run,
        report_path_latest=report_path_latest,
        report_path_run=report_path_run,
    )
    return {"ok": True, "completion_outputs": completion_outputs}


def _build_report_file_paths(out_dir, plot_symbol, run_id):
    report_file_latest = f"btc_regime_{plot_symbol.replace('/', '-')}.html"
    report_file_run = f"btc_regime_{plot_symbol.replace('/', '-')}_{run_id}.html"
    return {
        "report_file_latest": report_file_latest,
        "report_file_run": report_file_run,
        "report_path_latest": os.path.join(out_dir, report_file_latest),
        "report_path_run": os.path.join(out_dir, report_file_run),
    }


def _build_report_html(
    *,
    labels,
    data_range,
    best_timeframe,
    best_data_days,
    scan_timeframes,
    run_id,
    timestamp_utc,
    min_avg_daily_trades_target,
    min_avg_daily_trades_filter,
    capital_mode,
    init_cash_usdt,
    order_size_pct,
    max_concurrent_positions,
    wf_train_days,
    wf_test_days,
    wf_step_days,
    wf_mode,
    wf_segments,
    base_symbol,
    trade_symbols,
    summary_html,
    report_params_html,
    oos_summary_html,
    top10_html,
    lb_best_html,
    lb_recent_html,
    plot_symbol,
    plot_html,
):
    scan_timeframes_html = (
        f"<div><strong>{labels['scan_timeframes']}:</strong> {scan_timeframes}</div>"
        if scan_timeframes
        else ""
    )
    return f"""<!doctype html>
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
  <h1>{labels['report_title']}</h1>
    <div class="meta">
    <div><strong>{labels['data_range']}:</strong> {data_range}</div>
    <div><strong>{labels['timeframe']}:</strong> {best_timeframe}</div>
    <div><strong>{labels['data_days']}:</strong> {best_data_days}</div>
    {scan_timeframes_html}
    <div><strong>{labels['run_id']}:</strong> {run_id}</div>
    <div><strong>{labels['timestamp_utc']}:</strong> {timestamp_utc}</div>
    <div><strong>{labels['min_avg_daily_trades_target']}:</strong> {min_avg_daily_trades_target}</div>
    <div><strong>{labels['min_avg_daily_trades_filter']}:</strong> {min_avg_daily_trades_filter}</div>
    <div><strong>{labels['capital_mode']}:</strong> {capital_mode}</div>
    <div><strong>{labels['init_cash_usdt']}:</strong> {init_cash_usdt}</div>
    <div><strong>{labels['order_size_pct']}:</strong> {order_size_pct}</div>
    <div><strong>{labels['max_concurrent_positions']}:</strong> {max_concurrent_positions}</div>
    <div><strong>{labels['wf_train_days']}:</strong> {wf_train_days}</div>
    <div><strong>{labels['wf_test_days']}:</strong> {wf_test_days}</div>
    <div><strong>{labels['wf_step_days']}:</strong> {wf_step_days}</div>
    <div><strong>{labels['wf_mode']}:</strong> {wf_mode}</div>
    <div><strong>{labels['wf_segments']}:</strong> {wf_segments}</div>
    <div><strong>{labels['base_symbol']}:</strong> {base_symbol}</div>
    <div><strong>{labels['trade_symbols']}:</strong> {', '.join(trade_symbols)}</div>
  </div>

  <h2>{labels['summary_title']}</h2>
  {summary_html}

  <h2>{labels['params_title']}</h2>
  {report_params_html}

  <h2>{labels['oos_summary_title']}</h2>
  {oos_summary_html}

  <h2>{labels['top_title']}</h2>
  {top10_html}

  <h2>{labels['history_title']}</h2>

  <h2>{labels['leaderboard_title']}</h2>
  {lb_best_html}

  <h2>{labels['recent_runs_title']}</h2>
  {lb_recent_html}

  <h2>{labels['chart_title']} ({plot_symbol})</h2>
  {plot_html}
</body>
</html>
"""


def _write_report_files(report_path_latest, report_path_run, html):
    with open(report_path_latest, "w", encoding="utf-8") as f:
        f.write(html)
    with open(report_path_run, "w", encoding="utf-8") as f:
        f.write(html)


def _prepare_best_replay_payload(
    *,
    best,
    best_timeframe,
    best_ctx,
    timeframe_ranges,
    wf_train_days,
    wf_test_days,
    wf_step_days,
    wf_mode,
    indicator_param_fields,
    vol_lookbacks,
    vol_zs,
    mom_lookbacks,
    trade_mom_lookbacks,
    fees,
    slippage_bps,
    spread_bps,
    funding_rate_daily,
    order_size_pct,
    capital_mode,
    max_concurrent_positions,
    indicator_combo_label_fn,
    coerce_indicator_params_fn,
    pick_series_from_map_fn,
    apply_indicator_combo_fn,
    timeframe_to_hours_fn,
    run_pf_fn,
    plot_portfolio_fn,
    calc_pf_series_fn,
    build_walk_forward_slices_fn,
):
    trade_close = best_ctx["trade_close"]
    trade_symbols = best_ctx["trade_symbols"]
    plot_symbol = trade_symbols[0]
    data_range = best_ctx["data_range"]
    scan_timeframes = "; ".join(timeframe_ranges) if timeframe_ranges else ""
    wf_slices = build_walk_forward_slices_fn(
        trade_close.index,
        wf_train_days,
        wf_test_days,
        wf_step_days,
        mode=wf_mode,
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
    best_indicator_combo = (
        tuple([v for v in str(indicator_list).split(",") if v]) if indicator_list else tuple()
    )
    best_filter_name = best.get("filter_name") or indicator_combo_label_fn(best_indicator_combo)

    best_params = {}
    for field in indicator_param_fields:
        value = best.get(field)
        best_params[field] = value if pd.notna(value) else None
    best_params = coerce_indicator_params_fn(best_indicator_combo, best_params, best_ctx)

    best_vol_lookback = int(best["vol_lookback"]) if pd.notna(best["vol_lookback"]) else vol_lookbacks[0]
    best_vol_z = float(best["vol_z"]) if pd.notna(best["vol_z"]) else vol_zs[0]
    best_mom_lookback = int(best["mom_lookback"]) if pd.notna(best["mom_lookback"]) else mom_lookbacks[0]
    best_trade_mom_lookback = int(best["trade_mom_lookback"])
    best_tp_stop = float(best["tp_stop"])
    best_sl_stop = float(best["sl_stop"])
    best_max_hold = int(best["max_hold"])

    vol_zscore, _ = pick_series_from_map_fn(
        best_ctx["vol_zscore_by_lb"],
        best_vol_lookback,
        vol_lookbacks[0] if vol_lookbacks else None,
    )
    if best_regime["vol_mode"] == "high":
        vol_cond = vol_zscore > best_vol_z
    elif best_regime["vol_mode"] == "low":
        vol_cond = vol_zscore < -best_vol_z
    else:
        vol_cond = pd.Series(True, index=vol_zscore.index)

    best_regime_for_resolve = {
        "regime_name": best_regime["regime_name"],
        "regime_type": best_regime["regime_type"],
        "vol_mode": best_regime["vol_mode"],
        "rsi_pair": (best_regime["regime_rsi_long"], best_regime["regime_rsi_short"])
        if best_regime["regime_type"] == "rsi_revert"
        else None,
    }
    long_regime, short_regime, _, _ = _resolve_regime_signals(
        regime=best_regime_for_resolve,
        vol_cond=vol_cond,
        ctx=best_ctx,
        mom_lookback=best_mom_lookback,
    )
    trade_mom, _ = pick_series_from_map_fn(
        best_ctx["trade_mom_by_lb"],
        best_trade_mom_lookback,
        trade_mom_lookbacks[0] if trade_mom_lookbacks else None,
    )
    long_regime, short_regime, best_params = apply_indicator_combo_fn(
        long_regime,
        short_regime,
        best_indicator_combo,
        best_params,
        best_ctx,
    )

    best_bar_hours = timeframe_to_hours_fn(best_timeframe)
    best_effective_fees, best_effective_slippage = _compute_effective_costs(
        fees=fees,
        slippage_bps=slippage_bps,
        spread_bps=spread_bps,
        funding_rate_daily=funding_rate_daily,
        max_hold=best_max_hold,
        bar_hours=best_bar_hours,
    )

    best_pf = run_pf_fn(
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
        init_cash=best_ctx["init_cash_btc"],
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
    fig = plot_portfolio_fn(best_pf, plot_symbol)
    plot_html = fig.to_html(full_html=False, include_plotlyjs="cdn")

    best_metrics = calc_pf_series_fn(best_pf, trade_symbols, best_bar_hours)
    best_summary = pd.DataFrame(
        {
            "symbol": trade_symbols,
            "total_return_pct": best_metrics["total_return_pct"].to_numpy(),
            "total_profit": best_metrics["total_profit"].to_numpy(),
            "total_trades": best_metrics["total_trades"].to_numpy(),
            "win_rate_pct": best_metrics["win_rate_pct"].to_numpy(),
            "avg_trade_pct": best_metrics["avg_trade_pct"].to_numpy(),
            "max_drawdown_pct": best_metrics["max_drawdown_pct"].to_numpy(),
            "position_coverage_pct": best_metrics["position_coverage_pct"].to_numpy(),
            "avg_hold_hours": best_metrics["avg_hold_hours"].to_numpy(),
        }
    )

    return {
        "trade_symbols": trade_symbols,
        "plot_symbol": plot_symbol,
        "data_range": data_range,
        "scan_timeframes": scan_timeframes,
        "wf_slices": wf_slices,
        "best_regime": best_regime,
        "indicator_list": indicator_list,
        "best_indicator_combo": best_indicator_combo,
        "best_filter_name": best_filter_name,
        "best_params": best_params,
        "best_trade_mom_lookback": best_trade_mom_lookback,
        "best_tp_stop": best_tp_stop,
        "best_sl_stop": best_sl_stop,
        "best_max_hold": best_max_hold,
        "best_summary": best_summary,
        "plot_html": plot_html,
    }


def _build_best_report_frames(
    *,
    best,
    best_timeframe,
    best_data_days,
    capital_mode,
    wf_mode,
    best_regime,
    best_filter_name,
    indicator_list,
    best_indicator_combo,
    best_trade_mom_lookback,
    best_tp_stop,
    best_sl_stop,
    best_max_hold,
    rsi_window,
    best_params,
):
    report_params = pd.DataFrame(
        [
            {
                "timeframe": best_timeframe,
                "data_days": best_data_days,
                "capital_mode": capital_mode,
                "wf_mode": wf_mode,
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
            }
        ]
    )

    oos_summary = pd.DataFrame(
        [
            {
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
                "oos_return_std": best.get("oos_return_std"),
                "oos_positive_segment_ratio": best.get("oos_positive_segment_ratio"),
                "oos_sharpe_like": best.get("oos_sharpe_like"),
                "oos_low_trade_segment_ratio": best.get("oos_low_trade_segment_ratio"),
                "oos_low_trade_penalty": best.get("oos_low_trade_penalty"),
            }
        ]
    )
    return report_params, oos_summary


def _top_report_columns():
    return [
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
        "oos_return_std",
        "oos_positive_segment_ratio",
        "oos_sharpe_like",
        "oos_low_trade_segment_ratio",
        "oos_low_trade_penalty",
        "oos_segments",
        "avg_win_rate_pct",
        "avg_avg_trade_pct",
        "avg_max_drawdown_pct",
        "avg_position_coverage_pct",
        "avg_total_trades",
        "min_total_trades",
    ]


def _summary_report_columns():
    return [
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


def _build_report_table_html_sections(
    *,
    report_params,
    oos_summary,
    top10,
    best_summary,
    label_map,
    df_to_html_fn,
    top_columns=None,
    summary_columns=None,
):
    top_cols = list(top_columns) if top_columns is not None else _top_report_columns()
    summary_cols = list(summary_columns) if summary_columns is not None else _summary_report_columns()
    report_params_html = df_to_html_fn(report_params, list(report_params.columns), label_map)
    oos_summary_html = df_to_html_fn(oos_summary, list(oos_summary.columns), label_map)
    top10_html = df_to_html_fn(top10, top_cols, label_map)
    summary_html = df_to_html_fn(best_summary, summary_cols, label_map)
    return {
        "top_columns": top_cols,
        "summary_columns": summary_cols,
        "report_params_html": report_params_html,
        "oos_summary_html": oos_summary_html,
        "top10_html": top10_html,
        "summary_html": summary_html,
    }


def _leaderboard_report_columns():
    return [
        "timestamp_utc",
        "run_id",
        "config_sha256",
        "ranking_mode",
        "plot_symbol",
        "timeframe",
        "data_days",
        "min_avg_daily_trades_target",
        "min_avg_daily_trades_filter",
        "regime_name",
        "regime_type",
        "oos_avg_total_return_pct",
        "oos_sharpe_like",
        "avg_total_return_pct",
        "avg_daily_trades",
        "oos_avg_daily_trades",
        "avg_total_trades",
        "avg_position_coverage_pct",
        "min_total_trades",
        "filter_name",
        "report",
    ]


def _build_leaderboard_report_html(lb_recent, lb_best, label_map, df_to_html_fn, lb_cols=None):
    columns = list(lb_cols) if lb_cols is not None else _leaderboard_report_columns()
    lb_recent_html = df_to_html_fn(lb_recent.reindex(columns=columns), columns, label_map)
    lb_best_html = df_to_html_fn(lb_best.reindex(columns=columns), columns, label_map)
    return {
        "columns": columns,
        "lb_recent_html": lb_recent_html,
        "lb_best_html": lb_best_html,
    }


def _append_leaderboard_row(leaderboard_path, leaderboard_row):
    if os.path.exists(leaderboard_path):
        lb_df = pd.read_csv(leaderboard_path, low_memory=False)
        lb_df = pd.concat([lb_df, pd.DataFrame([leaderboard_row])], ignore_index=True)
    else:
        lb_df = pd.DataFrame([leaderboard_row])
    lb_df.to_csv(leaderboard_path, index=False)
    return lb_df


def _build_leaderboard_views(lb_df, history_rows, top_by_score_fn):
    lb_view = lb_df.copy()
    if "report_file" in lb_view.columns:
        lb_view["report"] = lb_view["report_file"].apply(lambda x: f'<a href="{x}">{x}</a>' if x else "")
    else:
        lb_view["report"] = ""
    lb_recent = lb_view.sort_values("timestamp_utc", ascending=False).head(history_rows)
    lb_best, _ = top_by_score_fn(lb_view, top_n=history_rows, tie_break_avg_hold=False)
    return lb_view, lb_recent, lb_best


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
