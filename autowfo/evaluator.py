"""Pure combo evaluation helpers for AUTOWFO."""

from __future__ import annotations

import numpy as np
import pandas as pd

from autowfo import metrics as autowfo_metrics
from autowfo import portfolio as autowfo_portfolio
from autowfo import strategy as autowfo_strategy
from autowfo import engine_runtime as autowfo_engine
from autowfo import engine_helpers
from autowfo import engine_runtime
from autowfo import engine_search
from autowfo import engine_finalize


SERIES_METRIC_FIELDS = (
    "total_return_pct",
    "total_profit",
    "total_trades",
    "win_rate_pct",
    "avg_trade_pct",
    "max_drawdown_pct",
    "position_coverage_pct",
    "avg_hold_hours",
)


def _series_to_symbol_map(series_value, symbols):
    return {symbol: float(series_value[symbol]) for symbol in symbols}


def _all_true_filter(template):
    if isinstance(template, pd.DataFrame):
        return pd.DataFrame(True, index=template.index, columns=template.columns)
    return pd.Series(True, index=template.index)


def _slice_stop_value(stop_value, index):
    if isinstance(stop_value, (pd.Series, pd.DataFrame)):
        return stop_value.loc[index]
    return stop_value


def _resolve_pf_stops(*, ctx, risk_mode, sl_stop, tp_stop):
    if str(risk_mode or "fixed_pct").lower() != "atr_multiple":
        return sl_stop, tp_stop
    trade_atr_ratio = ctx.get("trade_atr_ratio")
    if trade_atr_ratio is None:
        raise RuntimeError("trade_atr_ratio missing from timeframe context for ATR risk mode")
    atr_ratio = trade_atr_ratio.replace([np.inf, -np.inf], np.nan)
    atr_ratio = atr_ratio.where(atr_ratio > 0)
    sl_values = atr_ratio * float(sl_stop) if sl_stop is not None else None
    tp_values = atr_ratio * float(tp_stop) if tp_stop is not None else None
    return sl_values, tp_values


def _segment_combo_metrics(
    *,
    segment_close,
    segment_long,
    segment_short,
    segment_long_exit=None,
    segment_short_exit=None,
    segment_trade_mom,
    long_filter,
    short_filter,
    max_hold,
    effective_fees,
    sl_stop,
    tp_stop,
    timeframe,
    capital_mode,
    max_concurrent_positions,
    effective_slippage,
    order_size_pct,
    init_cash_btc,
    trade_symbols_tf,
    bar_hours,
    include_series=False,
):
    pf_segment = autowfo_portfolio._run_pf(
        segment_close,
        segment_long,
        segment_short,
        max_hold,
        effective_fees,
        sl_stop,
        tp_stop,
        freq=timeframe,
        long_exits=segment_long_exit,
        short_exits=segment_short_exit,
        long_filter=long_filter,
        short_filter=short_filter,
        init_cash=init_cash_btc,
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
        combo_metrics = autowfo_metrics._calc_pf_combo_metrics(pf_segment, bar_hours)
    else:
        seg_series = autowfo_metrics._calc_pf_series(pf_segment, trade_symbols_tf, bar_hours)
        seg_agg = autowfo_metrics._aggregate_metrics(seg_series)
        combo_metrics = {
            "total_return_pct": seg_agg["avg_total_return_pct"],
            "total_profit": np.nan,
            "total_trades": seg_agg["avg_total_trades"],
            "win_rate_pct": seg_agg["avg_win_rate_pct"],
            "avg_trade_pct": seg_agg["avg_avg_trade_pct"],
            "max_drawdown_pct": seg_agg["avg_max_drawdown_pct"],
            "position_coverage_pct": seg_agg["avg_position_coverage_pct"],
            "avg_hold_hours": seg_agg["avg_hold_hours"],
        }
    if include_series:
        if capital_mode == "shared":
            seg_series = autowfo_metrics._calc_pf_series(pf_segment, trade_symbols_tf, bar_hours)
        return {"combo_metrics": combo_metrics, "series_metrics": seg_series}
    return combo_metrics


def _build_strategy_mode_signals(
    *,
    strategy_mode,
    state_exit_policy,
    long_regime,
    short_regime,
    indicator_combo,
    state_indicator_combo,
    trigger_indicator_combo,
    combo_params,
    ctx,
):
    if strategy_mode != "state_trigger_entry":
        long_entries, short_entries, variant_params = autowfo_strategy._apply_indicator_combo(
            long_regime,
            short_regime,
            indicator_combo,
            combo_params,
            ctx,
        )
        return {
            "long_entries": long_entries,
            "short_entries": short_entries,
            "long_exits": None,
            "short_exits": None,
            "variant_params": variant_params,
        }

    if not state_indicator_combo or not trigger_indicator_combo:
        raise RuntimeError("state_trigger_entry requires both state and trigger indicator sets")

    variant_params = autowfo_strategy._coerce_indicator_params(indicator_combo, combo_params, ctx)
    state_long, state_short, _ = autowfo_strategy._apply_indicator_combo(
        long_regime,
        short_regime,
        state_indicator_combo,
        variant_params,
        ctx,
    )
    trigger_long, trigger_short, _ = autowfo_strategy._apply_indicator_combo(
        long_regime,
        short_regime,
        trigger_indicator_combo,
        variant_params,
        ctx,
    )
    long_entries = state_long & trigger_long
    short_entries = state_short & trigger_short

    long_exits = None
    short_exits = None
    if str(state_exit_policy or "state_reversal").strip().lower() == "state_reversal":
        long_exits = ~state_long.fillna(False)
        short_exits = ~state_short.fillna(False)

    return {
        "long_entries": long_entries,
        "short_entries": short_entries,
        "long_exits": long_exits,
        "short_exits": short_exits,
        "variant_params": variant_params,
    }


def evaluate_combo_task(task, runtime):
    """Evaluate one combo task and return combo/symbol rows.

    This function is side-effect free: it only consumes task/runtime payloads and
    returns computed rows for the caller to persist.
    """

    regime = task["regime"]
    indicator_combo = tuple(task["indicator_combo"])
    strategy_mode = str(task.get("strategy_mode") or "combo_entry").strip().lower()
    state_indicator_combo = tuple(task.get("state_indicator_combo") or ())
    trigger_indicator_combo = tuple(task.get("trigger_indicator_combo") or ())
    state_exit_policy = task.get("state_exit_policy")
    combo_params = dict(task["combo_params"])
    vol_lookback = task["vol_lookback"]
    vol_z = task["vol_z"]
    mom_lookback = task["mom_lookback"]
    trade_mom_lookback = task["trade_mom_lookback"]
    tp_stop = task["tp_stop"]
    sl_stop = task["sl_stop"]
    max_hold = task["max_hold"]
    risk_mode = task.get("risk_mode", runtime.get("risk_mode", "fixed_pct"))
    filter_name = task["filter_name"]
    filter_spec = task.get("filter_spec") or engine_runtime._parse_overlay_filter_name(filter_name)
    indicator_list = task["indicator_list"]

    ctx = runtime["ctx"]
    trade_symbols_tf = runtime["trade_symbols_tf"]
    timeframe = runtime["timeframe"]
    data_days = runtime["data_days"]
    exchange = runtime["exchange"]
    base_symbol = runtime["base_symbol"]
    capital_mode = runtime["capital_mode"]
    fees = runtime["fees"]
    slippage_bps = runtime["slippage_bps"]
    spread_bps = runtime["spread_bps"]
    funding_rate_daily = runtime["funding_rate_daily"]
    order_size_pct = runtime["order_size_pct"]
    max_concurrent_positions = runtime["max_concurrent_positions"]
    init_cash_usdt = runtime["init_cash_usdt"]
    wf_train_days = runtime["wf_train_days"]
    wf_test_days = runtime["wf_test_days"]
    wf_step_days = runtime["wf_step_days"]
    wf_mode = str(runtime.get("wf_mode", "anchored") or "anchored").lower()
    rsi_window = runtime["rsi_window"]
    bar_hours = runtime["bar_hours"]
    wf_windows = runtime.get("wf_windows")
    if wf_windows is None:
        wf_windows = []
        for test_start, test_end in runtime.get("wf_slices", []):
            wf_windows.append((None, None, None, None, test_start, test_end))
    config_sha256 = runtime["config_sha256"]
    data_fingerprint = runtime["data_fingerprint"]

    # Refine expansion may generate lookbacks outside precomputed indicator maps;
    # coerce to nearest available keys before applying indicator logic.
    combo_params = autowfo_strategy._coerce_indicator_params(indicator_combo, combo_params, ctx)

    vol_zscore = ctx["vol_zscore_by_lb"][vol_lookback]
    if regime["vol_mode"] == "high":
        vol_cond = vol_zscore > vol_z
    elif regime["vol_mode"] == "low":
        vol_cond = vol_zscore < -vol_z
    else:
        vol_cond = pd.Series(True, index=vol_zscore.index)

    long_regime, short_regime, regime_rsi_long, regime_rsi_short = (
        engine_runtime._resolve_regime_signals(
            regime=regime,
            vol_cond=vol_cond,
            ctx=ctx,
            mom_lookback=mom_lookback,
        )
    )

    trade_mom = ctx["trade_mom_by_lb"][trade_mom_lookback]
    base_long_filter, base_short_filter = engine_runtime._build_trade_mom_filters(trade_mom)
    overlay_long_filter, overlay_short_filter = engine_runtime._build_overlay_filters(
        ctx,
        filter_spec,
        trade_mom,
    )
    long_filter = base_long_filter & overlay_long_filter
    short_filter = base_short_filter & overlay_short_filter
    effective_fees, effective_slippage = engine_runtime._compute_effective_costs(
        fees=fees,
        slippage_bps=slippage_bps,
        spread_bps=spread_bps,
        funding_rate_daily=funding_rate_daily,
        max_hold=max_hold,
        bar_hours=bar_hours,
    )

    strategy_signals = _build_strategy_mode_signals(
        strategy_mode=strategy_mode,
        state_exit_policy=state_exit_policy,
        long_regime=long_regime,
        short_regime=short_regime,
        indicator_combo=indicator_combo,
        state_indicator_combo=state_indicator_combo,
        trigger_indicator_combo=trigger_indicator_combo,
        combo_params=combo_params,
        ctx=ctx,
    )
    long_regime_final = strategy_signals["long_entries"]
    short_regime_final = strategy_signals["short_entries"]
    long_exit_signal = strategy_signals["long_exits"]
    short_exit_signal = strategy_signals["short_exits"]
    variant_params = strategy_signals["variant_params"]
    pf_sl_stop, pf_tp_stop = _resolve_pf_stops(
        ctx=ctx,
        risk_mode=risk_mode,
        sl_stop=sl_stop,
        tp_stop=tp_stop,
    )

    pf = autowfo_portfolio._run_pf(
        ctx["trade_close"],
        long_regime_final,
        short_regime_final,
        max_hold,
        effective_fees,
        pf_sl_stop,
        pf_tp_stop,
        freq=timeframe,
        long_exits=long_exit_signal,
        short_exits=short_exit_signal,
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

    metrics = autowfo_metrics._calc_pf_series(pf, trade_symbols_tf, bar_hours)
    sym_metrics = autowfo_metrics._aggregate_metrics(metrics)
    if capital_mode == "shared":
        combo_metrics = autowfo_metrics._calc_pf_combo_metrics(pf, bar_hours)
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

    oos_rows = []
    oos_symbol_rows = {symbol: [] for symbol in trade_symbols_tf}
    for train_start, train_end, valid_start, valid_end, test_start, test_end in wf_windows:
        segment_close = ctx["trade_close"].loc[test_start:test_end]
        if segment_close.empty:
            continue
        segment_long = long_regime_final.loc[segment_close.index]
        segment_short = short_regime_final.loc[segment_close.index]
        segment_long_exit = (
            long_exit_signal.loc[segment_close.index] if long_exit_signal is not None else None
        )
        segment_short_exit = (
            short_exit_signal.loc[segment_close.index] if short_exit_signal is not None else None
        )
        segment_trade_mom = trade_mom.loc[segment_close.index]
        segment_overlay_long, segment_overlay_short = engine_runtime._build_overlay_filters(
            ctx,
            filter_spec,
            segment_trade_mom,
        )
        segment_base_long_filter, segment_base_short_filter = engine_runtime._build_trade_mom_filters(
            segment_trade_mom
        )
        selected_policy = "filtered"

        # Use validation segment for filter policy selection when available,
        # otherwise fall back to train segment (rolling mode only).
        policy_start = None
        policy_end = None
        if valid_start is not None and valid_end is not None and valid_start != valid_end:
            policy_start = valid_start
            policy_end = valid_end
        elif wf_mode == "rolling" and train_start is not None and train_end is not None:
            policy_start = train_start
            policy_end = train_end

        if policy_start is not None and policy_end is not None:
            policy_close = ctx["trade_close"].loc[policy_start:policy_end]
            if not policy_close.empty:
                policy_long = long_regime_final.loc[policy_close.index]
                policy_short = short_regime_final.loc[policy_close.index]
                policy_long_exit = (
                    long_exit_signal.loc[policy_close.index] if long_exit_signal is not None else None
                )
                policy_short_exit = (
                    short_exit_signal.loc[policy_close.index] if short_exit_signal is not None else None
                )
                policy_trade_mom = trade_mom.loc[policy_close.index]
                policy_overlay_long, policy_overlay_short = engine_runtime._build_overlay_filters(
                    ctx,
                    filter_spec,
                    policy_trade_mom,
                )
                policy_base_long_filter, policy_base_short_filter = engine_runtime._build_trade_mom_filters(
                    policy_trade_mom
                )
                candidate_filters = (
                    (
                        "filtered",
                        policy_base_long_filter & policy_overlay_long,
                        policy_base_short_filter & policy_overlay_short,
                    ),
                    ("unfiltered", policy_overlay_long, policy_overlay_short),
                )
                policy_sl_stop = _slice_stop_value(pf_sl_stop, policy_close.index)
                policy_tp_stop = _slice_stop_value(pf_tp_stop, policy_close.index)
                best_score = -np.inf
                for policy_name, p_long_filter, p_short_filter in candidate_filters:
                    policy_metrics = _segment_combo_metrics(
                        segment_close=policy_close,
                        segment_long=policy_long,
                        segment_short=policy_short,
                        segment_long_exit=policy_long_exit,
                        segment_short_exit=policy_short_exit,
                        segment_trade_mom=policy_trade_mom,
                        long_filter=p_long_filter,
                        short_filter=p_short_filter,
                        max_hold=max_hold,
                        effective_fees=effective_fees,
                        sl_stop=policy_sl_stop,
                        tp_stop=policy_tp_stop,
                        timeframe=timeframe,
                        capital_mode=capital_mode,
                        max_concurrent_positions=max_concurrent_positions,
                        effective_slippage=effective_slippage,
                        order_size_pct=order_size_pct,
                        init_cash_btc=ctx["init_cash_btc"],
                        trade_symbols_tf=trade_symbols_tf,
                        bar_hours=bar_hours,
                    )
                    score = float(policy_metrics.get("total_return_pct", np.nan))
                    if np.isnan(score):
                        continue
                    if score > best_score:
                        best_score = score
                        selected_policy = policy_name
        if selected_policy == "unfiltered":
            seg_long_filter = segment_overlay_long
            seg_short_filter = segment_overlay_short
        else:
            seg_long_filter = segment_base_long_filter & segment_overlay_long
            seg_short_filter = segment_base_short_filter & segment_overlay_short
        segment_sl_stop = _slice_stop_value(pf_sl_stop, segment_close.index)
        segment_tp_stop = _slice_stop_value(pf_tp_stop, segment_close.index)

        segment_metrics = _segment_combo_metrics(
            segment_close=segment_close,
            segment_long=segment_long,
            segment_short=segment_short,
            segment_long_exit=segment_long_exit,
            segment_short_exit=segment_short_exit,
            segment_trade_mom=segment_trade_mom,
            long_filter=seg_long_filter,
            short_filter=seg_short_filter,
            max_hold=max_hold,
            effective_fees=effective_fees,
            sl_stop=segment_sl_stop,
            tp_stop=segment_tp_stop,
            timeframe=timeframe,
            capital_mode=capital_mode,
            max_concurrent_positions=max_concurrent_positions,
            effective_slippage=effective_slippage,
            order_size_pct=order_size_pct,
            init_cash_btc=ctx["init_cash_btc"],
            trade_symbols_tf=trade_symbols_tf,
            bar_hours=bar_hours,
            include_series=True,
        )
        seg_combo_metrics = segment_metrics["combo_metrics"]
        seg_series_metrics = segment_metrics["series_metrics"]
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
        for symbol in trade_symbols_tf:
            sym_row = {
                "total_return_pct": float(seg_series_metrics["total_return_pct"][symbol]),
                "total_trades": float(seg_series_metrics["total_trades"][symbol]),
                "win_rate_pct": float(seg_series_metrics["win_rate_pct"][symbol]),
                "avg_trade_pct": float(seg_series_metrics["avg_trade_pct"][symbol]),
                "max_drawdown_pct": float(seg_series_metrics["max_drawdown_pct"][symbol]),
                "position_coverage_pct": float(seg_series_metrics["position_coverage_pct"][symbol]),
                "avg_hold_hours": float(seg_series_metrics["avg_hold_hours"][symbol]),
                "avg_daily_trades": float(seg_series_metrics["total_trades"][symbol]) / max(segment_days, 1),
            }
            oos_symbol_rows[symbol].append(sym_row)
    oos_metrics = autowfo_metrics._aggregate_oos_metrics(oos_rows)
    oos_symbol_metrics_values = {}
    for symbol in trade_symbols_tf:
        agg = autowfo_metrics._aggregate_oos_symbol_metrics(oos_symbol_rows.get(symbol, []))
        for field, value in agg.items():
            oos_symbol_metrics_values.setdefault(field, {})[symbol] = value

    metrics_values = {
        field: _series_to_symbol_map(metrics[field], trade_symbols_tf)
        for field in SERIES_METRIC_FIELDS
    }
    return {
        "regime_rsi_long": regime_rsi_long,
        "regime_rsi_short": regime_rsi_short,
        "variant_params": variant_params,
        "metrics_values": metrics_values,
        "combo_metrics": combo_metrics,
        "sym_metrics": sym_metrics,
        "oos_metrics": oos_metrics,
        "oos_symbol_metrics_values": oos_symbol_metrics_values,
    }

