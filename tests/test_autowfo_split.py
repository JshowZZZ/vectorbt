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
        s._build_walk_forward_slices(index, train_days=5, test_days=2, step_days=2, mode="invalid_mode")


def test_build_walk_forward_slices_rejects_non_positive_days():
    index = pd.date_range("2024-01-01", periods=24 * 20, freq="h")
    with pytest.raises(ValueError, match="train_days must be > 0"):
        s._build_walk_forward_slices(index, train_days=0, test_days=2, step_days=2)


def test_build_walk_forward_slices_default_mode_matches_explicit_anchored():
    index = pd.date_range("2024-01-01", periods=24 * 60, freq="h")
    default_mode = s._build_walk_forward_slices(index, train_days=10, test_days=3, step_days=3)
    explicit_anchored = s._build_walk_forward_slices(
        index, train_days=10, test_days=3, step_days=3, mode="anchored"
    )
    assert default_mode == explicit_anchored


def test_build_walk_forward_slices_count_matches_horizon_formula():
    index = pd.date_range("2024-01-01", periods=24 * 80, freq="h")
    train_days = 10
    test_days = 5
    step_days = 7

    got = s._build_walk_forward_slices(
        index, train_days=train_days, test_days=test_days, step_days=step_days
    )

    horizon = index[-1] - index[0]
    required = pd.Timedelta(days=train_days + test_days)
    if horizon < required:
        expected = 0
    else:
        expected = int((horizon - required) // pd.Timedelta(days=step_days)) + 1
    assert len(got) == expected


def test_build_walk_forward_slices_train_and_test_boundaries_are_monotonic():
    index = pd.date_range("2024-01-01", periods=24 * 40, freq="h")
    got = s._build_walk_forward_slices(index, train_days=8, test_days=4, step_days=4)

    assert len(got) > 1
    for i in range(1, len(got)):
        prev_train_end, prev_test_end = got[i - 1]
        curr_train_end, curr_test_end = got[i]
        assert curr_train_end > prev_train_end
        assert curr_test_end > prev_test_end
        assert curr_train_end - prev_train_end == pd.Timedelta(days=4)
        assert curr_test_end - curr_train_end == pd.Timedelta(days=4)


def test_build_walk_forward_slices_rejects_non_int_days():
    index = pd.date_range("2024-01-01", periods=24 * 20, freq="h")
    with pytest.raises(ValueError, match="train_days must be int"):
        s._build_walk_forward_slices(index, train_days=5.0, test_days=2, step_days=2)


def test_build_walk_forward_windows_anchored_keeps_train_start_fixed():
    index = pd.date_range("2024-01-01", periods=24 * 20, freq="h")
    got = s._build_walk_forward_windows(index, train_days=5, test_days=2, step_days=3, mode="anchored")

    assert len(got) > 1
    first_train_start = got[0][0]
    for train_start, train_end, test_start, test_end in got:
        assert train_start == first_train_start
        assert test_start == train_end
        assert test_end > test_start


def test_build_walk_forward_windows_rolling_moves_train_start():
    index = pd.date_range("2024-01-01", periods=24 * 20, freq="h")
    got = s._build_walk_forward_windows(index, train_days=5, test_days=2, step_days=3, mode="rolling")

    assert len(got) > 1
    first_train_start, first_train_end, _, _ = got[0]
    second_train_start, second_train_end, _, _ = got[1]
    assert second_train_start > first_train_start
    assert second_train_start - first_train_start == pd.Timedelta(days=3)
    assert first_train_end - first_train_start == pd.Timedelta(days=5)
    assert second_train_end - second_train_start == pd.Timedelta(days=5)
