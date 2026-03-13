"""Artifact contract loader and validator for AUTOWFO."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional


ARTIFACT_CONTRACT_PATH_ENV = "AUTOWFO_ARTIFACT_CONTRACT_PATH"
DEFAULT_ARTIFACT_CONTRACT_PATH = (
    Path(__file__).resolve().parents[1] / "plans" / "protocols" / "artifact_contract.yaml"
)


def _non_empty_str(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _assert_unique(items: Iterable[str], field_name: str) -> None:
    seen = set()
    for item in items:
        if item in seen:
            raise ValueError(f"duplicate {field_name}: {item}")
        seen.add(item)


def _resolve_artifact_contract_path(path: Optional[str] = None) -> Path:
    if path:
        return Path(path)
    env_path = os.environ.get(ARTIFACT_CONTRACT_PATH_ENV)
    if env_path:
        return Path(env_path)
    return DEFAULT_ARTIFACT_CONTRACT_PATH


def _assert_string_list(
    payload: Mapping[str, object],
    field_name: str,
    source: str,
) -> List[str]:
    values = payload.get(field_name)
    if not isinstance(values, list) or not values:
        raise ValueError(f"{field_name} must be a non-empty list: {source}")
    output: List[str] = []
    for idx, value in enumerate(values):
        if not _non_empty_str(value):
            raise ValueError(f"{field_name}[{idx}] must be a non-empty string: {source}")
        output.append(str(value).strip())
    _assert_unique(output, field_name)
    return output


def load_artifact_contract(path: Optional[str] = None) -> Dict[str, object]:
    contract_path = _resolve_artifact_contract_path(path)
    if not contract_path.exists():
        raise ValueError(f"artifact contract file not found: {contract_path}")
    try:
        payload = json.loads(contract_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"artifact contract is invalid JSON/YAML: {contract_path}") from exc
    validate_artifact_contract(payload, source=str(contract_path))
    return payload


def validate_artifact_contract(payload: object, source: str = "<in-memory>") -> None:
    if not isinstance(payload, dict):
        raise ValueError(f"artifact contract must be an object: {source}")
    contract_version = payload.get("contract_version")
    if not _non_empty_str(contract_version):
        raise ValueError(f"contract_version is required: {source}")
    _assert_string_list(payload, "required_files", source)
    _assert_string_list(payload, "row_metadata_fields", source)
    _assert_string_list(payload, "run_metadata_fields", source)


def build_string_list(payload: Mapping[str, object], field_name: str) -> List[str]:
    if field_name not in {"required_files", "row_metadata_fields", "run_metadata_fields"}:
        raise ValueError(f"unknown artifact contract field: {field_name}")
    return _assert_string_list(payload, field_name, "<in-memory>")

