"""Mode-B indicator pool expansion with auto-mapped Experiment configs."""

from __future__ import annotations

import copy
import hashlib
import itertools
import json
from typing import Any

import pandas as pd

from scripts.autowfo.experiment import Experiment
from scripts.autowfo.indicators import REGISTRY
from scripts.autowfo.pruning import PruningTracker


def _as_indicator_list(raw: Any) -> list[str]:
    if isinstance(raw, list):
        values = [str(item).strip() for item in raw if str(item).strip()]
    else:
        values = []
    deduped = []
    seen = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _parse_combo_sizes(pool_config: dict) -> list[int]:
    raw_sizes = pool_config.get("combo_sizes")
    if isinstance(raw_sizes, list):
        sizes = [int(item) for item in raw_sizes if int(item) >= 2]
        if sizes:
            return sorted(set(sizes))

    raw_range = pool_config.get("combo_size_range")
    if isinstance(raw_range, (list, tuple)) and len(raw_range) == 2:
        low = int(raw_range[0])
        high = int(raw_range[1])
        low = max(2, low)
        high = max(low, high)
        return list(range(low, high + 1))

    return [2, 3, 4]


def _json_list(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        try:
            payload = json.loads(text)
            if isinstance(payload, list):
                return [str(item).strip() for item in payload if str(item).strip()]
        except Exception:
            return [text]
    return []


def _as_dict(value: Any) -> dict:
    return dict(value) if isinstance(value, dict) else {}


def _ensure_list(value: Any, default: list[Any]) -> list[Any]:
    if isinstance(value, list):
        return value if value else list(default)
    if value in (None, ""):
        return list(default)
    return [value]


def _build_pruning_tracker(pool_config: dict, analytics_store: Any | None) -> PruningTracker | None:
    pruning_cfg = dict(pool_config.get("pruning", {}) or {})
    pruning_cfg.setdefault("enabled", True)
    pruning_cfg.setdefault("warmup_count", 0)
    pruning_cfg.setdefault("indicator_min_samples", 1)
    tracker = PruningTracker(pruning_cfg)
    if not tracker.enabled:
        return None
    if analytics_store is None:
        return tracker

    rows = []
    try:
        leaderboard = analytics_store.query_indicator_leaderboard(limit=500)
    except Exception:
        leaderboard = []
    for item in leaderboard or []:
        if not isinstance(item, dict):
            continue
        trigger_list = _json_list(item.get("trigger_indicators"))
        action_list = _json_list(item.get("action_indicators"))
        indicators = [val for val in trigger_list + action_list if val]
        if not indicators:
            continue
        try:
            score = float(item.get("avg_sharpe"))
        except Exception:
            continue
        rows.append({"indicator_list": ",".join(sorted(set(indicators))), "avg_sharpe": score})

    if rows:
        frame = pd.DataFrame(rows)
        tracker.warm_start(frame, score_column="avg_sharpe")
        tracker.update_threshold()
    return tracker


def _build_experiment_id(combo: tuple[str, ...]) -> str:
    combo_hash = hashlib.sha256(
        json.dumps(list(combo), ensure_ascii=False, separators=(",", ":"), sort_keys=False).encode("utf-8")
    ).hexdigest()
    return f"discovery_{combo_hash[:8]}"


class ExperimentTemplate:
    """Build runnable Experiment configs from discovery pool combos."""

    def __init__(self, pool_config: dict):
        self.pool_config = dict(pool_config or {})
        self.default_trigger = self._build_default_trigger()
        self.default_action = self._build_default_action()
        self.default_risk = self._build_default_risk()
        self.default_wf = self._build_default_wf()

    def _build_default_trigger(self) -> dict:
        raw = _as_dict(self.pool_config.get("default_trigger") or self.pool_config.get("trigger"))
        base = copy.deepcopy(raw)
        base.setdefault("asset", str(self.pool_config.get("default_trigger_asset") or "BTC/USDT"))
        base.setdefault("timeframe", str(self.pool_config.get("default_trigger_timeframe") or "1h"))
        base.setdefault("require_all", True)
        base["conditions"] = _as_dict(base.get("conditions"))
        return base

    def _build_default_action(self) -> dict:
        raw = _as_dict(self.pool_config.get("default_action") or self.pool_config.get("action"))
        base = copy.deepcopy(raw)
        base.setdefault("asset", str(self.pool_config.get("default_action_asset") or "ETH/USDT"))
        base.setdefault("timeframe", str(self.pool_config.get("default_action_timeframe") or "4h"))
        base.setdefault("require_all", True)
        base.setdefault("direction", "long")
        base["conditions"] = _as_dict(base.get("conditions"))
        return base

    def _build_default_risk(self) -> dict:
        raw = _as_dict(self.pool_config.get("default_risk") or self.pool_config.get("risk"))
        return {
            "stoploss_pct_values": _ensure_list(raw.get("stoploss_pct_values"), [-2]),
            "take_profit_pct_values": _ensure_list(raw.get("take_profit_pct_values"), [3]),
            "max_hold_bars_values": _ensure_list(raw.get("max_hold_bars_values"), [24]),
        }

    def _build_default_wf(self) -> dict:
        raw = _as_dict(self.pool_config.get("default_wf") or self.pool_config.get("wf"))
        return {
            "train_days": int(raw.get("train_days", 30)),
            "test_days": int(raw.get("test_days", 10)),
            "step_days": int(raw.get("step_days", 10)),
        }

    @staticmethod
    def _indicator_operator(indicator_id: str) -> str:
        if indicator_id == "RSI":
            return "below"
        if indicator_id == "BB":
            return "near_lower"
        if indicator_id == "Volume":
            return "above_avg"
        if indicator_id in {"MACD", "EMA"}:
            return "above"

        mod = REGISTRY[indicator_id]
        operators = list(getattr(mod, "CONDITION_OPERATORS", []))
        if not operators:
            raise ValueError(f"indicator {indicator_id!r} has no CONDITION_OPERATORS")
        return str(operators[0])

    @staticmethod
    def _build_indicator_param_defaults(indicator_id: str) -> dict:
        mod = REGISTRY[indicator_id]
        params = _as_dict(getattr(mod, "PARAMS", {}))
        out = {}
        for param_name, meta in sorted(params.items()):
            default_value = _as_dict(meta).get("default")
            out[f"{param_name}_values"] = [default_value]
        return out

    @classmethod
    def _build_operator_defaults(cls, indicator_id: str, operator: str) -> dict:
        if operator in {"below", "above", "crossover", "crossunder"}:
            if indicator_id == "RSI" and operator == "below":
                return {"threshold_values": [55]}
            return {"threshold_values": [0.0]}
        if operator in {"near_lower", "near_upper"}:
            return {"pct_values": [0.85]}
        if operator == "above_avg":
            return {"multiplier_values": [0.8]}
        if operator == "pct_move":
            return {
                "pct_values": [0.0],
                "direction_values": ["up"],
                "lookback_values": [1],
            }
        return {}

    @classmethod
    def _ensure_condition(cls, indicator_id: str, provided: dict | None) -> dict:
        cfg = copy.deepcopy(_as_dict(provided))
        operator = str(cfg.get("operator") or cls._indicator_operator(indicator_id)).strip()
        if not operator:
            raise ValueError(f"missing operator for indicator {indicator_id!r}")

        normalized = {"operator": operator}
        normalized.update(cls._build_indicator_param_defaults(indicator_id))
        normalized.update(cls._build_operator_defaults(indicator_id, operator))
        normalized.update(cfg)
        return normalized

    def _build_side_conditions(self, indicators: list[str], base_conditions: dict) -> dict:
        conditions = {}
        wildcard = _as_dict(base_conditions.get("*")) if isinstance(base_conditions, dict) else {}
        for indicator_id in indicators:
            provided = _as_dict(base_conditions.get(indicator_id)) if isinstance(base_conditions, dict) else {}
            merged = dict(wildcard)
            merged.update(provided)
            conditions[indicator_id] = self._ensure_condition(indicator_id, merged)
        return conditions

    def build(self, combo: tuple[str, ...]) -> dict:
        combo_list = list(combo)
        trigger = copy.deepcopy(self.default_trigger)
        action = copy.deepcopy(self.default_action)

        trigger["indicators"] = combo_list
        trigger["conditions"] = self._build_side_conditions(combo_list, _as_dict(trigger.get("conditions")))

        action_indicators = _as_indicator_list(action.get("indicators"))
        if not action_indicators:
            action_indicators = combo_list
        action["indicators"] = action_indicators
        action["conditions"] = self._build_side_conditions(action_indicators, _as_dict(action.get("conditions")))

        return {
            "experiment_id": _build_experiment_id(combo),
            "mode": "hypothesis",
            "description": str(self.pool_config.get("description") or "discovery generated"),
            "version": int(self.pool_config.get("version", 1) or 1),
            "trigger": trigger,
            "action": action,
            "risk": copy.deepcopy(self.default_risk),
            "wf": copy.deepcopy(self.default_wf),
            "priority": "discovery",
            "selected_indicators": combo_list,
            "combo_size": len(combo_list),
        }


def generate_combinations(pool_config: dict, analytics_store: Any | None = None) -> list[dict]:
    indicator_pool = _as_indicator_list(pool_config.get("indicator_ids") or pool_config.get("indicator_pool"))
    indicator_pool = [item for item in indicator_pool if item in REGISTRY]
    if len(indicator_pool) < 2:
        return []

    combo_sizes = _parse_combo_sizes(pool_config)
    tracker = _build_pruning_tracker(pool_config, analytics_store)
    template = ExperimentTemplate(pool_config)

    output = []
    for size in combo_sizes:
        if size > len(indicator_pool):
            continue
        for combo in itertools.combinations(indicator_pool, size):
            if tracker is not None and tracker.should_prune(combo):
                tracker.increment_pruned()
                continue
            config = template.build(combo)
            try:
                Experiment.from_dict(config)
            except Exception:
                continue
            output.append(config)
    return output


def generate_experiment_configs(pool_config: dict, analytics_store: Any | None = None) -> list[dict]:
    """Backward-compatible alias for discovery config generation."""
    return generate_combinations(pool_config=pool_config, analytics_store=analytics_store)
