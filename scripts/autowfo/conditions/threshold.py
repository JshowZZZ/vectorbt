"""Threshold-based condition operators."""

from __future__ import annotations

import pandas as pd


def _as_bool_series(values: pd.Series) -> pd.Series:
    return values.fillna(False).astype(bool)


def below(series: pd.Series, params: dict) -> pd.Series:
    threshold = float(params["threshold"])
    return _as_bool_series(series < threshold).reindex(series.index, fill_value=False)


def above(series: pd.Series, params: dict) -> pd.Series:
    threshold = float(params["threshold"])
    return _as_bool_series(series > threshold).reindex(series.index, fill_value=False)

