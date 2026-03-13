"""Momentum and movement condition operators."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _as_bool_series(values: pd.Series) -> pd.Series:
    return values.fillna(False).astype(bool)


def above_avg(series: pd.Series, params: dict) -> pd.Series:
    multiplier = float(params["multiplier"])
    return _as_bool_series(series >= multiplier).reindex(series.index, fill_value=False)


def pct_move(series: pd.Series, params: dict) -> pd.Series:
    pct = float(params["pct"])
    direction = str(params["direction"]).strip().lower()
    lookback = int(params["lookback"])
    base = series.shift(lookback)
    move = (series - base) / base.replace(0.0, np.nan)
    if direction == "up":
        out = move > pct
    elif direction == "down":
        out = move < -pct
    else:
        raise ValueError("pct_move direction must be 'up' or 'down'")
    return _as_bool_series(out).reindex(series.index, fill_value=False)


