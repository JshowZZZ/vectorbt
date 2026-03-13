# -*- coding: utf-8 -*-
"""Constants extracted from the AUTOWFO runtime."""

from __future__ import annotations

import html

from autowfo import strategy_schema as autowfo_strategy_schema


def _u(text: str) -> str:
    """Decode escaped Unicode literals for backward-compatible snapshots."""
    return text.encode("utf-8").decode("unicode_escape")


def _html_entity(text: str) -> str:
    """Resolve HTML entities for backward-compatible snapshots."""
    return html.unescape(text)


def _titleize(key: str) -> str:
    text = key.replace("_pct", " pct")
    text = text.replace("_", " ")
    text = text.replace("oos", "OOS")
    text = text.replace("wf", "WF")
    text = text.replace("avg", "avg")
    text = text.replace("tp", "TP")
    text = text.replace("sl", "SL")
    text = text.replace("usdt", "USDT")
    text = text.replace("bps", "bps")
    return " ".join(part.upper() if part.isupper() else part.capitalize() for part in text.split())


STRATEGY_SCHEMA = autowfo_strategy_schema.load_strategy_schema()
INDICATOR_META = autowfo_strategy_schema.build_indicator_meta(
    STRATEGY_SCHEMA,
    label_transform=None,
)
INDICATOR_LABELS = {key: value["label"] for key, value in INDICATOR_META.items()}

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
    "cci_lookback",
    "cci_long",
    "cci_short",
    "willr_lookback",
    "willr_long",
    "willr_short",
    "adx_lookback",
    "adx_threshold",
    "trix_lookback",
    "dpo_lookback",
    "efi_lookback",
    "vwma_lookback",
    "ultosc_long",
    "ultosc_short",
    "keltner_lookback",
    "keltner_long",
    "keltner_short",
    "donchian_lookback",
    "donchian_long",
    "donchian_short",
    "ppo_threshold",
    "chop_lookback",
    "chop_threshold",
]

REGIME_NAME_MAP = autowfo_strategy_schema.build_regime_name_map(
    STRATEGY_SCHEMA,
    label_transform=None,
)
REGIME_TYPE_MAP = autowfo_strategy_schema.build_regime_type_map(
    STRATEGY_SCHEMA,
    label_transform=None,
)

FILTER_NAME_MAP = {
    "vol_mom": "Volume + Momentum",
    "vol_mom_rsi": "Volume + Momentum + RSI",
    "vol_mom_bb": "Volume + Momentum + Bollinger Bands",
    "vol_mom_atr": "Volume + Momentum + ATR Ratio",
    "vol_mom_rsi_bb": "Volume + Momentum + RSI + Bollinger Bands",
    "vol_mom_rsi_atr": "Volume + Momentum + RSI + ATR Ratio",
    "vol_mom_ma": "Volume + Momentum + MA",
    "vol_mom_macd": "Volume + Momentum + MACD",
    "vol_mom_stoch": "Volume + Momentum + Stochastic",
    "vol_mom_obv": "Volume + Momentum + OBV",
    "vol_mom_volume": "Volume + Momentum + Volume Z",
    "none": "No Filter",
}

_BASE_LABEL_KEYS = {
    "report_title",
    "summary_title",
    "params_title",
    "top_title",
    "chart_title",
    "symbol",
    "filter_name",
    "regime_name",
    "regime_type",
    "vol_mode",
    "data_range",
    "data_days",
    "base_symbol",
    "trade_symbols",
    "capital_mode",
    "run_id",
    "timestamp_utc",
    "ranking_mode",
    "report",
    "min_trades_filter",
    "min_trades_target",
    "min_avg_daily_trades_filter",
    "min_avg_daily_trades_target",
    "history_title",
    "leaderboard_title",
    "recent_runs_title",
    "plot_symbol",
    "oos_summary_title",
    "wf_train_days",
    "wf_test_days",
    "wf_step_days",
    "wf_valid_days",
    "wf_mode",
    "wf_segments",
    "status_title",
    "status_stage",
    "status_total",
    "status_done",
    "status_remaining",
    "status_skipped",
    "status_percent",
    "status_elapsed",
    "status_eta",
    "status_updated",
    "init_cash_usdt",
    "order_size_pct",
    "max_concurrent_positions",
    "indicator_list",
    "indicator_count",
    "slippage_bps",
    "spread_bps",
    "funding_rate_daily",
    "timeframe",
    "scan_timeframes",
}

_METRIC_LABEL_KEYS = {
    "total_return_pct",
    "total_profit",
    "total_trades",
    "win_rate_pct",
    "avg_trade_pct",
    "max_drawdown_pct",
    "position_coverage_pct",
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
}

LABELS = {
    key: _titleize(key)
    for key in sorted(_BASE_LABEL_KEYS | _METRIC_LABEL_KEYS | set(INDICATOR_PARAM_FIELDS))
}
LABELS.update(
    {
        "report_title": _html_entity(_u("\\u56de\\u6e2c\\u5831\\u544a")),
        "status_title": _html_entity(_u("\\u57f7\\u884c\\u72c0\\u614b")),
        "summary_title": "Summary",
        "params_title": "Parameters",
        "top_title": "Top Results",
        "chart_title": "Performance Charts",
        "history_title": "Run History",
        "leaderboard_title": "Leaderboard",
        "recent_runs_title": "Recent Runs",
        "oos_summary_title": "OOS Summary",
        "plot_symbol": "Plot Symbol",
        "scan_timeframes": "Scan Timeframes",
        "trade_symbols": "Trade Symbols",
        "capital_mode": "Capital Mode",
        "funding_rate_daily": "Funding Rate / Day",
        "indicator_list": "Indicator List",
        "indicator_count": "Indicator Count",
        "status_done": "Done",
        "status_remaining": "Remaining",
        "status_skipped": "Skipped",
        "status_percent": "Percent (%)",
        "status_elapsed": "Elapsed",
        "status_eta": "ETA",
        "status_updated": "Updated",
    }
)
