import json

import pytest

from autowfo.analytics import AnalyticsStore
from autowfo.artifact_store import ArtifactStore
from autowfo.storage_contract import (
    ANALYTICS_STORE_SCHEMA_VERSION,
    PAPER_POSITIONS_SCHEMA_VERSION,
    RUN_META_SCHEMA_VERSION,
    SCHEDULER_QUEUE_SCHEMA_VERSION,
    SIGNAL_SCHEDULE_STATE_SCHEMA_VERSION,
)
from autowfo.storage_ops import migrate_storage, rebuild_analytics, validate_storage


duckdb = pytest.importorskip("duckdb")


def _insert_combo_row(conn, *, combo_id, experiment_id, run_id, wf_score):
    conn.execute(
        """
        INSERT INTO combo_results (
            combo_id, experiment_id, run_id, direction,
            trigger_asset, action_asset,
            indicator_params, condition_params, risk_params,
            oos_sharpe, oos_win_rate, oos_n_trades, oos_total_return,
            wf_score, created_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            combo_id,
            experiment_id,
            run_id,
            "long",
            "BTC/USDT",
            "ETH/USDT",
            "{\"trigger_indicators\": [\"RSI\"], \"action_indicators\": [\"BB\"]}",
            "{}",
            "{}",
            1.2,
            0.55,
            12,
            0.2,
            wf_score,
            "2026-03-13T00:00:00+00:00",
        ),
    )


def test_validate_storage_reports_legacy_payloads(tmp_path):
    artifacts = tmp_path / "artifacts"
    store = ArtifactStore("exp_storage", base_dir=artifacts)
    run_id = "20260313_010000"
    run_dir = store.init_run(run_id)
    (run_dir / "run_meta.json").write_text(json.dumps({"run_id": run_id, "n_combos": 1}), encoding="utf-8")
    (artifacts / "scheduler_queue.json").write_text(
        json.dumps({"version": 1, "next_seq": 1, "items": [], "updated_utc": ""}),
        encoding="utf-8",
    )
    (artifacts / "paper_positions.json").write_text(
        json.dumps(
            [
                {
                    "signal_id": "signal::exp_storage",
                    "experiment_id": "exp_storage",
                    "open_ts": "2026-03-13T00:00:00Z",
                    "open_price": 1.0,
                    "close_ts": None,
                    "close_price": None,
                    "pnl_pct": None,
                    "status": "open",
                }
            ]
        ),
        encoding="utf-8",
    )
    (artifacts / "signal_schedule_state.json").write_text(
        json.dumps(
            {
                "tracked_experiment_ids": ["exp_storage"],
                "last_experiment_id": "exp_storage",
                "last_export_ts": "2026-03-13T00:00:00Z",
                "schedule_interval_seconds": 3600,
                "top_n": 1,
            }
        ),
        encoding="utf-8",
    )

    report = validate_storage(artifacts)

    assert report["ok"] is True
    assert report["needs_migration"] is True
    assert report["summary"]["run_meta_legacy_files"] == 1
    assert report["components"]["run_meta"]["status"] == "warn"
    assert report["components"]["scheduler_queue"]["status"] == "warn"
    assert report["components"]["paper_positions"]["status"] == "warn"
    assert report["components"]["signal_scheduler"]["status"] == "warn"


def test_migrate_storage_normalizes_legacy_payloads(tmp_path):
    artifacts = tmp_path / "artifacts"
    store = ArtifactStore("exp_storage", base_dir=artifacts)
    run_id = "20260313_020000"
    run_dir = store.init_run(run_id)
    (run_dir / "run_meta.json").write_text(json.dumps({"run_id": run_id, "n_combos": 1}), encoding="utf-8")
    (artifacts / "scheduler_queue.json").write_text(
        json.dumps({"version": 1, "next_seq": 1, "items": [], "updated_utc": ""}),
        encoding="utf-8",
    )
    (artifacts / "paper_positions.json").write_text(
        json.dumps(
            [
                {
                    "signal_id": "signal::exp_storage",
                    "experiment_id": "exp_storage",
                    "open_ts": "2026-03-13T00:00:00Z",
                    "open_price": 1.0,
                    "close_ts": None,
                    "close_price": None,
                    "pnl_pct": None,
                    "status": "open",
                }
            ]
        ),
        encoding="utf-8",
    )
    (artifacts / "signal_schedule_state.json").write_text(
        json.dumps(
            {
                "tracked_experiment_ids": ["exp_storage"],
                "last_experiment_id": "exp_storage",
                "last_export_ts": "2026-03-13T00:00:00Z",
                "schedule_interval_seconds": 3600,
                "top_n": 1,
            }
        ),
        encoding="utf-8",
    )

    payload = migrate_storage(artifacts, dry_run=False)

    assert payload["ok"] is True
    assert payload["changed_files"] == 4
    assert store.read_run_meta(run_id)["schema_version"] == RUN_META_SCHEMA_VERSION
    queue_state = json.loads((artifacts / "scheduler_queue.json").read_text(encoding="utf-8"))
    assert queue_state["schema_version"] == SCHEDULER_QUEUE_SCHEMA_VERSION
    paper_state = json.loads((artifacts / "paper_positions.json").read_text(encoding="utf-8"))
    assert paper_state["schema_version"] == PAPER_POSITIONS_SCHEMA_VERSION
    assert isinstance(paper_state["positions"], list)
    signal_state = json.loads((artifacts / "signal_schedule_state.json").read_text(encoding="utf-8"))
    assert signal_state["schema_version"] == SIGNAL_SCHEDULE_STATE_SCHEMA_VERSION
    assert payload["post_validation"]["needs_migration"] is False


def test_rebuild_analytics_recreates_duckdb_from_run_artifacts(tmp_path):
    artifacts = tmp_path / "artifacts"
    store = ArtifactStore("exp_rebuild", base_dir=artifacts)
    run_id = "20260313_030000"
    conn = store.init_results_db(run_id)
    try:
        _insert_combo_row(conn, combo_id="combo_1", experiment_id="exp_rebuild", run_id=run_id, wf_score=0.7)
        conn.commit()
    finally:
        conn.close()

    payload = rebuild_analytics(artifacts)

    assert payload["ok"] is True
    assert payload["runs_imported"] == 1
    assert payload["experiments_imported"] == 1
    assert payload["combos_imported"] == 1
    assert payload["schema_version"] == ANALYTICS_STORE_SCHEMA_VERSION

    analytics = AnalyticsStore(artifacts / "analytics.duckdb")
    growth = analytics.query_analytics_growth()
    assert growth["total_runs"] == 1
    assert growth["total_combos"] == 1
