"""Condition operator registry and dispatcher for AUTOWFO."""

from __future__ import annotations

import pandas as pd

from scripts.autowfo.conditions import band, crossover, momentum, threshold

OPERATOR_REGISTRY = {
    "below": threshold.below,
    "above": threshold.above,
    "crossover": crossover.crossover,
    "crossunder": crossover.crossunder,
    "near_lower": band.near_lower,
    "near_upper": band.near_upper,
    "above_avg": momentum.above_avg,
    "pct_move": momentum.pct_move,
}


def apply(series: pd.Series, operator: str, params: dict) -> pd.Series:
    """Evaluate one condition operator against an indicator series."""
    if operator not in OPERATOR_REGISTRY:
        raise ValueError(
            f"Unknown operator: {operator!r}. Available: {list(OPERATOR_REGISTRY)}"
        )
    return OPERATOR_REGISTRY[operator](series, params)

