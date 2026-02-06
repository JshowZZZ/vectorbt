import pandas as pd

from scripts import run_btc_regime_sweep as sweep
from scripts.autowfo import strategy as s


def test_pick_series_from_map_wrapper_matches_module():
    series_map = {
        12: pd.Series([1.0, 2.0], index=[0, 1]),
        24: pd.Series([3.0, 4.0], index=[0, 1]),
    }
    expected_series, expected_key = s._pick_series_from_map(series_map, 20, default_key=12)
    actual_series, actual_key = sweep._pick_series_from_map(series_map, 20, default_key=12)

    pd.testing.assert_series_equal(actual_series, expected_series)
    assert actual_key == expected_key


def test_refine_indicator_params_wrapper_matches_module():
    base_row = {"rsi_long": 60, "rsi_short": 40}
    steps = {"threshold_pair": 5}
    defaults = {"rsi": {"rsi_long": 55, "rsi_short": 45}}

    expected = s._refine_indicator_params("rsi", base_row, steps, defaults)
    actual = sweep._refine_indicator_params("rsi", base_row, steps, defaults)

    assert actual == expected


def test_iter_indicator_param_combos_wrapper_matches_module():
    combo_keys = ("rsi", "roc")
    param_options = {
        "rsi": [{"rsi_long": 60, "rsi_short": 40}],
        "roc": [{"roc_lookback": 12, "roc_threshold": 0.01}],
    }
    expected = list(s._iter_indicator_param_combos(combo_keys, param_options))
    actual = list(sweep._iter_indicator_param_combos(combo_keys, param_options))
    assert actual == expected


def test_apply_indicator_combo_wrapper_matches_module():
    index = pd.date_range("2024-01-01", periods=5, freq="h")
    long_regime = pd.Series(True, index=index)
    short_regime = pd.Series(True, index=index)

    ctx = {
        "rsi_series": pd.Series([70, 50, 20, 80, 40], index=index),
        "roc_by_lb": {12: pd.Series([0.02, 0.0, -0.03, 0.05, -0.02], index=index)},
        "volume_zscore_by_lb": {12: pd.Series([1.0, 0.5, 1.2, 0.1, 0.9], index=index)},
    }
    combo_keys = ("rsi", "roc", "volume_z")
    combo_params = {
        "rsi_long": 60,
        "rsi_short": 40,
        "roc_lookback": 12,
        "roc_threshold": 0.01,
        "volume_lookback": 12,
        "volume_z": 0.8,
    }

    expected_long, expected_short, expected_params = s._apply_indicator_combo(
        long_regime,
        short_regime,
        combo_keys,
        combo_params,
        ctx,
    )
    actual_long, actual_short, actual_params = sweep._apply_indicator_combo(
        long_regime,
        short_regime,
        combo_keys,
        combo_params,
        ctx,
    )

    pd.testing.assert_series_equal(actual_long, expected_long)
    pd.testing.assert_series_equal(actual_short, expected_short)
    assert actual_params == expected_params


def test_coerce_indicator_params_wrapper_matches_module():
    ctx = {
        "ma_trend_by_pair": {(10, 30): (None, None), (20, 50): (None, None)},
        "roc_by_lb": {6: pd.Series(dtype=float), 12: pd.Series(dtype=float)},
    }
    combo_keys = ("ma_trend", "roc")
    params = {"ma_fast": 11, "ma_slow": 31, "roc_lookback": 9}

    expected = s._coerce_indicator_params(combo_keys, params, ctx)
    actual = sweep._coerce_indicator_params(combo_keys, params, ctx)

    assert actual == expected
