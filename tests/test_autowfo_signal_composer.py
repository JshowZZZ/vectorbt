from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd

from scripts.autowfo import signal_composer


def _make_ohlcv(index: pd.DatetimeIndex) -> pd.DataFrame:
    close = pd.Series(100.0 + np.arange(len(index)), index=index, dtype=float)
    return pd.DataFrame(
        {
            "open": close * 0.999,
            "high": close * 1.002,
            "low": close * 0.998,
            "close": close,
            "volume": pd.Series(1000.0, index=index, dtype=float),
        }
    )


def _indicator(values):
    return SimpleNamespace(
        compute=lambda ohlcv_df, _params: pd.Series(values, index=ohlcv_df.index, dtype=float),
        PARAMS={},
    )


def _build_experiment(
    trigger_indicators,
    action_indicators,
    trigger_conditions,
    action_conditions,
    trigger_require_all=True,
    action_require_all=True,
    trigger_asset="BTC/USDT",
    action_asset="BTC/USDT",
    trigger_tf="1h",
    action_tf="1h",
):
    return SimpleNamespace(
        config={
            "trigger": {
                "asset": trigger_asset,
                "timeframe": trigger_tf,
                "indicators": trigger_indicators,
                "conditions": trigger_conditions,
                "require_all": trigger_require_all,
            },
            "action": {
                "asset": action_asset,
                "timeframe": action_tf,
                "indicators": action_indicators,
                "conditions": action_conditions,
                "require_all": action_require_all,
            },
        }
    )


def test_compose_same_timeframe_long_direction(monkeypatch):
    index = pd.date_range("2025-01-01", periods=4, freq="1h")
    trigger_ohlcv = _make_ohlcv(index)
    action_ohlcv = _make_ohlcv(index)

    registry = {
        "TRIG": _indicator([0.1, 0.6, 0.7, 0.2]),
        "ACT": _indicator([0.9, 0.8, 0.4, 0.9]),
    }
    monkeypatch.setattr(signal_composer, "REGISTRY", registry)

    experiment = _build_experiment(
        trigger_indicators=["TRIG"],
        action_indicators=["ACT"],
        trigger_conditions={"TRIG": {"operator": "above"}},
        action_conditions={"ACT": {"operator": "above"}},
    )
    combo_params = {"trigger_threshold": 0.5, "action_threshold": 0.5, "direction": "long"}

    out = signal_composer.compose(trigger_ohlcv, action_ohlcv, experiment, combo_params)

    assert isinstance(out, signal_composer.SignalResult)
    assert out.entry_long.tolist() == [False, True, False, False]
    assert out.entry_short.tolist() == [False, False, False, False]
    assert out.exit_long.tolist() == [False, False, False, False]
    assert out.exit_short.tolist() == [False, False, False, False]
    assert out.entry_long.dtype == bool
    assert out.entry_short.dtype == bool
    assert out.exit_long.dtype == bool
    assert out.exit_short.dtype == bool


def test_compose_short_direction_routes_entry_short(monkeypatch):
    index = pd.date_range("2025-01-01", periods=4, freq="1h")
    trigger_ohlcv = _make_ohlcv(index)
    action_ohlcv = _make_ohlcv(index)

    registry = {
        "TRIG": _indicator([0.1, 0.6, 0.7, 0.2]),
        "ACT": _indicator([0.9, 0.8, 0.4, 0.9]),
    }
    monkeypatch.setattr(signal_composer, "REGISTRY", registry)

    experiment = _build_experiment(
        trigger_indicators=["TRIG"],
        action_indicators=["ACT"],
        trigger_conditions={"TRIG": {"operator": "above"}},
        action_conditions={"ACT": {"operator": "above"}},
    )
    combo_params = {"trigger_threshold": 0.5, "action_threshold": 0.5, "direction": "short"}

    out = signal_composer.compose(trigger_ohlcv, action_ohlcv, experiment, combo_params)

    assert out.entry_long.tolist() == [False, False, False, False]
    assert out.entry_short.tolist() == [False, True, False, False]


def test_require_all_false_uses_or(monkeypatch):
    index = pd.date_range("2025-01-01", periods=4, freq="1h")
    trigger_ohlcv = _make_ohlcv(index)
    action_ohlcv = _make_ohlcv(index)

    registry = {
        "TRIG": _indicator([1.0, 1.0, 1.0, 1.0]),
        "A1": _indicator([0.0, 0.0, 1.0, 0.0]),
        "A2": _indicator([0.0, 1.0, 0.0, 0.0]),
    }
    monkeypatch.setattr(signal_composer, "REGISTRY", registry)

    experiment = _build_experiment(
        trigger_indicators=["TRIG"],
        action_indicators=["A1", "A2"],
        trigger_conditions={"TRIG": {"operator": "above"}},
        action_conditions={"A1": {"operator": "above"}, "A2": {"operator": "above"}},
        action_require_all=False,
    )
    combo_params = {"trigger_threshold": 0.5, "action_threshold": 0.5, "direction": "long"}

    out = signal_composer.compose(trigger_ohlcv, action_ohlcv, experiment, combo_params)
    assert out.entry_long.tolist() == [False, True, True, False]


def test_require_all_true_uses_and(monkeypatch):
    index = pd.date_range("2025-01-01", periods=4, freq="1h")
    trigger_ohlcv = _make_ohlcv(index)
    action_ohlcv = _make_ohlcv(index)

    registry = {
        "TRIG": _indicator([1.0, 1.0, 1.0, 1.0]),
        "A1": _indicator([0.0, 0.0, 1.0, 0.0]),
        "A2": _indicator([0.0, 1.0, 0.0, 0.0]),
    }
    monkeypatch.setattr(signal_composer, "REGISTRY", registry)

    experiment = _build_experiment(
        trigger_indicators=["TRIG"],
        action_indicators=["A1", "A2"],
        trigger_conditions={"TRIG": {"operator": "above"}},
        action_conditions={"A1": {"operator": "above"}, "A2": {"operator": "above"}},
        action_require_all=True,
    )
    combo_params = {"trigger_threshold": 0.5, "action_threshold": 0.5, "direction": "long"}

    out = signal_composer.compose(trigger_ohlcv, action_ohlcv, experiment, combo_params)
    assert out.entry_long.tolist() == [False, False, False, False]


def test_cross_timeframe_alignment_propagates_any_trigger(monkeypatch):
    trigger_index = pd.date_range("2025-01-01 00:00:00", periods=8, freq="1h")
    action_index = pd.date_range("2025-01-01 00:00:00", periods=3, freq="4h")
    trigger_ohlcv = _make_ohlcv(trigger_index)
    action_ohlcv = _make_ohlcv(action_index)

    registry = {
        "TRIG": _indicator([0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0]),
        "ACT": _indicator([1.0, 1.0, 1.0]),
    }
    monkeypatch.setattr(signal_composer, "REGISTRY", registry)

    experiment = _build_experiment(
        trigger_indicators=["TRIG"],
        action_indicators=["ACT"],
        trigger_conditions={"TRIG": {"operator": "above"}},
        action_conditions={"ACT": {"operator": "above"}},
        trigger_asset="BTC/USDT",
        action_asset="ETH/USDT",
        trigger_tf="1h",
        action_tf="4h",
    )
    combo_params = {"trigger_threshold": 0.5, "action_threshold": 0.5, "direction": "long"}

    out = signal_composer.compose(trigger_ohlcv, action_ohlcv, experiment, combo_params)
    assert out.entry_long.tolist() == [False, True, True]


def test_nan_values_produce_false_not_nan(monkeypatch):
    index = pd.date_range("2025-01-01", periods=3, freq="1h")
    trigger_ohlcv = _make_ohlcv(index)
    action_ohlcv = _make_ohlcv(index)

    registry = {
        "TRIG": _indicator([np.nan, 0.7, np.nan]),
        "ACT": _indicator([1.0, 1.0, 1.0]),
    }
    monkeypatch.setattr(signal_composer, "REGISTRY", registry)

    experiment = _build_experiment(
        trigger_indicators=["TRIG"],
        action_indicators=["ACT"],
        trigger_conditions={"TRIG": {"operator": "above"}},
        action_conditions={"ACT": {"operator": "above"}},
    )
    combo_params = {"trigger_threshold": 0.5, "action_threshold": 0.5, "direction": "long"}

    out = signal_composer.compose(trigger_ohlcv, action_ohlcv, experiment, combo_params)
    assert out.entry_long.tolist() == [False, True, False]
    assert bool(out.entry_long.isna().any()) is False
