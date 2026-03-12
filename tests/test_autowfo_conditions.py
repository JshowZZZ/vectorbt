import numpy as np
import pandas as pd
import pytest

from scripts.autowfo.conditions import OPERATOR_REGISTRY, apply


def _series(values):
    return pd.Series(values, index=pd.date_range("2026-03-01", periods=len(values), freq="h"))


def test_registry_exports_all_operators():
    expected = {
        "below",
        "above",
        "crossover",
        "crossunder",
        "near_lower",
        "near_upper",
        "above_avg",
        "pct_move",
    }
    assert set(OPERATOR_REGISTRY.keys()) == expected


def test_apply_below_returns_bool_series():
    values = _series([10.0, 20.0, 30.0])
    out = apply(values, "below", {"threshold": 25.0})
    assert isinstance(out, pd.Series)
    pd.testing.assert_index_equal(out.index, values.index)
    assert out.dtype == bool
    assert out.tolist() == [True, True, False]


@pytest.mark.parametrize(
    ("operator", "params"),
    [
        ("below", {"threshold": 0.5}),
        ("above", {"threshold": 0.5}),
        ("crossover", {"threshold": 0.5}),
        ("crossunder", {"threshold": 0.5}),
        ("near_lower", {"pct": 0.2}),
        ("near_upper", {"pct": 0.2}),
        ("above_avg", {"multiplier": 1.2}),
        ("pct_move", {"pct": 0.1, "direction": "up", "lookback": 1}),
    ],
)
def test_nan_input_yields_false(operator, params):
    values = _series([np.nan, 0.4, np.nan, 0.8])
    out = apply(values, operator, params)
    assert out.dtype == bool
    assert bool(out.isna().any()) is False
    assert bool(out.iloc[0]) is False
    assert bool(out.iloc[2]) is False


def test_crossover_first_bar_false_and_cross_logic():
    values = _series([0.2, 0.4, 0.7, 0.8, 0.3, 0.9])
    out = apply(values, "crossover", {"threshold": 0.5})
    assert bool(out.iloc[0]) is False
    assert out.tolist() == [False, False, True, False, False, True]


def test_crossunder_first_bar_false_and_cross_logic():
    values = _series([0.8, 0.7, 0.4, 0.2, 0.6, 0.1])
    out = apply(values, "crossunder", {"threshold": 0.5})
    assert bool(out.iloc[0]) is False
    assert out.tolist() == [False, False, True, False, False, True]


def test_crossover_accepts_reference_series():
    values = _series([1.0, 2.0, 3.0, 1.0])
    reference = _series([1.5, 1.5, 1.5, 1.5])
    out = apply(values, "crossover", {"reference": reference})
    assert out.tolist() == [False, True, False, False]


def test_pct_move_direction_up_and_down():
    values = _series([100.0, 106.0, 90.0, 95.0])
    out_up = apply(values, "pct_move", {"pct": 0.05, "direction": "up", "lookback": 1})
    out_down = apply(values, "pct_move", {"pct": 0.05, "direction": "down", "lookback": 1})
    assert out_up.tolist() == [False, True, False, True]
    assert out_down.tolist() == [False, False, True, False]


def test_unknown_operator_raises_value_error():
    values = _series([1.0, 2.0, 3.0])
    with pytest.raises(ValueError, match="Unknown operator"):
        apply(values, "not_an_operator", {})
