"""Engine search: plan iteration, search execution, pipeline orchestration."""

import os

import numpy as np
import pandas as pd

from .engine_helpers import _fallback_activity_filter, _strip_data_range_from_combo_key
from .engine_finalize import _build_finalize_pipeline_kwargs_from_context
from .engine_runtime import (
    _append_eval_result_rows,
    _build_combo_row,
    _build_combo_task_payload,
    _build_oos_symbol_row,
    _build_symbol_row,
    _prepare_timeframe_runtime,
)


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
        "tp_stop_atr_multiple": 0.25,
        "sl_stop_atr_multiple": 0.25,
    }


def _resolve_refine_risk_steps(refine_steps, risk_mode):
    risk_mode_value = str(risk_mode or "fixed_pct").strip().lower()
    if risk_mode_value == "atr_multiple":
        return (
            float(refine_steps.get("tp_stop_atr_multiple", refine_steps["tp_stop"])),
            float(refine_steps.get("sl_stop_atr_multiple", refine_steps["sl_stop"])),
        )
    return (
        float(refine_steps["tp_stop"]),
        float(refine_steps["sl_stop"]),
    )


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
        tp_step, sl_step = _resolve_refine_risk_steps(refine_steps, row.get("risk_mode"))
        base_tp = safe_float_fn(row.get("tp_stop"), tp_stops[0])
        base_sl = safe_float_fn(row.get("sl_stop"), sl_stops[0])
        tp_candidates = expand_float_fn(base_tp, tp_step, min_value=0.0001)
        sl_candidates = expand_float_fn(base_sl, sl_step, min_value=0.0001)
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
    pruning_tracker=None,
):
    done = 0
    skipped = 0
    planned_keys = set()
    combo_tasks = []
    _skip_emit_count = 0  # AWF-108(a): throttle emit calls during consecutive skips

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
        stripped_key = _strip_data_range_from_combo_key(combo_key)
        if stripped_key in seen_keys or stripped_key in planned_keys:
            skipped += 1
            done += 1
            if on_progress_tick_fn is not None:
                on_progress_tick_fn(done_delta=1, skipped_delta=1)
            _skip_emit_count += 1
            if _skip_emit_count % 200 == 0:
                emit_progress_fn(stage=stage)
            continue
        planned_keys.add(stripped_key)
        if pruning_tracker is not None:
            if pruning_tracker.budget_exhausted():
                skipped += 1
                done += 1
                if on_progress_tick_fn is not None:
                    on_progress_tick_fn(done_delta=1, skipped_delta=1)
                _skip_emit_count += 1
                if _skip_emit_count % 200 == 0:
                    emit_progress_fn(stage=stage)
                continue
            if pruning_tracker.should_prune(tuple(task_payload.get("indicator_combo", ()))):
                pruning_tracker.increment_pruned()
                skipped += 1
                done += 1
                if on_progress_tick_fn is not None:
                    on_progress_tick_fn(done_delta=1, skipped_delta=1)
                _skip_emit_count += 1
                if _skip_emit_count % 200 == 0:
                    emit_progress_fn(stage=stage)
                continue
        combo_tasks.append(task_payload)

    if pruning_tracker is not None and pruning_tracker.batch_size > 0:
        from autowfo.pruning import _split_into_batches
        batches = _split_into_batches(combo_tasks, pruning_tracker.batch_size)
    else:
        batches = [combo_tasks] if combo_tasks else []

    for batch in batches:
        if pruning_tracker is not None and pruning_tracker.budget_exhausted():
            remaining = sum(len(b) for b in batches[batches.index(batch):])
            skipped += remaining
            done += remaining
            if on_progress_tick_fn is not None:
                on_progress_tick_fn(done_delta=remaining, skipped_delta=remaining)
            emit_progress_fn(stage=stage)
            break
        for task_payload, result in zip(
            batch,
            run_combo_tasks_fn(batch, runtime_eval, max_workers=max_workers),
        ):
            append_eval_result_fn(result, task_payload)
            seen_keys.add(_strip_data_range_from_combo_key(task_payload["combo_key"]))
            done += 1
            if on_progress_tick_fn is not None:
                on_progress_tick_fn(done_delta=1, skipped_delta=0)
            emit_progress_fn(stage=stage)
            checkpoint_fn()
            if pruning_tracker is not None:
                import math
                oos_metrics = result.get("oos_metrics") or {}
                score = oos_metrics.get("oos_avg_total_return_pct", 0.0)
                if score is None or (isinstance(score, float) and math.isnan(score)):
                    score = 0.0
                pruning_tracker.record_result(
                    tuple(task_payload.get("indicator_combo", ())),
                    float(score),
                )
        if pruning_tracker is not None:
            pruning_tracker.update_threshold()

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
    pruning_tracker=None,
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
    stripped_key = _strip_data_range_from_combo_key(combo_key)
    if stripped_key in seen_keys:
        if on_progress_tick_fn is not None:
            on_progress_tick_fn(done_delta=1, skipped_delta=1)
        emit_progress_fn(stage=stage)
        return {"skipped": True, "evaluated": False}

    if pruning_tracker is not None:
        if pruning_tracker.budget_exhausted():
            if on_progress_tick_fn is not None:
                on_progress_tick_fn(done_delta=1, skipped_delta=1)
            emit_progress_fn(stage=stage)
            return {"skipped": True, "evaluated": False, "pruned": True, "budget": True}
        if pruning_tracker.should_prune(indicator_combo):
            pruning_tracker.increment_pruned()
            if on_progress_tick_fn is not None:
                on_progress_tick_fn(done_delta=1, skipped_delta=1)
            emit_progress_fn(stage=stage)
            return {"skipped": True, "evaluated": False, "pruned": True}

    result = evaluate_combo_task_fn(task_payload, runtime_eval)
    append_eval_result_fn(result, task_payload)
    if pruning_tracker is not None:
        import math
        oos_metrics = result.get("oos_metrics") or {}
        score = oos_metrics.get("oos_avg_total_return_pct", 0.0)
        if score is None or (isinstance(score, float) and math.isnan(score)):
            score = 0.0
        pruning_tracker.record_result(indicator_combo, float(score))
        pruning_tracker.update_threshold()
    seen_keys.add(stripped_key)
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
    wf_train_days,
    wf_test_days,
    wf_step_days,
    wf_mode,
    wf_valid_days=0,
    fees,
    slippage_bps,
    spread_bps,
    funding_rate_daily,
    order_size_pct,
    max_concurrent_positions,
    config_sha256,
    bar_hours,
    data_start=None,
    data_end=None,
    prepare_timeframe_context_fn,
    build_walk_forward_windows_fn,
    compute_data_fingerprint_fn,
    risk_mode="fixed_pct",
):
    return {
        "timeframe": timeframe,
        "data_days": data_days,
        "data_start": data_start,
        "data_end": data_end,
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
        "cci_lookbacks": cci_lookbacks,
        "willr_lookbacks": willr_lookbacks,
        "adx_lookbacks": adx_lookbacks,
        "trix_lookbacks": trix_lookbacks,
        "dpo_lookbacks": dpo_lookbacks,
        "efi_lookbacks": efi_lookbacks,
        "vwma_lookbacks": vwma_lookbacks,
        "ultosc_periods": ultosc_periods,
        "keltner_lookbacks": keltner_lookbacks,
        "donchian_lookbacks": donchian_lookbacks,
        "ppo_fast": ppo_fast,
        "ppo_slow": ppo_slow,
        "ppo_signal": ppo_signal,
        "chop_lookbacks": chop_lookbacks,
        "init_cash_usdt": init_cash_usdt,
        "capital_mode": capital_mode,
        "wf_train_days": wf_train_days,
        "wf_test_days": wf_test_days,
        "wf_step_days": wf_step_days,
        "wf_valid_days": wf_valid_days,
        "wf_mode": wf_mode,
        "fees": fees,
        "slippage_bps": slippage_bps,
        "spread_bps": spread_bps,
        "funding_rate_daily": funding_rate_daily,
        "risk_mode": risk_mode,
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
    wf_train_days,
    wf_test_days,
    wf_step_days,
    wf_mode,
    wf_valid_days=0,
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
    risk_mode="fixed_pct",
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
        "cci_lookbacks": cci_lookbacks,
        "willr_lookbacks": willr_lookbacks,
        "adx_lookbacks": adx_lookbacks,
        "trix_lookbacks": trix_lookbacks,
        "dpo_lookbacks": dpo_lookbacks,
        "efi_lookbacks": efi_lookbacks,
        "vwma_lookbacks": vwma_lookbacks,
        "ultosc_periods": ultosc_periods,
        "keltner_lookbacks": keltner_lookbacks,
        "donchian_lookbacks": donchian_lookbacks,
        "ppo_fast": ppo_fast,
        "ppo_slow": ppo_slow,
        "ppo_signal": ppo_signal,
        "chop_lookbacks": chop_lookbacks,
        "init_cash_usdt": init_cash_usdt,
        "capital_mode": capital_mode,
        "wf_train_days": wf_train_days,
        "wf_test_days": wf_test_days,
        "wf_step_days": wf_step_days,
        "wf_valid_days": wf_valid_days,
        "wf_mode": wf_mode,
        "fees": fees,
        "slippage_bps": slippage_bps,
        "spread_bps": spread_bps,
        "funding_rate_daily": funding_rate_daily,
        "risk_mode": risk_mode,
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
    wf_train_days,
    wf_test_days,
    wf_step_days,
    wf_mode,
    wf_valid_days=0,
    indicator_param_fields,
    fees,
    slippage_bps,
    spread_bps,
    funding_rate_daily,
    order_size_pct,
    max_concurrent_positions,
    config_sha256,
    combo_seed=None,
    risk_mode="fixed_pct",
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
        "cci_lookbacks": cci_lookbacks,
        "willr_lookbacks": willr_lookbacks,
        "adx_lookbacks": adx_lookbacks,
        "trix_lookbacks": trix_lookbacks,
        "dpo_lookbacks": dpo_lookbacks,
        "efi_lookbacks": efi_lookbacks,
        "vwma_lookbacks": vwma_lookbacks,
        "ultosc_periods": ultosc_periods,
        "keltner_lookbacks": keltner_lookbacks,
        "donchian_lookbacks": donchian_lookbacks,
        "ppo_fast": ppo_fast,
        "ppo_slow": ppo_slow,
        "ppo_signal": ppo_signal,
        "chop_lookbacks": chop_lookbacks,
        "init_cash_usdt": init_cash_usdt,
        "capital_mode": capital_mode,
        "wf_train_days": wf_train_days,
        "wf_test_days": wf_test_days,
        "wf_step_days": wf_step_days,
        "wf_valid_days": wf_valid_days,
        "wf_mode": wf_mode,
        "indicator_param_fields": indicator_param_fields,
        "fees": fees,
        "slippage_bps": slippage_bps,
        "spread_bps": spread_bps,
        "funding_rate_daily": funding_rate_daily,
        "risk_mode": risk_mode,
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
        cci_lookbacks=shared["cci_lookbacks"],
        willr_lookbacks=shared["willr_lookbacks"],
        adx_lookbacks=shared["adx_lookbacks"],
        trix_lookbacks=shared["trix_lookbacks"],
        dpo_lookbacks=shared["dpo_lookbacks"],
        efi_lookbacks=shared["efi_lookbacks"],
        vwma_lookbacks=shared["vwma_lookbacks"],
        ultosc_periods=shared["ultosc_periods"],
        keltner_lookbacks=shared["keltner_lookbacks"],
        donchian_lookbacks=shared["donchian_lookbacks"],
        ppo_fast=shared["ppo_fast"],
        ppo_slow=shared["ppo_slow"],
        ppo_signal=shared["ppo_signal"],
        chop_lookbacks=shared["chop_lookbacks"],
        init_cash_usdt=shared["init_cash_usdt"],
        capital_mode=shared["capital_mode"],
        wf_train_days=shared["wf_train_days"],
        wf_test_days=shared["wf_test_days"],
        wf_step_days=shared["wf_step_days"],
        wf_mode=shared["wf_mode"],
        wf_valid_days=shared["wf_valid_days"],
        fees=shared["fees"],
        slippage_bps=shared["slippage_bps"],
        spread_bps=shared["spread_bps"],
        funding_rate_daily=shared["funding_rate_daily"],
        risk_mode=shared["risk_mode"],
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
    data_start=None,
    data_end=None,
):
    context = dict(prepare_timeframe_runtime_context)
    return _build_prepare_timeframe_runtime_kwargs(
        timeframe=timeframe,
        data_days=data_days,
        data_start=data_start,
        data_end=data_end,
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
    wf_valid_days=0,
    rsi_window,
    config_sha256,
    seen_keys,
    pending_symbol_rows,
    pending_combo_rows,
    pending_oos_symbol_rows=None,
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
    pruning_config=None,
    risk_mode="fixed_pct",
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
        "risk_mode": risk_mode,
        "order_size_pct": order_size_pct,
        "max_concurrent_positions": max_concurrent_positions,
        "init_cash_usdt": init_cash_usdt,
        "wf_train_days": wf_train_days,
        "wf_test_days": wf_test_days,
        "wf_step_days": wf_step_days,
        "wf_valid_days": wf_valid_days,
        "wf_mode": wf_mode,
        "rsi_window": rsi_window,
        "config_sha256": config_sha256,
        "seen_keys": seen_keys,
        "pending_symbol_rows": pending_symbol_rows,
        "pending_combo_rows": pending_combo_rows,
        "pending_oos_symbol_rows": pending_oos_symbol_rows,
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
        "pruning_config": pruning_config,
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
    wf_valid_days=0,
    rsi_window,
    config_sha256,
    ranking_config,
    seen_keys,
    pending_symbol_rows,
    pending_combo_rows,
    pending_oos_symbol_rows=None,
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
    pruning_config=None,
    risk_mode="fixed_pct",
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
        "risk_mode": risk_mode,
        "order_size_pct": order_size_pct,
        "max_concurrent_positions": max_concurrent_positions,
        "init_cash_usdt": init_cash_usdt,
        "wf_train_days": wf_train_days,
        "wf_test_days": wf_test_days,
        "wf_step_days": wf_step_days,
        "wf_valid_days": wf_valid_days,
        "wf_mode": wf_mode,
        "rsi_window": rsi_window,
        "config_sha256": config_sha256,
        "ranking_config": ranking_config,
        "seen_keys": seen_keys,
        "pending_symbol_rows": pending_symbol_rows,
        "pending_combo_rows": pending_combo_rows,
        "pending_oos_symbol_rows": pending_oos_symbol_rows,
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
        "pruning_config": pruning_config,
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
    pending_oos_symbol_rows=None,
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
    pruning_config=None,
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
        risk_mode=shared["risk_mode"],
        order_size_pct=shared["order_size_pct"],
        max_concurrent_positions=shared["max_concurrent_positions"],
        init_cash_usdt=shared["init_cash_usdt"],
        wf_train_days=shared["wf_train_days"],
        wf_test_days=shared["wf_test_days"],
        wf_step_days=shared["wf_step_days"],
        wf_mode=shared["wf_mode"],
        wf_valid_days=shared["wf_valid_days"],
        rsi_window=shared["rsi_window"],
        config_sha256=shared["config_sha256"],
        ranking_config=ranking_config,
        seen_keys=seen_keys,
        pending_symbol_rows=pending_symbol_rows,
        pending_combo_rows=pending_combo_rows,
        pending_oos_symbol_rows=pending_oos_symbol_rows,
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
        pruning_config=pruning_config,
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
    def _prepare_runtime_attempt(
        *,
        timeframe,
        data_days,
        data_start=None,
        data_end=None,
        stage_prefix,
        bar_hours,
        done,
        total_combos,
    ):
        prepare_kwargs = build_prepare_kwargs_from_context_fn(
            timeframe=timeframe,
            data_days=data_days,
            data_start=data_start,
            data_end=data_end,
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

    def _run_timeframe_body(
        *,
        timeframe,
        data_days,
        data_start=None,
        data_end=None,
        stage_prefix,
        bar_hours,
        timeframe_runtime,
    ):
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
    timeframe_diagnostics = []

    for tf_cfg in timeframe_configs:
        timeframe = tf_cfg["timeframe"]
        data_days = tf_cfg["days"]
        data_start = tf_cfg.get("start")
        data_end = tf_cfg.get("end")
        stage_prefix = f"{timeframe}"
        bar_hours = timeframe_to_hours_fn(timeframe)
        runtime_attempt = prepare_runtime_attempt_fn(
            timeframe=timeframe,
            data_days=data_days,
            data_start=data_start,
            data_end=data_end,
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
        timeframe_diagnostics.append(dict(timeframe_runtime.get("timeframe_diagnostics") or {}))

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
            data_start=data_start,
            data_end=data_end,
            stage_prefix=stage_prefix,
            bar_hours=bar_hours,
            timeframe_runtime=timeframe_runtime,
        )

    return {
        "timeframe_ranges": timeframe_ranges,
        "timeframe_fingerprints": timeframe_fingerprints,
        "timeframe_diagnostics": timeframe_diagnostics,
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
    wf_valid_days=0,
    rsi_window,
    config_sha256,
    seen_keys,
    pending_symbol_rows,
    pending_combo_rows,
    pending_oos_symbol_rows=None,
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
    pruning_config=None,
    risk_mode="fixed_pct",
):
    ctx = timeframe_runtime["ctx"]
    trade_symbols_tf = timeframe_runtime["trade_symbols_tf"]
    timeframe_data_fingerprint = timeframe_runtime["timeframe_data_fingerprint"]
    runtime_eval = timeframe_runtime["runtime_eval"]

    from autowfo.pruning import PruningTracker
    pruning_tracker = None
    if pruning_config and pruning_config.get("enabled", False):
        pruning_tracker = PruningTracker(pruning_config)
        if existing_combo_df is not None and not existing_combo_df.empty:
            pruning_tracker.warm_start(existing_combo_df)

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
            risk_mode=risk_mode,
            order_size_pct=order_size_pct,
            max_concurrent_positions=max_concurrent_positions,
            init_cash_usdt=init_cash_usdt,
            wf_train_days=wf_train_days,
            wf_test_days=wf_test_days,
            wf_step_days=wf_step_days,
            wf_mode=wf_mode,
            wf_valid_days=wf_valid_days,
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
            wf_valid_days=wf_valid_days,
            data_start=ctx["trade_close"].index[0],
            data_end=ctx["trade_close"].index[-1],
            rsi_window=rsi_window,
            config_sha256=config_sha256,
            timeframe_data_fingerprint=timeframe_data_fingerprint,
            ctx_total_days=ctx["total_days"],
            pending_symbol_rows=pending_symbol_rows,
            pending_combo_rows=pending_combo_rows,
            pending_oos_symbol_rows=pending_oos_symbol_rows,
            build_symbol_row_fn=_build_symbol_row,
            build_combo_row_fn=_build_combo_row,
            build_oos_symbol_row_fn=_build_oos_symbol_row,
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
            pruning_tracker=pruning_tracker,
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
            pruning_tracker=pruning_tracker,
        )
        if pruning_tracker is not None:
            summary = pruning_tracker.summary()
            print(f"[pruning] {stage}: evaluated={summary['evaluated']} pruned={summary['pruned']} threshold={summary['score_threshold']:.4f}")
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
    if pruning_tracker is not None:
        summary = pruning_tracker.summary()
        print(f"[pruning] {stage_prefix}: evaluated={summary['evaluated']} pruned={summary['pruned']} threshold={summary['score_threshold']:.4f}")


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
    run_kwargs["timeframe_diagnostics"] = timeframe_loop_result.get("timeframe_diagnostics", [])
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



