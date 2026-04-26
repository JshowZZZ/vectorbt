"""Evidence Warehouse V1 protocol and candidate identity helpers."""

from __future__ import annotations

import hashlib
import json
import os
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
