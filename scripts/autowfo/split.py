"""Walk-forward split helpers extracted from run_btc_regime_sweep monolith."""

import pandas as pd

from scripts.autowfo import split_protocol as autowfo_split_protocol


SPLIT_PROTOCOL = autowfo_split_protocol.load_split_protocol()
SUPPORTED_SPLIT_MODES = tuple(autowfo_split_protocol.build_supported_modes(SPLIT_PROTOCOL))
DEFAULT_SPLIT_MODE = autowfo_split_protocol.build_default_mode(SPLIT_PROTOCOL)


def _to_positive_int(value, field_name):
    if not isinstance(value, int):
        raise ValueError(f"{field_name} must be int")
    if value <= 0:
        raise ValueError(f"{field_name} must be > 0")
    return value


def _normalize_split_mode(mode):
    mode_value = DEFAULT_SPLIT_MODE if mode is None else str(mode).strip().lower()
    if mode_value not in SUPPORTED_SPLIT_MODES:
        raise ValueError(f"unsupported split mode: {mode_value}")
    return mode_value


def _to_non_negative_int(value, field_name):
    if not isinstance(value, int):
        raise ValueError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")
    return value


def _build_walk_forward_windows(index, train_days, test_days, step_days, mode=None, valid_days=0):
    """Build walk-forward windows as 6-tuples.

    Returns list of (train_start, train_end, valid_start, valid_end, test_start, test_end).
    When *valid_days* is 0 the validation segment is zero-length
    (valid_start == valid_end == train_end) and the result is semantically
    equivalent to the legacy 4-tuple layout.
    """
    mode_value = _normalize_split_mode(mode)
    train_days = _to_positive_int(train_days, "train_days")
    test_days = _to_positive_int(test_days, "test_days")
    step_days = _to_positive_int(step_days, "step_days")
    valid_days = _to_non_negative_int(valid_days, "valid_days")

    if step_days < test_days:
        raise ValueError(
            f"step_days ({step_days}) must be >= test_days ({test_days}) "
            "to avoid overlapping OOS segments"
        )
    if index.empty:
        return []
    train_delta = pd.Timedelta(days=train_days)
    valid_delta = pd.Timedelta(days=valid_days)
    test_delta = pd.Timedelta(days=test_days)
    step_delta = pd.Timedelta(days=step_days)
    cursor = index[0]
    end = index[-1]
    windows = []
    while True:
        if mode_value == "anchored":
            train_start = index[0]
            train_end = cursor + train_delta
        else:
            train_start = cursor
            train_end = train_start + train_delta
        valid_start = train_end
        valid_end = train_end + valid_delta
        test_start = valid_end
        test_end = valid_end + test_delta
        if test_end > end:
            break
        windows.append((train_start, train_end, valid_start, valid_end, test_start, test_end))
        cursor = cursor + step_delta
    return windows


def _build_walk_forward_slices(index, train_days, test_days, step_days, mode=None, valid_days=0):
    windows = _build_walk_forward_windows(
        index=index,
        train_days=train_days,
        test_days=test_days,
        step_days=step_days,
        mode=mode,
        valid_days=valid_days,
    )
    return [(test_start, test_end) for _, _, _, _, test_start, test_end in windows]
