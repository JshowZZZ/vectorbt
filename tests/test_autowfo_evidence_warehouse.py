import json
import hashlib
import sqlite3

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


def _write_phase61_62_replay_artifacts(artifacts, *, include_drift=True):
    summary_path = artifacts / "freqtrade_bridge" / "awf331_rerun_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "row_id": "stable_top10_rank_1",
            "signal_manifest_path": str(artifacts / "freqtrade_bridge" / "bundle_a" / "signal_manifest.json"),
            "parity_report_path": str(artifacts / "freqtrade_bridge" / "awf339" / "bundle_a" / "parity_report.json"),
            "rerun_output_dir": str(artifacts / "freqtrade_bridge" / "awf339" / "bundle_a"),
            "strategy_name": "AutowfoGenericSignalStrategyLongShort",
            "verdict": "review",
            "autowfo_trade_count": 100,
            "freqtrade_trade_count": 98,
            "trade_count_delta": -2,
            "open_match_ratio": 0.98,
            "exact_match_ratio": 0.62,
            "profit_ratio_abs_delta_mean": 0.01,
            "indicator_list": "obv_roc,keltner_pos",
            "regime_name": "trend_high",
            "vol_mode": "high",
            "filter_name": "OBV trend + Keltner position",
            "timeframe": "2h",
            "data_days": 180,
            "vol_lookback": 24,
            "mom_lookback": 6,
            "trade_mom_lookback": 3,
            "tp_stop": 1.5,
            "sl_stop": 1.0,
            "max_hold": 4,
            "per_pair_counts": [
                {"pair": "ETH/BTC", "direction": "Long", "autowfo_count": 10, "freqtrade_count": 9, "delta": -1},
                {"pair": "SOL/BTC", "direction": "Short", "autowfo_count": 8, "freqtrade_count": 8, "delta": 0},
            ],
        },
        {
            "row_id": "stable_top10_rank_2",
            "signal_manifest_path": str(artifacts / "freqtrade_bridge" / "bundle_b" / "signal_manifest.json"),
            "parity_report_path": str(artifacts / "freqtrade_bridge" / "awf339" / "bundle_b" / "parity_report.json"),
            "rerun_output_dir": str(artifacts / "freqtrade_bridge" / "awf339" / "bundle_b"),
            "strategy_name": "AutowfoGenericSignalStrategyLongShort",
            "verdict": "review",
            "autowfo_trade_count": 50,
            "freqtrade_trade_count": 50,
            "trade_count_delta": 0,
            "open_match_ratio": 1.0,
            "exact_match_ratio": 0.7,
            "profit_ratio_abs_delta_mean": 0.02,
            "indicator_list": "obv_roc,cmf",
            "regime_name": "trend_any",
            "vol_mode": "any",
            "filter_name": "OBV trend + CMF",
            "timeframe": "2h",
            "data_days": 180,
            "vol_lookback": 20,
            "mom_lookback": 8,
            "trade_mom_lookback": 4,
            "tp_stop": 1.25,
            "sl_stop": 1.0,
            "max_hold": 4,
            "per_pair_counts": [
                {"pair": "ETH/BTC", "direction": "Long", "autowfo_count": 5, "freqtrade_count": 5, "delta": 0},
                {"pair": "SOL/BTC", "direction": "Short", "autowfo_count": 6, "freqtrade_count": 6, "delta": 0},
            ],
        },
    ]
    summary_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "name": "awf331_rerun_summary",
                "created_utc": "2026-04-18T00:00:00Z",
                "aggregate": {"row_count": len(rows), "pairs": ["ETH/BTC", "SOL/BTC"]},
                "rows": rows,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    drift_path = artifacts / "reports" / "execution_drift_report.json"
    if include_drift:
        drift_path.parent.mkdir(parents=True, exist_ok=True)
        drift_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0.0",
                    "generated_utc": "2026-04-18T01:00:00Z",
                    "row_scope_count": len(rows),
                    "report_sections": {
                        "row_level_drift": [
                            {
                                "row_id": "stable_top10_rank_1",
                                "open_match_ratio": 0.98,
                                "exact_match_ratio": 0.62,
                                "trade_count_delta": -2,
                                "drift_severity": "high",
                            },
                            {
                                "row_id": "stable_top10_rank_2",
                                "open_match_ratio": 1.0,
                                "exact_match_ratio": 0.7,
                                "trade_count_delta": 0,
                                "drift_severity": "low",
                            },
                        ],
                        "source_consistency": [
                            {
                                "row_id": "stable_top10_rank_1",
                                "signal_bundle_id": "bundle_a",
                                "parity_bundle_id": "bundle_a",
                                "signal_manifest_joined": True,
                                "parity_report_joined": True,
                            },
                            {
                                "row_id": "stable_top10_rank_2",
                                "signal_bundle_id": "bundle_b",
                                "parity_bundle_id": "bundle_b",
                                "signal_manifest_joined": True,
                                "parity_report_joined": True,
                            },
                        ],
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    return summary_path, drift_path


def _phase63_selected_row(**overrides):
    payload = {
        "timeframe": "2h",
        "data_days": 180,
        "indicator_list": "obv_roc,keltner_pos",
        "regime_name": "trend_high",
        "vol_mode": "high",
        "vol_lookback": 24,
        "mom_lookback": 6,
        "trade_mom_lookback": 3,
        "tp_stop": 1.5,
        "sl_stop": 1.0,
        "max_hold": 4,
        "analysis_bucket": "canonical_gate_passed",
        "analysis_rank": 1,
        "passes_overall_gate": True,
    }
    payload.update(overrides)
    return payload


def _phase63_daily_summary(
    *,
    artifacts,
    db_path,
    paper_dir=None,
    day="2026-04-20",
    trade_id=11,
    include_trade=True,
    include_opened=True,
    include_closed=True,
    selected_row=None,
):
    selected_row = dict(selected_row or _phase63_selected_row())
    paper_dir = paper_dir or artifacts / "paper_dryrun"
    paper_dir.mkdir(parents=True, exist_ok=True)
    opened_trades = []
    closed_trades = []
    if include_trade and include_opened:
        opened_trades.append(
            {
                "trade_id": trade_id,
                "pair": "LTC/USDT:USDT",
                "source_pair": "LTC/BTC",
                "direction": "Long",
                "open_date": f"{day}T10:00:00+00:00",
                "open_rate": 100.0,
                "stake_amount": 100.0,
                "matched": True,
            }
        )
    if include_trade and include_closed:
        closed_trades.append(
            {
                "trade_id": trade_id,
                "pair": "LTC/USDT:USDT",
                "source_pair": "LTC/BTC",
                "direction": "Long",
                "close_date": f"{day}T12:00:00+00:00",
                "close_rate": 103.0,
                "close_profit": 0.03,
                "close_profit_abs": 3.0,
                "matched": True,
            }
        )
    payload = {
        "schema_version": "1.0.0",
        "created_utc": f"{day}T23:55:00+00:00",
        "date_utc": day,
        "window_start_utc": f"{day}T00:00:00+00:00",
        "window_end_utc": f"{day}T23:59:59+00:00",
        "db_path": str(db_path),
        "live_manifest_path": str(artifacts / "live_signal_store" / "live_manifest.json"),
        "source_bundle_manifest": str(artifacts / "freqtrade_bridge" / "canonical" / "signal_manifest.json"),
        "analysis": {
            "selection": selected_row["analysis_bucket"],
            "rank": selected_row["analysis_rank"],
            "main_run_id": "20260411_microcohort_dropsol_main",
            "selected_row": selected_row,
        },
        "source": {
            "run_root": str(artifacts / "runs" / "20260411_microcohort_dropsol_main"),
            "timeframe": "2h",
            "data_days": 180,
            "pairs": ["LTC/BTC", "ETH/BTC"],
            "exchange": "binance",
            "quote_currency": "BTC",
        },
        "runtime": {"window_days": 180},
        "pair_mapping": {"LTC/BTC": "LTC/USDT:USDT"},
        "totals": {
            "opened_trades_day": len(opened_trades),
            "closed_trades_day": len(closed_trades),
            "entry_signal_match_rate": 1.0 if opened_trades else None,
            "exit_signal_match_rate": 1.0 if closed_trades else None,
            "realized_profit_abs_sum": 3.0 if closed_trades else 0.0,
        },
        "pair_summary": [],
        "opened_trades": opened_trades,
        "closed_trades": closed_trades,
    }
    out_path = paper_dir / f"daily_summary_{day.replace('-', '')}.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return out_path


def _write_phase63_live_manifest(artifacts, *, created_utc="2026-04-27T00:00:00+00:00"):
    manifest_path = artifacts / "live_signal_store" / "live_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps({"created_utc": created_utc}, ensure_ascii=False),
        encoding="utf-8",
    )
    return manifest_path


def _write_phase63_trade_db(
    db_path,
    *,
    trade_id=11,
    include_fees=True,
    open_rate=100,
    close_rate=103,
    open_date="2026-04-20T10:00:00+00:00",
    close_date="2026-04-20T12:00:00+00:00",
    close_profit=0.03,
    close_profit_abs=3.0,
):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE trades (
                id INTEGER,
                pair TEXT,
                is_open BOOLEAN,
                open_rate FLOAT,
                close_rate FLOAT,
                open_date TEXT,
                close_date TEXT,
                close_profit FLOAT,
                close_profit_abs FLOAT,
                stake_amount FLOAT,
                amount FLOAT,
                exit_reason TEXT,
                strategy TEXT,
                enter_tag TEXT,
                timeframe INTEGER,
                trading_mode TEXT,
                leverage FLOAT,
                is_short BOOLEAN,
                fee_open_cost FLOAT,
                fee_close_cost FLOAT
            )
            """
        )
        fee_open = 0.1 if include_fees else None
        fee_close = 0.2 if include_fees else None
        conn.execute(
            """
            INSERT INTO trades VALUES (
                ?, 'LTC/USDT:USDT', 0, ?, ?,
                ?, ?,
                ?, ?, 100, 1, 'exit_signal', 'AutowfoLiveSignalStrategyLongShort',
                'autowfo-long', 120, 'futures', 1, 0, ?, ?
            )
            """,
            [
                trade_id,
                open_rate,
                close_rate,
                open_date,
                close_date,
                close_profit,
                close_profit_abs,
                fee_open,
                fee_close,
            ],
        )
        conn.commit()
    finally:
        conn.close()


def _phase63_expected_candidate_id(artifacts, db_path):
    selected_row = _phase63_selected_row()
    summary = {
        "analysis": {
            "selection": selected_row["analysis_bucket"],
            "rank": selected_row["analysis_rank"],
            "selected_row": selected_row,
        },
        "source": {"pairs": ["LTC/BTC", "ETH/BTC"]},
        "pair_mapping": {"LTC/BTC": "LTC/USDT:USDT"},
        "opened_trades": [
            {
                "trade_id": 11,
                "pair": "LTC/USDT:USDT",
                "source_pair": "LTC/BTC",
                "direction": "Long",
            }
        ],
        "closed_trades": [],
    }
    candidate_definition = ew._candidate_definition_from_selected_row(
        selected_row,
        pairs=ew._phase63_summary_pairs(summary),
        direction_scope=ew._phase63_direction_scope(
            summary,
            {"created_utc": "2026-04-27T00:00:00+00:00"},
        ),
    )
    return ew.build_candidate_id(candidate_definition)


def _insert_legacy_phase63_paper_trade(artifacts, *, db_path, summary_path, trade_id):
    payload = ew.build_evidence_warehouse(artifacts)
    candidate_id = _phase63_expected_candidate_id(artifacts, db_path)
    legacy_paper_trade_id = ew._stable_prefixed_id(
        ew.PHASE63_PAPER_TRADE_ID_PREFIX,
        {
            "candidate_id": candidate_id,
            "trade_id": str(trade_id),
            "db_path": str(db_path),
            "summary_path": str(summary_path.resolve()),
        },
    )
    conn = duckdb.connect(payload["db_path"])
    try:
        conn.execute(
            """
            INSERT INTO paper_trades (
                paper_trade_id,
                candidate_id,
                freqtrade_trade_id,
                pair,
                direction,
                opened_utc,
                closed_utc,
                open_rate,
                close_rate,
                profit_abs,
                profit_ratio,
                fee_abs,
                funding_abs,
                source_db_path
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                legacy_paper_trade_id,
                candidate_id,
                str(trade_id),
                "LTC/USDT:USDT",
                "Long",
                "legacy_open",
                "",
                "1.0",
                "",
                "",
                "",
                "",
                "",
                str(db_path),
            ],
        )
    finally:
        conn.close()
    return legacy_paper_trade_id


def _insert_strategy_candidate(artifacts, *, candidate_id="cand_a", source_system="autowfo"):
    payload = ew.build_evidence_warehouse(artifacts)
    conn = duckdb.connect(payload["db_path"])
    try:
        conn.execute(
            """
            INSERT INTO strategy_candidates (
                candidate_id,
                candidate_version,
                strategy_family,
                indicator_set,
                parameter_set,
                timeframe,
                market_universe,
                direction_scope,
                entry_rule,
                exit_rule,
                risk_rule,
                cost_profile_id,
                data_profile_id,
                source_system,
                created_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                candidate_id,
                "autowfo_candidate_v1",
                "autowfo_combo_entry",
                '["obv_roc","keltner_pos"]',
                '{"regime_name":"trend_high"}',
                "2h",
                '["LTC/BTC"]',
                "long_short",
                '{"source":"signal_long_signal_short"}',
                '{"source":"signal_exit_long_signal_exit_short"}',
                '{"max_hold":4}',
                "cost_autowfo_replay_paper_v1",
                "data_autowfo_test",
                source_system,
                "2026-04-26T00:00:00Z",
            ],
        )
    finally:
        conn.close()
    return payload["db_path"]


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


def test_import_phase61_62_replay_evidence_writes_candidates_replay_and_gap_rows(tmp_path):
    artifacts = tmp_path / "artifacts"
    _write_phase61_62_replay_artifacts(artifacts)

    payload = ew.import_phase61_62_replay_evidence(artifacts)

    assert payload["ok"] is True
    assert payload["imported_candidates"] == 2
    assert payload["imported_ft_replay_results"] == 2
    assert payload["imported_execution_gap_events"] == 2
    assert payload["warnings"] == []

    conn = duckdb.connect(payload["db_path"], read_only=True)
    try:
        candidate_count = conn.execute("SELECT COUNT(*) FROM strategy_candidates").fetchone()[0]
        replay_rows = conn.execute(
            """
            SELECT signal_bundle_id, parity_bundle_id, trade_count_delta_pct
            FROM ft_replay_results
            ORDER BY signal_bundle_id
            """
        ).fetchall()
        gap_rows = conn.execute(
            """
            SELECT gap_type, severity, expected_source, actual_source
            FROM execution_gap_events
            ORDER BY severity DESC
            """
        ).fetchall()
    finally:
        conn.close()

    assert candidate_count == 2
    assert replay_rows == [("bundle_a", "bundle_a", "-0.02"), ("bundle_b", "bundle_b", "0.0")]
    assert gap_rows[0] == ("adapter_gap", "low", "autowfo_replay", "freqtrade_replay")
    assert gap_rows[1] == ("adapter_gap", "high", "autowfo_replay", "freqtrade_replay")


def test_import_phase61_62_replay_evidence_uses_canonical_autowfo_source_system(tmp_path):
    artifacts = tmp_path / "artifacts"
    _write_phase61_62_replay_artifacts(artifacts)

    payload = ew.import_phase61_62_replay_evidence(artifacts)

    conn = duckdb.connect(payload["db_path"], read_only=True)
    try:
        source_systems = conn.execute(
            "SELECT DISTINCT source_system FROM strategy_candidates"
        ).fetchall()
    finally:
        conn.close()

    assert source_systems == [("autowfo",)]


def test_import_phase61_62_replay_evidence_removes_legacy_candidate_source_rows(tmp_path):
    artifacts = tmp_path / "artifacts"
    _write_phase61_62_replay_artifacts(artifacts)
    _insert_strategy_candidate(
        artifacts,
        candidate_id="legacy_awf362_candidate",
        source_system="autowfo_phase61_62_awf339",
    )

    payload = ew.import_phase61_62_replay_evidence(artifacts)

    conn = duckdb.connect(payload["db_path"], read_only=True)
    try:
        rows = conn.execute(
            "SELECT candidate_id, source_system FROM strategy_candidates ORDER BY candidate_id"
        ).fetchall()
    finally:
        conn.close()

    assert len(rows) == 2
    assert all(source_system == "autowfo" for _candidate_id, source_system in rows)
    assert "legacy_awf362_candidate" not in {candidate_id for candidate_id, _source_system in rows}


def test_import_phase61_62_replay_evidence_is_idempotent_and_read_only(tmp_path):
    artifacts = tmp_path / "artifacts"
    summary_path, drift_path = _write_phase61_62_replay_artifacts(artifacts)
    before_summary_hash = hashlib.sha256(summary_path.read_bytes()).hexdigest()
    before_drift_hash = hashlib.sha256(drift_path.read_bytes()).hexdigest()

    first = ew.import_phase61_62_replay_evidence(artifacts)
    second = ew.import_phase61_62_replay_evidence(artifacts)

    conn = duckdb.connect(second["db_path"], read_only=True)
    try:
        counts = dict(
            conn.execute(
                """
                SELECT 'strategy_candidates', COUNT(*) FROM strategy_candidates
                UNION ALL SELECT 'ft_replay_results', COUNT(*) FROM ft_replay_results
                UNION ALL SELECT 'execution_gap_events', COUNT(*) FROM execution_gap_events
                """
            ).fetchall()
        )
    finally:
        conn.close()

    assert first["ok"] is True
    assert second["ok"] is True
    assert counts == {
        "strategy_candidates": 2,
        "ft_replay_results": 2,
        "execution_gap_events": 2,
    }
    assert hashlib.sha256(summary_path.read_bytes()).hexdigest() == before_summary_hash
    assert hashlib.sha256(drift_path.read_bytes()).hexdigest() == before_drift_hash


def test_import_phase61_62_replay_evidence_warns_when_drift_report_is_missing(tmp_path):
    artifacts = tmp_path / "artifacts"
    _summary_path, drift_path = _write_phase61_62_replay_artifacts(artifacts, include_drift=False)

    payload = ew.import_phase61_62_replay_evidence(artifacts)

    assert payload["ok"] is True
    assert payload["imported_candidates"] == 2
    assert payload["imported_ft_replay_results"] == 2
    assert payload["imported_execution_gap_events"] == 0
    assert payload["warnings"] == [
        {
            "code": "missing_drift_report",
            "path": str(drift_path.resolve()),
            "message": "Phase 61-62 drift report is missing; imported replay rows only",
        }
    ]


def test_import_phase63_paper_reconcile_evidence_imports_trades_with_fee_enrichment(tmp_path):
    artifacts = tmp_path / "artifacts"
    db_path = tmp_path / "freqtrade" / "tradesv3.dryrun.sqlite"
    daily_path = _phase63_daily_summary(artifacts=artifacts, db_path=db_path)
    _write_phase63_trade_db(db_path)
    before_daily_hash = hashlib.sha256(daily_path.read_bytes()).hexdigest()
    before_db_hash = hashlib.sha256(db_path.read_bytes()).hexdigest()

    payload = ew.import_phase63_paper_reconcile_evidence(
        artifacts,
        paper_dir=artifacts / "paper_dryrun",
    )

    conn = duckdb.connect(payload["db_path"], read_only=True)
    try:
        candidates = conn.execute(
            "SELECT source_system FROM strategy_candidates"
        ).fetchall()
        paper_rows = conn.execute(
            """
            SELECT freqtrade_trade_id, pair, direction, profit_abs, profit_ratio, fee_abs
            FROM paper_trades
            """
        ).fetchall()
    finally:
        conn.close()

    assert payload["ok"] is True
    assert payload["imported_candidates"] == 1
    assert payload["imported_paper_trades"] == 1
    assert candidates == [("autowfo",)]
    assert paper_rows == [("11", "LTC/USDT:USDT", "Long", "3.0", "0.03", "0.30000000000000004")]
    assert hashlib.sha256(daily_path.read_bytes()).hexdigest() == before_daily_hash
    assert hashlib.sha256(db_path.read_bytes()).hexdigest() == before_db_hash


def test_import_phase63_paper_reconcile_evidence_preserves_other_paper_batches(tmp_path):
    artifacts = tmp_path / "artifacts"
    paper1 = artifacts / "paper1"
    paper2 = artifacts / "paper2"
    db1 = tmp_path / "freqtrade" / "paper1.sqlite"
    db2 = tmp_path / "freqtrade" / "paper2.sqlite"
    _phase63_daily_summary(
        artifacts=artifacts,
        db_path=db1,
        paper_dir=paper1,
        day="2026-04-20",
        trade_id=31,
    )
    _phase63_daily_summary(
        artifacts=artifacts,
        db_path=db2,
        paper_dir=paper2,
        day="2026-04-21",
        trade_id=32,
    )
    _write_phase63_trade_db(db1, trade_id=31)
    _write_phase63_trade_db(
        db2,
        trade_id=32,
        open_date="2026-04-21T10:00:00+00:00",
        close_date="2026-04-21T12:00:00+00:00",
    )

    first = ew.import_phase63_paper_reconcile_evidence(artifacts, paper_dir=paper1)
    second = ew.import_phase63_paper_reconcile_evidence(artifacts, paper_dir=paper2)

    conn = duckdb.connect(second["db_path"], read_only=True)
    try:
        trade_ids = [
            row[0]
            for row in conn.execute(
                "SELECT freqtrade_trade_id FROM paper_trades ORDER BY freqtrade_trade_id"
            ).fetchall()
        ]
    finally:
        conn.close()

    assert first["imported_paper_trades"] == 1
    assert second["imported_paper_trades"] == 1
    assert trade_ids == ["31", "32"]


def test_import_phase63_paper_reconcile_evidence_enriches_cross_day_trade_facts_from_db(tmp_path):
    artifacts = tmp_path / "artifacts"
    db_path = tmp_path / "freqtrade" / "tradesv3.dryrun.sqlite"
    _phase63_daily_summary(
        artifacts=artifacts,
        db_path=db_path,
        day="2026-04-21",
        trade_id=41,
        include_opened=False,
        include_closed=True,
    )
    _write_phase63_trade_db(
        db_path,
        trade_id=41,
        open_rate=99.0,
        close_rate=104.5,
        open_date="2026-04-20T10:00:00+00:00",
        close_date="2026-04-21T12:00:00+00:00",
        close_profit=0.055,
        close_profit_abs=5.5,
    )

    payload = ew.import_phase63_paper_reconcile_evidence(
        artifacts,
        paper_dir=artifacts / "paper_dryrun",
    )

    conn = duckdb.connect(payload["db_path"], read_only=True)
    try:
        paper_row = conn.execute(
            """
            SELECT opened_utc, closed_utc, open_rate, close_rate, profit_abs, profit_ratio, fee_abs
            FROM paper_trades
            """
        ).fetchone()
    finally:
        conn.close()

    assert payload["imported_paper_trades"] == 1
    assert paper_row == (
        "2026-04-20T10:00:00+00:00",
        "2026-04-21T12:00:00+00:00",
        "99.0",
        "104.5",
        "5.5",
        "0.055",
        "0.30000000000000004",
    )


def test_import_phase63_paper_reconcile_evidence_merges_open_and_close_days_for_same_trade(tmp_path):
    artifacts = tmp_path / "artifacts"
    db_path = tmp_path / "freqtrade" / "tradesv3.dryrun.sqlite"
    _phase63_daily_summary(
        artifacts=artifacts,
        db_path=db_path,
        day="2026-04-20",
        trade_id=51,
        include_opened=True,
        include_closed=False,
    )
    _phase63_daily_summary(
        artifacts=artifacts,
        db_path=db_path,
        day="2026-04-21",
        trade_id=51,
        include_opened=False,
        include_closed=True,
    )
    _write_phase63_trade_db(
        db_path,
        trade_id=51,
        open_rate=99.0,
        close_rate=104.5,
        open_date="2026-04-20T10:00:00+00:00",
        close_date="2026-04-21T12:00:00+00:00",
        close_profit=0.055,
        close_profit_abs=5.5,
    )

    payload = ew.import_phase63_paper_reconcile_evidence(
        artifacts,
        paper_dir=artifacts / "paper_dryrun",
    )

    conn = duckdb.connect(payload["db_path"], read_only=True)
    try:
        paper_rows = conn.execute(
            """
            SELECT freqtrade_trade_id, opened_utc, closed_utc, open_rate, close_rate, profit_abs, profit_ratio, fee_abs
            FROM paper_trades
            """
        ).fetchall()
    finally:
        conn.close()

    assert payload["imported_paper_trades"] == 1
    assert paper_rows == [
        (
            "51",
            "2026-04-20T10:00:00+00:00",
            "2026-04-21T12:00:00+00:00",
            "99.0",
            "104.5",
            "5.5",
            "0.055",
            "0.30000000000000004",
        )
    ]


def test_import_phase63_paper_reconcile_evidence_replaces_legacy_summary_scoped_trade_ids(tmp_path):
    artifacts = tmp_path / "artifacts"
    db_path = tmp_path / "freqtrade" / "tradesv3.dryrun.sqlite"
    opened_summary = _phase63_daily_summary(
        artifacts=artifacts,
        db_path=db_path,
        day="2026-04-20",
        trade_id=61,
        include_opened=True,
        include_closed=False,
    )
    closed_summary = _phase63_daily_summary(
        artifacts=artifacts,
        db_path=db_path,
        day="2026-04-21",
        trade_id=61,
        include_opened=False,
        include_closed=True,
    )
    _write_phase63_trade_db(
        db_path,
        trade_id=61,
        open_date="2026-04-20T10:00:00+00:00",
        close_date="2026-04-21T12:00:00+00:00",
    )
    legacy_ids = {
        _insert_legacy_phase63_paper_trade(
            artifacts,
            db_path=db_path,
            summary_path=opened_summary,
            trade_id=61,
        ),
        _insert_legacy_phase63_paper_trade(
            artifacts,
            db_path=db_path,
            summary_path=closed_summary,
            trade_id=61,
        ),
    }

    payload = ew.import_phase63_paper_reconcile_evidence(
        artifacts,
        paper_dir=artifacts / "paper_dryrun",
    )

    conn = duckdb.connect(payload["db_path"], read_only=True)
    try:
        rows = conn.execute(
            "SELECT paper_trade_id, freqtrade_trade_id FROM paper_trades"
        ).fetchall()
    finally:
        conn.close()

    assert payload["imported_paper_trades"] == 1
    assert len(rows) == 1
    assert rows[0][0] not in legacy_ids
    assert rows[0][1] == "61"


def test_import_phase63_paper_reconcile_evidence_is_idempotent_and_warns_on_gaps(tmp_path):
    artifacts = tmp_path / "artifacts"
    db_path = tmp_path / "freqtrade" / "missing.sqlite"
    _phase63_daily_summary(artifacts=artifacts, db_path=db_path, include_trade=False)
    live_manifest_path = artifacts / "live_signal_store" / "live_manifest.json"
    live_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    live_manifest_path.write_text(
        json.dumps({"created_utc": "2026-04-18T00:00:00+00:00"}),
        encoding="utf-8",
    )

    first = ew.import_phase63_paper_reconcile_evidence(
        artifacts,
        paper_dir=artifacts / "paper_dryrun",
        live_manifest_path=live_manifest_path,
    )
    second = ew.import_phase63_paper_reconcile_evidence(
        artifacts,
        paper_dir=artifacts / "paper_dryrun",
        live_manifest_path=live_manifest_path,
    )

    conn = duckdb.connect(second["db_path"], read_only=True)
    try:
        counts = dict(
            conn.execute(
                """
                SELECT 'paper_trades', COUNT(*) FROM paper_trades
                UNION ALL SELECT 'execution_gap_events', COUNT(*) FROM execution_gap_events
                """
            ).fetchall()
        )
        gap_types = conn.execute(
            "SELECT gap_type, attribution FROM execution_gap_events ORDER BY attribution"
        ).fetchall()
    finally:
        conn.close()

    warning_codes = {item["code"] for item in second["warnings"]}
    assert first["ok"] is True
    assert second["ok"] is True
    assert counts == {"paper_trades": 0, "execution_gap_events": 2}
    assert ("zero_trade_day" in warning_codes) is True
    assert ("stale_live_manifest" in warning_codes) is True
    assert gap_types == [
        ("execution_gap", "phase63_stale_live_manifest"),
        ("execution_gap", "phase63_zero_trade_day"),
    ]


def test_survival_gate_policy_and_verdict_writer_are_immutable(tmp_path):
    artifacts = tmp_path / "artifacts"
    policy_path = tmp_path / "survival_gate_policy.json"
    policy_path.write_text(
        json.dumps(
            {
                "policy_id": "policy_phase63_paper_v1",
                "policy_name": "phase63 paper observation gate",
                "policy_version": "1.0.0",
                "created_utc": "2026-04-26T00:00:00Z",
                "capital_stage": "paper",
                "scope": {"timeframe": "2h", "strategy_family": "combo_entry"},
                "rationale": "test policy",
            }
        ),
        encoding="utf-8",
    )

    policy_payload = ew.write_gate_policy(artifacts, policy_path=policy_path)
    _insert_strategy_candidate(artifacts, candidate_id="cand_a")
    first = ew.write_gate_verdict(
        artifacts,
        {
            "verdict_id": "verdict_a",
            "candidate_id": "cand_a",
            "policy_id": "policy_phase63_paper_v1",
            "verdict": "observe",
            "metric_snapshot": {"evidence_days": 4},
            "failed_rules": [],
            "warning_rules": ["insufficient_days"],
            "generated_utc": "2026-04-26T00:00:01Z",
            "artifact_path": "artifacts/reports/phase63_paper_survival_report.json",
        },
    )
    second = ew.write_gate_verdict(
        artifacts,
        {
            "verdict_id": "verdict_b",
            "candidate_id": "cand_a",
            "policy_id": "policy_phase63_paper_v1",
            "verdict": "reject",
            "metric_snapshot": {"evidence_days": 14},
            "failed_rules": ["open_match_ratio"],
            "warning_rules": [],
            "generated_utc": "2026-04-27T00:00:01Z",
            "artifact_path": "artifacts/reports/phase63_paper_survival_report_2.json",
        },
    )

    conn = duckdb.connect(second["db_path"], read_only=True)
    try:
        verdicts = conn.execute(
            "SELECT verdict_id, verdict FROM gate_verdicts ORDER BY verdict_id"
        ).fetchall()
        policies = conn.execute("SELECT policy_id FROM gate_policies").fetchall()
    finally:
        conn.close()

    assert policy_payload["ok"] is True
    assert first["ok"] is True
    assert second["ok"] is True
    assert policies == [("policy_phase63_paper_v1",)]
    assert verdicts == [("verdict_a", "observe"), ("verdict_b", "reject")]


def test_write_gate_verdict_rejects_missing_policy_id_and_unknown_verdict(tmp_path):
    artifacts = tmp_path / "artifacts"

    with pytest.raises(ValueError, match="policy_id"):
        ew.write_gate_verdict(
            artifacts,
            {
                "verdict_id": "verdict_missing_policy",
                "candidate_id": "cand_a",
                "verdict": "observe",
                "metric_snapshot": {"evidence_days": 4},
                "failed_rules": [],
                "warning_rules": [],
                "generated_utc": "2026-04-26T00:00:01Z",
                "artifact_path": "artifact.json",
            },
        )

    with pytest.raises(ValueError, match="unknown Survival Gate verdict"):
        ew.write_gate_verdict(
            artifacts,
            {
                "verdict_id": "verdict_bad",
                "candidate_id": "cand_a",
                "policy_id": "policy_phase63_paper_v1",
                "verdict": "maybe",
                "metric_snapshot": {"evidence_days": 4},
                "failed_rules": [],
                "warning_rules": [],
                "generated_utc": "2026-04-26T00:00:01Z",
                "artifact_path": "artifact.json",
            },
        )


def test_write_gate_verdict_rejects_unknown_policy_or_candidate_references(tmp_path):
    artifacts = tmp_path / "artifacts"
    policy_path = tmp_path / "survival_gate_policy.json"
    policy_path.write_text(
        json.dumps(
            {
                "policy_id": "policy_phase63_paper_v1",
                "policy_name": "phase63 paper observation gate",
                "policy_version": "1.0.0",
                "created_utc": "2026-04-26T00:00:00Z",
                "capital_stage": "paper",
                "scope": {"timeframe": "2h", "strategy_family": "combo_entry"},
                "rationale": "test policy",
            }
        ),
        encoding="utf-8",
    )

    ew.write_gate_policy(artifacts, policy_path=policy_path)
    with pytest.raises(ValueError, match="candidate_id.*not found"):
        ew.write_gate_verdict(
            artifacts,
            {
                "verdict_id": "verdict_missing_candidate",
                "candidate_id": "missing_candidate",
                "policy_id": "policy_phase63_paper_v1",
                "verdict": "observe",
                "metric_snapshot": {"evidence_days": 7},
                "failed_rules": [],
                "warning_rules": [],
                "generated_utc": "2026-04-26T00:00:01Z",
                "artifact_path": "artifact.json",
            },
        )

    _insert_strategy_candidate(artifacts, candidate_id="cand_a")
    with pytest.raises(ValueError, match="policy_id.*not found"):
        ew.write_gate_verdict(
            artifacts,
            {
                "verdict_id": "verdict_missing_policy",
                "candidate_id": "cand_a",
                "policy_id": "missing_policy",
                "verdict": "observe",
                "metric_snapshot": {"evidence_days": 7},
                "failed_rules": [],
                "warning_rules": [],
                "generated_utc": "2026-04-26T00:00:01Z",
                "artifact_path": "artifact.json",
            },
        )


def test_build_phase63_paper_survival_report_blocks_verdict_when_evidence_is_short(tmp_path):
    artifacts = tmp_path / "artifacts"
    db_path = tmp_path / "freqtrade" / "tradesv3.dryrun.sqlite"
    _phase63_daily_summary(artifacts=artifacts, db_path=db_path, day="2026-04-20", trade_id=20)
    _phase63_daily_summary(artifacts=artifacts, db_path=db_path, day="2026-04-21", trade_id=21)
    _phase63_daily_summary(artifacts=artifacts, db_path=db_path, day="2026-04-22", trade_id=22)
    _phase63_daily_summary(artifacts=artifacts, db_path=db_path, day="2026-04-23", trade_id=23)
    output_path = artifacts / "reports" / "phase63_paper_survival_report.json"

    report = ew.build_phase63_paper_survival_report(
        artifacts,
        paper_dir=artifacts / "paper_dryrun",
        output_path=output_path,
    )

    assert report["ok"] is True
    assert report["evidence_day_count"] == 4
    assert report["minimum_verdict_days"] == 7
    assert report["minimum_day_count_met"] is False
    assert report["verdict_allowed"] is False
    assert "insufficient_evidence_days" in report["blocking_reasons"]
    assert report["classification"] == "incomplete_evidence"
    assert report["candidate_role"] == "Champion"
    assert output_path.exists()


def test_build_phase63_paper_survival_report_blocks_verdict_on_quality_reasons(tmp_path):
    artifacts = tmp_path / "artifacts"
    db_path = tmp_path / "freqtrade" / "tradesv3.dryrun.sqlite"
    _write_phase63_live_manifest(artifacts, created_utc="2026-04-27T00:00:00+00:00")
    for offset in range(7):
        day = f"2026-04-{20 + offset:02d}"
        _phase63_daily_summary(
            artifacts=artifacts,
            db_path=db_path,
            day=day,
            trade_id=50 + offset,
            include_trade=(offset != 3),
        )
    output_path = artifacts / "reports" / "phase63_paper_survival_report.json"

    report = ew.build_phase63_paper_survival_report(
        artifacts,
        paper_dir=artifacts / "paper_dryrun",
        output_path=output_path,
    )

    assert report["ok"] is True
    assert report["evidence_day_count"] == 7
    assert report["minimum_day_count_met"] is True
    assert report["verdict_allowed"] is False
    assert "zero_trade_day" in report["blocking_reasons"]
    assert report["classification"] == "incomplete_evidence"
    assert report["valid_evidence_day_count"] == 6
    assert report["minimum_valid_day_count_met"] is False
    assert report["quality_by_day"]["2026-04-23"] == "zero_trade_day"


def test_build_phase63_paper_survival_report_blocks_when_manifest_freshness_evidence_is_missing(tmp_path):
    artifacts = tmp_path / "artifacts"
    db_path = tmp_path / "freqtrade" / "tradesv3.dryrun.sqlite"
    for offset in range(7):
        day = f"2026-04-{20 + offset:02d}"
        _phase63_daily_summary(
            artifacts=artifacts,
            db_path=db_path,
            day=day,
            trade_id=70 + offset,
        )

    report = ew.build_phase63_paper_survival_report(
        artifacts,
        paper_dir=artifacts / "paper_dryrun",
    )

    assert report["evidence_day_count"] == 7
    assert report["minimum_day_count_met"] is True
    assert report["verdict_allowed"] is False
    assert "missing_manifest_freshness_evidence" in report["blocking_reasons"]


def test_build_phase63_paper_survival_report_can_filter_to_canonical_lane(tmp_path):
    artifacts = tmp_path / "artifacts"
    db_path = tmp_path / "freqtrade" / "tradesv3.dryrun.sqlite"
    _write_phase63_live_manifest(artifacts, created_utc="2026-04-27T00:00:00+00:00")
    _phase63_daily_summary(
        artifacts=artifacts,
        db_path=db_path,
        day="2026-04-20",
        trade_id=101,
    )
    _phase63_daily_summary(
        artifacts=artifacts,
        db_path=db_path,
        day="2026-04-21",
        trade_id=102,
        selected_row=_phase63_selected_row(analysis_bucket="top_stable_positive", analysis_rank=10),
    )

    report = ew.build_phase63_paper_survival_report(
        artifacts,
        paper_dir=artifacts / "paper_dryrun",
        expected_selection="canonical_gate_passed",
        expected_rank=1,
    )

    assert report["daily_summary_count"] == 1
    assert report["source_summary_count"] == 2
    assert report["excluded_summary_count"] == 1
    assert report["candidate_role"] == "Champion"
    assert report["evidence_days"] == ["2026-04-20"]


def test_build_phase63_paper_survival_report_allows_verdict_when_minimum_quality_is_met(tmp_path):
    artifacts = tmp_path / "artifacts"
    db_path = tmp_path / "freqtrade" / "tradesv3.dryrun.sqlite"
    _write_phase63_live_manifest(artifacts, created_utc="2026-04-27T00:00:00+00:00")
    for offset in range(7):
        day = f"2026-04-{20 + offset:02d}"
        _phase63_daily_summary(
            artifacts=artifacts,
            db_path=db_path,
            day=day,
            trade_id=80 + offset,
        )

    report = ew.build_phase63_paper_survival_report(
        artifacts,
        paper_dir=artifacts / "paper_dryrun",
    )

    assert report["evidence_day_count"] == 7
    assert report["minimum_day_count_met"] is True
    assert report["blocking_reasons"] == []
    assert report["verdict_allowed"] is True
    assert report["classification"] == "paper_evidence_ready"
    assert report["valid_evidence_day_count"] == 7
    assert report["minimum_valid_day_count_met"] is True
