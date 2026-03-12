"""Cross-over and cross-under condition operators."""

from __future__ import annotations

import pandas as pd


def _as_bool_series(values: pd.Series) -> pd.Series:
    return values.fillna(False).astype(bool)


def _reference_series(series: pd.Series, params: dict) -> pd.Series:
    if "reference" in params and isinstance(params["reference"], pd.Series):
        return params["reference"].reindex(series.index)
    if "threshold" in params:
        return pd.Series(float(params["threshold"]), index=series.index)
    raise ValueError("crossover/crossunder requires 'threshold' or 'reference'")


def crossover(series: pd.Series, params: dict) -> pd.Series:
    ref = _reference_series(series, params)
    prev_below = series.shift(1) < ref.shift(1)
    now_above = series > ref
    crossed = prev_below & now_above
    if not crossed.empty:
        crossed.iloc[0] = False
    return _as_bool_series(crossed).reindex(series.index, fill_value=False)


def crossunder(series: pd.Series, params: dict) -> pd.Series:
    ref = _reference_series(series, params)
    prev_above = series.shift(1) > ref.shift(1)
    now_below = series < ref
    crossed = prev_above & now_below
    if not crossed.empty:
        crossed.iloc[0] = False
    return _as_bool_series(crossed).reindex(series.index, fill_value=False)

