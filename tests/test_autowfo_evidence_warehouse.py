import json
import hashlib

import pytest

from autowfo import evidence_warehouse as ew


duckdb = pytest.importorskip("duckdb")


def _candidate_definition(**overrides):
    payload = {
        "strategy_family": "obv_roc_keltner",
        "indicator_set": ["obv_roc", "keltner_pos"],
        "parameter_set": {
            "obv_roc": {"lookback": 20},
            "keltner_pos": {"ema": 20, "atr": 10},
        },
        "timeframe": "2h",
        "market_universe": ["ETH/BTC", "SOL/BTC"],
        "direction_scope": "long",
        "entry_rule": {"signal": "signal_long"},
        "exit_rule": {"signal": "signal_exit"},
        "risk_rule": {"tp_stop": 1.5, "sl_stop": 1.0, "max_hold": 12},
        "cost_profile_id": "cost_binance_spot_v1",
        "data_profile_id": "data_binance_btc_2h_180d_v1",
        "source_system": "autowfo",
    }
    payload.update(overrides)
    return payload


def test_default_evidence_warehouse_protocol_loads_required_contract():
    protocol = ew.load_evidence_warehouse_protocol()

    assert protocol["schema_version"] == "1.0.0"
    assert protocol["name"] == "autowfo_evidence_warehouse_v1"
    assert set(protocol["identity_keys"]) == set(ew.REQUIRED_IDENTITY_KEYS)
    assert set(protocol["table_contracts"]) == set(ew.REQUIRED_TABLE_CONTRACTS)
    assert "policy_id" in protocol["table_contracts"]["gate_verdicts"]["required_fields"]
    assert "candidate_identity_helper" in protocol["initial_implementation_sequence"]


def test_validate_evidence_warehouse_protocol_rejects_missing_identity_key():
    protocol = ew.load_evidence_warehouse_protocol()
    protocol["identity_keys"].pop("candidate_id")

    with pytest.raises(ValueError, match="identity_keys.candidate_id"):
        ew.validate_evidence_warehouse_protocol(protocol)


def test_validate_evidence_warehouse_protocol_rejects_gate_verdict_without_policy_id():
    protocol = ew.load_evidence_warehouse_protocol()
    required_fields = protocol["table_contracts"]["gate_verdicts"]["required_fields"]
    required_fields.remove("policy_id")

    with pytest.raises(ValueError, match="gate_verdicts.*policy_id"):
        ew.validate_evidence_warehouse_protocol(protocol)


def test_build_candidate_id_is_stable_for_equivalent_nested_definitions():
    first = _candidate_definition()
    second = {
        "source_system": "autowfo",
        "data_profile_id": "data_binance_btc_2h_180d_v1",
        "cost_profile_id": "cost_binance_spot_v1",
        "risk_rule": {"max_hold": 12, "sl_stop": 1.0, "tp_stop": 1.5},
        "exit_rule": {"signal": "signal_exit"},
        "entry_rule": {"signal": "signal_long"},
        "direction_scope": "long",
        "market_universe": ["ETH/BTC", "SOL/BTC"],
        "timeframe": "2h",
        "parameter_set": {
            "keltner_pos": {"atr": 10, "ema": 20},
            "obv_roc": {"lookback": 20},
        },
        "indicator_set": ["obv_roc", "keltner_pos"],
        "strategy_family": "obv_roc_keltner",
    }

    first_id = ew.build_candidate_id(first)
    second_id = ew.build_candidate_id(second)

    assert first_id == second_id
    assert first_id.startswith("cand_")


def test_build_candidate_id_changes_when_candidate_definition_changes():
    first_id = ew.build_candidate_id(_candidate_definition())
    changed_id = ew.build_candidate_id(_candidate_definition(timeframe="4h"))

    assert first_id != changed_id


def test_build_candidate_id_rejects_missing_required_definition_field():
    payload = _candidate_definition()
    payload.pop("risk_rule")

    with pytest.raises(ValueError, match="candidate definition missing required field: risk_rule"):
        ew.build_candidate_id(payload)


def test_candidate_identity_payload_is_json_stable():
    payload = ew.build_candidate_identity_payload(_candidate_definition())
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)

    assert json.loads(encoded) == payload
    assert list(payload) == list(ew.CANDIDATE_DEFINITION_FIELDS)


def test_build_evidence_warehouse_creates_empty_protocol_tables(tmp_path):
    artifacts = tmp_path / "artifacts"

    payload = ew.build_evidence_warehouse(artifacts)

    assert payload["ok"] is True
    assert payload["schema_version"] == "1.0.0"
    assert payload["tables_created"] == len(ew.REQUIRED_TABLE_CONTRACTS)
    db_path = artifacts / "evidence_warehouse" / "evidence_warehouse.duckdb"
    assert payload["db_path"] == str(db_path.resolve())

    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
        assert set(ew.REQUIRED_TABLE_CONTRACTS).issubset(tables)
        columns = {
            row[1]
            for row in conn.execute('PRAGMA table_info("gate_verdicts")').fetchall()
        }
        assert {"candidate_id", "policy_id", "verdict", "artifact_path"}.issubset(columns)
        metadata = dict(
            conn.execute(
                "SELECT meta_key, meta_value FROM evidence_warehouse_metadata"
            ).fetchall()
        )
        assert metadata["schema_version"] == "1.0.0"
        assert metadata["protocol_name"] == "autowfo_evidence_warehouse_v1"
    finally:
        conn.close()


def test_build_evidence_warehouse_is_idempotent_and_preserves_source_artifacts(tmp_path):
    artifacts = tmp_path / "artifacts"
    source_path = artifacts / "freqtrade_bridge" / "awf331_rerun_summary.json"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(json.dumps({"rows": [{"row_id": "row_a"}]}), encoding="utf-8")
    before_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()

    first = ew.build_evidence_warehouse(artifacts)
    second = ew.build_evidence_warehouse(artifacts)
    after_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()

    assert first["ok"] is True
    assert second["ok"] is True
    assert second["db_path"] == first["db_path"]
    assert after_hash == before_hash


def test_validate_evidence_warehouse_detects_missing_table(tmp_path):
    artifacts = tmp_path / "artifacts"
    build_payload = ew.build_evidence_warehouse(artifacts)

    conn = duckdb.connect(build_payload["db_path"])
    try:
        conn.execute("DROP TABLE backtest_metrics")
    finally:
        conn.close()

    validation = ew.validate_evidence_warehouse(artifacts)

    assert validation["ok"] is False
    assert "backtest_metrics" in validation["missing_tables"]
