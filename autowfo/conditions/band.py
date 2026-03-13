"""Band-position condition operators."""

from __future__ import annotations

import pandas as pd


def _as_bool_series(values: pd.Series) -> pd.Series:
    return values.fillna(False).astype(bool)


def near_lower(series: pd.Series, params: dict) -> pd.Series:
    pct = float(params["pct"])
    return _as_bool_series(series <= pct).reindex(series.index, fill_value=False)


def near_upper(series: pd.Series, params: dict) -> pd.Series:
    pct = float(params["pct"])
    return _as_bool_series(series >= (1.0 - pct)).reindex(series.index, fill_value=False)


