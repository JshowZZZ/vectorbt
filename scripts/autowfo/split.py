"""Walk-forward split helpers extracted from run_btc_regime_sweep monolith."""

import pandas as pd


def _build_walk_forward_slices(index, train_days, test_days, step_days):
    if index.empty:
        return []
    train_delta = pd.Timedelta(days=train_days)
    test_delta = pd.Timedelta(days=test_days)
    step_delta = pd.Timedelta(days=step_days)
    cursor = index[0]
    end = index[-1]
    slices = []
    while True:
        train_end = cursor + train_delta
        test_end = train_end + test_delta
        if test_end > end:
            break
        slices.append((train_end, test_end))
        cursor = cursor + step_delta
    return slices
