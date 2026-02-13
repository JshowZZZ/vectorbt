import json
import sqlite3

import pytest

from scripts.autowfo import artifacts as a
from scripts.autowfo.constants import LABELS


def test_artifacts_db_schema_and_append_module(tmp_path):
    db_path = tmp_path / "results.db"
    columns = ["timeframe", "value"]

    a._ensure_db_schema(str(db_path), "combo_summary", columns, indexes=[("idx_tf", ["timeframe"])])
    inserted = a._append_db_rows(
        str(db_path),
        "combo_summary",
        [{"timeframe": "3m", "value": 1.0}, {"timeframe": "15m", "value": 2.0}],
        columns,
    )

    assert inserted == 2
    with sqlite3.connect(db_path) as conn:
        cols = [row[1] for row in conn.execute("PRAGMA table_info(combo_summary)").fetchall()]
        assert "created_utc" in cols
        count = conn.execute("SELECT COUNT(*) FROM combo_summary").fetchone()[0]
        assert count == 2


def test_config_hash_and_data_fingerprint_are_deterministic():
    config = {"b": 2, "a": 1}
    assert a._compute_config_sha256(config) == a._compute_config_sha256({"a": 1, "b": 2})

    payload = {"timeframe": "3m", "data_start": "2024-01-01", "data_end": "2024-01-31"}
    assert a._compute_data_fingerprint(payload) == a._compute_data_fingerprint(dict(payload))


def test_write_run_metadata_requires_contract_fields(tmp_path):
    path = tmp_path / "run_metadata.json"
    payload = {
        "run_id": "20260208_000000",
        "timestamp_utc": "2026-02-08T00:00:00Z",
        "search_mode": "combo",
        "config_sha256": "abc",
        "combo_seed": 42,
        "data_fingerprint": "def",
        "config_path": "artifacts/sweep_config.json",
        "exchange": "binance",
        "base_symbol": "BTC/USDT",
        "trade_symbols": ["ETH/BTC"],
        "timeframes": [{"timeframe": "3m", "days": 60}],
        "wf_train_days": 120,
        "wf_test_days": 30,
        "wf_step_days": 30,
        "wf_mode": "anchored",
        "capital_mode": "shared",
        "init_cash_usdt": 1000,
    }
    a._write_run_metadata(str(path), payload)
    got = json.loads(path.read_text(encoding="utf-8"))
    assert got["run_id"] == payload["run_id"]
    assert got["config_sha256"] == payload["config_sha256"]
    assert got["combo_seed"] == 42

    bad_payload = dict(payload)
    bad_payload.pop("config_sha256")
    with pytest.raises(ValueError, match="missing required fields"):
        a._write_run_metadata(str(path), bad_payload)

    bad_payload_seed = dict(payload)
    bad_payload_seed.pop("combo_seed")
    with pytest.raises(ValueError, match="missing required fields"):
        a._write_run_metadata(str(path), bad_payload_seed)
