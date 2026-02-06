"""Search/keying helpers extracted from run_btc_regime_sweep monolith."""

import numpy as np


def _normalize_key_value(value):
    if value is None:
        return None
    if isinstance(value, float) and np.isnan(value):
        return None
    if isinstance(value, (float, np.floating)):
        return round(float(value), 6)
    if isinstance(value, (int, np.integer)):
        return int(value)
    return value


def _combo_key_from_dict(values, combo_key_fields):
    parts = []
    for field in combo_key_fields:
        parts.append(f"{field}={_normalize_key_value(values.get(field))}")
    return "|".join(parts)
