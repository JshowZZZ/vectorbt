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
    "combo_segment_start": 0,
    "combo_segment_size": None,
    "timeframes": [{"timeframe": "3m", "days": 60}],
    "wf_train_days": 120,
    "wf_test_days": 30,
    "wf_step_days": 30,
    "top_n_refine": 50,
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


def _load_runtime_config(out_dir, env_mode=None):
    config = copy.deepcopy(DEFAULT_CONFIG)
    config_path = os.path.join(out_dir, "sweep_config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
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
