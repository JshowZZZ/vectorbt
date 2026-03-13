import pandas as pd
import pytest

from autowfo import split as s


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
        prev_test_start, prev_test_end = got[i - 1]
        curr_test_start, curr_test_end = got[i]
        assert curr_test_start > prev_test_start
        assert curr_test_end > prev_test_end
        assert curr_test_start - prev_test_start == pd.Timedelta(days=4)
        assert curr_test_end - curr_test_start == pd.Timedelta(days=4)


def test_build_walk_forward_slices_rejects_non_int_days():
    index = pd.date_range("2024-01-01", periods=24 * 20, freq="h")
    with pytest.raises(ValueError, match="train_days must be int"):
        s._build_walk_forward_slices(index, train_days=5.0, test_days=2, step_days=2)


def test_build_walk_forward_windows_anchored_keeps_train_start_fixed():
    index = pd.date_range("2024-01-01", periods=24 * 20, freq="h")
    got = s._build_walk_forward_windows(index, train_days=5, test_days=2, step_days=3, mode="anchored")

    assert len(got) > 1
    first_train_start = got[0][0]
    for train_start, train_end, valid_start, valid_end, test_start, test_end in got:
        assert train_start == first_train_start
        assert valid_start == train_end
        assert valid_end == train_end  # valid_days=0 default
        assert test_start == valid_end
        assert test_end > test_start


def test_build_walk_forward_windows_rolling_moves_train_start():
    index = pd.date_range("2024-01-01", periods=24 * 20, freq="h")
    got = s._build_walk_forward_windows(index, train_days=5, test_days=2, step_days=3, mode="rolling")

    assert len(got) > 1
    first_train_start, first_train_end, _, _, _, _ = got[0]
    second_train_start, second_train_end, _, _, _, _ = got[1]
    assert second_train_start > first_train_start
    assert second_train_start - first_train_start == pd.Timedelta(days=3)
    assert first_train_end - first_train_start == pd.Timedelta(days=5)
    assert second_train_end - second_train_start == pd.Timedelta(days=5)


# ?? 3-way split (validation segment) tests ?????????????????????????

def test_windows_valid_days_zero_degenerates_to_2way():
    """valid_days=0 should produce 6-tuples where valid_start == valid_end == train_end."""
    index = pd.date_range("2024-01-01", periods=24 * 30, freq="h")
    got = s._build_walk_forward_windows(index, train_days=5, test_days=3, step_days=3, valid_days=0)

    assert len(got) > 0
    for train_start, train_end, valid_start, valid_end, test_start, test_end in got:
        assert valid_start == train_end
        assert valid_end == train_end
        assert test_start == train_end


def test_windows_valid_days_positive_inserts_segment():
    """valid_days>0 should insert a validation segment between train and test."""
    index = pd.date_range("2024-01-01", periods=24 * 40, freq="h")
    got = s._build_walk_forward_windows(
        index, train_days=5, test_days=3, step_days=3, valid_days=2
    )

    assert len(got) > 0
    for train_start, train_end, valid_start, valid_end, test_start, test_end in got:
        assert valid_start == train_end
        assert valid_end == train_end + pd.Timedelta(days=2)
        assert test_start == valid_end
        assert test_end == valid_end + pd.Timedelta(days=3)
        assert valid_end > valid_start  # non-zero length


def test_windows_valid_segment_no_overlap():
    """Train, valid, and test segments must not overlap."""
    index = pd.date_range("2024-01-01", periods=24 * 60, freq="h")
    got = s._build_walk_forward_windows(
        index, train_days=10, test_days=5, step_days=5, valid_days=3
    )

    assert len(got) > 0
    for train_start, train_end, valid_start, valid_end, test_start, test_end in got:
        assert train_end <= valid_start
        assert valid_end <= test_start
        assert train_start < train_end
        assert test_start < test_end


def test_windows_valid_days_rolling_mode():
    """3-way split in rolling mode should move train_start."""
    index = pd.date_range("2024-01-01", periods=24 * 40, freq="h")
    got = s._build_walk_forward_windows(
        index, train_days=5, test_days=3, step_days=3, valid_days=2, mode="rolling"
    )

    assert len(got) > 1
    first_train_start = got[0][0]
    second_train_start = got[1][0]
    assert second_train_start > first_train_start
    assert second_train_start - first_train_start == pd.Timedelta(days=3)
    # Each window: train=5d, valid=2d, test=3d = 10d total
    for _, train_end, valid_start, valid_end, test_start, test_end in got:
        assert valid_start == train_end
        assert valid_end - valid_start == pd.Timedelta(days=2)
        assert test_start == valid_end
        assert test_end - test_start == pd.Timedelta(days=3)


def test_windows_valid_days_anchored_mode():
    """3-way split in anchored mode should keep train_start fixed."""
    index = pd.date_range("2024-01-01", periods=24 * 40, freq="h")
    got = s._build_walk_forward_windows(
        index, train_days=5, test_days=3, step_days=3, valid_days=2, mode="anchored"
    )

    assert len(got) > 0
    origin = index[0]
    for train_start, _, _, _, _, _ in got:
        assert train_start == origin


def test_windows_valid_days_reduces_window_count():
    """Adding valid_days should reduce window count (more data consumed per window)."""
    index = pd.date_range("2024-01-01", periods=24 * 40, freq="h")
    without_valid = s._build_walk_forward_windows(
        index, train_days=5, test_days=3, step_days=3, valid_days=0
    )
    with_valid = s._build_walk_forward_windows(
        index, train_days=5, test_days=3, step_days=3, valid_days=5
    )
    assert len(with_valid) < len(without_valid)


def test_slices_with_valid_days_still_return_test_segment():
    """_build_walk_forward_slices should always return only the test (OOS) segment."""
    index = pd.date_range("2024-01-01", periods=24 * 40, freq="h")
    windows = s._build_walk_forward_windows(
        index, train_days=5, test_days=3, step_days=3, valid_days=2
    )
    slices = s._build_walk_forward_slices(
        index, train_days=5, test_days=3, step_days=3, valid_days=2
    )

    assert len(slices) == len(windows)
    for (_, _, _, _, test_start_w, test_end_w), (test_start_s, test_end_s) in zip(windows, slices):
        assert test_start_s == test_start_w
        assert test_end_s == test_end_w


def test_windows_valid_days_negative_raises():
    """valid_days must be >= 0."""
    index = pd.date_range("2024-01-01", periods=24 * 20, freq="h")
    with pytest.raises(ValueError, match="valid_days must be >= 0"):
        s._build_walk_forward_windows(index, train_days=5, test_days=2, step_days=2, valid_days=-1)


def test_windows_valid_days_non_int_raises():
    """valid_days must be int."""
    index = pd.date_range("2024-01-01", periods=24 * 20, freq="h")
    with pytest.raises(ValueError, match="valid_days must be int"):
        s._build_walk_forward_windows(index, train_days=5, test_days=2, step_days=2, valid_days=2.5)


def test_windows_count_formula_with_valid_days():
    """Window count formula: floor((horizon - (train+valid+test)) / step) + 1."""
    index = pd.date_range("2024-01-01", periods=24 * 80, freq="h")
    train_days = 10
    valid_days = 3
    test_days = 5
    step_days = 7

    got = s._build_walk_forward_windows(
        index, train_days=train_days, test_days=test_days, step_days=step_days, valid_days=valid_days
    )

    horizon = index[-1] - index[0]
    required = pd.Timedelta(days=train_days + valid_days + test_days)
    if horizon < required:
        expected = 0
    else:
        expected = int((horizon - required) // pd.Timedelta(days=step_days)) + 1
    assert len(got) == expected


def test_windows_returns_6_tuples():
    """Each window element must be a 6-tuple."""
    index = pd.date_range("2024-01-01", periods=24 * 30, freq="h")
    got = s._build_walk_forward_windows(index, train_days=5, test_days=3, step_days=3, valid_days=2)
    assert len(got) > 0
    for w in got:
        assert len(w) == 6

