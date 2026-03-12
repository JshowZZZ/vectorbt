"""EMA distance indicator plugin."""

from __future__ import annotations

import numpy as np
import pandas as pd

try:
    import pandas_ta as ta  # type: ignore
except Exception:  # pragma: no cover
    ta = None

INDICATOR_ID = "EMA"
DISPLAY_NAME = "Exponential Moving Average Distance"
PARAMS = {
    "ema_period": {"type": "int", "default": 20, "min": 5, "max": 200},
}
CONDITION_OPERATORS = ["above", "below", "crossover", "crossunder"]


def _manual_ema_distance(close: pd.Series, period: int) -> pd.Series:
    ema = close.ewm(span=period, adjust=False, min_periods=period).mean()
    return close / ema.replace(0.0, np.nan) - 1.0


def compute(ohlcv_df: pd.DataFrame, params: dict) -> pd.Series:
    period = int(params.get("ema_period", PARAMS["ema_period"]["default"]))
    close = ohlcv_df["close"]
    if ta is not None:
        try:
            ema = ta.ema(close=close, length=period)
            if isinstance(ema, pd.DataFrame):
                ema = ema.iloc[:, 0]
            if isinstance(ema, pd.Series):
                out = close / ema.replace(0.0, np.nan) - 1.0
                return out.reindex(ohlcv_df.index)
        except Exception:
            pass
    return _manual_ema_distance(close, period).reindex(ohlcv_df.index)

