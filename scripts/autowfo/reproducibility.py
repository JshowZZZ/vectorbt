"""Helpers for Gate C reproducibility checks."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from scripts.autowfo import artifact_contract as autowfo_artifact_contract


DEFAULT_IDENTITY_FIELDS: Tuple[str, ...] = (
    "timeframe",
    "data_days",
    "regime_name",
    "regime_type",
    "vol_mode",
    "filter_name",
    "indicator_list",
    "vol_lookback",
    "vol_z",
    "mom_lookback",
    "trade_mom_lookback",
    "tp_stop",
    "sl_stop",
    "max_hold",
)

DEFAULT_METRIC_FIELDS: Tuple[str, ...] = (
    "oos_avg_total_return_pct",
    "oos_sharpe_like",
    "oos_avg_max_drawdown_pct",
    "oos_min_total_trades",
)

DEFAULT_ROW_METADATA_ARTIFACT_FILES: Tuple[str, ...] = (
    "param_sweep_combo_summary.csv",
    "param_sweep_symbol_summary.csv",
    "leaderboard.csv",
)


def _safe_json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (float, np.floating)):
        val = float(value)
        return None if np.isnan(val) else val
    if isinstance(value, (int, np.integer)):
        return int(value)
    return value


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (float, np.floating)):
        val = float(value)
        return None if np.isnan(val) else val
    if isinstance(value, (int, np.integer)):
        return float(value)
    try:
        val = float(value)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(val) else val


def _identity_key_from_row(row: pd.Series, identity_fields: Sequence[str]) -> Tuple[Any, ...]:
    return tuple(_safe_json_value(row.get(field)) for field in identity_fields)


def _identity_payload_from_key(identity_fields: Sequence[str], key: Sequence[Any]) -> Dict[str, Any]:
    return {field: value for field, value in zip(identity_fields, key)}


def _top_n_identity_map(
    df: pd.DataFrame,
    *,
    top_n: int,
    identity_fields: Sequence[str],
) -> Dict[Tuple[Any, ...], pd.Series]:
    if df is None or df.empty:
        return {}
    top_n_effective = max(0, int(top_n))
    if top_n_effective == 0:
        return {}

    top_df = df.head(top_n_effective)
    result: Dict[Tuple[Any, ...], pd.Series] = {}
    for _, row in top_df.iterrows():
        key = _identity_key_from_row(row, identity_fields)
        if key not in result:
            result[key] = row
    return result


def compare_top_n_stability(
    reference_df: pd.DataFrame,
    candidate_df: pd.DataFrame,
    *,
    top_n: int = 10,
    identity_fields: Iterable[str] = DEFAULT_IDENTITY_FIELDS,
    metric_fields: Iterable[str] = DEFAULT_METRIC_FIELDS,
    metric_abs_tolerance: float = 1e-9,
) -> Dict[str, Any]:
    """Compare two top-N result sets by identity overlap and metric drift."""

    identity_fields_tuple = tuple(identity_fields)
    metric_fields_tuple = tuple(metric_fields)
    tolerance = max(0.0, float(metric_abs_tolerance))

    reference_map = _top_n_identity_map(
        reference_df,
        top_n=top_n,
        identity_fields=identity_fields_tuple,
    )
    candidate_map = _top_n_identity_map(
        candidate_df,
        top_n=top_n,
        identity_fields=identity_fields_tuple,
    )

    reference_keys = set(reference_map.keys())
    candidate_keys = set(candidate_map.keys())
    overlap_keys = sorted(reference_keys & candidate_keys)
    reference_only_keys = sorted(reference_keys - candidate_keys)
    candidate_only_keys = sorted(candidate_keys - reference_keys)

    metric_deltas: Dict[str, Dict[str, Any]] = {}
    metric_within_tolerance: Dict[str, bool] = {}
    for field in metric_fields_tuple:
        abs_deltas: List[float] = []
        missing_count = 0
        for key in overlap_keys:
            ref_value = _safe_float(reference_map[key].get(field))
            cand_value = _safe_float(candidate_map[key].get(field))
            if ref_value is None or cand_value is None:
                missing_count += 1
                continue
            abs_deltas.append(abs(cand_value - ref_value))

        max_abs_delta = max(abs_deltas) if abs_deltas else None
        mean_abs_delta = float(np.mean(abs_deltas)) if abs_deltas else None
        within = (max_abs_delta is None) or (max_abs_delta <= tolerance)
        metric_within_tolerance[field] = bool(within)
        metric_deltas[field] = {
            "compared_rows": int(len(abs_deltas)),
            "missing_rows": int(missing_count),
            "max_abs_delta": _safe_json_value(max_abs_delta),
            "mean_abs_delta": _safe_json_value(mean_abs_delta),
            "within_tolerance": bool(within),
        }

    overlap_ratio = float(len(overlap_keys)) / float(max(len(reference_keys), 1))
    identity_match = reference_keys == candidate_keys
    metric_match = all(metric_within_tolerance.values()) if metric_within_tolerance else True

    return {
        "top_n": int(max(0, int(top_n))),
        "identity_fields": list(identity_fields_tuple),
        "metric_fields": list(metric_fields_tuple),
        "metric_abs_tolerance": float(tolerance),
        "reference_rows": int(len(reference_keys)),
        "candidate_rows": int(len(candidate_keys)),
        "overlap_rows": int(len(overlap_keys)),
        "reference_only_rows": int(len(reference_only_keys)),
        "candidate_only_rows": int(len(candidate_only_keys)),
        "overlap_ratio": float(overlap_ratio),
        "identity_match": bool(identity_match),
        "metric_match": bool(metric_match),
        "stable": bool(identity_match and metric_match),
        "metric_deltas": metric_deltas,
        "reference_only": [
            _identity_payload_from_key(identity_fields_tuple, key) for key in reference_only_keys
        ],
        "candidate_only": [
            _identity_payload_from_key(identity_fields_tuple, key) for key in candidate_only_keys
        ],
    }


def _resolve_contract_payload(
    contract_payload: Optional[Mapping[str, object]] = None,
    contract_path: Optional[str] = None,
) -> Dict[str, object]:
    if contract_payload is not None:
        payload = dict(contract_payload)
        autowfo_artifact_contract.validate_artifact_contract(payload, source="<in-memory>")
        return payload
    return autowfo_artifact_contract.load_artifact_contract(contract_path)


def _csv_header(path: Path) -> List[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        try:
            return [str(col).strip() for col in next(reader)]
        except StopIteration:
            return []


def validate_run_artifact_schema(
    run_dir: str | Path,
    *,
    contract_payload: Optional[Mapping[str, object]] = None,
    contract_path: Optional[str] = None,
    row_metadata_artifact_files: Iterable[str] = DEFAULT_ROW_METADATA_ARTIFACT_FILES,
) -> Dict[str, Any]:
    """Validate one run directory against the artifact contract."""

    run_dir_path = Path(run_dir).resolve()
    if not run_dir_path.exists():
        raise FileNotFoundError(f"run dir not found: {run_dir_path}")
    if not run_dir_path.is_dir():
        raise ValueError(f"run dir must be a directory: {run_dir_path}")

    contract = _resolve_contract_payload(contract_payload, contract_path)
    required_files = list(autowfo_artifact_contract.build_string_list(contract, "required_files"))
    row_metadata_fields = list(autowfo_artifact_contract.build_string_list(contract, "row_metadata_fields"))
    run_metadata_fields = list(autowfo_artifact_contract.build_string_list(contract, "run_metadata_fields"))

    missing_files: List[str] = []
    for filename in required_files:
        if not (run_dir_path / filename).exists():
            missing_files.append(filename)

    run_metadata_path = run_dir_path / "run_metadata.json"
    run_metadata_payload: Dict[str, Any] = {}
    missing_run_metadata_fields: List[str] = []
    run_metadata_error = None
    if run_metadata_path.exists():
        try:
            run_metadata_payload = json.loads(run_metadata_path.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            run_metadata_error = str(exc)
        else:
            if not isinstance(run_metadata_payload, dict):
                run_metadata_error = "run_metadata.json must decode to object"
                run_metadata_payload = {}
    else:
        run_metadata_error = "run_metadata.json missing"

    if run_metadata_error is None:
        missing_run_metadata_fields = [
            field for field in run_metadata_fields if field not in run_metadata_payload
        ]

    row_metadata_checks = []
    missing_row_metadata_by_file: Dict[str, List[str]] = {}
    for filename in tuple(row_metadata_artifact_files):
        path = run_dir_path / filename
        check = {"file": filename, "exists": path.exists(), "missing_fields": []}
        if path.exists():
            try:
                columns = _csv_header(path)
            except Exception:
                columns = []
            missing_fields = [field for field in row_metadata_fields if field not in columns]
            check["missing_fields"] = missing_fields
            if missing_fields:
                missing_row_metadata_by_file[filename] = missing_fields
        else:
            missing_row_metadata_by_file[filename] = list(row_metadata_fields)
        row_metadata_checks.append(check)

    valid = (
        not missing_files
        and run_metadata_error is None
        and not missing_run_metadata_fields
        and not missing_row_metadata_by_file
    )

    return {
        "run_dir": str(run_dir_path),
        "contract_version": contract.get("contract_version"),
        "required_files": required_files,
        "missing_required_files": missing_files,
        "run_metadata_file": str(run_metadata_path),
        "run_metadata_missing_fields": missing_run_metadata_fields,
        "run_metadata_error": run_metadata_error,
        "row_metadata_fields": row_metadata_fields,
        "row_metadata_checks": row_metadata_checks,
        "row_metadata_missing_by_file": missing_row_metadata_by_file,
        "valid": bool(valid),
    }
