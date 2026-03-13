"""Split protocol loader and validator for AUTOWFO."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional


SPLIT_PROTOCOL_PATH_ENV = "AUTOWFO_SPLIT_PROTOCOL_PATH"
DEFAULT_SPLIT_PROTOCOL_PATH = (
    Path(__file__).resolve().parents[1] / "plans" / "protocols" / "split_protocol.yaml"
)


def _non_empty_str(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _assert_unique(items: Iterable[str], field_name: str) -> None:
    seen = set()
    for item in items:
        if item in seen:
            raise ValueError(f"duplicate {field_name}: {item}")
        seen.add(item)


def _resolve_split_protocol_path(path: Optional[str] = None) -> Path:
    if path:
        return Path(path)
    env_path = os.environ.get(SPLIT_PROTOCOL_PATH_ENV)
    if env_path:
        return Path(env_path)
    return DEFAULT_SPLIT_PROTOCOL_PATH


def _assert_segment(payload: Mapping[str, object], name: str, source: str) -> None:
    segments = payload.get("segments")
    if not isinstance(segments, dict):
        raise ValueError(f"segments must be an object: {source}")
    segment = segments.get(name)
    if not isinstance(segment, dict):
        raise ValueError(f"segments.{name} must be an object: {source}")
    required = segment.get("required")
    if not isinstance(required, bool):
        raise ValueError(f"segments.{name}.required must be bool: {source}")
    min_days = segment.get("min_days")
    if not isinstance(min_days, int) or min_days < 0:
        raise ValueError(f"segments.{name}.min_days must be int >= 0: {source}")


def _assert_string_list(payload: Mapping[str, object], field_name: str, source: str) -> List[str]:
    values = payload.get(field_name)
    if not isinstance(values, list) or not values:
        raise ValueError(f"{field_name} must be a non-empty list: {source}")
    output = []
    for idx, value in enumerate(values):
        if not _non_empty_str(value):
            raise ValueError(f"{field_name}[{idx}] must be a non-empty string: {source}")
        output.append(str(value).strip())
    _assert_unique(output, field_name)
    return output


def load_split_protocol(path: Optional[str] = None) -> Dict[str, object]:
    protocol_path = _resolve_split_protocol_path(path)
    if not protocol_path.exists():
        raise ValueError(f"split protocol file not found: {protocol_path}")
    try:
        payload = json.loads(protocol_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"split protocol is invalid JSON/YAML: {protocol_path}") from exc
    validate_split_protocol(payload, source=str(protocol_path))
    return payload


def validate_split_protocol(payload: object, source: str = "<in-memory>") -> None:
    if not isinstance(payload, dict):
        raise ValueError(f"split protocol must be an object: {source}")

    protocol_version = payload.get("protocol_version")
    if not _non_empty_str(protocol_version):
        raise ValueError(f"protocol_version is required: {source}")

    default_mode = payload.get("default_mode")
    if not _non_empty_str(default_mode):
        raise ValueError(f"default_mode is required: {source}")

    supported_modes = _assert_string_list(payload, "supported_modes", source)
    if str(default_mode).strip() not in supported_modes:
        raise ValueError(f"default_mode '{default_mode}' is not in supported_modes: {source}")

    time_units = payload.get("time_units")
    if not _non_empty_str(time_units):
        raise ValueError(f"time_units is required: {source}")

    _assert_segment(payload, "train", source)
    _assert_segment(payload, "valid", source)
    _assert_segment(payload, "test", source)

    constraints = payload.get("constraints")
    if not isinstance(constraints, dict):
        raise ValueError(f"constraints must be an object: {source}")
    for field_name in ("step_days_min_equals_test_days", "allow_oos_overlap"):
        if not isinstance(constraints.get(field_name), bool):
            raise ValueError(f"constraints.{field_name} must be bool: {source}")

    output_schema = payload.get("output_schema")
    if not isinstance(output_schema, dict):
        raise ValueError(f"output_schema must be an object: {source}")
    _assert_string_list(output_schema, "slice_tuple", source)
    if "window_tuple" in output_schema:
        _assert_string_list(output_schema, "window_tuple", source)


def build_supported_modes(payload: Mapping[str, object]) -> List[str]:
    return _assert_string_list(payload, "supported_modes", "<in-memory>")


def build_default_mode(payload: Mapping[str, object]) -> str:
    value = payload.get("default_mode")
    if not _non_empty_str(value):
        raise ValueError("default_mode is required")
    return str(value).strip()

