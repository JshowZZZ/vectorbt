"""Search/keying helpers extracted from run_btc_regime_sweep monolith."""

import numpy as np


def _normalize_key_value(value):
    if value is None:
        return None
    if isinstance(value, float) and np.isnan(value):
        return None
    if isinstance(value, (float, np.floating)):
        # AWF-106c: When pandas reads a column that contains NaN for some rows,
        # it up-casts the entire column to float64 (e.g. wf_valid_days, wf_train_days).
        # An integer value stored as 0.0 / 10.0 / 30.0 must produce the same key
        # as the same value read directly from config as a Python int (0 / 10 / 30).
        # Canonicalize integer-valued floats to int so the key representation is
        # stable regardless of how the value was sourced.
        fval = float(value)
        if fval == int(fval):
            return int(fval)
        return round(fval, 6)
    if isinstance(value, (int, np.integer)):
        return int(value)
    return value


def _combo_key_from_dict(values, combo_key_fields):
    parts = []
    for field in combo_key_fields:
        parts.append(f"{field}={_normalize_key_value(values.get(field))}")
    return "|".join(parts)
