"""Cross-asset and cross-timeframe signal composition."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from scripts.autowfo.conditions import apply as apply_condition
from scripts.autowfo.indicators import REGISTRY


@dataclass
class SignalResult:
    """Signal composition output aligned to action OHLCV index."""

    entry_long: pd.Series
    entry_short: pd.Series
    exit_long: pd.Series
    exit_short: pd.Series


def _false_series(index: pd.Index) -> pd.Series:
    return pd.Series(False, index=index, dtype=bool)


def _true_series(index: pd.Index) -> pd.Series:
    return pd.Series(True, index=index, dtype=bool)


def _as_bool_series(series: pd.Series, index: pd.Index) -> pd.Series:
    out = series.reindex(index)
    return out.fillna(False).astype(bool)


def _extract_side_params(combo_params: dict, side: str) -> dict:
    prefix = f"{side}_"
    out = {}
    for key, value in combo_params.items():
        if not key.startswith(prefix):
            continue
        field = key[len(prefix) :]
        if field.startswith("indicator") or field.startswith("operator"):
            continue
        out[field] = value
    return out


def _resolve_indicator_name(
    combo_params: dict,
    side: str,
    idx: int,
    fallback_indicator: str,
) -> str:
    keys = [f"{side}_indicator_{idx}", f"{side}_indicator"]
    for key in keys:
        val = combo_params.get(key)
        if val:
            return str(val)
    return str(fallback_indicator)


def _resolve_operator(
    combo_params: dict,
    side: str,
    idx: int,
    fallback_operator: Any,
) -> str:
    keys = [f"{side}_operator_{idx}", f"{side}_operator"]
    for key in keys:
        val = combo_params.get(key)
        if val:
            return str(val)
    if fallback_operator:
        return str(fallback_operator)
    raise ValueError(f"Missing operator for {side} indicator index {idx}")


def _evaluate_conditions(
    ohlcv: pd.DataFrame,
    indicators: list[str],
    conditions: dict,
    combo_params: dict,
    side: str,
    require_all: bool,
) -> pd.Series:
    if not indicators:
        return _true_series(ohlcv.index)

    side_params = _extract_side_params(combo_params, side)
    condition_signals = []
    for idx, fallback_indicator in enumerate(indicators):
        indicator_name = _resolve_indicator_name(combo_params, side, idx, fallback_indicator)
        if indicator_name not in REGISTRY:
            raise ValueError(f"Unknown indicator: {indicator_name!r}")

        indicator_mod = REGISTRY[indicator_name]
        indicator_values = indicator_mod.compute(ohlcv, side_params)
        if not isinstance(indicator_values, pd.Series):
            indicator_values = pd.Series(indicator_values, index=ohlcv.index)
        indicator_values = indicator_values.reindex(ohlcv.index)

        condition_cfg = conditions.get(fallback_indicator, {}) or {}
        operator = _resolve_operator(
            combo_params=combo_params,
            side=side,
            idx=idx,
            fallback_operator=condition_cfg.get("operator"),
        )
        condition_params = dict(condition_cfg)
        condition_params.update(side_params)
        signal = apply_condition(indicator_values, operator, condition_params)
        condition_signals.append(_as_bool_series(signal, ohlcv.index))

    merged = condition_signals[0]
    for signal in condition_signals[1:]:
        if require_all:
            merged = merged & signal
        else:
            merged = merged | signal
    return _as_bool_series(merged, ohlcv.index)


def _align_trigger_to_action(
    trigger_signal: pd.Series,
    trigger_index: pd.Index,
    action_index: pd.Index,
) -> pd.Series:
    if len(action_index) == 0:
        return _false_series(action_index)
    if len(action_index) == 1:
        return _false_series(action_index)
    if trigger_signal.empty:
        return _false_series(action_index)

    trigger_bool = _as_bool_series(trigger_signal, trigger_index)
    if not bool(trigger_bool.any()):
        return _false_series(action_index)

    duration = action_index[1] - action_index[0]
    out = _false_series(action_index)
    for i in range(1, len(action_index)):
        current_ts = action_index[i]
        window_start = current_ts - duration
        window_hits = trigger_bool.loc[(trigger_bool.index > window_start) & (trigger_bool.index <= current_ts)]
        out.iloc[i] = bool(window_hits.any())
    return out


def compose(
    trigger_ohlcv: pd.DataFrame,
    action_ohlcv: pd.DataFrame,
    experiment: Any,
    combo_params: dict,
) -> SignalResult:
    """Generate entry/exit signals for one experiment combo."""
    config = getattr(experiment, "config", None)
    if not isinstance(config, dict):
        raise TypeError("experiment must provide a .config dict")

    trigger_cfg = config.get("trigger", {}) or {}
    action_cfg = config.get("action", {}) or {}

    trigger_signal = _evaluate_conditions(
        ohlcv=trigger_ohlcv,
        indicators=list(trigger_cfg.get("indicators", [])),
        conditions=dict(trigger_cfg.get("conditions", {})),
        combo_params=combo_params,
        side="trigger",
        require_all=bool(trigger_cfg.get("require_all", True)),
    )

    same_asset = str(trigger_cfg.get("asset", "")).strip() == str(action_cfg.get("asset", "")).strip()
    same_timeframe = str(trigger_cfg.get("timeframe", "")).strip() == str(action_cfg.get("timeframe", "")).strip()
    if same_asset and same_timeframe:
        trigger_aligned = _as_bool_series(trigger_signal, action_ohlcv.index)
    else:
        trigger_aligned = _align_trigger_to_action(
            trigger_signal=trigger_signal,
            trigger_index=trigger_ohlcv.index,
            action_index=action_ohlcv.index,
        )

    action_signal = _evaluate_conditions(
        ohlcv=action_ohlcv,
        indicators=list(action_cfg.get("indicators", [])),
        conditions=dict(action_cfg.get("conditions", {})),
        combo_params=combo_params,
        side="action",
        require_all=bool(action_cfg.get("require_all", True)),
    )

    combined = _as_bool_series(trigger_aligned & action_signal, action_ohlcv.index)
    direction = str(combo_params.get("direction", "long")).strip().lower()
    false_signal = _false_series(action_ohlcv.index)

    if direction == "long":
        entry_long = combined
        entry_short = false_signal
    elif direction == "short":
        entry_long = false_signal
        entry_short = combined
    else:
        raise ValueError("combo_params['direction'] must be 'long' or 'short'")

    return SignalResult(
        entry_long=_as_bool_series(entry_long, action_ohlcv.index),
        entry_short=_as_bool_series(entry_short, action_ohlcv.index),
        exit_long=false_signal.copy(),
        exit_short=false_signal.copy(),
    )
