"""Metric contract loader and validator for AUTOWFO."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional


METRIC_CONTRACT_PATH_ENV = "AUTOWFO_METRIC_CONTRACT_PATH"
DEFAULT_METRIC_CONTRACT_PATH = (
    Path(__file__).resolve().parents[1] / "plans" / "protocols" / "metric_contract.yaml"
)

METRIC_SECTIONS = (
    "is_series_metrics",
    "combo_metrics",
    "is_aggregate_metrics",
    "oos_aggregate_metrics",
)


def _non_empty_str(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _assert_unique(items: Iterable[str], field_name: str) -> None:
    seen = set()
    for item in items:
        if item in seen:
            raise ValueError(f"duplicate {field_name}: {item}")
        seen.add(item)


def _resolve_metric_contract_path(path: Optional[str] = None) -> Path:
    if path:
        return Path(path)
    env_path = os.environ.get(METRIC_CONTRACT_PATH_ENV)
    if env_path:
        return Path(env_path)
    return DEFAULT_METRIC_CONTRACT_PATH


def _assert_metric_entries(
    payload: Mapping[str, object],
    section_name: str,
    source: str,
) -> List[Dict[str, str]]:
    section = payload.get(section_name)
    if not isinstance(section, list) or not section:
        raise ValueError(f"{section_name} must be a non-empty list: {source}")

    output: List[Dict[str, str]] = []
    names: List[str] = []
    for idx, item in enumerate(section):
        if not isinstance(item, dict):
            raise ValueError(f"{section_name}[{idx}] must be an object: {source}")
        name = item.get("name")
        formula = item.get("formula")
        if not _non_empty_str(name):
            raise ValueError(f"{section_name}[{idx}].name must be a non-empty string: {source}")
        if not _non_empty_str(formula):
            raise ValueError(f"{section_name}[{idx}].formula must be a non-empty string: {source}")
        metric_name = str(name).strip()
        names.append(metric_name)
        output.append({"name": metric_name, "formula": str(formula).strip()})
    _assert_unique(names, f"{section_name} metric")
    return output


def load_metric_contract(path: Optional[str] = None) -> Dict[str, object]:
    contract_path = _resolve_metric_contract_path(path)
    if not contract_path.exists():
        raise ValueError(f"metric contract file not found: {contract_path}")
    try:
        # Keep format dependency-free by storing YAML as JSON-compatible content.
        payload = json.loads(contract_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"metric contract is invalid JSON/YAML: {contract_path}") from exc
    validate_metric_contract(payload, source=str(contract_path))
    return payload


def validate_metric_contract(payload: object, source: str = "<in-memory>") -> None:
    if not isinstance(payload, dict):
        raise ValueError(f"metric contract must be an object: {source}")

    contract_version = payload.get("contract_version")
    if not _non_empty_str(contract_version):
        raise ValueError(f"contract_version is required: {source}")

    for section_name in METRIC_SECTIONS:
        _assert_metric_entries(payload, section_name, source)


def build_metric_name_list(
    payload: Mapping[str, object],
    section_name: str,
) -> List[str]:
    if section_name not in METRIC_SECTIONS:
        raise ValueError(f"unknown metric section: {section_name}")
    entries = _assert_metric_entries(payload, section_name, "<in-memory>")
    return [entry["name"] for entry in entries]

