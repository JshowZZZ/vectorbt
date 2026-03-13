"""MACD indicator plugin."""

from __future__ import annotations

import pandas as pd

try:
    import pandas_ta as ta  # type: ignore
except Exception:  # pragma: no cover
    ta = None

INDICATOR_ID = "MACD"
DISPLAY_NAME = "Moving Average Convergence Divergence"
PARAMS = {
    "macd_fast": {"type": "int", "default": 12, "min": 5, "max": 30},
    "macd_slow": {"type": "int", "default": 26, "min": 15, "max": 60},
    "macd_signal": {"type": "int", "default": 9, "min": 3, "max": 20},
}
CONDITION_OPERATORS = ["above", "below", "crossover", "crossunder"]


def _manual_macd(close: pd.Series, fast: int, slow: int) -> pd.Series:
    ema_fast = close.ewm(span=fast, adjust=False, min_periods=fast).mean()
    ema_slow = close.ewm(span=slow, adjust=False, min_periods=slow).mean()
    return ema_fast - ema_slow


def compute(ohlcv_df: pd.DataFrame, params: dict) -> pd.Series:
    fast = int(params.get("macd_fast", PARAMS["macd_fast"]["default"]))
    slow = int(params.get("macd_slow", PARAMS["macd_slow"]["default"]))
    signal = int(params.get("macd_signal", PARAMS["macd_signal"]["default"]))
    close = ohlcv_df["close"]
    if ta is not None:
        try:
            out = ta.macd(close=close, fast=fast, slow=slow, signal=signal)
            if isinstance(out, pd.DataFrame) and not out.empty:
                return out.iloc[:, 0].reindex(ohlcv_df.index)
        except Exception:
            pass
    return _manual_macd(close, fast, slow).reindex(ohlcv_df.index)


