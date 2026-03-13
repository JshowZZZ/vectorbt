"""Strategy schema loader and validator for AUTOWFO."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Mapping, Optional


STRATEGY_SCHEMA_PATH_ENV = "AUTOWFO_STRATEGY_SCHEMA_PATH"
DEFAULT_STRATEGY_SCHEMA_PATH = (
    Path(__file__).resolve().parents[1] / "plans" / "protocols" / "strategy_schema.json"
)


def _non_empty_str(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _assert_list_of_dicts(values: object, field_name: str) -> List[Dict[str, object]]:
    if not isinstance(values, list):
        raise ValueError(f"{field_name} must be a list")
    output: List[Dict[str, object]] = []
    for idx, item in enumerate(values):
        if not isinstance(item, dict):
            raise ValueError(f"{field_name}[{idx}] must be an object")
        output.append(item)
    return output


def _assert_unique(items: Iterable[str], field_name: str) -> None:
    seen = set()
    for item in items:
        if item in seen:
            raise ValueError(f"duplicate {field_name}: {item}")
        seen.add(item)


def _resolve_strategy_schema_path(path: Optional[str] = None) -> Path:
    if path:
        return Path(path)
    env_path = os.environ.get(STRATEGY_SCHEMA_PATH_ENV)
    if env_path:
        return Path(env_path)
    return DEFAULT_STRATEGY_SCHEMA_PATH


def load_strategy_schema(path: Optional[str] = None) -> Dict[str, object]:
    schema_path = _resolve_strategy_schema_path(path)
    if not schema_path.exists():
        raise ValueError(f"strategy schema file not found: {schema_path}")
    try:
        payload = json.loads(schema_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"strategy schema is invalid JSON: {schema_path}") from exc
    validate_strategy_schema(payload, source=str(schema_path))
    return payload


def validate_strategy_schema(payload: object, source: str = "<in-memory>") -> None:
    if not isinstance(payload, dict):
        raise ValueError(f"strategy schema must be a JSON object: {source}")

    schema_version = payload.get("schema_version")
    if not _non_empty_str(schema_version):
        raise ValueError(f"schema_version is required: {source}")

    categories = payload.get("indicator_categories")
    if not isinstance(categories, list) or not categories:
        raise ValueError(f"indicator_categories must be a non-empty list: {source}")
    category_values = []
    for idx, value in enumerate(categories):
        if not _non_empty_str(value):
            raise ValueError(f"indicator_categories[{idx}] must be a non-empty string: {source}")
        category_values.append(value.strip())
    _assert_unique(category_values, "indicator category")

    vol_modes = payload.get("vol_modes")
    if not isinstance(vol_modes, list) or not vol_modes:
        raise ValueError(f"vol_modes must be a non-empty list: {source}")
    vol_mode_values = []
    for idx, value in enumerate(vol_modes):
        if not _non_empty_str(value):
            raise ValueError(f"vol_modes[{idx}] must be a non-empty string: {source}")
        vol_mode_values.append(value.strip())
    _assert_unique(vol_mode_values, "vol_mode")

    regime_types = _assert_list_of_dicts(payload.get("regime_types"), "regime_types")
    regime_type_keys = []
    for idx, item in enumerate(regime_types):
        key = item.get("key")
        label = item.get("label")
        if not _non_empty_str(key):
            raise ValueError(f"regime_types[{idx}].key must be a non-empty string: {source}")
        if not _non_empty_str(label):
            raise ValueError(f"regime_types[{idx}].label must be a non-empty string: {source}")
        regime_type_keys.append(key.strip())
    _assert_unique(regime_type_keys, "regime type key")
    regime_type_key_set = set(regime_type_keys)

    indicators = _assert_list_of_dicts(payload.get("indicators"), "indicators")
    if not indicators:
        raise ValueError(f"indicators must be non-empty: {source}")
    indicator_keys = []
    for idx, item in enumerate(indicators):
        key = item.get("key")
        label = item.get("label")
        category = item.get("category")
        if not _non_empty_str(key):
            raise ValueError(f"indicators[{idx}].key must be a non-empty string: {source}")
        if not _non_empty_str(label):
            raise ValueError(f"indicators[{idx}].label must be a non-empty string: {source}")
        if not _non_empty_str(category):
            raise ValueError(f"indicators[{idx}].category must be a non-empty string: {source}")
        if category.strip() not in set(category_values):
            raise ValueError(
                f"indicators[{idx}].category '{category}' not in indicator_categories: {source}"
            )
        indicator_keys.append(key.strip())
    _assert_unique(indicator_keys, "indicator key")

    regimes = _assert_list_of_dicts(payload.get("regimes"), "regimes")
    if not regimes:
        raise ValueError(f"regimes must be non-empty: {source}")
    regime_names = []
    for idx, item in enumerate(regimes):
        name = item.get("name")
        label = item.get("label")
        regime_type = item.get("type")
        vol_mode = item.get("vol_mode")
        if not _non_empty_str(name):
            raise ValueError(f"regimes[{idx}].name must be a non-empty string: {source}")
        if not _non_empty_str(label):
            raise ValueError(f"regimes[{idx}].label must be a non-empty string: {source}")
        if not _non_empty_str(regime_type):
            raise ValueError(f"regimes[{idx}].type must be a non-empty string: {source}")
        if regime_type.strip() not in regime_type_key_set:
            raise ValueError(f"regimes[{idx}].type '{regime_type}' is unknown: {source}")
        if not _non_empty_str(vol_mode):
            raise ValueError(f"regimes[{idx}].vol_mode must be a non-empty string: {source}")
        if vol_mode.strip() not in set(vol_mode_values):
            raise ValueError(f"regimes[{idx}].vol_mode '{vol_mode}' is unknown: {source}")
        regime_names.append(name.strip())
    _assert_unique(regime_names, "regime name")


def _with_label_transform(
    value: str,
    label_transform: Optional[Callable[[str], str]] = None,
) -> str:
    if label_transform is None:
        return value
    return label_transform(value)


def build_indicator_meta(
    payload: Mapping[str, object],
    label_transform: Optional[Callable[[str], str]] = None,
) -> Dict[str, Dict[str, str]]:
    indicators = _assert_list_of_dicts(payload.get("indicators"), "indicators")
    return {
        item["key"].strip(): {
            "label": _with_label_transform(item["label"].strip(), label_transform),
            "category": item["category"].strip(),
        }
        for item in indicators
    }


def build_regime_name_map(
    payload: Mapping[str, object],
    label_transform: Optional[Callable[[str], str]] = None,
) -> Dict[str, str]:
    regimes = _assert_list_of_dicts(payload.get("regimes"), "regimes")
    return {
        item["name"].strip(): _with_label_transform(item["label"].strip(), label_transform)
        for item in regimes
    }


def build_regime_type_map(
    payload: Mapping[str, object],
    label_transform: Optional[Callable[[str], str]] = None,
) -> Dict[str, str]:
    regime_types = _assert_list_of_dicts(payload.get("regime_types"), "regime_types")
    return {
        item["key"].strip(): _with_label_transform(item["label"].strip(), label_transform)
        for item in regime_types
    }

