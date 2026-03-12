"""RSI indicator plugin."""

from __future__ import annotations

import numpy as np
import pandas as pd

try:
    import pandas_ta as ta  # type: ignore
except Exception:  # pragma: no cover
    ta = None

INDICATOR_ID = "RSI"
DISPLAY_NAME = "Relative Strength Index"
PARAMS = {
    "rsi_period": {"type": "int", "default": 14, "min": 5, "max": 50},
}
CONDITION_OPERATORS = ["below", "above", "crossover", "crossunder"]


def _manual_rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gains = delta.clip(lower=0.0)
    losses = -delta.clip(upper=0.0)
    avg_gain = gains.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = losses.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi = rsi.where(~((avg_gain == 0.0) & (avg_loss == 0.0)), 50.0)
    rsi = rsi.where(avg_loss != 0.0, 100.0)
    return rsi


def compute(ohlcv_df: pd.DataFrame, params: dict) -> pd.Series:
    period = int(params.get("rsi_period", PARAMS["rsi_period"]["default"]))
    close = ohlcv_df["close"]
    if ta is not None:
        try:
            out = ta.rsi(close=close, length=period)
            if isinstance(out, pd.DataFrame):
                out = out.iloc[:, 0]
            if isinstance(out, pd.Series):
                return out.reindex(ohlcv_df.index)
        except Exception:
            pass
    return _manual_rsi(close, period).reindex(ohlcv_df.index)

