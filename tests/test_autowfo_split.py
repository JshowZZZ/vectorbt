import pandas as pd
import pytest

from scripts.autowfo import split as s


def test_build_walk_forward_slices_empty_index():
    got = s._build_walk_forward_slices(pd.DatetimeIndex([]), train_days=5, test_days=2, step_days=2)
    assert got == []


def test_build_walk_forward_slices_characterization():
    index = pd.date_range("2024-01-01", periods=24 * 20, freq="h")
    got = s._build_walk_forward_slices(index, train_days=5, test_days=2, step_days=3)

    assert len(got) > 0
    assert got[0] == (index[0] + pd.Timedelta(days=5), index[0] + pd.Timedelta(days=7))
    assert all(test_end <= index[-1] for _, test_end in got)


def test_build_walk_forward_slices_step_lt_test_raises():
    index = pd.date_range("2024-01-01", periods=24 * 20, freq="h")
    with pytest.raises(ValueError, match="step_days.*must be.*test_days"):
        s._build_walk_forward_slices(index, train_days=5, test_days=3, step_days=2)


def test_build_walk_forward_slices_rejects_invalid_mode():
    index = pd.date_range("2024-01-01", periods=24 * 20, freq="h")
    with pytest.raises(ValueError, match="unsupported split mode"):
        s._build_walk_forward_slices(index, train_days=5, test_days=2, step_days=2, mode="rolling")


def test_build_walk_forward_slices_rejects_non_positive_days():
    index = pd.date_range("2024-01-01", periods=24 * 20, freq="h")
    with pytest.raises(ValueError, match="train_days must be > 0"):
        s._build_walk_forward_slices(index, train_days=0, test_days=2, step_days=2)
