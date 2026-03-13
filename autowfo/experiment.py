"""Experiment definition model for AUTOWFO."""

from __future__ import annotations

import itertools
import json
import re
from pathlib import Path
from typing import Dict, List

from autowfo.conditions import OPERATOR_REGISTRY
from autowfo.indicators import REGISTRY

_EXPERIMENT_ID_RE = re.compile(r"^[A-Za-z0-9_]+$")


class Experiment:
    def __init__(self, config: dict):
        self.config = dict(config or {})
        self.validate()

    @classmethod
    def from_json(cls, path: Path) -> "Experiment":
        payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        return cls.from_dict(payload)

    @classmethod
    def from_dict(cls, config: dict) -> "Experiment":
        return cls(config)

    def save(self, path: Path) -> None:
        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(self.config, ensure_ascii=False, indent=2), encoding="utf-8")

    @property
    def experiment_id(self) -> str:
        return str(self.config.get("experiment_id", ""))

    @property
    def artifact_dir(self) -> Path:
        return Path("artifacts") / "experiments" / self.experiment_id

    def validate(self) -> None:
        experiment_id = str(self.config.get("experiment_id", "")).strip()
        if not experiment_id or not _EXPERIMENT_ID_RE.fullmatch(experiment_id):
            raise ValueError("experiment_id must be non-empty alphanumeric/underscore")

        mode = str(self.config.get("mode", "")).strip().lower()
        if mode not in {"hypothesis", "discovery"}:
            raise ValueError("mode must be 'hypothesis' or 'discovery'")

        trigger = self.config.get("trigger")
        action = self.config.get("action")
        if not isinstance(trigger, dict):
            raise ValueError("trigger must be an object")
        if not isinstance(action, dict):
            raise ValueError("action must be an object")

        if not str(trigger.get("asset", "")).strip() or not str(action.get("asset", "")).strip():
            raise ValueError("trigger.asset and action.asset must be non-empty strings")
        if not str(trigger.get("timeframe", "")).strip() or not str(action.get("timeframe", "")).strip():
            raise ValueError("trigger.timeframe and action.timeframe must be non-empty strings")

        for scope in ("trigger", "action"):
            block = self.config.get(scope, {})
            indicators = block.get("indicators", [])
            if not isinstance(indicators, list):
                raise ValueError(f"{scope}.indicators must be a list")
            for indicator in indicators:
                if indicator not in REGISTRY:
                    raise ValueError(f"{scope}.indicators contains unknown indicator: {indicator}")

            conditions = block.get("conditions", {})
            if not isinstance(conditions, dict):
                raise ValueError(f"{scope}.conditions must be an object")
            for condition_name, condition_cfg in conditions.items():
                if not isinstance(condition_cfg, dict):
                    raise ValueError(f"{scope}.conditions[{condition_name}] must be an object")
                operator = str(condition_cfg.get("operator", "")).strip()
                if operator not in OPERATOR_REGISTRY:
                    raise ValueError(f"{scope}.conditions[{condition_name}].operator is invalid: {operator!r}")

        wf = self.config.get("wf", {})
        if not isinstance(wf, dict):
            raise ValueError("wf must be an object")
        try:
            train_days = int(wf.get("train_days"))
            test_days = int(wf.get("test_days"))
            step_days = int(wf.get("step_days"))
        except Exception as exc:
            raise ValueError("wf.train_days/wf.test_days/wf.step_days must be integers") from exc
        if train_days < 7 or test_days < 1 or step_days < test_days:
            raise ValueError("wf must satisfy: train_days >= 7, test_days >= 1, step_days >= test_days")

        risk = self.config.get("risk", {})
        if not isinstance(risk, dict):
            raise ValueError("risk must be an object")
        stoploss_values = self._as_values_list(risk, "stoploss_pct_values", default=[-1.0])
        take_profit_values = self._as_values_list(risk, "take_profit_pct_values", default=[1.0])

        if any(float(v) >= 0.0 for v in stoploss_values):
            raise ValueError("risk.stoploss_pct_values must all be negative")
        if any(float(v) <= 0.0 for v in take_profit_values):
            raise ValueError("risk.take_profit_pct_values must all be positive")

    def expand_grid(self) -> List[dict]:
        self.validate()
        trigger_grid = self._build_side_grid("trigger")
        action_grid = self._build_side_grid("action")
        risk_grid = self._build_risk_grid()
        wf = self.config.get("wf", {})
        wf_payload = {
            "wf_train_days": int(wf["train_days"]),
            "wf_test_days": int(wf["test_days"]),
            "wf_step_days": int(wf["step_days"]),
        }
        action_direction = str(self.config.get("action", {}).get("direction", "long")).strip().lower()
        directions = ["long", "short"] if action_direction == "both" else [action_direction or "long"]

        output = []
        for trigger_params, action_params, risk_params, direction in itertools.product(
            trigger_grid,
            action_grid,
            risk_grid,
            directions,
        ):
            row = {}
            row.update(trigger_params)
            row.update(action_params)
            row.update(risk_params)
            row.update(wf_payload)
            row["direction"] = direction
            output.append(row)
        return output

    def _build_side_grid(self, side: str) -> List[dict]:
        block = self.config.get(side, {})
        indicators = block.get("indicators", [])
        conditions = block.get("conditions", {})
        if not isinstance(indicators, list) or not indicators:
            return [{}]

        per_indicator_grid: List[List[dict]] = []
        for idx, indicator in enumerate(indicators):
            condition_cfg = conditions.get(indicator, {})
            if not isinstance(condition_cfg, dict):
                condition_cfg = {}
            options = self._expand_condition_values(indicator, condition_cfg)
            side_rows = []
            for option in options:
                row = {}
                if len(indicators) == 1:
                    row[f"{side}_indicator"] = indicator
                    row[f"{side}_operator"] = condition_cfg.get("operator")
                else:
                    row[f"{side}_indicator_{idx}"] = indicator
                    row[f"{side}_operator_{idx}"] = condition_cfg.get("operator")
                for key, value in option.items():
                    row[f"{side}_{key}"] = value
                side_rows.append(row)
            per_indicator_grid.append(side_rows or [{}])

        merged_rows = []
        for parts in itertools.product(*per_indicator_grid):
            merged = {}
            for part in parts:
                for key, value in part.items():
                    if key not in merged:
                        merged[key] = value
                        continue
                    suffix = 2
                    while f"{key}_{suffix}" in merged:
                        suffix += 1
                    merged[f"{key}_{suffix}"] = value
            merged_rows.append(merged)
        return merged_rows

    def _expand_condition_values(self, indicator: str, condition_cfg: dict) -> List[dict]:
        params_meta = getattr(REGISTRY[indicator], "PARAMS", {})
        value_axes: List[tuple[str, List[object]]] = []

        if "param_values" in condition_cfg:
            param_name = str(condition_cfg.get("param_name", "")).strip()
            if not param_name:
                raise ValueError(f"condition for {indicator} has param_values but missing param_name")
            values = self._normalized_values(
                condition_cfg.get("param_values"),
                default=self._indicator_default(params_meta, param_name),
            )
            value_axes.append((param_name, values))

        for key in sorted(condition_cfg.keys()):
            if key == "param_values" or not key.endswith("_values"):
                continue
            field_name = key[:-7]
            default_value = condition_cfg.get(field_name)
            if default_value is None:
                default_value = self._indicator_default(params_meta, field_name)
            values = self._normalized_values(condition_cfg.get(key), default=default_value)
            value_axes.append((field_name, values))

        if not value_axes:
            return [{}]

        rows = []
        keys = [item[0] for item in value_axes]
        values_lists = [item[1] for item in value_axes]
        for values in itertools.product(*values_lists):
            rows.append(dict(zip(keys, values)))
        return rows

    def _build_risk_grid(self) -> List[dict]:
        risk = self.config.get("risk", {})
        stoploss_values = self._as_values_list(risk, "stoploss_pct_values", default=[-1.0])
        take_profit_values = self._as_values_list(risk, "take_profit_pct_values", default=[1.0])
        max_hold_values = self._as_values_list(risk, "max_hold_bars_values", default=[1])

        rows = []
        for sl, tp, hold in itertools.product(stoploss_values, take_profit_values, max_hold_values):
            rows.append(
                {
                    "risk_stoploss_pct": sl,
                    "risk_take_profit_pct": tp,
                    "risk_max_hold_bars": hold,
                }
            )
        return rows

    @staticmethod
    def _as_values_list(obj: dict, key: str, default: List[object]) -> List[object]:
        raw = obj.get(key)
        if isinstance(raw, list):
            if raw:
                return list(raw)
            return list(default)
        if raw is None:
            return list(default)
        return [raw]

    @staticmethod
    def _normalized_values(raw: object, default: object) -> List[object]:
        if isinstance(raw, list):
            if raw:
                return list(raw)
            return [default]
        if raw is None:
            return [default]
        return [raw]

    @staticmethod
    def _indicator_default(params_meta: Dict[str, dict], field_name: str) -> object:
        if field_name in params_meta:
            return params_meta[field_name].get("default")
        return None


