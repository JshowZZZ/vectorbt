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


def _u(text):
    return text.encode("ascii").decode("unicode_escape")


def _html_entity(text):
    return text.encode("ascii", "xmlcharrefreplace").decode("ascii")


LABELS = {
    "report_title": _html_entity(_u("\\u56de\\u6e2c\\u5831\\u544a")),
    "summary_title": _html_entity(_u("\\u56de\\u6e2c\\u6458\\u8981")),
    "params_title": _html_entity(_u("\\u6700\\u4f73\\u53c3\\u6578")),
    "top_title": _html_entity(_u("\\u53c3\\u6578\\u6392\\u884c")),
    "chart_title": _html_entity(_u("\\u56de\\u6e2c\\u5716\\u8868")),
    "symbol": _html_entity(_u("\\u4ea4\\u6613\\u5c0d")),
    "filter_name": _html_entity(_u("\\u6307\\u6a19\\u7d44\\u5408")),
    "vol_lookback": _html_entity(_u("\\u6ce2\\u52d5\\u56de\\u770b(\\u6839)")),
    "vol_z": _html_entity(_u("\\u6ce2\\u52d5 Z \\u5206\\u6578\\u9580\\u6abb")),
    "mom_lookback": _html_entity(_u("\\u52d5\\u80fd\\u56de\\u770b(\\u6839)")),
    "trade_mom_lookback": _html_entity(_u("\\u4ea4\\u6613\\u5e63\\u52d5\\u80fd\\u56de\\u770b(\\u6839)")),
    "regime_name": _html_entity(_u("\\u7b56\\u7565\\u578b\\u614b")),
    "regime_type": _html_entity(_u("\\u8a0a\\u865f\\u985e\\u578b")),
    "vol_mode": _html_entity(_u("\\u6ce2\\u52d5\\u689d\\u4ef6")),
    "regime_rsi_long": _html_entity(_u("RSI \\u56de\\u6b78\\u591a\\u982d\\u9580\\u6abb")),
    "regime_rsi_short": _html_entity(_u("RSI \\u56de\\u6b78\\u7a7a\\u982d\\u9580\\u6abb")),
    "tp_stop": _html_entity(_u("\\u7372\\u5229%\\u51fa\\u5834")),
    "sl_stop": _html_entity(_u("\\u6b62\\u640d")),
    "max_hold": _html_entity(_u("\\u6700\\u9577\\u6301\\u6709(\\u6839)")),
    "rsi_window": _html_entity(_u("RSI \\u9031\\u671f")),
    "rsi_long": _html_entity(_u("RSI \\u591a\\u982d\\u9580\\u6abb")),
    "rsi_short": _html_entity(_u("RSI \\u7a7a\\u982d\\u9580\\u6abb")),
    "bb_width": _html_entity(_u("\\u5e03\\u6797\\u5e36\\u5bec\\u5ea6\\u9580\\u6abb")),
    "atr_ratio": _html_entity(_u("ATR/\\u50f9\\u683c\\u9580\\u6abb")),
    "total_return_pct": _html_entity(_u("\\u7e3d\\u5831\\u916c(%)")),
    "total_profit": _html_entity(_u("\\u7e3d\\u76c8\\u5229")),
    "total_trades": _html_entity(_u("\\u7e3d\\u4ea4\\u6613\\u7b46\\u6578")),
    "win_rate_pct": _html_entity(_u("\\u52dd\\u7387(%)")),
    "avg_trade_pct": _html_entity(_u("\\u5e73\\u5747\\u6bcf\\u7b46(%)")),
    "max_drawdown_pct": _html_entity(_u("\\u6700\\u5927\\u56de\\u64a4(%)")),
    "position_coverage_pct": _html_entity(_u("\\u6301\\u5009\\u8986\\u84cb\\u7387(%)")),
    "avg_total_return_pct": _html_entity(_u("\\u5e73\\u5747\\u7e3d\\u5831\\u916c(%)")),
    "avg_win_rate_pct": _html_entity(_u("\\u5e73\\u5747\\u52dd\\u7387(%)")),
    "avg_avg_trade_pct": _html_entity(_u("\\u5e73\\u5747\\u6bcf\\u7b46(%)")),
    "avg_max_drawdown_pct": _html_entity(_u("\\u5e73\\u5747\\u6700\\u5927\\u56de\\u64a4(%)")),
    "avg_position_coverage_pct": _html_entity(_u("\\u5e73\\u5747\\u6301\\u5009\\u8986\\u84cb\\u7387(%)")),
    "avg_total_trades": _html_entity(_u("\\u5e73\\u5747\\u7e3d\\u4ea4\\u6613\\u7b46\\u6578")),
    "min_total_trades": _html_entity(_u("\\u6700\\u5c0f\\u7e3d\\u4ea4\\u6613\\u7b46\\u6578")),
    "avg_daily_trades": _html_entity(_u("\\u5e73\\u5747\\u6bcf\\u65e5\\u4ea4\\u6613\\u6b21\\u6578")),
    "avg_hold_hours": _html_entity(_u("\\u5e73\\u5747\\u6301\\u5009(\\u5c0f\\u6642)")),
    "ma_fast": _html_entity(_u("MA \\u5feb\\u7dda")),
    "ma_slow": _html_entity(_u("MA \\u6162\\u7dda")),
    "macd_hist_ratio": _html_entity(_u("MACD \\u67f1\\u72c0\\u6bd4\\u7387\\u9580\\u6abb")),
    "stoch_long": _html_entity(_u("KD \\u591a\\u982d\\u9580\\u6abb")),
    "stoch_short": _html_entity(_u("KD \\u7a7a\\u982d\\u9580\\u6abb")),
    "obv_lookback": _html_entity(_u("OBV \\u56de\\u770b(\\u6839)")),
    "volume_lookback": _html_entity(_u("\\u91cf\\u80fd\\u56de\\u770b(\\u6839)")),
    "volume_z": _html_entity(_u("\\u91cf\\u80fd Z \\u5206\\u6578\\u9580\\u6abb")),
    "roc_lookback": _html_entity(_u("ROC \\u56de\\u770b(\\u6839)")),
    "roc_threshold": _html_entity(_u("ROC \\u9580\\u6abb")),
    "mfi_long": _html_entity(_u("MFI \\u591a\\u982d\\u9580\\u6abb")),
    "mfi_short": _html_entity(_u("MFI \\u7a7a\\u982d\\u9580\\u6abb")),
    "cmf_lookback": _html_entity(_u("CMF \\u56de\\u770b(\\u6839)")),
    "cmf_threshold": _html_entity(_u("CMF \\u9580\\u6abb")),
    "vroc_lookback": _html_entity(_u("\\u91cf\\u80fd\\u8b8a\\u5316\\u7387 \\u56de\\u770b(\\u6839)")),
    "vroc_threshold": _html_entity(_u("\\u91cf\\u80fd\\u8b8a\\u5316\\u7387 \\u9580\\u6abb")),
    "ad_lookback": _html_entity(_u("A/D \\u56de\\u770b(\\u6839)")),
    "oos_avg_total_return_pct": _html_entity(_u("\\u9a57\\u8b49\\u5e73\\u5747\\u7e3d\\u5831\\u916c(%)")),
    "oos_avg_win_rate_pct": _html_entity(_u("\\u9a57\\u8b49\\u5e73\\u5747\\u52dd\\u7387(%)")),
    "oos_avg_avg_trade_pct": _html_entity(_u("\\u9a57\\u8b49\\u5e73\\u5747\\u6bcf\\u7b46(%)")),
    "oos_avg_max_drawdown_pct": _html_entity(_u("\\u9a57\\u8b49\\u5e73\\u5747\\u6700\\u5927\\u56de\\u64a4(%)")),
    "oos_avg_position_coverage_pct": _html_entity(_u("\\u9a57\\u8b49\\u5e73\\u5747\\u6301\\u5009\\u8986\\u84cb\\u7387(%)")),
    "oos_avg_total_trades": _html_entity(_u("\\u9a57\\u8b49\\u5e73\\u5747\\u4ea4\\u6613\\u7b46\\u6578")),
    "oos_min_total_trades": _html_entity(_u("\\u9a57\\u8b49\\u6700\\u5c0f\\u4ea4\\u6613\\u7b46\\u6578")),
    "oos_avg_daily_trades": _html_entity(_u("\\u9a57\\u8b49\\u5e73\\u5747\\u6bcf\\u65e5\\u4ea4\\u6613\\u6b21\\u6578")),
    "oos_avg_hold_hours": _html_entity(_u("\\u9a57\\u8b49\\u5e73\\u5747\\u6301\\u5009(\\u5c0f\\u6642)")),
    "oos_segments": _html_entity(_u("\\u9a57\\u8b49\\u5340\\u6bb5\\u6578")),
    "data_range": _html_entity(_u("\\u8cc7\\u6599\\u5340\\u9593")),
    "scan_timeframes": _html_entity(_u("\\u6383\\u63cf\\u6642\\u9593\\u6846\\u67b6")),
    "timeframe": _html_entity(_u("\\u6642\\u9593\\u6846\\u67b6")),
    "data_days": _html_entity(_u("\\u8cc7\\u6599\\u5929\\u6578")),
    "base_symbol": _html_entity(_u("\\u57fa\\u6e96\\u5e63\\u5c0d")),
    "trade_symbols": _html_entity(_u("\\u4ea4\\u6613\\u5e63\\u5c0d")),
    "capital_mode": _html_entity(_u("\\u8cc7\\u91d1\\u6a21\\u5f0f")),
    "run_id": _html_entity(_u("\\u57f7\\u884c\\u7de8\\u865f")),
    "timestamp_utc": _html_entity(_u("UTC \\u6642\\u9593")),
    "report": _html_entity(_u("\\u5831\\u544a")),
    "min_trades_filter": _html_entity(_u("\\u6700\\u5c0f\\u4ea4\\u6613\\u7b46\\u6578\\u9580\\u6abb")),
    "min_trades_target": _html_entity(_u("\\u76ee\\u6a19\\u6700\\u5c0f\\u4ea4\\u6613\\u7b46\\u6578")),
    "min_avg_daily_trades_filter": _html_entity(_u("\\u5e73\\u5747\\u6bcf\\u65e5\\u4ea4\\u6613\\u6b21\\u6578\\u9580\\u6abb")),
    "min_avg_daily_trades_target": _html_entity(_u("\\u76ee\\u6a19\\u5e73\\u5747\\u6bcf\\u65e5\\u4ea4\\u6613\\u6b21\\u6578")),
    "history_title": _html_entity(_u("\\u6b77\\u53f2\\u7d2f\\u7a4d")),
    "leaderboard_title": _html_entity(_u("\\u6b77\\u53f2\\u6392\\u884c\\u699c")),
    "recent_runs_title": _html_entity(_u("\\u6700\\u8fd1\\u57f7\\u884c\\u7d00\\u9304")),
    "plot_symbol": _html_entity(_u("\\u5716\\u8868\\u5e63\\u5c0d")),
    "oos_summary_title": _html_entity(_u("\\u9a57\\u8b49\\u6458\\u8981")),
    "wf_train_days": _html_entity(_u("\\u8a13\\u7df4\\u671f\\u9593(\\u5929)")),
    "wf_test_days": _html_entity(_u("\\u9a57\\u8b49\\u671f\\u9593(\\u5929)")),
    "wf_step_days": _html_entity(_u("\\u524d\\u9032\\u6b65\\u9577(\\u5929)")),
    "wf_segments": _html_entity(_u("\\u9a57\\u8b49\\u5340\\u6bb5\\u6578")),
    "status_title": _html_entity(_u("\\u57f7\\u884c\\u72c0\\u614b")),
    "status_stage": _html_entity(_u("\\u968e\\u6bb5")),
    "status_total": _html_entity(_u("\\u7e3d\\u7d44\\u5408")),
    "status_done": _html_entity(_u("\\u5df2\\u5b8c\\u6210")),
    "status_remaining": _html_entity(_u("\\u5269\\u9918")),
    "status_skipped": _html_entity(_u("\\u5df2\\u8df3\\u904e")),
    "status_percent": _html_entity(_u("\\u9032\\u5ea6(%)")),
    "status_elapsed": _html_entity(_u("\\u7d93\\u904e\\u6642\\u9593")),
    "status_eta": _html_entity(_u("\\u9810\\u8a08\\u5269\\u9918")),
    "status_updated": _html_entity(_u("\\u66f4\\u65b0\\u6642\\u9593")),
    "init_cash_usdt": _html_entity(_u("\\u8d77\\u59cb\\u8cc7\\u91d1(USDT)")),
    "order_size_pct": _html_entity(_u("\\u55ae\\u7b46\\u4f4f\\u5009(\\u6bd4\\u4f8b)")),
    "max_concurrent_positions": _html_entity(_u("\\u6700\\u5927\\u540c\\u6642\\u6301\\u5009")),
    "indicator_list": _html_entity(_u("\\u6307\\u6a19\\u6e05\\u55ae")),
    "indicator_count": _html_entity(_u("\\u6307\\u6a19\\u6578\\u91cf")),
    "slippage_bps": _html_entity(_u("\\u6ed1\\u9ede(bps)")),
    "spread_bps": _html_entity(_u("\\u50f9\\u5dee(bps)")),
    "funding_rate_daily": _html_entity(_u("\\u8cc7\\u91d1\\u8cbb\\u7387/\\u65e5")),
    "sym_avg_total_return_pct": _html_entity(_u("\\u5e63\\u5c0d\\u5e73\\u5747\\u7e3d\\u5831\\u916c(%)")),
    "sym_avg_win_rate_pct": _html_entity(_u("\\u5e63\\u5c0d\\u5e73\\u5747\\u52dd\\u7387(%)")),
    "sym_avg_avg_trade_pct": _html_entity(_u("\\u5e63\\u5c0d\\u5e73\\u5747\\u6bcf\\u7b46(%)")),
    "sym_avg_max_drawdown_pct": _html_entity(_u("\\u5e63\\u5c0d\\u5e73\\u5747\\u6700\\u5927\\u56de\\u64a4(%)")),
    "sym_avg_position_coverage_pct": _html_entity(_u("\\u5e63\\u5c0d\\u5e73\\u5747\\u6301\\u5009\\u8986\\u84cb\\u7387(%)")),
    "sym_avg_total_trades": _html_entity(_u("\\u5e63\\u5c0d\\u5e73\\u5747\\u4ea4\\u6613\\u7b46\\u6578")),
    "sym_min_total_trades": _html_entity(_u("\\u5e63\\u5c0d\\u6700\\u5c0f\\u4ea4\\u6613\\u7b46\\u6578")),
    "sym_avg_daily_trades": _html_entity(_u("\\u5e63\\u5c0d\\u5e73\\u5747\\u6bcf\\u65e5\\u4ea4\\u6613\\u6b21\\u6578")),
    "sym_avg_hold_hours": _html_entity(_u("\\u5e63\\u5c0d\\u5e73\\u5747\\u6301\\u5009(\\u5c0f\\u6642)")),
}

FILTER_NAME_MAP = {
    "vol_mom": _html_entity(_u("\\u6ce2\\u52d5+\\u52d5\\u80fd")),
    "vol_mom_rsi": _html_entity(_u("\\u6ce2\\u52d5+\\u52d5\\u80fd+RSI")),
    "vol_mom_bb": _html_entity(_u("\\u6ce2\\u52d5+\\u52d5\\u80fd+\\u5e03\\u6797\\u5e36\\u5bec\\u5ea6")),
    "vol_mom_atr": _html_entity(_u("\\u6ce2\\u52d5+\\u52d5\\u80fd+ATR/\\u50f9\\u683c")),
    "vol_mom_rsi_bb": _html_entity(_u("\\u6ce2\\u52d5+\\u52d5\\u80fd+RSI+\\u5e03\\u6797\\u5e36\\u5bec\\u5ea6")),
    "vol_mom_rsi_atr": _html_entity(_u("\\u6ce2\\u52d5+\\u52d5\\u80fd+RSI+ATR/\\u50f9\\u683c")),
    "vol_mom_ma": _html_entity(_u("\\u6ce2\\u52d5+\\u52d5\\u80fd+MA")),
    "vol_mom_macd": _html_entity(_u("\\u6ce2\\u52d5+\\u52d5\\u80fd+MACD")),
    "vol_mom_stoch": _html_entity(_u("\\u6ce2\\u52d5+\\u52d5\\u80fd+KD")),
    "vol_mom_obv": _html_entity(_u("\\u6ce2\\u52d5+\\u52d5\\u80fd+OBV")),
    "vol_mom_volume": _html_entity(_u("\\u6ce2\\u52d5+\\u52d5\\u80fd+\\u91cf\\u80fd")),
    "none": _html_entity(_u("\\u7121\\u984d\\u5916\\u6ffe\\u7db2")),
}

INDICATOR_LABELS = {
    "volume_z": _html_entity(_u("\\u91cf\\u80fdZ")),
    "obv_roc": _html_entity(_u("OBV \\u8da8\\u52e2")),
    "cmf": _html_entity(_u("\\u8cc7\\u91d1\\u6d41\\u5411(CMF)")),
    "mfi": _html_entity(_u("\\u8cc7\\u91d1\\u6d41\\u6307\\u6a19(MFI)")),
    "vroc": _html_entity(_u("\\u91cf\\u80fd\\u8b8a\\u5316\\u7387")),
    "ad": _html_entity(_u("A/D \\u8da8\\u52e2")),
    "rsi": _html_entity(_u("RSI")),
    "roc": _html_entity(_u("ROC")),
    "macd_hist": _html_entity(_u("MACD \\u67f1\\u72c0")),
    "stoch": _html_entity(_u("KD")),
    "bb_width": _html_entity(_u("\\u5e03\\u6797\\u5e36\\u5bec\\u5ea6")),
    "atr_ratio": _html_entity(_u("ATR/\\u50f9\\u683c")),
    "ma_trend": _html_entity(_u("MA \\u8da8\\u52e2")),
}

INDICATOR_META = {
    "volume_z": {"label": INDICATOR_LABELS["volume_z"], "category": "volume"},
    "obv_roc": {"label": INDICATOR_LABELS["obv_roc"], "category": "volume"},
    "cmf": {"label": INDICATOR_LABELS["cmf"], "category": "volume"},
    "mfi": {"label": INDICATOR_LABELS["mfi"], "category": "volume"},
    "vroc": {"label": INDICATOR_LABELS["vroc"], "category": "volume"},
    "ad": {"label": INDICATOR_LABELS["ad"], "category": "volume"},
    "rsi": {"label": INDICATOR_LABELS["rsi"], "category": "momentum"},
    "roc": {"label": INDICATOR_LABELS["roc"], "category": "momentum"},
    "macd_hist": {"label": INDICATOR_LABELS["macd_hist"], "category": "momentum"},
    "stoch": {"label": INDICATOR_LABELS["stoch"], "category": "momentum"},
    "bb_width": {"label": INDICATOR_LABELS["bb_width"], "category": "volatility"},
    "atr_ratio": {"label": INDICATOR_LABELS["atr_ratio"], "category": "volatility"},
    "ma_trend": {"label": INDICATOR_LABELS["ma_trend"], "category": "volatility"},
}

INDICATOR_PARAM_FIELDS = [
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


def _indicator_combo_label(combo_keys):
    labels = []
    for key in combo_keys:
        labels.append(INDICATOR_META.get(key, {}).get("label", key))
    return "+".join(labels)


def _format_indicator_list(value):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    keys = [k for k in str(value).split(",") if k]
    if not keys:
        return str(value)
    return _indicator_combo_label(keys)

REGIME_NAME_MAP = {
    "trend_high": _html_entity(_u("\\u8da8\\u52e2(\\u9ad8\\u6ce2\\u52d5)")),
    "trend_low": _html_entity(_u("\\u8da8\\u52e2(\\u4f4e\\u6ce2\\u52d5)")),
    "trend_any": _html_entity(_u("\\u8da8\\u52e2(\\u4e0d\\u9650\\u6ce2\\u52d5)")),
    "rsi_revert_low": _html_entity(_u("RSI \\u56de\\u6b78(\\u4f4e\\u6ce2\\u52d5)")),
    "rsi_revert_high": _html_entity(_u("RSI \\u56de\\u6b78(\\u9ad8\\u6ce2\\u52d5)")),
    "bb_revert_low": _html_entity(_u("\\u5e03\\u6797\\u56de\\u6b78(\\u4f4e\\u6ce2\\u52d5)")),
    "bb_revert_high": _html_entity(_u("\\u5e03\\u6797\\u56de\\u6b78(\\u9ad8\\u6ce2\\u52d5)")),
    "bb_breakout_high": _html_entity(_u("\\u5e03\\u6797\\u7a81\\u7834(\\u9ad8\\u6ce2\\u52d5)")),
}

REGIME_TYPE_MAP = {
    "trend": _html_entity(_u("\\u8da8\\u52e2")),
    "rsi_revert": _html_entity(_u("RSI \\u56de\\u6b78")),
    "bb_revert": _html_entity(_u("\\u5e03\\u6797\\u56de\\u6b78")),
    "bb_breakout": _html_entity(_u("\\u5e03\\u6797\\u7a81\\u7834")),
}


def _df_to_html(df, columns, label_map):
    view = df[columns].copy()
    if "filter_name" in view.columns:
        view["filter_name"] = view["filter_name"].map(lambda x: FILTER_NAME_MAP.get(x, x))
    if "indicator_list" in view.columns:
        view["indicator_list"] = view["indicator_list"].map(_format_indicator_list)
    if "regime_name" in view.columns:
        view["regime_name"] = view["regime_name"].map(lambda x: REGIME_NAME_MAP.get(x, x))
    if "regime_type" in view.columns:
        view["regime_type"] = view["regime_type"].map(lambda x: REGIME_TYPE_MAP.get(x, x))
    for col in view.columns:
        if pd.api.types.is_numeric_dtype(view[col]):
            view[col] = view[col].round(4)
    view = view.fillna("")
    rename = {col: label_map.get(col, col) for col in columns}
    view.rename(columns=rename, inplace=True)
    return view.to_html(index=False, escape=False)


def _normalize_index(df):
    view = df.copy()
    view.index = pd.to_datetime(view.index, utc=True).tz_convert(None)
    view = view[~view.index.duplicated(keep="last")].sort_index()
    return view


def _format_duration(seconds):
    if seconds is None or np.isnan(seconds):
        return ""
    seconds = int(max(0, seconds))
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


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
    if value is None:
        return None
    if isinstance(value, float) and np.isnan(value):
        return None
    if isinstance(value, (float, np.floating)):
        return round(float(value), 6)
    if isinstance(value, (int, np.integer)):
        return int(value)
    return value


def _combo_key_from_dict(values):
    parts = []
    for field in COMBO_KEY_FIELDS:
        parts.append(f"{field}={_normalize_key_value(values.get(field))}")
    return "|".join(parts)


def _safe_int(value, default):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return default
    return int(value)


def _safe_float(value, default):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return default
    return float(value)


def _pick_series_from_map(series_map, key, default_key=None):
    if not series_map:
        return pd.Series(dtype=float), None
    if key in series_map:
        return series_map[key], key
    if default_key is not None and default_key in series_map:
        return series_map[default_key], default_key
    try:
        target = float(key)
        keys = sorted(series_map.keys(), key=lambda k: abs(float(k) - target))
    except Exception:
        keys = list(series_map.keys())
    chosen = keys[0]
    return series_map[chosen], chosen


def _coerce_indicator_params(combo_keys, params, ctx):
    params = params.copy()

    def _coerce_lb(field, data_map):
        if field not in params or params[field] is None or not data_map:
            return
        try:
            lb = int(params[field])
        except Exception:
            lb = params[field]
        if lb in data_map:
            return
        try:
            keys = sorted(data_map.keys(), key=lambda k: abs(float(k) - float(lb)))
        except Exception:
            keys = list(data_map.keys())
        if keys:
            params[field] = keys[0]

    if "obv_roc" in combo_keys:
        _coerce_lb("obv_lookback", ctx.get("obv_roc_by_lb"))
    if "volume_z" in combo_keys:
        _coerce_lb("volume_lookback", ctx.get("volume_zscore_by_lb"))
    if "roc" in combo_keys:
        _coerce_lb("roc_lookback", ctx.get("roc_by_lb"))
    if "cmf" in combo_keys:
        _coerce_lb("cmf_lookback", ctx.get("cmf_by_window"))
    if "vroc" in combo_keys:
        _coerce_lb("vroc_lookback", ctx.get("vroc_by_lb"))
    if "ad" in combo_keys:
        _coerce_lb("ad_lookback", ctx.get("ad_roc_by_lb"))
    if "ma_trend" in combo_keys:
        fast = params.get("ma_fast")
        slow = params.get("ma_slow")
        pairs = ctx.get("ma_trend_by_pair", {})
        if pairs and (fast, slow) not in pairs:
            try:
                target = (float(fast), float(slow))
                keys = sorted(
                    pairs.keys(),
                    key=lambda k: abs(float(k[0]) - target[0]) + abs(float(k[1]) - target[1]),
                )
            except Exception:
                keys = list(pairs.keys())
            if keys:
                params["ma_fast"], params["ma_slow"] = keys[0]
    return params


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
    if not os.path.exists(path):
        return
    try:
        df = pd.read_csv(path, low_memory=False)
    except Exception:
        return
    missing = [col for col in columns if col not in df.columns]
    if not missing:
        return
    for col in missing:
        df[col] = np.nan
    df = df.reindex(columns=[col for col in columns if col in df.columns])
    df.to_csv(path, index=False)


def _append_rows(path, rows, columns):
    if not rows:
        return 0
    file_exists = os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        if not file_exists:
            writer.writeheader()
        for row in rows:
            record = {col: row.get(col, None) for col in columns}
            writer.writerow(record)
    return len(rows)


def _ensure_db_schema(db_path, table, columns, indexes=None):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        col_defs = ", ".join([f'"{col}" TEXT' for col in columns])
        conn.execute(
            f'CREATE TABLE IF NOT EXISTS {table} '
            f'(id INTEGER PRIMARY KEY AUTOINCREMENT, '
            f'created_utc TEXT DEFAULT CURRENT_TIMESTAMP, '
            f'{col_defs})'
        )
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if "created_utc" not in existing:
            conn.execute(f'ALTER TABLE {table} ADD COLUMN "created_utc" TEXT')
        for col in columns:
            if col not in existing:
                conn.execute(f'ALTER TABLE {table} ADD COLUMN "{col}" TEXT')
        if indexes:
            for idx_name, idx_cols in indexes:
                cols_sql = ", ".join([f'"{col}"' for col in idx_cols])
                conn.execute(f'CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({cols_sql})')
        conn.commit()
    finally:
        conn.close()


def _append_db_rows(db_path, table, rows, columns):
    if not rows:
        return 0
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        col_sql = ", ".join([f'"{col}"' for col in columns])
        placeholders = ", ".join(["?"] * len(columns))
        sql = f"INSERT INTO {table} ({col_sql}) VALUES ({placeholders})"
        values = [
            tuple(_normalize_key_value(row.get(col, None)) for col in columns)
            for row in rows
        ]
        conn.executemany(sql, values)
        conn.commit()
    finally:
        conn.close()
    return len(rows)


def _write_status(status_json_path, status_html_path, payload):
    with open(status_json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="5">
  <title>{LABELS['status_title']}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 20px; color: #111; }}
    table {{ border-collapse: collapse; width: 100%; max-width: 680px; }}
    th, td {{ border: 1px solid #ddd; padding: 6px 8px; text-align: left; }}
    th {{ background: #f3f3f3; }}
  </style>
</head>
<body>
  <h1>{LABELS['status_title']}</h1>
  <table>
    <tr><th>{LABELS['run_id']}</th><td>{payload.get('run_id','')}</td></tr>
    <tr><th>{LABELS['status_stage']}</th><td>{payload.get('stage','')}</td></tr>
    <tr><th>{LABELS['status_total']}</th><td>{payload.get('total','')}</td></tr>
    <tr><th>{LABELS['status_done']}</th><td>{payload.get('done','')}</td></tr>
    <tr><th>{LABELS['status_remaining']}</th><td>{payload.get('remaining','')}</td></tr>
    <tr><th>{LABELS['status_skipped']}</th><td>{payload.get('skipped','')}</td></tr>
    <tr><th>{LABELS['status_percent']}</th><td>{payload.get('percent','')}</td></tr>
    <tr><th>{LABELS['status_elapsed']}</th><td>{payload.get('elapsed','')}</td></tr>
    <tr><th>{LABELS['status_eta']}</th><td>{payload.get('eta','')}</td></tr>
    <tr><th>{LABELS['status_updated']}</th><td>{payload.get('updated','')}</td></tr>
  </table>
</body>
</html>
"""
    with open(status_html_path, "w", encoding="utf-8") as f:
        f.write(html)


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
    start = f"{data_days} days ago UTC"
    end = "now UTC"
    all_symbols = [base_symbol] + trade_symbols
    symbol_data = {}
    for symbol in all_symbols:
        try:
            symbol_data[symbol] = _load_or_update_symbol(
                symbol, exchange, timeframe, start, end, cache_dir, cache_format
            )
        except Exception as exc:
            print(f"[warn] skip {symbol}: {exc}")

    # Keep the effective window close to requested `data_days` even when cache files
    # have grown older than the latest run configuration.
    try:
        latest_end = min(df.index.max() for df in symbol_data.values() if not df.empty)
        if pd.notna(latest_end):
            window_start = latest_end - pd.Timedelta(days=int(data_days))
            for symbol, df in list(symbol_data.items()):
                clipped = df.loc[df.index >= window_start]
                if not clipped.empty:
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

    trade_close = trade_close.loc[common_index]
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

    data_range = f"{trade_close.index[0]} -> {trade_close.index[-1]}"

    return {
        "timeframe": timeframe,
        "data_days": data_days,
        "start": start,
        "end": end,
        "trade_symbols": trade_symbols,
        "trade_close": trade_close,
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
        "ma_trend_by_pair": ma_trend_by_pair,
        "macd_hist_ratio_series": macd_hist_ratio_series,
        "stoch_k": stoch_k,
        "obv_roc_by_lb": obv_roc_by_lb,
        "volume_zscore_by_lb": volume_zscore_by_lb,
        "roc_by_lb": roc_by_lb,
        "cmf_by_window": cmf_by_window,
        "mfi_by_window": mfi_by_window,
        "mfi_window": mfi_window,
        "vroc_by_lb": vroc_by_lb,
        "ad_roc_by_lb": ad_roc_by_lb,
        "data_range": data_range,
    }


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


def _download_symbol_ohlcv(symbol, exchange, timeframe, start, end, show_progress):
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
    return _normalize_index(df)


def _load_or_update_symbol(symbol, exchange, timeframe, start, end, cache_dir, cache_format):
    os.makedirs(cache_dir, exist_ok=True)
    cache_name = f"{exchange}_{symbol.replace('/', '-')}_{timeframe}.{cache_format}"
    cache_path = os.path.join(cache_dir, cache_name)
    if os.path.exists(cache_path):
        df = _read_cache(cache_path, cache_format)
        df = _normalize_index(df)
        last_ts = df.index.max()
        try:
            step = pd.Timedelta(timeframe)
        except ValueError:
            step = pd.Timedelta("1h")
        update_start = last_ts + step
        now_ts = pd.Timestamp.now(tz="UTC").tz_convert(None)
        if update_start < now_ts:
            try:
                new_df = _download_symbol_ohlcv(
                    symbol,
                    exchange,
                    timeframe,
                    start=update_start.isoformat(),
                    end=end,
                    show_progress=False,
                )
            except Exception as exc:
                print(f"[warn] update failed for {symbol}, using cached data: {exc}")
                return df
            if not new_df.empty:
                df = pd.concat([df, new_df], axis=0)
                df = df[~df.index.duplicated(keep="last")].sort_index()
                _write_cache(df, cache_path, cache_format)
    else:
        df = _download_symbol_ohlcv(symbol, exchange, timeframe, start, end, show_progress=True)
        _write_cache(df, cache_path, cache_format)
    return df


def _build_walk_forward_slices(index, train_days, test_days, step_days):
    if index.empty:
        return []
    train_delta = pd.Timedelta(days=train_days)
    test_delta = pd.Timedelta(days=test_days)
    step_delta = pd.Timedelta(days=step_days)
    cursor = index[0]
    end = index[-1]
    slices = []
    while True:
        train_end = cursor + train_delta
        test_end = train_end + test_delta
        if test_end > end:
            break
        slices.append((train_end, test_end))
        cursor = cursor + step_delta
    return slices


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


def _plot_portfolio(pf, plot_symbol):
    try:
        return pf.plot(column=plot_symbol, group_by=False, silence_warnings=True)
    except Exception as exc:
        print(f"[warn] plot failed, fallback to value plot: {exc}")
        try:
            value = pf.value()
            if isinstance(value, pd.DataFrame) and plot_symbol in value.columns:
                return value[plot_symbol].vbt.plot()
            return value.vbt.plot()
        except Exception as exc2:
            print(f"[warn] value plot failed, fallback to total return: {exc2}")
            return pf.total_return().vbt.plot()


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


def _build_indicator_param_options_coarse():
    return {
        "volume_z": [
            {"volume_lookback": 12, "volume_z": 0.6},
            {"volume_lookback": 24, "volume_z": 0.9},
        ],
        "obv_roc": [
            {"obv_lookback": 12},
            {"obv_lookback": 24},
        ],
        "cmf": [
            {"cmf_lookback": 20, "cmf_threshold": 0.05},
            {"cmf_lookback": 30, "cmf_threshold": 0.08},
        ],
        "mfi": [
            {"mfi_long": 70, "mfi_short": 30},
            {"mfi_long": 80, "mfi_short": 20},
        ],
        "vroc": [
            {"vroc_lookback": 12, "vroc_threshold": 0.5},
            {"vroc_lookback": 24, "vroc_threshold": 1.0},
        ],
        "ad": [
            {"ad_lookback": 20},
            {"ad_lookback": 40},
        ],
        "rsi": [
            {"rsi_long": 55, "rsi_short": 45},
            {"rsi_long": 60, "rsi_short": 40},
        ],
        "roc": [
            {"roc_lookback": 6, "roc_threshold": 0.01},
            {"roc_lookback": 12, "roc_threshold": 0.02},
        ],
        "macd_hist": [
            {"macd_hist_ratio": 0.001},
            {"macd_hist_ratio": 0.002},
        ],
        "stoch": [
            {"stoch_long": 80, "stoch_short": 20},
            {"stoch_long": 70, "stoch_short": 30},
        ],
        "bb_width": [
            {"bb_width": 0.04},
            {"bb_width": 0.06},
        ],
        "atr_ratio": [
            {"atr_ratio": 0.006},
            {"atr_ratio": 0.01},
        ],
        "ma_trend": [
            {"ma_fast": 10, "ma_slow": 30},
            {"ma_fast": 20, "ma_slow": 50},
        ],
    }


def _expand_float(base, step, min_value=None, max_value=None):
    values = []
    for delta in (-step, 0, step):
        if base is None or (isinstance(base, float) and np.isnan(base)):
            continue
        val = float(base) + float(delta)
        if min_value is not None and val < min_value:
            continue
        if max_value is not None and val > max_value:
            continue
        values.append(round(val, 6))
    return sorted(set(values))


def _expand_int(base, step, min_value=1):
    values = []
    for delta in (-step, 0, step):
        if base is None or (isinstance(base, float) and np.isnan(base)):
            continue
        val = int(round(float(base))) + int(delta)
        if val < min_value:
            continue
        values.append(int(val))
    return sorted(set(values))


def _expand_lookback_list(values, step, min_value=2):
    expanded = set()
    for value in values:
        for delta in (-step, 0, step):
            try:
                val = int(round(float(value))) + int(delta)
            except (TypeError, ValueError):
                continue
            if val < min_value:
                continue
            expanded.add(val)
    return sorted(expanded)


def _expand_pair(base_long, base_short, step, min_value=0, max_value=100):
    longs = _expand_int(base_long, step, min_value=min_value)
    shorts = _expand_int(base_short, step, min_value=min_value)
    pairs = []
    for long_v in longs:
        for short_v in shorts:
            if long_v <= short_v:
                continue
            if long_v > max_value or short_v > max_value:
                continue
            pairs.append((long_v, short_v))
    return sorted(set(pairs))


def _indicator_defaults(options):
    defaults = {}
    for key, opts in options.items():
        if opts:
            defaults[key] = opts[0]
    return defaults


def _refine_indicator_params(ind_key, base_row, steps, defaults):
    base = defaults.get(ind_key, {})
    if ind_key == "rsi":
        long_v = _safe_int(base_row.get("rsi_long"), base.get("rsi_long"))
        short_v = _safe_int(base_row.get("rsi_short"), base.get("rsi_short"))
        pairs = _expand_pair(long_v, short_v, steps["threshold_pair"], min_value=1, max_value=99)
        return [{"rsi_long": p[0], "rsi_short": p[1]} for p in pairs] or [base]
    if ind_key == "stoch":
        long_v = _safe_int(base_row.get("stoch_long"), base.get("stoch_long"))
        short_v = _safe_int(base_row.get("stoch_short"), base.get("stoch_short"))
        pairs = _expand_pair(long_v, short_v, steps["threshold_pair"], min_value=1, max_value=99)
        return [{"stoch_long": p[0], "stoch_short": p[1]} for p in pairs] or [base]
    if ind_key == "mfi":
        long_v = _safe_int(base_row.get("mfi_long"), base.get("mfi_long"))
        short_v = _safe_int(base_row.get("mfi_short"), base.get("mfi_short"))
        pairs = _expand_pair(long_v, short_v, steps["threshold_pair"], min_value=1, max_value=99)
        return [{"mfi_long": p[0], "mfi_short": p[1]} for p in pairs] or [base]
    if ind_key == "bb_width":
        base_val = _safe_float(base_row.get("bb_width"), base.get("bb_width"))
        vals = _expand_float(base_val, steps["bb_width"], min_value=0.0)
        return [{"bb_width": v} for v in vals] or [base]
    if ind_key == "atr_ratio":
        base_val = _safe_float(base_row.get("atr_ratio"), base.get("atr_ratio"))
        vals = _expand_float(base_val, steps["atr_ratio"], min_value=0.0)
        return [{"atr_ratio": v} for v in vals] or [base]
    if ind_key == "macd_hist":
        base_val = _safe_float(base_row.get("macd_hist_ratio"), base.get("macd_hist_ratio"))
        vals = _expand_float(base_val, steps["macd_hist_ratio"], min_value=0.0)
        return [{"macd_hist_ratio": v} for v in vals] or [base]
    if ind_key == "roc":
        lb = _safe_int(base_row.get("roc_lookback"), base.get("roc_lookback"))
        thr = _safe_float(base_row.get("roc_threshold"), base.get("roc_threshold"))
        lbs = _expand_int(lb, steps["lookback"], min_value=2)
        thrs = _expand_float(thr, steps["roc_threshold"], min_value=0.0)
        return [{"roc_lookback": l, "roc_threshold": t} for l in lbs for t in thrs] or [base]
    if ind_key == "obv_roc":
        lb = _safe_int(base_row.get("obv_lookback"), base.get("obv_lookback"))
        lbs = _expand_int(lb, steps["lookback"], min_value=2)
        return [{"obv_lookback": l} for l in lbs] or [base]
    if ind_key == "volume_z":
        lb = _safe_int(base_row.get("volume_lookback"), base.get("volume_lookback"))
        z = _safe_float(base_row.get("volume_z"), base.get("volume_z"))
        lbs = _expand_int(lb, steps["lookback"], min_value=2)
        zs = _expand_float(z, steps["volume_z"], min_value=0.0)
        return [{"volume_lookback": l, "volume_z": v} for l in lbs for v in zs] or [base]
    if ind_key == "cmf":
        lb = _safe_int(base_row.get("cmf_lookback"), base.get("cmf_lookback"))
        thr = _safe_float(base_row.get("cmf_threshold"), base.get("cmf_threshold"))
        lbs = _expand_int(lb, steps["lookback"], min_value=2)
        thrs = _expand_float(thr, steps["cmf_threshold"], min_value=0.0)
        return [{"cmf_lookback": l, "cmf_threshold": t} for l in lbs for t in thrs] or [base]
    if ind_key == "vroc":
        lb = _safe_int(base_row.get("vroc_lookback"), base.get("vroc_lookback"))
        thr = _safe_float(base_row.get("vroc_threshold"), base.get("vroc_threshold"))
        lbs = _expand_int(lb, steps["lookback"], min_value=2)
        thrs = _expand_float(thr, steps["vroc_threshold"], min_value=0.0)
        return [{"vroc_lookback": l, "vroc_threshold": t} for l in lbs for t in thrs] or [base]
    if ind_key == "ad":
        lb = _safe_int(base_row.get("ad_lookback"), base.get("ad_lookback"))
        lbs = _expand_int(lb, steps["lookback"], min_value=2)
        return [{"ad_lookback": l} for l in lbs] or [base]
    if ind_key == "ma_trend":
        fast = _safe_int(base_row.get("ma_fast"), base.get("ma_fast"))
        slow = _safe_int(base_row.get("ma_slow"), base.get("ma_slow"))
        fasts = _expand_int(fast, steps["ma_step"], min_value=2)
        slows = _expand_int(slow, steps["ma_step"], min_value=3)
        pairs = []
        for f in fasts:
            for s in slows:
                if f >= s:
                    continue
                pairs.append((f, s))
        return [{"ma_fast": p[0], "ma_slow": p[1]} for p in sorted(set(pairs))] or [base]
    return [base]


def _iter_indicator_param_combos(combo_keys, param_options):
    param_lists = [param_options.get(key, [{}]) for key in combo_keys]
    for combo_params in itertools.product(*param_lists):
        merged = {field: None for field in INDICATOR_PARAM_FIELDS}
        for params in combo_params:
            merged.update(params)
        yield merged


def _apply_indicator_combo(long_regime, short_regime, combo_keys, combo_params, ctx):
    params_out = {field: combo_params.get(field) for field in INDICATOR_PARAM_FIELDS}

    if "rsi" in combo_keys:
        rsi_long = params_out["rsi_long"]
        rsi_short = params_out["rsi_short"]
        long_regime = long_regime & (ctx["rsi_series"] > rsi_long)
        short_regime = short_regime & (ctx["rsi_series"] < rsi_short)

    if "bb_width" in combo_keys:
        bb_width = params_out["bb_width"]
        long_regime = long_regime & (ctx["bb_width"] > bb_width)
        short_regime = short_regime & (ctx["bb_width"] > bb_width)

    if "atr_ratio" in combo_keys:
        atr_ratio = params_out["atr_ratio"]
        long_regime = long_regime & (ctx["atr_ratio"] > atr_ratio)
        short_regime = short_regime & (ctx["atr_ratio"] > atr_ratio)

    if "ma_trend" in combo_keys:
        ma_pair = (params_out["ma_fast"], params_out["ma_slow"])
        ma_long, ma_short = ctx["ma_trend_by_pair"][ma_pair]
        long_regime = long_regime & ma_long
        short_regime = short_regime & ma_short

    if "macd_hist" in combo_keys:
        macd_hist_ratio = params_out["macd_hist_ratio"]
        long_regime = long_regime & (ctx["macd_hist_ratio_series"] > macd_hist_ratio)
        short_regime = short_regime & (ctx["macd_hist_ratio_series"] < -macd_hist_ratio)

    if "stoch" in combo_keys:
        stoch_long = params_out["stoch_long"]
        stoch_short = params_out["stoch_short"]
        long_regime = long_regime & (ctx["stoch_k"] > stoch_long)
        short_regime = short_regime & (ctx["stoch_k"] < stoch_short)

    if "obv_roc" in combo_keys:
        obv_lookback = params_out["obv_lookback"]
        obv_roc = ctx["obv_roc_by_lb"][obv_lookback]
        long_regime = long_regime & (obv_roc > 0)
        short_regime = short_regime & (obv_roc < 0)

    if "volume_z" in combo_keys:
        volume_lookback = params_out["volume_lookback"]
        volume_z = params_out["volume_z"]
        vol_zscore = ctx["volume_zscore_by_lb"][volume_lookback]
        long_regime = long_regime & (vol_zscore > volume_z)
        short_regime = short_regime & (vol_zscore > volume_z)

    if "roc" in combo_keys:
        roc_lookback = params_out["roc_lookback"]
        roc_threshold = params_out["roc_threshold"]
        roc = ctx["roc_by_lb"][roc_lookback]
        long_regime = long_regime & (roc > roc_threshold)
        short_regime = short_regime & (roc < -roc_threshold)

    if "mfi" in combo_keys:
        mfi_long = params_out["mfi_long"]
        mfi_short = params_out["mfi_short"]
        mfi_series = ctx["mfi_by_window"][ctx["mfi_window"]]
        long_regime = long_regime & (mfi_series > mfi_long)
        short_regime = short_regime & (mfi_series < mfi_short)

    if "cmf" in combo_keys:
        cmf_lookback = params_out["cmf_lookback"]
        cmf_threshold = params_out["cmf_threshold"]
        cmf = ctx["cmf_by_window"][cmf_lookback]
        long_regime = long_regime & (cmf > cmf_threshold)
        short_regime = short_regime & (cmf < -cmf_threshold)

    if "vroc" in combo_keys:
        vroc_lookback = params_out["vroc_lookback"]
        vroc_threshold = params_out["vroc_threshold"]
        vroc = ctx["vroc_by_lb"][vroc_lookback]
        long_regime = long_regime & (vroc > vroc_threshold)
        short_regime = short_regime & (vroc > vroc_threshold)

    if "ad" in combo_keys:
        ad_lookback = params_out["ad_lookback"]
        ad_roc = ctx["ad_roc_by_lb"][ad_lookback]
        long_regime = long_regime & (ad_roc > 0)
        short_regime = short_regime & (ad_roc < 0)

    return long_regime, short_regime, params_out


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
    long_matrix = pd.DataFrame(
        np.broadcast_to(long_regime.to_numpy()[:, None], trade_close.shape),
        index=trade_close.index,
        columns=trade_close.columns,
    )
    short_matrix = pd.DataFrame(
        np.broadcast_to(short_regime.to_numpy()[:, None], trade_close.shape),
        index=trade_close.index,
        columns=trade_close.columns,
    )
    if long_filter is not None:
        long_matrix = long_matrix & long_filter.fillna(False)
    if short_filter is not None:
        short_matrix = short_matrix & short_filter.fillna(False)
    entries = long_matrix.vbt.fshift(1, fill_value=False)
    short_entries = short_matrix.vbt.fshift(1, fill_value=False)
    if max_positions is not None and max_positions > 0:
        if long_scores is not None:
            long_scores = long_scores.reindex_like(entries).where(entries, -np.inf).fillna(-np.inf)
            long_ranks = long_scores.rank(axis=1, method="first", ascending=False)
            entries = entries & (long_ranks <= max_positions)
        if short_scores is not None:
            short_scores = short_scores.reindex_like(short_entries).where(short_entries, -np.inf).fillna(-np.inf)
            short_ranks = short_scores.rank(axis=1, method="first", ascending=False)
            short_entries = short_entries & (short_ranks <= max_positions)
    entries_shifted = entries.vbt.fshift(max_hold, fill_value=False)
    short_entries_shifted = short_entries.vbt.fshift(max_hold, fill_value=False)
    exits = entries_shifted
    short_exits = short_entries_shifted
    group_by_param = True if cash_sharing else None
    return vbt.Portfolio.from_signals(
        trade_close,
        entries=entries,
        exits=exits,
        short_entries=short_entries,
        short_exits=short_exits,
        init_cash=init_cash,
        cash_sharing=cash_sharing,
        group_by=group_by_param,
        size=size,
        size_type=size_type,
        lock_cash=lock_cash,
        allow_partial=allow_partial,
        upon_opposite_entry="close",
        upon_dir_conflict="ignore",
        fees=fees,
        slippage=slippage,
        sl_stop=sl_stop,
        tp_stop=tp_stop,
        freq=freq,
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

    default_config = {
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
    config_path = os.path.join(out_dir, "sweep_config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                override = json.load(f)
            for key, value in override.items():
                if isinstance(value, dict) and isinstance(default_config.get(key), dict):
                    merged = default_config[key].copy()
                    merged.update(value)
                    default_config[key] = merged
                else:
                    default_config[key] = value
        except Exception as exc:
            print(f"[warn] failed to load sweep_config.json: {exc}")

    env_mode = os.getenv("VBT_SWEEP_MODE")
    if env_mode:
        default_config["search_mode"] = env_mode

    search_mode = str(default_config.get("search_mode", "combo")).lower()
    if search_mode not in {"combo", "refine"}:
        search_mode = "combo"
    timeframe_configs = default_config["timeframes"]
    combo_sizes = default_config["combo_sizes"]
    combo_seed = int(default_config.get("combo_seed", 42))
    combo_segment_start = int(default_config.get("combo_segment_start", 0))
    combo_segment_size = default_config.get("combo_segment_size")
    combo_group_fields = default_config.get("combo_group_fields", ["indicator_list", "regime_name", "vol_mode"])
    trade_symbols = default_config.get("trade_symbols", default_trade_symbols)
    if isinstance(trade_symbols, str):
        trade_symbols = [s.strip() for s in trade_symbols.split(",") if s.strip()]
    trade_symbols = [s.strip() for s in trade_symbols if s and str(s).strip()]
    trade_symbols = [s for s in trade_symbols if s != base_symbol]
    if not trade_symbols:
        trade_symbols = default_trade_symbols

    def _safe_positive_config_int(name, default):
        try:
            value = int(default_config.get(name, default))
        except (TypeError, ValueError):
            return default
        return value if value > 0 else default

    wf_train_days = _safe_positive_config_int("wf_train_days", 120)
    wf_test_days = _safe_positive_config_int("wf_test_days", 30)
    wf_step_days = _safe_positive_config_int("wf_step_days", 30)

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
    ma_pairs = sorted({
        (fast_val, slow_val)
        for base_fast, base_slow in base_ma_pairs
        for fast_val in (base_fast - 5, base_fast, base_fast + 5)
        for slow_val in (base_slow - 5, base_slow, base_slow + 5)
        if fast_val > 1 and slow_val > fast_val
    })
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

    regime_variants = [
        {"regime_name": "trend_high", "regime_type": "trend", "vol_mode": "high", "rsi_pair": None},
        {"regime_name": "trend_low", "regime_type": "trend", "vol_mode": "low", "rsi_pair": None},
        {"regime_name": "trend_any", "regime_type": "trend", "vol_mode": "any", "rsi_pair": None},
    ]
    for rsi_pair in rsi_revert_pairs:
        regime_variants.append({
            "regime_name": "rsi_revert_low",
            "regime_type": "rsi_revert",
            "vol_mode": "low",
            "rsi_pair": rsi_pair,
        })
    for rsi_pair in rsi_revert_pairs:
        regime_variants.append({
            "regime_name": "rsi_revert_high",
            "regime_type": "rsi_revert",
            "vol_mode": "high",
            "rsi_pair": rsi_pair,
        })
    regime_variants.append({
        "regime_name": "bb_revert_low",
        "regime_type": "bb_revert",
        "vol_mode": "low",
        "rsi_pair": None,
    })
    regime_variants.append({
        "regime_name": "bb_revert_high",
        "regime_type": "bb_revert",
        "vol_mode": "high",
        "rsi_pair": None,
    })
    regime_variants.append({
        "regime_name": "bb_breakout_high",
        "regime_type": "bb_breakout",
        "vol_mode": "high",
        "rsi_pair": None,
    })

    # scanning logic (multi-timeframe, incremental, two-space)
    regime_lookup = {regime["regime_name"]: regime for regime in regime_variants}
    timeframe_days_map = {cfg["timeframe"]: cfg["days"] for cfg in timeframe_configs}

    def count_coarse_combos():
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
            sort_primary = "oos_avg_total_return_pct"
            if sort_primary not in tf_filtered.columns or not tf_filtered[sort_primary].notna().any():
                sort_primary = "avg_total_return_pct"
            sort_cols = [sort_primary]
            sort_asc = [False]
            if "avg_hold_hours" in tf_filtered.columns:
                sort_cols.append("avg_hold_hours")
                sort_asc.append(True)
            tf_sorted = tf_filtered.sort_values(sort_cols, ascending=sort_asc)
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

    sort_col = "oos_avg_total_return_pct"
    if sort_col not in filtered.columns or not filtered[sort_col].notna().any():
        sort_col = "avg_total_return_pct"
    sort_cols = [sort_col]
    sort_asc = [False]
    if "avg_hold_hours" in filtered.columns:
        sort_cols.append("avg_hold_hours")
        sort_asc.append(True)
    top10 = filtered.sort_values(sort_cols, ascending=sort_asc).head(10)
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
    lb_sort_col = "oos_avg_total_return_pct"
    if lb_sort_col not in lb_view.columns or not lb_view[lb_sort_col].notna().any():
        lb_sort_col = "avg_total_return_pct"
    lb_best = lb_view.sort_values(lb_sort_col, ascending=False).head(history_rows)
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
