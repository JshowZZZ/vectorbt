"""Volume ratio indicator plugin."""

from __future__ import annotations

import numpy as np
import pandas as pd

INDICATOR_ID = "Volume"
DISPLAY_NAME = "Volume Ratio vs Rolling Mean"
PARAMS = {
    "vol_period": {"type": "int", "default": 20, "min": 5, "max": 60},
}
CONDITION_OPERATORS = ["above_avg"]


def compute(ohlcv_df: pd.DataFrame, params: dict) -> pd.Series:
    period = int(params.get("vol_period", PARAMS["vol_period"]["default"]))
    volume = ohlcv_df["volume"]
    avg_volume = volume.rolling(window=period, min_periods=period).mean()
    out = volume / avg_volume.replace(0.0, np.nan)
    return out.reindex(ohlcv_df.index)

