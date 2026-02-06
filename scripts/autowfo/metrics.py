"""Metric helpers extracted from run_btc_regime_sweep monolith."""

import numpy as np
import pandas as pd
import vectorbt as vbt


def _timeframe_to_hours(timeframe):
    tf = str(timeframe).strip().lower()
    try:
        if tf.endswith("m"):
            return float(tf[:-1]) / 60.0
        if tf.endswith("h"):
            return float(tf[:-1])
        if tf.endswith("d"):
            return float(tf[:-1]) * 24.0
    except ValueError:
        return np.nan
    return np.nan


def _as_series(value, index):
    if isinstance(value, pd.Series):
        return value.reindex(index)
    if isinstance(value, pd.DataFrame):
        if value.shape[1] == 1:
            return value.iloc[:, 0].reindex(index)
        return value.reindex(columns=index).iloc[0]
    arr = np.asarray(value)
    if arr.ndim == 0:
        return pd.Series([float(arr)] * len(index), index=index)
    arr = arr.reshape(-1)
    if arr.size == len(index):
        return pd.Series(arr, index=index)
    return pd.Series([np.nan] * len(index), index=index)


def _as_scalar(value):
    if isinstance(value, pd.Series):
        return float(value.iloc[0]) if not value.empty else np.nan
    if isinstance(value, pd.DataFrame):
        if value.empty:
            return np.nan
        return float(value.iloc[0, 0])
    arr = np.asarray(value)
    if arr.size == 0:
        return np.nan
    return float(arr.reshape(-1)[0])


def _calc_pf_series(pf, symbols, bar_hours):
    avg_hold_bars = pf.trades.duration.mean(group_by=False)
    avg_hold_hours = _as_series(avg_hold_bars, symbols) * bar_hours
    return {
        "total_return_pct": _as_series(pf.total_return(group_by=False) * 100, symbols),
        "total_profit": _as_series(pf.total_profit(group_by=False), symbols),
        "total_trades": _as_series(pf.trades.count(group_by=False), symbols),
        "win_rate_pct": _as_series(pf.trades.win_rate(group_by=False) * 100, symbols),
        "avg_trade_pct": _as_series(pf.trades.returns.mean(group_by=False) * 100, symbols),
        "max_drawdown_pct": _as_series(pf.drawdowns.max_drawdown(group_by=False) * -100, symbols),
        "position_coverage_pct": _as_series(pf.position_coverage(group_by=False) * 100, symbols),
        "avg_hold_hours": avg_hold_hours,
    }


def _calc_pf_combo_metrics(pf, bar_hours):
    avg_hold_bars = _as_scalar(pf.trades.duration.mean(group_by=True))
    max_drawdown = np.nan
    try:
        max_drawdown = _as_scalar(pf.drawdowns.max_drawdown(group_by=True))
    except Exception:
        try:
            combo_value = pf.value(group_by=True)
            max_drawdown = _as_scalar(vbt.Drawdowns.from_ts(combo_value).max_drawdown())
        except Exception:
            max_drawdown = np.nan
    return {
        "total_return_pct": _as_scalar(pf.total_return(group_by=True)) * 100,
        "total_profit": _as_scalar(pf.total_profit(group_by=True)),
        "total_trades": _as_scalar(pf.trades.count(group_by=True)),
        "win_rate_pct": _as_scalar(pf.trades.win_rate(group_by=True)) * 100,
        "avg_trade_pct": _as_scalar(pf.trades.returns.mean(group_by=True)) * 100,
        "max_drawdown_pct": max_drawdown * -100,
        "position_coverage_pct": _as_scalar(pf.position_coverage(group_by=True)) * 100,
        "avg_hold_hours": avg_hold_bars * bar_hours if avg_hold_bars is not None else np.nan,
    }


def _aggregate_metrics(series_metrics):
    return {
        "avg_total_return_pct": float(series_metrics["total_return_pct"].mean()),
        "avg_win_rate_pct": float(series_metrics["win_rate_pct"].mean()),
        "avg_avg_trade_pct": float(series_metrics["avg_trade_pct"].mean()),
        "avg_max_drawdown_pct": float(series_metrics["max_drawdown_pct"].mean()),
        "avg_position_coverage_pct": float(series_metrics["position_coverage_pct"].mean()),
        "avg_total_trades": float(series_metrics["total_trades"].mean()),
        "min_total_trades": float(series_metrics["total_trades"].min()),
        "avg_hold_hours": float(series_metrics["avg_hold_hours"].mean()),
    }


def _aggregate_oos_metrics(oos_rows):
    if not oos_rows:
        return {
            "oos_avg_total_return_pct": np.nan,
            "oos_avg_win_rate_pct": np.nan,
            "oos_avg_avg_trade_pct": np.nan,
            "oos_avg_max_drawdown_pct": np.nan,
            "oos_avg_position_coverage_pct": np.nan,
            "oos_avg_total_trades": np.nan,
            "oos_min_total_trades": np.nan,
            "oos_avg_hold_hours": np.nan,
            "oos_segments": 0,
        }

    def safe_nanmean(values):
        arr = np.asarray(values, dtype="float64")
        if arr.size == 0 or np.all(np.isnan(arr)):
            return np.nan
        return float(np.nanmean(arr))

    def safe_nanmin(values):
        arr = np.asarray(values, dtype="float64")
        if arr.size == 0 or np.all(np.isnan(arr)):
            return np.nan
        return float(np.nanmin(arr))

    return {
        "oos_avg_total_return_pct": safe_nanmean([row["avg_total_return_pct"] for row in oos_rows]),
        "oos_avg_win_rate_pct": safe_nanmean([row["avg_win_rate_pct"] for row in oos_rows]),
        "oos_avg_avg_trade_pct": safe_nanmean([row["avg_avg_trade_pct"] for row in oos_rows]),
        "oos_avg_max_drawdown_pct": safe_nanmean([row["avg_max_drawdown_pct"] for row in oos_rows]),
        "oos_avg_position_coverage_pct": safe_nanmean([row["avg_position_coverage_pct"] for row in oos_rows]),
        "oos_avg_total_trades": safe_nanmean([row["avg_total_trades"] for row in oos_rows]),
        "oos_min_total_trades": safe_nanmin([row["min_total_trades"] for row in oos_rows]),
        "oos_avg_daily_trades": safe_nanmean([row["avg_daily_trades"] for row in oos_rows]),
        "oos_avg_hold_hours": safe_nanmean([row["avg_hold_hours"] for row in oos_rows]),
        "oos_segments": len(oos_rows),
    }
