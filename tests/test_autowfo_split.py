import pandas as pd

from scripts import run_btc_regime_sweep as sweep
from scripts.autowfo import split as s


def test_build_walk_forward_slices_empty_index():
    got = s._build_walk_forward_slices(pd.DatetimeIndex([]), train_days=5, test_days=2, step_days=1)
    assert got == []


def test_build_walk_forward_slices_characterization():
    index = pd.date_range("2024-01-01", periods=24 * 20, freq="h")
    got = s._build_walk_forward_slices(index, train_days=5, test_days=2, step_days=3)

    assert len(got) > 0
    assert got[0] == (index[0] + pd.Timedelta(days=5), index[0] + pd.Timedelta(days=7))
    assert all(test_end <= index[-1] for _, test_end in got)


def test_build_walk_forward_slices_wrapper_matches_module():
    index = pd.date_range("2024-01-01", periods=24 * 12, freq="h")
    expected = s._build_walk_forward_slices(index, train_days=4, test_days=2, step_days=1)
    actual = sweep._build_walk_forward_slices(index, train_days=4, test_days=2, step_days=1)
    assert actual == expected
