"""Pure combo evaluation helpers for AUTOWFO."""

from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.autowfo import engine as autowfo_engine
from scripts.autowfo import metrics as autowfo_metrics
from scripts.autowfo import portfolio as autowfo_portfolio
from scripts.autowfo import strategy as autowfo_strategy


def evaluate_combo_task(task, runtime):
    """Evaluate one combo task and return combo/symbol rows.

    This function is side-effect free: it only consumes task/runtime payloads and
    returns computed rows for the caller to persist.
    """

    regime = task["regime"]
    indicator_combo = tuple(task["indicator_combo"])
    combo_params = dict(task["combo_params"])
    vol_lookback = task["vol_lookback"]
    vol_z = task["vol_z"]
    mom_lookback = task["mom_lookback"]
    trade_mom_lookback = task["trade_mom_lookback"]
    tp_stop = task["tp_stop"]
    sl_stop = task["sl_stop"]
    max_hold = task["max_hold"]
    filter_name = task["filter_name"]
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
    rsi_window = runtime["rsi_window"]
    bar_hours = runtime["bar_hours"]
    wf_slices = runtime["wf_slices"]
    config_sha256 = runtime["config_sha256"]
    data_fingerprint = runtime["data_fingerprint"]

    vol_zscore = ctx["vol_zscore_by_lb"][vol_lookback]
    if regime["vol_mode"] == "high":
        vol_cond = vol_zscore > vol_z
    elif regime["vol_mode"] == "low":
        vol_cond = vol_zscore < -vol_z
    else:
        vol_cond = pd.Series(True, index=vol_zscore.index)

    long_regime, short_regime, regime_rsi_long, regime_rsi_short = (
        autowfo_engine._resolve_regime_signals(
            regime=regime,
            vol_cond=vol_cond,
            ctx=ctx,
            mom_lookback=mom_lookback,
        )
    )

    trade_mom = ctx["trade_mom_by_lb"][trade_mom_lookback]
    long_filter, short_filter = autowfo_engine._build_trade_mom_filters(trade_mom)
    effective_fees, effective_slippage = autowfo_engine._compute_effective_costs(
        fees=fees,
        slippage_bps=slippage_bps,
        spread_bps=spread_bps,
        funding_rate_daily=funding_rate_daily,
        max_hold=max_hold,
        bar_hours=bar_hours,
    )

    long_regime_final, short_regime_final, variant_params = autowfo_strategy._apply_indicator_combo(
        long_regime,
        short_regime,
        indicator_combo,
        combo_params,
        ctx,
    )

    pf = autowfo_portfolio._run_pf(
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
    for test_start, test_end in wf_slices:
        segment_close = ctx["trade_close"].loc[test_start:test_end]
        if segment_close.empty:
            continue
        segment_long = long_regime_final.loc[segment_close.index]
        segment_short = short_regime_final.loc[segment_close.index]
        segment_trade_mom = trade_mom.loc[segment_close.index]
        seg_long_filter, seg_short_filter = autowfo_engine._build_trade_mom_filters(
            segment_trade_mom
        )
        pf_test = autowfo_portfolio._run_pf(
            segment_close,
            segment_long,
            segment_short,
            max_hold,
            effective_fees,
            sl_stop,
            tp_stop,
            freq=timeframe,
            long_filter=seg_long_filter,
            short_filter=seg_short_filter,
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
            seg_combo_metrics = autowfo_metrics._calc_pf_combo_metrics(pf_test, bar_hours)
        else:
            seg_series = autowfo_metrics._calc_pf_series(pf_test, trade_symbols_tf, bar_hours)
            seg_agg = autowfo_metrics._aggregate_metrics(seg_series)
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
    oos_metrics = autowfo_metrics._aggregate_oos_metrics(oos_rows)

    symbol_rows = []
    for symbol in trade_symbols_tf:
        symbol_rows.append(
            autowfo_engine._build_symbol_row(
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
                data_start=ctx["trade_close"].index[0],
                data_end=ctx["trade_close"].index[-1],
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
                data_fingerprint=data_fingerprint,
            )
        )

    combo_row = autowfo_engine._build_combo_row(
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
        data_start=ctx["trade_close"].index[0],
        data_end=ctx["trade_close"].index[-1],
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
        combo_metrics=combo_metrics,
        sym_metrics=sym_metrics,
        metrics=metrics,
        ctx_total_days=ctx["total_days"],
        oos_metrics=oos_metrics,
        config_sha256=config_sha256,
        data_fingerprint=data_fingerprint,
    )
    return {
        "combo_key": task["combo_key"],
        "combo_row": combo_row,
        "symbol_rows": symbol_rows,
    }
