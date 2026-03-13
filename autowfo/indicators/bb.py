"""Bollinger Band position indicator plugin."""

from __future__ import annotations

import numpy as np
import pandas as pd

try:
    import pandas_ta as ta  # type: ignore
except Exception:  # pragma: no cover
    ta = None

INDICATOR_ID = "BB"
DISPLAY_NAME = "Bollinger Band Position"
PARAMS = {
    "bb_period": {"type": "int", "default": 20, "min": 5, "max": 50},
    "bb_std": {"type": "float", "default": 2.0, "min": 1.0, "max": 3.0},
}
CONDITION_OPERATORS = ["below", "above", "near_lower", "near_upper"]


def _manual_bb_position(close: pd.Series, period: int, std_mul: float) -> pd.Series:
    mid = close.rolling(window=period, min_periods=period).mean()
    stdev = close.rolling(window=period, min_periods=period).std(ddof=0)
    upper = mid + stdev * std_mul
    lower = mid - stdev * std_mul
    denom = (upper - lower).replace(0.0, np.nan)
    return (close - lower) / denom


def compute(ohlcv_df: pd.DataFrame, params: dict) -> pd.Series:
    period = int(params.get("bb_period", PARAMS["bb_period"]["default"]))
    std_mul = float(params.get("bb_std", PARAMS["bb_std"]["default"]))
    close = ohlcv_df["close"]
    if ta is not None:
        try:
            bands = ta.bbands(close=close, length=period, std=std_mul)
            if isinstance(bands, pd.DataFrame) and bands.shape[1] >= 3:
                lower = bands.iloc[:, 0]
                upper = bands.iloc[:, 2]
                denom = (upper - lower).replace(0.0, np.nan)
                out = (close - lower) / denom
                return out.reindex(ohlcv_df.index)
        except Exception:
            pass
    return _manual_bb_position(close, period, std_mul).reindex(ohlcv_df.index)


