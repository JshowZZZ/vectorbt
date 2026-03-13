"""Ranking helpers extracted from run_btc_regime_sweep monolith."""

from __future__ import annotations

import copy
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd


DEFAULT_RANKING_CONFIG = {
    "mode": "composite",
    "low_trade_threshold": 30.0,
    "legacy": {
        "preferred": "oos_avg_total_return_pct",
        "fallback": "avg_total_return_pct",
    },
    "weights": {
        "return": 1.0,
        "stability": 1.0,
        "risk_adjust": 0.5,
        "drawdown_penalty": 1.0,
        "low_sample_penalty": 1.0,
    },
    "regime_weights": {},
}


def _to_numeric_series(df, column):
    if column not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype="float64")
    return pd.to_numeric(df[column], errors="coerce")


def _coerce_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _resolve_ranking_config(config=None):
    resolved = copy.deepcopy(DEFAULT_RANKING_CONFIG)
    if config is None:
        return resolved
    if not isinstance(config, dict):
        return resolved

    mode = str(config.get("mode", resolved["mode"])).strip().lower()
    if mode not in {"legacy", "composite"}:
        mode = resolved["mode"]
    resolved["mode"] = mode

    legacy = config.get("legacy")
    if isinstance(legacy, dict):
        preferred = legacy.get("preferred")
        fallback = legacy.get("fallback")
        if isinstance(preferred, str) and preferred.strip():
            resolved["legacy"]["preferred"] = preferred.strip()
        if isinstance(fallback, str) and fallback.strip():
            resolved["legacy"]["fallback"] = fallback.strip()

    weights = config.get("weights")
    if isinstance(weights, dict):
        for key in resolved["weights"]:
            if key in weights:
                resolved["weights"][key] = _coerce_float(weights[key], resolved["weights"][key])

    if "low_trade_threshold" in config:
        resolved["low_trade_threshold"] = max(
            _coerce_float(config.get("low_trade_threshold"), resolved["low_trade_threshold"]),
            0.0,
        )

    regime_weights = config.get("regime_weights")
    if isinstance(regime_weights, dict):
        resolved["regime_weights"] = {str(k): float(v) for k, v in regime_weights.items()}

    return resolved


def _choose_score_col(df, preferred="oos_avg_total_return_pct", fallback="avg_total_return_pct"):
    sort_col = preferred
    if sort_col not in df.columns or not df[sort_col].notna().any():
        sort_col = fallback
    return sort_col


def _build_composite_score(
    df,
    ranking_config,
    preferred="oos_avg_total_return_pct",
    fallback="avg_total_return_pct",
):
    threshold = float(ranking_config["low_trade_threshold"])
    weights = ranking_config["weights"]

    return_pct = _to_numeric_series(df, preferred)
    fallback_return = _to_numeric_series(df, fallback)
    return_pct = return_pct.where(return_pct.notna(), fallback_return)
    return_component = return_pct / 100.0

    positive_ratio = _to_numeric_series(df, "oos_positive_segment_ratio").fillna(0.0)
    return_std = (_to_numeric_series(df, "oos_return_std").clip(lower=0.0) / 100.0).fillna(0.0)
    stability_component = positive_ratio - return_std

    # Cap risk-adjust to avoid accidental outlier domination.
    risk_adjust = (_to_numeric_series(df, "oos_sharpe_like").clip(lower=-10.0, upper=10.0) / 10.0).fillna(0.0)

    drawdown_pct = _to_numeric_series(df, "oos_avg_max_drawdown_pct")
    fallback_drawdown_pct = _to_numeric_series(df, "avg_max_drawdown_pct")
    drawdown_pct = drawdown_pct.where(drawdown_pct.notna(), fallback_drawdown_pct)
    drawdown_penalty = (-drawdown_pct).clip(lower=0.0).fillna(0.0) / 100.0

    low_sample_penalty = _to_numeric_series(df, "oos_low_trade_penalty")
    if (not low_sample_penalty.notna().any()) and threshold > 0:
        min_trades = _to_numeric_series(df, "oos_min_total_trades")
        low_sample_penalty = ((threshold - min_trades) / threshold).clip(lower=0.0)
    low_sample_penalty = low_sample_penalty.fillna(0.0)

    score = (
        weights["return"] * return_component
        + weights["stability"] * stability_component
        + weights["risk_adjust"] * risk_adjust
        - weights["drawdown_penalty"] * drawdown_penalty
        - weights["low_sample_penalty"] * low_sample_penalty
    )
    # Keep rows with missing returns as NaN so legacy fallback can still be chosen.
    return score.where(return_component.notna(), np.nan)


def _sort_by_score(
    df,
    preferred="oos_avg_total_return_pct",
    fallback="avg_total_return_pct",
    tie_break_avg_hold=True,
    ranking_config=None,
):
    working_df = df.copy()
    resolved = _resolve_ranking_config(ranking_config)
    preferred_col = resolved["legacy"]["preferred"] or preferred
    fallback_col = resolved["legacy"]["fallback"] or fallback
    score_col = _choose_score_col(working_df, preferred=preferred_col, fallback=fallback_col)

    if resolved["mode"] == "composite":
        composite_col = "composite_score"
        working_df[composite_col] = _build_composite_score(
            working_df,
            ranking_config=resolved,
            preferred=preferred_col,
            fallback=fallback_col,
        )
        if working_df[composite_col].notna().any():
            score_col = composite_col

    sort_cols = [score_col]
    sort_asc = [False]
    if tie_break_avg_hold and "avg_hold_hours" in working_df.columns:
        sort_cols.append("avg_hold_hours")
        sort_asc.append(True)
    return working_df.sort_values(sort_cols, ascending=sort_asc), score_col


def _top_by_score(
    df,
    top_n,
    preferred="oos_avg_total_return_pct",
    fallback="avg_total_return_pct",
    tie_break_avg_hold=True,
    ranking_config=None,
):
    sorted_df, score_col = _sort_by_score(
        df,
        preferred=preferred,
        fallback=fallback,
        tie_break_avg_hold=tie_break_avg_hold,
        ranking_config=ranking_config,
    )
    return sorted_df.head(top_n), score_col


# ---------------------------------------------------------------------------
#  AWF-026: Regime-aware ranking helpers
# ---------------------------------------------------------------------------

def _apply_regime_weight(
    df: pd.DataFrame,
    ranking_config: Optional[Dict[str, Any]] = None,
) -> pd.DataFrame:
    """Multiply composite_score by per-regime weight if configured.

    ``ranking_config["regime_weights"]`` is an optional dict mapping
    ``regime_name`` ??float multiplier (default 1.0 for missing names).
    When empty or absent, no adjustment is applied.
    """
    resolved = _resolve_ranking_config(ranking_config)
    regime_weights = resolved.get("regime_weights")
    if not regime_weights or "composite_score" not in df.columns:
        return df
    if "regime_name" not in df.columns:
        return df
    working = df.copy()
    weight_series = working["regime_name"].map(
        lambda name: float(regime_weights.get(str(name), 1.0))
    )
    working["composite_score"] = working["composite_score"] * weight_series
    return working


def _top_by_score_per_regime(
    df: pd.DataFrame,
    top_n: int,
    preferred: str = "oos_avg_total_return_pct",
    fallback: str = "avg_total_return_pct",
    tie_break_avg_hold: bool = True,
    ranking_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Tuple[pd.DataFrame, str]]:
    """Group *df* by ``regime_name`` and return top-N per group.

    Returns ``{regime_name: (top_df, score_col)}``.
    Groups with fewer than 1 row are omitted.
    """
    if "regime_name" not in df.columns:
        return {}
    result: Dict[str, Tuple[pd.DataFrame, str]] = {}
    for regime_name, group_df in df.groupby("regime_name", sort=True):
        if group_df.empty:
            continue
        top_df, score_col = _top_by_score(
            group_df,
            top_n=top_n,
            preferred=preferred,
            fallback=fallback,
            tie_break_avg_hold=tie_break_avg_hold,
            ranking_config=ranking_config,
        )
        result[str(regime_name)] = (top_df, score_col)
    return result


def _regime_summary(
    df: pd.DataFrame,
    ranking_config: Optional[Dict[str, Any]] = None,
) -> list:
    """Produce a per-regime summary: count, avg return, avg score."""
    if "regime_name" not in df.columns:
        return []
    resolved = _resolve_ranking_config(ranking_config)
    preferred = resolved["legacy"]["preferred"]
    fallback = resolved["legacy"]["fallback"]
    rows = []
    for regime_name, group_df in df.groupby("regime_name", sort=True):
        ret_col = preferred if preferred in group_df.columns else fallback
        avg_ret = _to_numeric_series(group_df, ret_col).mean() if ret_col in group_df.columns else None
        score_col_val = None
        if "composite_score" in group_df.columns:
            score_col_val = group_df["composite_score"].mean()
        rows.append({
            "regime_name": str(regime_name),
            "combo_count": len(group_df),
            "avg_return_pct": round(float(avg_ret), 4) if avg_ret is not None and not np.isnan(avg_ret) else None,
            "avg_composite_score": round(float(score_col_val), 4) if score_col_val is not None and not np.isnan(score_col_val) else None,
        })
    return rows

