"""Evidence Warehouse V1 protocol and candidate identity helpers."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple


EVIDENCE_WAREHOUSE_PROTOCOL_PATH_ENV = "AUTOWFO_EVIDENCE_WAREHOUSE_PROTOCOL_PATH"
DEFAULT_EVIDENCE_WAREHOUSE_PROTOCOL_PATH = (
    Path(__file__).resolve().parents[1] / "plans" / "protocols" / "evidence_warehouse_v1.json"
)
DEFAULT_EVIDENCE_WAREHOUSE_DB_RELATIVE_PATH = (
    Path("evidence_warehouse") / "evidence_warehouse.duckdb"
)

REQUIRED_IDENTITY_KEYS: Tuple[str, ...] = (
    "candidate_id",
    "run_id",
    "policy_id",
    "verdict_id",
    "cost_profile_id",
    "data_profile_id",
)

REQUIRED_TABLE_CONTRACTS: Tuple[str, ...] = (
    "strategy_candidates",
    "backtest_runs",
    "backtest_metrics",
    "ft_replay_results",
    "paper_trades",
    "live_trades",
    "execution_gap_events",
    "cost_observations",
    "gate_policies",
    "gate_verdicts",
    "promotion_decisions",
    "benchmark_results",
)

CANDIDATE_DEFINITION_FIELDS: Tuple[str, ...] = (
    "strategy_family",
    "indicator_set",
    "parameter_set",
    "timeframe",
    "market_universe",
    "direction_scope",
    "entry_rule",
    "exit_rule",
    "risk_rule",
    "cost_profile_id",
    "data_profile_id",
    "source_system",
)

REQUIRED_GATE_VERDICT_FIELDS: Tuple[str, ...] = (
    "verdict_id",
    "candidate_id",
    "policy_id",
    "verdict",
    "metric_snapshot",
    "artifact_path",
)

ALLOWED_GATE_VERDICTS: Tuple[str, ...] = ("pass", "observe", "reject", "halt")
ALLOWED_EXECUTION_GAP_TYPES: Tuple[str, ...] = (
    "data_gap",
    "signal_gap",
    "adapter_gap",
    "execution_gap",
    "cost_gap",
    "regime_gap",
)

PHASE61_62_SOURCE_SYSTEM = "autowfo_phase61_62_awf339"
PHASE61_62_RUN_ID_PREFIX = "run_phase61_62_awf339_"
PHASE61_62_GAP_ID_PREFIX = "gap_phase61_62_awf347_"
AUTOWFO_SOURCE_SYSTEM = "autowfo"
PHASE63_PAPER_TRADE_ID_PREFIX = "paper_phase63_"
PHASE63_PAPER_GAP_ID_PREFIX = "gap_phase63_paper_"


def _non_empty_str(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _assert_unique(items: Iterable[str], field_name: str) -> None:
    seen = set()
    for item in items:
        if item in seen:
            raise ValueError(f"duplicate {field_name}: {item}")
        seen.add(item)


def _assert_string_list(payload: Mapping[str, object], field_name: str, source: str) -> List[str]:
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


def _resolve_evidence_warehouse_protocol_path(path: Optional[str] = None) -> Path:
    if path:
        return Path(path)
    env_path = os.environ.get(EVIDENCE_WAREHOUSE_PROTOCOL_PATH_ENV)
    if env_path:
        return Path(env_path)
    return DEFAULT_EVIDENCE_WAREHOUSE_PROTOCOL_PATH


def _assert_required_object(
    payload: Mapping[str, object],
    field_name: str,
    source: str,
) -> Dict[str, object]:
    value = payload.get(field_name)
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object: {source}")
    return dict(value)


def _assert_required_fields(
    table_contracts: Mapping[str, object],
    table_name: str,
    source: str,
) -> List[str]:
    table_contract = table_contracts.get(table_name)
    if not isinstance(table_contract, dict):
        raise ValueError(f"table_contracts.{table_name} must be an object: {source}")
    return _assert_string_list(table_contract, "required_fields", source)


def load_evidence_warehouse_protocol(path: Optional[str] = None) -> Dict[str, object]:
    protocol_path = _resolve_evidence_warehouse_protocol_path(path)
    if not protocol_path.exists():
        raise ValueError(f"evidence warehouse protocol file not found: {protocol_path}")
    try:
        payload = json.loads(protocol_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"evidence warehouse protocol is invalid JSON: {protocol_path}") from exc
    validate_evidence_warehouse_protocol(payload, source=str(protocol_path))
    return payload


def validate_evidence_warehouse_protocol(payload: object, source: str = "<in-memory>") -> None:
    if not isinstance(payload, dict):
        raise ValueError(f"evidence warehouse protocol must be an object: {source}")

    if not _non_empty_str(payload.get("schema_version")):
        raise ValueError(f"schema_version is required: {source}")
    if not _non_empty_str(payload.get("name")):
        raise ValueError(f"name is required: {source}")

    identity_keys = _assert_required_object(payload, "identity_keys", source)
    table_contracts = _assert_required_object(payload, "table_contracts", source)

    table_required_fields: Dict[str, List[str]] = {}
    for table_name in REQUIRED_TABLE_CONTRACTS:
        table_required_fields[table_name] = _assert_required_fields(
            table_contracts,
            table_name,
            source,
        )

    for identity_key in REQUIRED_IDENTITY_KEYS:
        identity_contract = identity_keys.get(identity_key)
        if not isinstance(identity_contract, dict):
            raise ValueError(f"identity_keys.{identity_key} must be an object: {source}")
        if not _non_empty_str(identity_contract.get("purpose")):
            raise ValueError(f"identity_keys.{identity_key}.purpose is required: {source}")
        required_for = _assert_string_list(identity_contract, "required_for", source)
        for table_name in required_for:
            if table_name not in table_required_fields:
                raise ValueError(f"identity_keys.{identity_key}.required_for unknown table: {table_name}")
            if identity_key not in table_required_fields[table_name]:
                raise ValueError(
                    f"table_contracts.{table_name}.required_fields must include {identity_key}: {source}"
                )

    gate_verdict_fields = table_required_fields["gate_verdicts"]
    for field_name in REQUIRED_GATE_VERDICT_FIELDS:
        if field_name not in gate_verdict_fields:
            raise ValueError(
                f"table_contracts.gate_verdicts.required_fields must include {field_name}: {source}"
            )

    gate_verdict_contract = table_contracts["gate_verdicts"]
    allowed_verdicts = _assert_string_list(gate_verdict_contract, "allowed_verdicts", source)
    if set(allowed_verdicts) != set(ALLOWED_GATE_VERDICTS):
        raise ValueError(f"gate_verdicts.allowed_verdicts must match Survival Gate verdicts: {source}")

    gap_contract = table_contracts["execution_gap_events"]
    allowed_gap_types = _assert_string_list(gap_contract, "allowed_gap_types", source)
    if set(allowed_gap_types) != set(ALLOWED_EXECUTION_GAP_TYPES):
        raise ValueError(f"execution_gap_events.allowed_gap_types must match protocol gap types: {source}")

    _assert_string_list(payload, "implementation_invariants", source)
    _assert_string_list(payload, "initial_implementation_sequence", source)


def _canonical_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _canonical_json_value(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, tuple):
        return [_canonical_json_value(item) for item in value]
    if isinstance(value, list):
        return [_canonical_json_value(item) for item in value]
    if isinstance(value, str):
        return value.strip()
    if value is None or isinstance(value, (bool, int, float)):
        return value
    raise TypeError(f"candidate definition contains unsupported value type: {type(value).__name__}")


def build_candidate_identity_payload(candidate_definition: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(candidate_definition, Mapping):
        raise ValueError("candidate definition must be a mapping")

    payload: Dict[str, Any] = {}
    for field_name in CANDIDATE_DEFINITION_FIELDS:
        if field_name not in candidate_definition:
            raise ValueError(f"candidate definition missing required field: {field_name}")
        value = candidate_definition[field_name]
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValueError(f"candidate definition field is empty: {field_name}")
        payload[field_name] = _canonical_json_value(value)

    return payload


def build_candidate_id(candidate_definition: Mapping[str, Any]) -> str:
    payload = build_candidate_identity_payload(candidate_definition)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return f"cand_{digest[:24]}"


def _import_duckdb():
    try:
        import duckdb  # type: ignore
    except Exception as exc:
        raise RuntimeError("duckdb package is required for Evidence Warehouse operations") from exc
    return duckdb


def _resolve_warehouse_db_path(
    artifacts_dir: str | Path,
    db_path: str | Path | None = None,
) -> Path:
    if db_path:
        return Path(db_path).resolve()
    return (Path(artifacts_dir) / DEFAULT_EVIDENCE_WAREHOUSE_DB_RELATIVE_PATH).resolve()


def _quote_ident(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def _table_required_fields(protocol: Mapping[str, object]) -> Dict[str, List[str]]:
    table_contracts = _assert_required_object(protocol, "table_contracts", "<protocol>")
    return {
        table_name: _assert_required_fields(table_contracts, table_name, "<protocol>")
        for table_name in REQUIRED_TABLE_CONTRACTS
    }


def _metadata_rows(protocol: Mapping[str, object]) -> Dict[str, str]:
    return {
        "schema_version": str(protocol.get("schema_version") or ""),
        "protocol_name": str(protocol.get("name") or ""),
        "frozen_on": str(protocol.get("frozen_on") or ""),
    }


def _read_json_object(path: Path, label: str) -> Dict[str, object]:
    if not path.exists():
        raise ValueError(f"{label} file not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must decode to an object: {path}")
    return payload


def _cell_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (dict, list, tuple, bool, int, float)):
        return json.dumps(
            _canonical_json_value(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    return str(value)


def _insert_protocol_row(conn: object, table_name: str, fields: List[str], row: Mapping[str, object]) -> None:
    columns_sql = ", ".join(_quote_ident(field_name) for field_name in fields)
    placeholders = ", ".join("?" for _ in fields)
    values = [_cell_value(row.get(field_name)) for field_name in fields]
    conn.execute(
        f"INSERT INTO {_quote_ident(table_name)} ({columns_sql}) VALUES ({placeholders})",
        values,
    )


def _stable_prefixed_id(prefix: str, payload: object, *, length: int = 16) -> str:
    encoded = json.dumps(
        _canonical_json_value(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return f"{prefix}{hashlib.sha256(encoded.encode('utf-8')).hexdigest()[:length]}"


def _split_indicator_list(value: object) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _pair_universe(row: Mapping[str, object], summary: Mapping[str, object]) -> List[str]:
    pairs = set()
    for item in row.get("per_pair_counts") or []:
        if isinstance(item, Mapping) and _non_empty_str(item.get("pair")):
            pairs.add(str(item["pair"]).strip())
    aggregate = summary.get("aggregate")
    if not pairs and isinstance(aggregate, Mapping):
        for pair in aggregate.get("pairs") or []:
            if _non_empty_str(pair):
                pairs.add(str(pair).strip())
    return sorted(pairs)


def _direction_scope(row: Mapping[str, object]) -> str:
    directions = set()
    for item in row.get("per_pair_counts") or []:
        if not isinstance(item, Mapping):
            continue
        direction = str(item.get("direction") or "").strip().lower()
        if direction in {"long", "short"}:
            directions.add(direction)
    if directions == {"long", "short"}:
        return "long_short"
    if directions == {"long"}:
        return "long"
    if directions == {"short"}:
        return "short"
    strategy_name = str(row.get("strategy_name") or "").lower()
    if "longshort" in strategy_name or "long_short" in strategy_name:
        return "long_short"
    return "unknown"


def _safe_float(value: object, *, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _trade_count_delta_pct(row: Mapping[str, object]) -> float:
    autowfo_count = _safe_float(row.get("autowfo_trade_count"))
    if autowfo_count == 0:
        return 0.0
    return _safe_float(row.get("trade_count_delta")) / autowfo_count


def _bundle_id_from_path(path_value: object) -> str:
    normalized = str(path_value or "").replace("\\", "/").strip("/")
    parts = [part for part in normalized.split("/") if part]
    if len(parts) >= 2:
        return parts[-2]
    return ""


def _data_profile_id(row: Mapping[str, object], pairs: List[str]) -> str:
    payload = {
        "timeframe": str(row.get("timeframe") or ""),
        "data_days": row.get("data_days"),
        "market_universe": pairs,
    }
    return _stable_prefixed_id("data_autowfo_", payload, length=12)


def _candidate_definition_from_selected_row(
    selected_row: Mapping[str, object],
    *,
    pairs: List[str],
    direction_scope: str,
) -> Dict[str, object]:
    strategy_mode = str(selected_row.get("strategy_mode") or "combo_entry").strip() or "combo_entry"
    timeframe = str(selected_row.get("timeframe") or "").strip()
    data_profile_id = _data_profile_id(selected_row, pairs)
    cost_profile_id = "cost_autowfo_replay_paper_v1"
    parameter_set = {
        "regime_name": selected_row.get("regime_name"),
        "vol_mode": selected_row.get("vol_mode"),
        "vol_lookback": selected_row.get("vol_lookback"),
        "mom_lookback": selected_row.get("mom_lookback"),
        "trade_mom_lookback": selected_row.get("trade_mom_lookback"),
    }
    if selected_row.get("state_indicator_list") or selected_row.get("trigger_indicator_list"):
        parameter_set["state_indicator_list"] = selected_row.get("state_indicator_list")
        parameter_set["trigger_indicator_list"] = selected_row.get("trigger_indicator_list")
        parameter_set["state_exit_policy"] = selected_row.get("state_exit_policy")
    return {
        "strategy_family": f"autowfo_{strategy_mode}",
        "indicator_set": _split_indicator_list(
            selected_row.get("indicator_list")
            or selected_row.get("state_indicator_list")
            or selected_row.get("trigger_indicator_list")
        ),
        "parameter_set": parameter_set,
        "timeframe": timeframe,
        "market_universe": sorted(str(pair).strip() for pair in pairs if str(pair).strip()),
        "direction_scope": direction_scope or "unknown",
        "entry_rule": {
            "source": "signal_long_signal_short",
            "execution_contract": "autowfo_corrected_raw_signal",
        },
        "exit_rule": {
            "source": "signal_exit_long_signal_exit_short",
            "max_hold": selected_row.get("max_hold"),
        },
        "risk_rule": {
            "tp_stop": selected_row.get("tp_stop"),
            "sl_stop": selected_row.get("sl_stop"),
            "max_hold": selected_row.get("max_hold"),
        },
        "cost_profile_id": cost_profile_id,
        "data_profile_id": data_profile_id,
        "source_system": AUTOWFO_SOURCE_SYSTEM,
    }


def _candidate_row_from_definition(
    candidate_id: str,
    candidate_definition: Mapping[str, object],
    *,
    created_utc: str,
) -> Dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "candidate_version": "autowfo_candidate_v1",
        "strategy_family": candidate_definition["strategy_family"],
        "indicator_set": candidate_definition["indicator_set"],
        "parameter_set": candidate_definition["parameter_set"],
        "timeframe": candidate_definition["timeframe"],
        "market_universe": candidate_definition["market_universe"],
        "direction_scope": candidate_definition["direction_scope"],
        "entry_rule": candidate_definition["entry_rule"],
        "exit_rule": candidate_definition["exit_rule"],
        "risk_rule": candidate_definition["risk_rule"],
        "cost_profile_id": candidate_definition["cost_profile_id"],
        "data_profile_id": candidate_definition["data_profile_id"],
        "source_system": AUTOWFO_SOURCE_SYSTEM,
        "created_utc": created_utc,
    }


def _phase61_62_candidate_row(
    row: Mapping[str, object],
    summary: Mapping[str, object],
    created_utc: str,
) -> Tuple[str, Dict[str, object]]:
    pairs = _pair_universe(row, summary)
    candidate_definition = _candidate_definition_from_selected_row(
        row,
        pairs=pairs,
        direction_scope=_direction_scope(row),
    )
    candidate_id = build_candidate_id(candidate_definition)
    return candidate_id, _candidate_row_from_definition(
        candidate_id,
        candidate_definition,
        created_utc=str(summary.get("created_utc") or created_utc or ""),
    )


def _phase61_62_replay_row(
    row: Mapping[str, object],
    candidate_id: str,
    source_consistency: Mapping[str, object],
) -> Dict[str, object]:
    row_id = str(row.get("row_id") or "")
    signal_bundle_id = str(source_consistency.get("signal_bundle_id") or "") or _bundle_id_from_path(
        row.get("signal_manifest_path")
    )
    parity_bundle_id = str(source_consistency.get("parity_bundle_id") or "") or _bundle_id_from_path(
        row.get("parity_report_path")
    )
    return {
        "run_id": _stable_prefixed_id(PHASE61_62_RUN_ID_PREFIX, {"row_id": row_id, "parity_bundle_id": parity_bundle_id}),
        "candidate_id": candidate_id,
        "signal_bundle_id": signal_bundle_id,
        "parity_bundle_id": parity_bundle_id,
        "open_match_ratio": row.get("open_match_ratio"),
        "exact_match_ratio": row.get("exact_match_ratio"),
        "trade_count_delta_pct": _trade_count_delta_pct(row),
        "verdict": row.get("verdict"),
        "artifact_path": row.get("parity_report_path"),
    }


def _phase61_62_gap_row(
    drift_row: Mapping[str, object],
    source_row: Mapping[str, object],
    candidate_id: str,
    drift_report_path: Path,
    generated_utc: str,
) -> Dict[str, object]:
    row_id = str(drift_row.get("row_id") or source_row.get("row_id") or "")
    return {
        "gap_id": _stable_prefixed_id(PHASE61_62_GAP_ID_PREFIX, {"row_id": row_id}),
        "candidate_id": candidate_id,
        "expected_source": "autowfo_replay",
        "actual_source": "freqtrade_replay",
        "pair": "portfolio",
        "direction": _direction_scope(source_row),
        "event_time_utc": generated_utc,
        "gap_type": "adapter_gap",
        "severity": drift_row.get("drift_severity") or "unknown",
        "expected_value": {
            "open_match_ratio": 1.0,
            "exact_match_ratio": 1.0,
            "trade_count_delta": 0,
        },
        "actual_value": {
            "open_match_ratio": drift_row.get("open_match_ratio"),
            "exact_match_ratio": drift_row.get("exact_match_ratio"),
            "trade_count_delta": drift_row.get("trade_count_delta"),
        },
        "attribution": "phase61_62_replay_drift",
        "artifact_path": str(drift_report_path),
    }


def _phase61_62_source_consistency_by_row(drift_report: Mapping[str, object]) -> Dict[str, Mapping[str, object]]:
    report_sections = drift_report.get("report_sections")
    if not isinstance(report_sections, Mapping):
        return {}
    output: Dict[str, Mapping[str, object]] = {}
    for item in report_sections.get("source_consistency") or []:
        if isinstance(item, Mapping) and _non_empty_str(item.get("row_id")):
            output[str(item["row_id"])] = item
    return output


def _phase61_62_row_level_drift(drift_report: Mapping[str, object]) -> List[Mapping[str, object]]:
    report_sections = drift_report.get("report_sections")
    if not isinstance(report_sections, Mapping):
        return []
    return [
        item
        for item in report_sections.get("row_level_drift") or []
        if isinstance(item, Mapping) and _non_empty_str(item.get("row_id"))
    ]


def build_evidence_warehouse(
    artifacts_dir: str | Path = "artifacts",
    *,
    protocol_path: str | Path | None = None,
    db_path: str | Path | None = None,
) -> dict:
    """Create the empty Evidence Warehouse V1 DuckDB skeleton.

    This does not import legacy artifacts. Source evidence remains untouched.
    """

    protocol = load_evidence_warehouse_protocol(str(protocol_path) if protocol_path else None)
    table_fields = _table_required_fields(protocol)
    resolved_db_path = _resolve_warehouse_db_path(artifacts_dir, db_path)
    resolved_db_path.parent.mkdir(parents=True, exist_ok=True)

    duckdb = _import_duckdb()
    conn = duckdb.connect(str(resolved_db_path))
    try:
        for table_name, required_fields in table_fields.items():
            columns_sql = ", ".join(f"{_quote_ident(field_name)} VARCHAR" for field_name in required_fields)
            conn.execute(f"CREATE TABLE IF NOT EXISTS {_quote_ident(table_name)} ({columns_sql})")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS evidence_warehouse_metadata (
                meta_key VARCHAR,
                meta_value VARCHAR
            )
            """
        )
        metadata = _metadata_rows(protocol)
        for key, value in metadata.items():
            conn.execute("DELETE FROM evidence_warehouse_metadata WHERE meta_key = ?", [key])
            conn.execute(
                "INSERT INTO evidence_warehouse_metadata (meta_key, meta_value) VALUES (?, ?)",
                [key, value],
            )
    finally:
        conn.close()

    return {
        "ok": True,
        "artifacts_dir": str(Path(artifacts_dir)),
        "db_path": str(resolved_db_path),
        "protocol_path": str(_resolve_evidence_warehouse_protocol_path(str(protocol_path) if protocol_path else None).resolve()),
        "schema_version": str(protocol.get("schema_version") or ""),
        "protocol_name": str(protocol.get("name") or ""),
        "tables_created": len(table_fields),
        "tables": sorted(table_fields),
        "imported_rows": 0,
    }


def import_phase61_62_replay_evidence(
    artifacts_dir: str | Path = "artifacts",
    *,
    protocol_path: str | Path | None = None,
    db_path: str | Path | None = None,
    summary_path: str | Path | None = None,
    drift_report_path: str | Path | None = None,
) -> dict:
    """Import frozen Phase 61-62 replay/drift evidence into the warehouse.

    This is a read-only source import. It does not mutate replay, drift, signal,
    or Freqtrade artifacts.
    """

    artifacts = Path(artifacts_dir)
    resolved_summary_path = (
        Path(summary_path).resolve()
        if summary_path
        else (artifacts / "freqtrade_bridge" / "awf331_rerun_summary.json").resolve()
    )
    resolved_drift_report_path = (
        Path(drift_report_path).resolve()
        if drift_report_path
        else (artifacts / "reports" / "execution_drift_report.json").resolve()
    )

    summary = _read_json_object(resolved_summary_path, "Phase 61-62 rerun summary")
    raw_rows = summary.get("rows")
    if not isinstance(raw_rows, list):
        raise ValueError(f"Phase 61-62 rerun summary rows must be a list: {resolved_summary_path}")
    summary_rows = [row for row in raw_rows if isinstance(row, Mapping)]
    if len(summary_rows) != len(raw_rows):
        raise ValueError(f"Phase 61-62 rerun summary rows must be objects: {resolved_summary_path}")

    warnings: List[dict] = []
    drift_report: Dict[str, object] = {}
    if resolved_drift_report_path.exists():
        drift_report = _read_json_object(resolved_drift_report_path, "Phase 61-62 drift report")
    else:
        warnings.append(
            {
                "code": "missing_drift_report",
                "path": str(resolved_drift_report_path),
                "message": "Phase 61-62 drift report is missing; imported replay rows only",
            }
        )

    build_payload = build_evidence_warehouse(
        artifacts,
        protocol_path=protocol_path,
        db_path=db_path,
    )
    protocol = load_evidence_warehouse_protocol(str(protocol_path) if protocol_path else None)
    table_fields = _table_required_fields(protocol)
    resolved_db_path = Path(str(build_payload["db_path"]))

    source_consistency_by_row = _phase61_62_source_consistency_by_row(drift_report)
    candidates_by_row_id: Dict[str, str] = {}
    candidate_rows_by_id: Dict[str, Dict[str, object]] = {}
    replay_rows: List[Dict[str, object]] = []

    import_created_utc = str(summary.get("created_utc") or drift_report.get("generated_utc") or "")
    for row in summary_rows:
        row_id = str(row.get("row_id") or "").strip()
        if not row_id:
            warnings.append(
                {
                    "code": "missing_row_id",
                    "path": str(resolved_summary_path),
                    "message": "Skipped Phase 61-62 replay row without row_id",
                }
            )
            continue
        candidate_id, candidate_row = _phase61_62_candidate_row(row, summary, import_created_utc)
        candidates_by_row_id[row_id] = candidate_id
        candidate_rows_by_id[candidate_id] = candidate_row
        replay_rows.append(
            _phase61_62_replay_row(
                row,
                candidate_id,
                source_consistency_by_row.get(row_id, {}),
            )
        )

    generated_utc = str(drift_report.get("generated_utc") or summary.get("created_utc") or "")
    source_rows_by_id = {str(row.get("row_id") or ""): row for row in summary_rows}
    gap_rows: List[Dict[str, object]] = []
    for drift_row in _phase61_62_row_level_drift(drift_report):
        row_id = str(drift_row.get("row_id") or "")
        candidate_id = candidates_by_row_id.get(row_id)
        source_row = source_rows_by_id.get(row_id)
        if not candidate_id or not source_row:
            warnings.append(
                {
                    "code": "unmatched_drift_row",
                    "path": str(resolved_drift_report_path),
                    "message": f"Skipped drift row without matching replay summary row: {row_id}",
                }
            )
            continue
        gap_rows.append(
            _phase61_62_gap_row(
                drift_row,
                source_row,
                candidate_id,
                resolved_drift_report_path,
                generated_utc,
            )
        )

    duckdb = _import_duckdb()
    conn = duckdb.connect(str(resolved_db_path))
    try:
        conn.execute("BEGIN TRANSACTION")
        conn.execute(
            "DELETE FROM strategy_candidates WHERE source_system = ?",
            [PHASE61_62_SOURCE_SYSTEM],
        )
        for candidate_id in candidate_rows_by_id:
            conn.execute("DELETE FROM strategy_candidates WHERE candidate_id = ?", [candidate_id])
        conn.execute(
            "DELETE FROM ft_replay_results WHERE run_id LIKE ?",
            [f"{PHASE61_62_RUN_ID_PREFIX}%"],
        )
        conn.execute(
            "DELETE FROM execution_gap_events WHERE gap_id LIKE ?",
            [f"{PHASE61_62_GAP_ID_PREFIX}%"],
        )
        for candidate_row in sorted(candidate_rows_by_id.values(), key=lambda item: str(item["candidate_id"])):
            _insert_protocol_row(
                conn,
                "strategy_candidates",
                table_fields["strategy_candidates"],
                candidate_row,
            )
        for replay_row in replay_rows:
            _insert_protocol_row(
                conn,
                "ft_replay_results",
                table_fields["ft_replay_results"],
                replay_row,
            )
        for gap_row in gap_rows:
            _insert_protocol_row(
                conn,
                "execution_gap_events",
                table_fields["execution_gap_events"],
                gap_row,
            )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()

    return {
        "ok": True,
        "artifacts_dir": str(artifacts),
        "db_path": str(resolved_db_path),
        "protocol_path": str(_resolve_evidence_warehouse_protocol_path(str(protocol_path) if protocol_path else None).resolve()),
        "summary_path": str(resolved_summary_path),
        "drift_report_path": str(resolved_drift_report_path),
        "schema_version": str(protocol.get("schema_version") or ""),
        "imported_candidates": len(candidate_rows_by_id),
        "imported_ft_replay_results": len(replay_rows),
        "imported_execution_gap_events": len(gap_rows),
        "imported_rows": len(candidate_rows_by_id) + len(replay_rows) + len(gap_rows),
        "warnings": warnings,
    }


def _parse_utc_timestamp(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _phase63_daily_summary_paths(paper_dir: Path) -> List[Path]:
    if not paper_dir.exists():
        raise ValueError(f"Phase 63 paper summary directory not found: {paper_dir}")
    return sorted(path for path in paper_dir.glob("daily_summary_*.json") if path.is_file())


def _phase63_summary_selected_row(summary: Mapping[str, object]) -> Dict[str, object]:
    analysis = summary.get("analysis")
    if not isinstance(analysis, Mapping):
        return {}
    selected_row = analysis.get("selected_row")
    return dict(selected_row) if isinstance(selected_row, Mapping) else {}


def _phase63_summary_pairs(summary: Mapping[str, object]) -> List[str]:
    pairs = set()
    source = summary.get("source")
    if isinstance(source, Mapping):
        for pair in source.get("pairs") or []:
            if _non_empty_str(pair):
                pairs.add(str(pair).strip())
    pair_mapping = summary.get("pair_mapping")
    if isinstance(pair_mapping, Mapping):
        for pair in pair_mapping:
            if _non_empty_str(pair):
                pairs.add(str(pair).strip())
    for section_name in ("opened_trades", "closed_trades"):
        for trade in summary.get(section_name) or []:
            if isinstance(trade, Mapping) and _non_empty_str(trade.get("source_pair")):
                pairs.add(str(trade["source_pair"]).strip())
    return sorted(pairs)


def _phase63_direction_scope(summary: Mapping[str, object], live_manifest: Mapping[str, object]) -> str:
    directions = set()
    for section_name in ("opened_trades", "closed_trades"):
        for trade in summary.get(section_name) or []:
            if not isinstance(trade, Mapping):
                continue
            direction = str(trade.get("direction") or "").strip().lower()
            if direction in {"long", "short"}:
                directions.add(direction)
    if directions == {"long", "short"}:
        return "long_short"
    if directions == {"long"}:
        return "long"
    if directions == {"short"}:
        return "short"
    signals = live_manifest.get("signals")
    if isinstance(signals, Mapping) and bool(signals.get("has_short_signals")):
        return "long_short"
    return "long_short"


def _sqlite_readonly_uri(path: Path) -> str:
    return f"{path.resolve().as_uri()}?mode=ro"


def _phase63_has_value(value: object) -> bool:
    return value is not None and str(value).strip() != ""


def _phase63_first_value(*values: object) -> object:
    for value in values:
        if _phase63_has_value(value):
            return value
    return None


def _phase63_normalized_trade_id(value: object) -> str:
    if not _phase63_has_value(value):
        return ""
    try:
        numeric = float(str(value).strip())
    except (TypeError, ValueError):
        return str(value).strip()
    if numeric.is_integer():
        return str(int(numeric))
    return str(value).strip()


def _phase63_sqlite_row_first(row: Mapping[str, object], *names: str) -> object:
    for name in names:
        if name in row and _phase63_has_value(row[name]):
            return row[name]
    return None


def _phase63_direction_from_db_row(row: Mapping[str, object]) -> str:
    explicit = _phase63_sqlite_row_first(row, "direction", "trade_direction", "side")
    if explicit:
        text = str(explicit).strip().lower()
        if text in {"short", "sell"}:
            return "Short"
        if text in {"long", "buy"}:
            return "Long"
    is_short = _phase63_sqlite_row_first(row, "is_short", "short")
    if is_short is None:
        return ""
    if str(is_short).strip().lower() in {"1", "true", "yes", "y"}:
        return "Short"
    return "Long"


def _phase63_fee_abs_from_db_row(row: Mapping[str, object]) -> float | object | None:
    explicit = _phase63_sqlite_row_first(row, "fee_abs", "fee_cost", "trade_fee_cost")
    if explicit is not None:
        return explicit
    fee_open = _phase63_sqlite_row_first(row, "fee_open_cost", "open_fee_cost")
    fee_close = _phase63_sqlite_row_first(row, "fee_close_cost", "close_fee_cost")
    if fee_open is None or fee_close is None:
        return None
    try:
        return float(fee_open) + float(fee_close)
    except (TypeError, ValueError):
        return None


def _phase63_paper_trade_id(candidate_id: str, trade_id: str, db_path: str) -> str:
    return _stable_prefixed_id(
        PHASE63_PAPER_TRADE_ID_PREFIX,
        {
            "candidate_id": candidate_id,
            "trade_id": str(trade_id),
            "db_path": str(db_path),
        },
    )


def _phase63_legacy_summary_scoped_paper_trade_id(
    candidate_id: str,
    trade_id: str,
    db_path: str,
    summary_path: Path,
) -> str:
    return _stable_prefixed_id(
        PHASE63_PAPER_TRADE_ID_PREFIX,
        {
            "candidate_id": candidate_id,
            "trade_id": str(trade_id),
            "db_path": str(db_path),
            "summary_path": str(summary_path),
        },
    )


def _phase63_trade_fact_lookup(db_path: Path, warnings: List[dict]) -> Dict[str, Dict[str, object]]:
    if not db_path.exists():
        warnings.append(
            {
                "code": "missing_source_db",
                "path": str(db_path),
                "message": "Phase 63 paper source database is missing; trade facts and fee fields left blank",
            }
        )
        return {}
    try:
        conn = sqlite3.connect(_sqlite_readonly_uri(db_path), uri=True)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("SELECT * FROM trades").fetchall()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        warnings.append(
            {
                "code": "source_db_trade_read_failed",
                "path": str(db_path),
                "message": f"Could not read Freqtrade trade facts: {exc}",
            }
        )
        return {}

    facts: Dict[str, Dict[str, object]] = {}
    for sqlite_row in rows:
        row = {key: sqlite_row[key] for key in sqlite_row.keys()}
        trade_id = _phase63_normalized_trade_id(_phase63_sqlite_row_first(row, "id", "trade_id"))
        if not trade_id:
            continue
        facts[trade_id] = {
            "pair": _phase63_sqlite_row_first(row, "pair"),
            "direction": _phase63_direction_from_db_row(row),
            "opened_utc": _phase63_sqlite_row_first(row, "open_date", "open_date_utc", "opened_utc"),
            "closed_utc": _phase63_sqlite_row_first(row, "close_date", "close_date_utc", "closed_utc"),
            "open_rate": _phase63_sqlite_row_first(row, "open_rate"),
            "close_rate": _phase63_sqlite_row_first(row, "close_rate"),
            "profit_abs": _phase63_sqlite_row_first(row, "close_profit_abs", "profit_abs", "realized_profit"),
            "profit_ratio": _phase63_sqlite_row_first(row, "close_profit", "profit_ratio"),
            "fee_abs": _phase63_fee_abs_from_db_row(row),
            "funding_abs": _phase63_sqlite_row_first(row, "funding_abs", "funding_fee", "funding_fees"),
        }
    return facts


def _phase63_summary_trade_ids(summary: Mapping[str, object]) -> List[str]:
    trade_ids = []
    for section_name in ("opened_trades", "closed_trades"):
        for trade in summary.get(section_name) or []:
            if not isinstance(trade, Mapping):
                continue
            trade_id = str(trade.get("trade_id") or "").strip()
            if trade_id:
                trade_ids.append(trade_id)
    return sorted(set(trade_ids))


def _phase63_trade_rows(
    summary: Mapping[str, object],
    candidate_id: str,
    summary_path: Path,
    trade_fact_lookup: Mapping[str, Mapping[str, object]],
    warnings: List[dict],
) -> List[Dict[str, object]]:
    trades_by_id: Dict[str, Dict[str, object]] = {}
    for opened in summary.get("opened_trades") or []:
        if not isinstance(opened, Mapping):
            continue
        trade_id = str(opened.get("trade_id") or "").strip()
        if not trade_id:
            continue
        row = trades_by_id.setdefault(trade_id, {"freqtrade_trade_id": trade_id})
        row.update(
            {
                "pair": opened.get("pair"),
                "direction": opened.get("direction"),
                "opened_utc": opened.get("open_date"),
                "open_rate": opened.get("open_rate"),
                "fee_abs": opened.get("fee_abs"),
                "funding_abs": opened.get("funding_abs"),
            }
        )
    for closed in summary.get("closed_trades") or []:
        if not isinstance(closed, Mapping):
            continue
        trade_id = str(closed.get("trade_id") or "").strip()
        if not trade_id:
            continue
        row = trades_by_id.setdefault(trade_id, {"freqtrade_trade_id": trade_id})
        row.update(
            {
                "pair": row.get("pair") or closed.get("pair"),
                "direction": row.get("direction") or closed.get("direction"),
                "closed_utc": closed.get("close_date"),
                "close_rate": closed.get("close_rate"),
                "profit_abs": closed.get("close_profit_abs"),
                "profit_ratio": closed.get("close_profit"),
                "fee_abs": row.get("fee_abs") or closed.get("fee_abs"),
                "funding_abs": row.get("funding_abs") or closed.get("funding_abs"),
            }
        )

    db_path = str(summary.get("db_path") or "")
    rows: List[Dict[str, object]] = []
    for trade_id, raw in sorted(trades_by_id.items(), key=lambda item: item[0]):
        db_fact = trade_fact_lookup.get(trade_id) or {}
        if db_path and Path(db_path).exists() and not db_fact:
            warnings.append(
                {
                    "code": "missing_source_db_trade",
                    "path": str(summary_path),
                    "message": f"Freqtrade source database has no trade row for paper trade {trade_id}",
                }
            )
        fee_abs = _phase63_first_value(db_fact.get("fee_abs"), raw.get("fee_abs"))
        if not _phase63_has_value(fee_abs):
            warnings.append(
                {
                    "code": "missing_fee",
                    "path": str(summary_path),
                    "message": f"Missing fee fields for Freqtrade paper trade {trade_id}",
                }
            )
        rows.append(
            {
                "paper_trade_id": _phase63_paper_trade_id(candidate_id, trade_id, db_path),
                "candidate_id": candidate_id,
                "freqtrade_trade_id": trade_id,
                "pair": _phase63_first_value(db_fact.get("pair"), raw.get("pair")) or "",
                "direction": _phase63_first_value(db_fact.get("direction"), raw.get("direction")) or "",
                "opened_utc": _phase63_first_value(db_fact.get("opened_utc"), raw.get("opened_utc")) or "",
                "closed_utc": _phase63_first_value(db_fact.get("closed_utc"), raw.get("closed_utc")) or "",
                "open_rate": _phase63_first_value(db_fact.get("open_rate"), raw.get("open_rate")) or "",
                "close_rate": _phase63_first_value(db_fact.get("close_rate"), raw.get("close_rate")) or "",
                "profit_abs": _phase63_first_value(db_fact.get("profit_abs"), raw.get("profit_abs")) or "",
                "profit_ratio": _phase63_first_value(db_fact.get("profit_ratio"), raw.get("profit_ratio")) or "",
                "fee_abs": fee_abs if _phase63_has_value(fee_abs) else "",
                "funding_abs": _phase63_first_value(db_fact.get("funding_abs"), raw.get("funding_abs")) or "",
                "source_db_path": db_path,
            }
        )
    return rows


def _phase63_merge_paper_trade_rows(rows: Iterable[Mapping[str, object]]) -> List[Dict[str, object]]:
    merged: Dict[Tuple[str, str, str], Dict[str, object]] = {}
    for row in rows:
        key = (
            str(row.get("candidate_id") or ""),
            str(row.get("source_db_path") or ""),
            str(row.get("freqtrade_trade_id") or ""),
        )
        existing = merged.setdefault(key, dict(row))
        if existing is row:
            continue
        for field_name, value in row.items():
            if not _phase63_has_value(existing.get(field_name)) and _phase63_has_value(value):
                existing[field_name] = value
    return sorted(
        merged.values(),
        key=lambda item: (
            str(item.get("candidate_id") or ""),
            str(item.get("source_db_path") or ""),
            str(item.get("freqtrade_trade_id") or ""),
        ),
    )


def _phase63_gap_row(
    *,
    candidate_id: str,
    summary: Mapping[str, object],
    summary_path: Path,
    attribution: str,
    expected_value: object,
    actual_value: object,
    severity: str = "warning",
) -> Dict[str, object]:
    return {
        "gap_id": _stable_prefixed_id(
            PHASE63_PAPER_GAP_ID_PREFIX,
            {
                "candidate_id": candidate_id,
                "summary_path": str(summary_path),
                "attribution": attribution,
            },
        ),
        "candidate_id": candidate_id,
        "expected_source": "autowfo_live_signal",
        "actual_source": "freqtrade_dryrun",
        "pair": "portfolio",
        "direction": "long_short",
        "event_time_utc": summary.get("window_end_utc") or summary.get("created_utc") or "",
        "gap_type": "execution_gap",
        "severity": severity,
        "expected_value": expected_value,
        "actual_value": actual_value,
        "attribution": attribution,
        "artifact_path": str(summary_path),
    }


def import_phase63_paper_reconcile_evidence(
    artifacts_dir: str | Path = "artifacts",
    *,
    protocol_path: str | Path | None = None,
    db_path: str | Path | None = None,
    paper_dir: str | Path | None = None,
    live_manifest_path: str | Path | None = None,
) -> dict:
    """Import Phase 63 dry-run paper reconcile summaries into the warehouse."""

    artifacts = Path(artifacts_dir)
    resolved_paper_dir = Path(paper_dir).resolve() if paper_dir else (artifacts / "paper_dryrun").resolve()
    summary_paths = _phase63_daily_summary_paths(resolved_paper_dir)
    warnings: List[dict] = []
    live_manifest: Dict[str, object] = {}
    resolved_live_manifest_path: Path | None = Path(live_manifest_path).resolve() if live_manifest_path else None
    if resolved_live_manifest_path and resolved_live_manifest_path.exists():
        live_manifest = _read_json_object(resolved_live_manifest_path, "Phase 63 live manifest")
    elif resolved_live_manifest_path:
        warnings.append(
            {
                "code": "missing_live_manifest",
                "path": str(resolved_live_manifest_path),
                "message": "Phase 63 live manifest is missing; freshness cannot be evaluated",
            }
        )

    build_payload = build_evidence_warehouse(
        artifacts,
        protocol_path=protocol_path,
        db_path=db_path,
    )
    protocol = load_evidence_warehouse_protocol(str(protocol_path) if protocol_path else None)
    table_fields = _table_required_fields(protocol)
    resolved_db_path = Path(str(build_payload["db_path"]))

    candidate_rows_by_id: Dict[str, Dict[str, object]] = {}
    paper_trade_rows: List[Dict[str, object]] = []
    legacy_paper_trade_ids: List[str] = []
    gap_rows: List[Dict[str, object]] = []

    for summary_path in summary_paths:
        summary = _read_json_object(summary_path, "Phase 63 paper daily summary")
        if not live_manifest:
            embedded_manifest_path = str(summary.get("live_manifest_path") or "").strip()
            if embedded_manifest_path and Path(embedded_manifest_path).exists():
                live_manifest = _read_json_object(Path(embedded_manifest_path), "Phase 63 live manifest")
        selected_row = _phase63_summary_selected_row(summary)
        if not selected_row:
            warnings.append(
                {
                    "code": "missing_selected_row",
                    "path": str(summary_path),
                    "message": "Skipped Phase 63 paper summary without analysis.selected_row",
                }
            )
            continue
        pairs = _phase63_summary_pairs(summary)
        candidate_definition = _candidate_definition_from_selected_row(
            selected_row,
            pairs=pairs,
            direction_scope=_phase63_direction_scope(summary, live_manifest),
        )
        candidate_id = build_candidate_id(candidate_definition)
        candidate_rows_by_id[candidate_id] = _candidate_row_from_definition(
            candidate_id,
            candidate_definition,
            created_utc=str(summary.get("created_utc") or ""),
        )

        db_path_text = str(summary.get("db_path") or "").strip()
        trade_fact_lookup: Dict[str, Dict[str, object]] = {}
        if db_path_text:
            trade_fact_lookup = _phase63_trade_fact_lookup(Path(db_path_text), warnings)
        else:
            warnings.append(
                {
                    "code": "missing_source_db_path",
                    "path": str(summary_path),
                    "message": "Phase 63 paper summary does not record db_path; fee fields left blank",
                }
            )

        paper_trade_rows.extend(
            _phase63_trade_rows(summary, candidate_id, summary_path, trade_fact_lookup, warnings)
        )
        for trade_id in _phase63_summary_trade_ids(summary):
            legacy_paper_trade_ids.append(
                _phase63_legacy_summary_scoped_paper_trade_id(
                    candidate_id,
                    trade_id,
                    db_path_text,
                    summary_path,
                )
            )

        opened_count = len(summary.get("opened_trades") or [])
        closed_count = len(summary.get("closed_trades") or [])
        if opened_count == 0 and closed_count == 0:
            warnings.append(
                {
                    "code": "zero_trade_day",
                    "path": str(summary_path),
                    "message": "Phase 63 paper summary has zero opened and closed trades",
                }
            )
            gap_rows.append(
                _phase63_gap_row(
                    candidate_id=candidate_id,
                    summary=summary,
                    summary_path=summary_path,
                    attribution="phase63_zero_trade_day",
                    expected_value={"opened_or_closed_trades": ">0"},
                    actual_value={"opened_trades": opened_count, "closed_trades": closed_count},
                )
            )

        manifest_created = _parse_utc_timestamp(live_manifest.get("created_utc")) if live_manifest else None
        window_end = _parse_utc_timestamp(summary.get("window_end_utc"))
        if manifest_created and window_end and (window_end - manifest_created).total_seconds() > 86400:
            warnings.append(
                {
                    "code": "stale_live_manifest",
                    "path": str(resolved_live_manifest_path or summary.get("live_manifest_path") or ""),
                    "message": "Phase 63 live manifest is older than the imported paper day",
                }
            )
            gap_rows.append(
                _phase63_gap_row(
                    candidate_id=candidate_id,
                    summary=summary,
                    summary_path=summary_path,
                    attribution="phase63_stale_live_manifest",
                    expected_value={"manifest_created_after": summary.get("window_start_utc")},
                    actual_value={"manifest_created_utc": live_manifest.get("created_utc")},
                )
            )

    paper_trade_rows = _phase63_merge_paper_trade_rows(paper_trade_rows)

    duckdb = _import_duckdb()
    conn = duckdb.connect(str(resolved_db_path))
    try:
        conn.execute("BEGIN TRANSACTION")
        for candidate_id in candidate_rows_by_id:
            conn.execute("DELETE FROM strategy_candidates WHERE candidate_id = ?", [candidate_id])
        for paper_trade_id in sorted(
            {str(row["paper_trade_id"]) for row in paper_trade_rows} | {str(item) for item in legacy_paper_trade_ids}
        ):
            conn.execute("DELETE FROM paper_trades WHERE paper_trade_id = ?", [paper_trade_id])
        for gap_id in sorted({str(row["gap_id"]) for row in gap_rows}):
            conn.execute("DELETE FROM execution_gap_events WHERE gap_id = ?", [gap_id])
        for candidate_row in sorted(candidate_rows_by_id.values(), key=lambda item: str(item["candidate_id"])):
            _insert_protocol_row(
                conn,
                "strategy_candidates",
                table_fields["strategy_candidates"],
                candidate_row,
            )
        for paper_row in paper_trade_rows:
            _insert_protocol_row(conn, "paper_trades", table_fields["paper_trades"], paper_row)
        for gap_row in gap_rows:
            _insert_protocol_row(conn, "execution_gap_events", table_fields["execution_gap_events"], gap_row)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()

    return {
        "ok": True,
        "artifacts_dir": str(artifacts),
        "db_path": str(resolved_db_path),
        "protocol_path": str(_resolve_evidence_warehouse_protocol_path(str(protocol_path) if protocol_path else None).resolve()),
        "paper_dir": str(resolved_paper_dir),
        "live_manifest_path": str(resolved_live_manifest_path) if resolved_live_manifest_path else "",
        "schema_version": str(protocol.get("schema_version") or ""),
        "daily_summary_count": len(summary_paths),
        "imported_candidates": len(candidate_rows_by_id),
        "imported_paper_trades": len(paper_trade_rows),
        "imported_execution_gap_events": len(gap_rows),
        "imported_rows": len(candidate_rows_by_id) + len(paper_trade_rows) + len(gap_rows),
        "warnings": warnings,
    }


def _phase63_candidate_role(summary: Mapping[str, object]) -> str:
    analysis = summary.get("analysis")
    if not isinstance(analysis, Mapping):
        return "Unknown"
    selection = str(analysis.get("selection") or "").strip()
    rank = str(analysis.get("rank") or "").strip()
    selected_row = analysis.get("selected_row")
    selected = selected_row if isinstance(selected_row, Mapping) else {}
    if selection == "canonical_gate_passed" and rank == "1":
        return "Champion"
    if bool(selected.get("is_canonical_family")) and str(selected.get("analysis_rank") or "") == "1":
        return "Champion"
    return "Challenger"


def _phase63_summary_manifest_freshness_status(summary: Mapping[str, object]) -> str:
    manifest_path_text = str(summary.get("live_manifest_path") or "").strip()
    if not manifest_path_text:
        return "missing"
    manifest_path = Path(manifest_path_text)
    if not manifest_path.exists():
        return "missing"
    try:
        live_manifest = _read_json_object(manifest_path, "Phase 63 live manifest")
    except ValueError:
        return "missing"
    manifest_created = _parse_utc_timestamp(live_manifest.get("created_utc"))
    window_end = _parse_utc_timestamp(summary.get("window_end_utc"))
    if not manifest_created or not window_end:
        return "missing"
    if (window_end - manifest_created).total_seconds() > 86400:
        return "stale"
    return "fresh"


def _phase63_daily_quality(
    *,
    opened_count: int,
    closed_count: int,
    missing_match_rate: bool,
    manifest_freshness_status: str,
) -> str:
    if manifest_freshness_status in {"missing", "stale"}:
        return "invalid_manifest"
    if missing_match_rate:
        return "missing_match_rate_evidence"
    if opened_count == 0 and closed_count == 0:
        return "zero_trade_day"
    return "valid_trade_evidence"


def _phase63_summary_matches_filter(
    summary: Mapping[str, object],
    *,
    expected_selection: str | None,
    expected_rank: int | None,
    min_date_utc: str | None,
) -> bool:
    if min_date_utc:
        date_utc = str(summary.get("date_utc") or "")
        if date_utc and date_utc < str(min_date_utc):
            return False
    analysis = summary.get("analysis")
    analysis_obj = analysis if isinstance(analysis, Mapping) else {}
    if expected_selection is not None and str(analysis_obj.get("selection") or "") != str(expected_selection):
        return False
    if expected_rank is not None and str(analysis_obj.get("rank") or "") != str(expected_rank):
        return False
    return True


def build_phase63_paper_survival_report(
    artifacts_dir: str | Path = "artifacts",
    *,
    paper_dir: str | Path | None = None,
    output_path: str | Path | None = None,
    minimum_verdict_days: int = 7,
    expected_selection: str | None = None,
    expected_rank: int | None = None,
    min_date_utc: str | None = None,
) -> dict:
    """Build a bounded Phase 63 paper evidence report without producing a verdict."""

    artifacts = Path(artifacts_dir)
    resolved_paper_dir = Path(paper_dir).resolve() if paper_dir else (artifacts / "paper_dryrun").resolve()
    summary_paths = _phase63_daily_summary_paths(resolved_paper_dir)
    daily_summaries = [_read_json_object(path, "Phase 63 paper daily summary") for path in summary_paths]
    source_summary_count = len(summary_paths)
    filtered_pairs = [
        (path, summary)
        for path, summary in zip(summary_paths, daily_summaries)
        if _phase63_summary_matches_filter(
            summary,
            expected_selection=expected_selection,
            expected_rank=expected_rank,
            min_date_utc=min_date_utc,
        )
    ]
    excluded_summary_paths = [
        path
        for path, summary in zip(summary_paths, daily_summaries)
        if not _phase63_summary_matches_filter(
            summary,
            expected_selection=expected_selection,
            expected_rank=expected_rank,
            min_date_utc=min_date_utc,
        )
    ]
    summary_paths = [path for path, _summary in filtered_pairs]
    daily_summaries = [summary for _path, summary in filtered_pairs]
    evidence_days = sorted({str(summary.get("date_utc") or "") for summary in daily_summaries if summary.get("date_utc")})
    opened_total = 0
    closed_total = 0
    entry_rates: List[float] = []
    exit_rates: List[float] = []
    roles = set()
    zero_trade_days: List[str] = []
    missing_match_rate_days: List[str] = []
    stale_manifest_days: List[str] = []
    missing_manifest_freshness_days: List[str] = []
    quality_by_day: Dict[str, str] = {}
    valid_evidence_days: List[str] = []
    for summary in daily_summaries:
        date_utc = str(summary.get("date_utc") or "")
        totals = summary.get("totals")
        opened_count = len(summary.get("opened_trades") or [])
        closed_count = len(summary.get("closed_trades") or [])
        day_missing_match_rate = False
        if isinstance(totals, Mapping):
            opened_count = int(_safe_float(totals.get("opened_trades_day"), default=float(opened_count)))
            closed_count = int(_safe_float(totals.get("closed_trades_day"), default=float(closed_count)))
            opened_total += opened_count
            closed_total += closed_count
            if totals.get("entry_signal_match_rate") is not None:
                entry_rates.append(_safe_float(totals.get("entry_signal_match_rate")))
            if totals.get("exit_signal_match_rate") is not None:
                exit_rates.append(_safe_float(totals.get("exit_signal_match_rate")))
            if opened_count > 0 and totals.get("entry_signal_match_rate") is None:
                missing_match_rate_days.append(date_utc)
                day_missing_match_rate = True
            if closed_count > 0 and totals.get("exit_signal_match_rate") is None:
                missing_match_rate_days.append(date_utc)
                day_missing_match_rate = True
        else:
            opened_total += opened_count
            closed_total += closed_count
            if opened_count > 0 or closed_count > 0:
                missing_match_rate_days.append(date_utc)
                day_missing_match_rate = True
        if opened_count == 0 and closed_count == 0:
            zero_trade_days.append(date_utc)
        manifest_freshness_status = _phase63_summary_manifest_freshness_status(summary)
        if manifest_freshness_status == "stale":
            stale_manifest_days.append(date_utc)
        elif manifest_freshness_status == "missing":
            missing_manifest_freshness_days.append(date_utc)
        if date_utc:
            day_quality = _phase63_daily_quality(
                opened_count=opened_count,
                closed_count=closed_count,
                missing_match_rate=day_missing_match_rate,
                manifest_freshness_status=manifest_freshness_status,
            )
            quality_by_day[date_utc] = day_quality
            if day_quality == "valid_trade_evidence":
                valid_evidence_days.append(date_utc)
        roles.add(_phase63_candidate_role(summary))
    evidence_day_count = len(evidence_days)
    minimum_day_count_met = evidence_day_count >= int(minimum_verdict_days)
    valid_evidence_days = sorted(set(valid_evidence_days))
    minimum_valid_day_count_met = len(valid_evidence_days) >= int(minimum_verdict_days)
    if roles == {"Champion"}:
        candidate_role = "Champion"
    elif roles == {"Challenger"}:
        candidate_role = "Challenger"
    elif roles:
        candidate_role = "Mixed"
    else:
        candidate_role = "Unknown"
    blocking_reasons: List[str] = []
    if not minimum_day_count_met:
        blocking_reasons.append("insufficient_evidence_days")
    if stale_manifest_days:
        blocking_reasons.append("stale_manifest")
    if missing_manifest_freshness_days:
        blocking_reasons.append("missing_manifest_freshness_evidence")
    if zero_trade_days:
        blocking_reasons.append("zero_trade_day")
    if missing_match_rate_days:
        blocking_reasons.append("missing_match_rate_evidence")
    if candidate_role == "Mixed":
        blocking_reasons.append("mixed_candidate_roles")
    verdict_allowed = minimum_valid_day_count_met and not blocking_reasons
    report = {
        "ok": True,
        "schema_version": "phase63_paper_survival_report/v1",
        "artifacts_dir": str(artifacts),
        "paper_dir": str(resolved_paper_dir),
        "source_summary_count": source_summary_count,
        "daily_summary_count": len(summary_paths),
        "excluded_summary_count": len(excluded_summary_paths),
        "summary_filter": {
            "expected_selection": expected_selection,
            "expected_rank": expected_rank,
            "min_date_utc": min_date_utc,
        },
        "evidence_days": evidence_days,
        "evidence_day_count": evidence_day_count,
        "minimum_verdict_days": int(minimum_verdict_days),
        "minimum_day_count_met": minimum_day_count_met,
        "valid_evidence_days": valid_evidence_days,
        "valid_evidence_day_count": len(valid_evidence_days),
        "minimum_valid_day_count_met": minimum_valid_day_count_met,
        "quality_by_day": quality_by_day,
        "verdict_allowed": verdict_allowed,
        "classification": "paper_evidence_ready" if verdict_allowed else "incomplete_evidence",
        "blocking_reasons": blocking_reasons,
        "blocking_reason_days": {
            "zero_trade_day": zero_trade_days,
            "missing_match_rate_evidence": sorted(set(missing_match_rate_days)),
            "stale_manifest": stale_manifest_days,
            "missing_manifest_freshness_evidence": missing_manifest_freshness_days,
        },
        "candidate_role": candidate_role,
        "opened_trades_total": opened_total,
        "closed_trades_total": closed_total,
        "entry_signal_match_rate_mean": (
            sum(entry_rates) / len(entry_rates) if entry_rates else None
        ),
        "exit_signal_match_rate_mean": (
            sum(exit_rates) / len(exit_rates) if exit_rates else None
        ),
        "source_artifacts": [str(path) for path in summary_paths],
        "excluded_source_artifacts": [str(path) for path in excluded_summary_paths],
    }
    if output_path:
        resolved_output_path = Path(output_path).resolve()
    else:
        resolved_output_path = (artifacts / "reports" / "phase63_paper_survival_report.json").resolve()
    resolved_output_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["output_path"] = str(resolved_output_path)
    return report


SURVIVAL_GATE_REQUIRED_POLICY_FIELDS: Tuple[str, ...] = (
    "policy_id",
    "policy_name",
    "policy_version",
    "created_utc",
    "capital_stage",
    "scope",
    "rationale",
)
ALLOWED_CAPITAL_STAGES: Tuple[str, ...] = (
    "backtest",
    "ft_replay",
    "paper",
    "micro_live",
    "scaled_live",
)


def load_survival_gate_policy(path: str | Path) -> Dict[str, object]:
    payload = _read_json_object(Path(path), "Survival Gate policy")
    for field_name in SURVIVAL_GATE_REQUIRED_POLICY_FIELDS:
        if field_name not in payload or payload[field_name] in (None, ""):
            raise ValueError(f"Survival Gate policy missing required field: {field_name}")
    if str(payload.get("capital_stage")) not in ALLOWED_CAPITAL_STAGES:
        raise ValueError(f"unknown Survival Gate capital_stage: {payload.get('capital_stage')}")
    if not isinstance(payload.get("scope"), Mapping):
        raise ValueError("Survival Gate policy scope must be an object")
    return payload


def write_gate_policy(
    artifacts_dir: str | Path = "artifacts",
    *,
    policy_path: str | Path,
    protocol_path: str | Path | None = None,
    db_path: str | Path | None = None,
) -> dict:
    policy = load_survival_gate_policy(policy_path)
    build_payload = build_evidence_warehouse(
        artifacts_dir,
        protocol_path=protocol_path,
        db_path=db_path,
    )
    protocol = load_evidence_warehouse_protocol(str(protocol_path) if protocol_path else None)
    table_fields = _table_required_fields(protocol)
    resolved_db_path = Path(str(build_payload["db_path"]))
    row = {
        "policy_id": policy["policy_id"],
        "policy_name": policy["policy_name"],
        "policy_version": policy["policy_version"],
        "capital_stage": policy["capital_stage"],
        "scope": policy["scope"],
        "created_utc": policy["created_utc"],
        "policy_path": str(Path(policy_path).resolve()),
        "rationale": policy["rationale"],
    }
    duckdb = _import_duckdb()
    conn = duckdb.connect(str(resolved_db_path))
    try:
        conn.execute("BEGIN TRANSACTION")
        conn.execute("DELETE FROM gate_policies WHERE policy_id = ?", [str(policy["policy_id"])])
        _insert_protocol_row(conn, "gate_policies", table_fields["gate_policies"], row)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()
    return {
        "ok": True,
        "db_path": str(resolved_db_path),
        "policy_id": str(policy["policy_id"]),
        "policy_path": str(Path(policy_path).resolve()),
        "written_gate_policies": 1,
    }


def _validate_gate_verdict_row(verdict: Mapping[str, object]) -> Dict[str, object]:
    fields = {
        "verdict_id",
        "candidate_id",
        "policy_id",
        "verdict",
        "metric_snapshot",
        "failed_rules",
        "warning_rules",
        "generated_utc",
        "artifact_path",
    }
    for field_name in fields:
        if field_name not in verdict or verdict[field_name] in (None, ""):
            raise ValueError(f"gate verdict missing required field: {field_name}")
    if str(verdict.get("verdict")) not in ALLOWED_GATE_VERDICTS:
        raise ValueError(f"unknown Survival Gate verdict: {verdict.get('verdict')}")
    if not isinstance(verdict.get("metric_snapshot"), Mapping):
        raise ValueError("gate verdict metric_snapshot must be an object")
    if not isinstance(verdict.get("failed_rules"), list):
        raise ValueError("gate verdict failed_rules must be a list")
    if not isinstance(verdict.get("warning_rules"), list):
        raise ValueError("gate verdict warning_rules must be a list")
    return {field_name: verdict[field_name] for field_name in fields}


def write_gate_verdict(
    artifacts_dir: str | Path = "artifacts",
    verdict: Mapping[str, object] | None = None,
    *,
    protocol_path: str | Path | None = None,
    db_path: str | Path | None = None,
) -> dict:
    if verdict is None:
        raise ValueError("gate verdict payload is required")
    row = _validate_gate_verdict_row(verdict)
    build_payload = build_evidence_warehouse(
        artifacts_dir,
        protocol_path=protocol_path,
        db_path=db_path,
    )
    protocol = load_evidence_warehouse_protocol(str(protocol_path) if protocol_path else None)
    table_fields = _table_required_fields(protocol)
    resolved_db_path = Path(str(build_payload["db_path"]))

    duckdb = _import_duckdb()
    conn = duckdb.connect(str(resolved_db_path))
    try:
        conn.execute("BEGIN TRANSACTION")
        existing = conn.execute(
            "SELECT COUNT(*) FROM gate_verdicts WHERE verdict_id = ?",
            [str(row["verdict_id"])],
        ).fetchone()[0]
        if existing:
            raise ValueError(f"gate verdict already exists and cannot be overwritten: {row['verdict_id']}")
        policy_exists = conn.execute(
            "SELECT COUNT(*) FROM gate_policies WHERE policy_id = ?",
            [str(row["policy_id"])],
        ).fetchone()[0]
        if not policy_exists:
            raise ValueError(f"gate verdict policy_id not found in gate_policies: {row['policy_id']}")
        candidate_exists = conn.execute(
            "SELECT COUNT(*) FROM strategy_candidates WHERE candidate_id = ?",
            [str(row["candidate_id"])],
        ).fetchone()[0]
        if not candidate_exists:
            raise ValueError(f"gate verdict candidate_id not found in strategy_candidates: {row['candidate_id']}")
        _insert_protocol_row(conn, "gate_verdicts", table_fields["gate_verdicts"], row)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()
    return {
        "ok": True,
        "db_path": str(resolved_db_path),
        "verdict_id": str(row["verdict_id"]),
        "policy_id": str(row["policy_id"]),
        "written_gate_verdicts": 1,
    }


def validate_evidence_warehouse(
    artifacts_dir: str | Path = "artifacts",
    *,
    protocol_path: str | Path | None = None,
    db_path: str | Path | None = None,
) -> dict:
    """Validate that the Evidence Warehouse V1 skeleton matches the protocol."""

    protocol = load_evidence_warehouse_protocol(str(protocol_path) if protocol_path else None)
    table_fields = _table_required_fields(protocol)
    resolved_db_path = _resolve_warehouse_db_path(artifacts_dir, db_path)
    issues: List[dict] = []

    if not resolved_db_path.exists():
        return {
            "ok": False,
            "artifacts_dir": str(Path(artifacts_dir)),
            "db_path": str(resolved_db_path),
            "protocol_path": str(_resolve_evidence_warehouse_protocol_path(str(protocol_path) if protocol_path else None).resolve()),
            "schema_version": str(protocol.get("schema_version") or ""),
            "tables_expected": len(table_fields),
            "tables_present": 0,
            "missing_tables": sorted(table_fields),
            "missing_columns": {},
            "issues": [
                {
                    "component": "evidence_warehouse",
                    "severity": "error",
                    "message": "evidence warehouse database is missing",
                    "path": str(resolved_db_path),
                }
            ],
        }

    duckdb = _import_duckdb()
    missing_tables: List[str] = []
    missing_columns: Dict[str, List[str]] = {}
    metadata: Dict[str, str] = {}

    conn = duckdb.connect(str(resolved_db_path), read_only=True)
    try:
        tables = {str(row[0]) for row in conn.execute("SHOW TABLES").fetchall()}
        for table_name, required_fields in table_fields.items():
            if table_name not in tables:
                missing_tables.append(table_name)
                continue
            columns = {
                str(row[1])
                for row in conn.execute(f"PRAGMA table_info({_quote_ident(table_name)})").fetchall()
            }
            missing = [field_name for field_name in required_fields if field_name not in columns]
            if missing:
                missing_columns[table_name] = missing

        if "evidence_warehouse_metadata" in tables:
            metadata = {
                str(key): str(value)
                for key, value in conn.execute(
                    "SELECT meta_key, meta_value FROM evidence_warehouse_metadata"
                ).fetchall()
            }
        else:
            issues.append(
                {
                    "component": "evidence_warehouse",
                    "severity": "error",
                    "message": "metadata table missing",
                    "path": str(resolved_db_path),
                }
            )
    finally:
        conn.close()

    expected_metadata = _metadata_rows(protocol)
    for key, value in expected_metadata.items():
        if metadata.get(key) != value:
            issues.append(
                {
                    "component": "evidence_warehouse",
                    "severity": "error",
                    "message": f"metadata mismatch for {key}",
                    "path": str(resolved_db_path),
                }
            )

    for table_name in missing_tables:
        issues.append(
            {
                "component": "evidence_warehouse",
                "severity": "error",
                "message": f"required table missing: {table_name}",
                "path": str(resolved_db_path),
            }
        )
    for table_name, fields in missing_columns.items():
        issues.append(
            {
                "component": "evidence_warehouse",
                "severity": "error",
                "message": f"required columns missing from {table_name}: {', '.join(fields)}",
                "path": str(resolved_db_path),
            }
        )

    return {
        "ok": not issues,
        "artifacts_dir": str(Path(artifacts_dir)),
        "db_path": str(resolved_db_path),
        "protocol_path": str(_resolve_evidence_warehouse_protocol_path(str(protocol_path) if protocol_path else None).resolve()),
        "schema_version": str(protocol.get("schema_version") or ""),
        "tables_expected": len(table_fields),
        "tables_present": len(set(table_fields) - set(missing_tables)),
        "missing_tables": sorted(missing_tables),
        "missing_columns": missing_columns,
        "issues": issues,
    }
