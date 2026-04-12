"""Engine report: HTML generation, best replay, leaderboard rendering."""

import os

import numpy as np
import pandas as pd

from .engine_runtime import (
    _build_overlay_filters,
    _compute_effective_costs,
    _parse_overlay_filter_name,
    _resolve_regime_signals,
)


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
    wf_valid_days=0,
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
    <div><strong>{labels['wf_valid_days']}:</strong> {wf_valid_days}</div>
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
    wf_valid_days=0,
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
        valid_days=wf_valid_days,
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
    best_filter_spec = _parse_overlay_filter_name(best_filter_name)

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
    overlay_long_filter, overlay_short_filter = _build_overlay_filters(
        best_ctx,
        best_filter_spec,
        trade_mom,
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
        long_filter=(trade_mom > 0) & overlay_long_filter,
        short_filter=(trade_mom < 0) & overlay_short_filter,
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
                "oi_lookback": best_params.get("oi_lookback"),
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
        "oi_lookback",
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


def _mark_leaderboard_is_latest(lb_df):
    """Set ``is_latest`` flag: only the newest run per (plot_symbol, timeframe) is True."""
    if lb_df.empty:
        return lb_df
    lb_df = lb_df.copy()
    lb_df["is_latest"] = False
    group_cols = []
    if "plot_symbol" in lb_df.columns:
        group_cols.append("plot_symbol")
    if "timeframe" in lb_df.columns:
        group_cols.append("timeframe")
    if not group_cols:
        lb_df["is_latest"] = True
        return lb_df
    ts_col = "timestamp_utc" if "timestamp_utc" in lb_df.columns else None
    if ts_col:
        latest_idx = lb_df.sort_values(ts_col, ascending=False).groupby(group_cols, sort=False).head(1).index
    else:
        latest_idx = lb_df.groupby(group_cols, sort=False).tail(1).index
    lb_df.loc[latest_idx, "is_latest"] = True
    return lb_df


def _append_leaderboard_row(leaderboard_path, leaderboard_row):
    if os.path.exists(leaderboard_path):
        lb_df = pd.read_csv(leaderboard_path, low_memory=False)
        lb_df = pd.concat([lb_df, pd.DataFrame([leaderboard_row])], ignore_index=True)
    else:
        lb_df = pd.DataFrame([leaderboard_row])
    lb_df = _mark_leaderboard_is_latest(lb_df)
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


