import json

import pandas as pd
import pytest

from autowfo.analytics import AnalyticsStore
from autowfo.artifact_store import ArtifactStore
from autowfo.run_workspace import build_run_workspace
from autowfo.storage_contract import (
    ANALYTICS_STORE_SCHEMA_VERSION,
    PAPER_POSITIONS_SCHEMA_VERSION,
    RUN_META_SCHEMA_VERSION,
    SCHEDULER_QUEUE_SCHEMA_VERSION,
    SIGNAL_SCHEDULE_STATE_SCHEMA_VERSION,
)
from autowfo.storage_ops import (
    migrate_storage,
    purge_legacy_outputs,
    rebuild_analytics,
    rebuild_shared_views,
    validate_storage,
)


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
    (artifacts / "leaderboard.csv").write_text("run_id\nlegacy\n", encoding="utf-8")

    report = validate_storage(artifacts)

    assert report["ok"] is True
    assert report["needs_migration"] is True
    assert report["summary"]["run_meta_legacy_files"] == 1
    assert report["components"]["run_meta"]["status"] == "warn"
    assert report["components"]["scheduler_queue"]["status"] == "warn"
    assert report["components"]["paper_positions"]["status"] == "warn"
    assert report["components"]["signal_scheduler"]["status"] == "warn"
    assert report["components"]["shared_views"]["status"] == "warn"
    assert report["summary"]["trusted_runs"] == 0


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


def test_rebuild_shared_views_recreates_root_compatibility_outputs(tmp_path):
    artifacts = tmp_path / "artifacts"
    latest_run_id = "20260314_020000"
    runs = [
        ("20260314_010000", "2026-03-14T01:00:00Z", "ETH/BTC"),
        (latest_run_id, "2026-03-14T02:00:00Z", "BNB/BTC"),
    ]

    for run_id, timestamp_utc, symbol in runs:
        workspace = build_run_workspace(tmp_path, run_id)
        workspace.ensure_directories()
        pd.DataFrame(
            [{"timeframe": "1h", "symbol": symbol, "avg_total_return_pct": 1.0}]
        ).to_csv(workspace.combo_summary_path, index=False)
        pd.DataFrame(
            [{"timeframe": "1h", "symbol": symbol, "total_return_pct": 1.0}]
        ).to_csv(workspace.symbol_summary_path, index=False)
        pd.DataFrame(
            [
                {
                    "run_id": run_id,
                    "timestamp_utc": timestamp_utc,
                    "timeframe": "1h",
                    "data_days": 30,
                    "avg_total_return_pct": 1.0,
                    "oos_avg_total_return_pct": 0.5,
                    "report_file": f"btc_regime_{symbol.replace('/', '-')}.html",
                }
            ]
        ).to_csv(workspace.leaderboard_path, index=False)
        metadata = {
            "run_id": run_id,
            "timestamp_utc": timestamp_utc,
            "search_mode": "combo",
            "config_sha256": f"cfg-{run_id}",
            "data_fingerprint": f"fp-{run_id}",
            "trade_symbols": [symbol],
            "timeframes": [{"timeframe": "1h", "days": 30}],
        }
        workspace.run_metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        workspace.run_metadata_run_path.write_text(json.dumps(metadata), encoding="utf-8")
        workspace.top10_path.write_text("timeframe,symbol\n1h," + symbol + "\n", encoding="utf-8")
        (workspace.reports_dir / f"btc_regime_{symbol.replace('/', '-')}.html").write_text(
            "<html>latest</html>",
            encoding="utf-8",
        )
        (workspace.reports_dir / f"btc_regime_{symbol.replace('/', '-')}_{run_id}.html").write_text(
            "<html>run</html>",
            encoding="utf-8",
        )

    payload = rebuild_shared_views(artifacts)

    assert payload["ok"] is True
    assert payload["trusted_runs"] == 2
    assert payload["registry_runs"] == 2
    assert payload["leaderboard_rows"] == 2
    assert payload["combo_rows"] == 2
    assert payload["symbol_rows"] == 2

    registry_payload = json.loads((artifacts / "run_registry.json").read_text(encoding="utf-8"))
    assert [row["run_id"] for row in registry_payload["runs"]] == [latest_run_id, "20260314_010000"]
    assert (artifacts / "leaderboard.csv").exists()
    assert (artifacts / "param_sweep_combo_summary.csv").exists()
    assert (artifacts / "param_sweep_symbol_summary.csv").exists()
    assert (artifacts / "run_metadata.json").exists()
    assert (artifacts / f"run_metadata_{latest_run_id}.json").exists()
    assert (artifacts / f"param_sweep_top10_{latest_run_id}.csv").exists()
    assert (artifacts / "shared_views_manifest.json").exists()

    report = validate_storage(artifacts)
    assert report["components"]["shared_views"]["status"] == "ok"
    assert report["summary"]["trusted_runs"] == 2


def test_rebuild_shared_views_skips_inconsistent_run_roots(tmp_path):
    artifacts = tmp_path / "artifacts"

    trusted_workspace = build_run_workspace(tmp_path, "20260314_030000")
    trusted_workspace.ensure_directories()
    pd.DataFrame([{"timeframe": "1h", "symbol": "ETH/BTC", "avg_total_return_pct": 1.0}]).to_csv(
        trusted_workspace.combo_summary_path, index=False
    )
    pd.DataFrame([{"timeframe": "1h", "symbol": "ETH/BTC", "total_return_pct": 1.0}]).to_csv(
        trusted_workspace.symbol_summary_path, index=False
    )
    pd.DataFrame(
        [
            {
                "run_id": "20260314_030000",
                "timestamp_utc": "2026-03-14T03:00:00Z",
                "timeframe": "1h",
                "data_days": 30,
                "avg_total_return_pct": 1.0,
                "oos_avg_total_return_pct": 0.5,
                "report_file": "btc_regime_ETH-BTC.html",
            }
        ]
    ).to_csv(trusted_workspace.leaderboard_path, index=False)
    trusted_meta = {
        "run_id": "20260314_030000",
        "timestamp_utc": "2026-03-14T03:00:00Z",
        "search_mode": "combo",
        "config_sha256": "cfg-20260314_030000",
        "data_fingerprint": "fp-20260314_030000",
        "trade_symbols": ["ETH/BTC"],
        "timeframes": [{"timeframe": "1h", "days": 30}],
    }
    trusted_workspace.run_metadata_path.write_text(json.dumps(trusted_meta), encoding="utf-8")
    trusted_workspace.run_metadata_run_path.write_text(json.dumps(trusted_meta), encoding="utf-8")
    trusted_workspace.top10_path.write_text("timeframe,symbol\n1h,ETH/BTC\n", encoding="utf-8")
    (trusted_workspace.reports_dir / "btc_regime_ETH-BTC.html").write_text("<html>trusted</html>", encoding="utf-8")

    invalid_workspace = build_run_workspace(tmp_path, "20260314_040000")
    invalid_workspace.ensure_directories()
    invalid_meta = {
        "run_id": "WRONG_RUN_ID",
        "timestamp_utc": "2026-03-14T04:00:00Z",
        "trade_symbols": ["BNB/BTC"],
        "timeframes": [{"timeframe": "1h", "days": 30}],
    }
    invalid_workspace.run_metadata_path.write_text(json.dumps(invalid_meta), encoding="utf-8")
    invalid_workspace.run_metadata_run_path.write_text(json.dumps(invalid_meta), encoding="utf-8")
    pd.DataFrame([{"run_id": "20260314_040000", "timestamp_utc": "2026-03-14T04:00:00Z"}]).to_csv(
        invalid_workspace.leaderboard_path, index=False
    )
    invalid_workspace.top10_path.write_text("timeframe,symbol\n1h,BNB/BTC\n", encoding="utf-8")

    payload = rebuild_shared_views(artifacts)

    assert payload["ok"] is True
    assert payload["trusted_runs"] == 1
    assert payload["skipped_runs"] >= 1
    manifest = json.loads((artifacts / "shared_views_manifest.json").read_text(encoding="utf-8"))
    assert manifest["trusted_runs"] == ["20260314_030000"]
    registry_payload = json.loads((artifacts / "run_registry.json").read_text(encoding="utf-8"))
    assert [row["run_id"] for row in registry_payload["runs"]] == ["20260314_030000"]


def test_rebuild_shared_views_ignores_legacy_isolated_pass_layout(tmp_path):
    artifacts = tmp_path / "artifacts"
    run_root = artifacts / "runs" / "20260314_060000"
    combo_root = run_root / "combo"
    combo_root.mkdir(parents=True, exist_ok=True)

    (run_root / "manifest.json").write_text(
        json.dumps(
            {
                "run_label": "20260314_060000",
                "passes": [{"mode": "combo", "run_id": "20260314_060013"}],
            }
        ),
        encoding="utf-8",
    )
    pd.DataFrame([{"timeframe": "1h", "symbol": "ETH/BTC", "avg_total_return_pct": 1.0}]).to_csv(
        combo_root / "param_sweep_combo_summary.csv", index=False
    )
    pd.DataFrame([{"timeframe": "1h", "symbol": "ETH/BTC", "total_return_pct": 1.0}]).to_csv(
        combo_root / "param_sweep_symbol_summary.csv", index=False
    )
    pd.DataFrame(
        [
            {
                "run_id": "20260314_060013",
                "timestamp_utc": "2026-03-14T06:00:13Z",
                "timeframe": "1h",
                "data_days": 30,
                "avg_total_return_pct": 1.0,
                "oos_avg_total_return_pct": 0.5,
                "report_file": "btc_regime_ETH-BTC.html",
            }
        ]
    ).to_csv(combo_root / "leaderboard.csv", index=False)
    combo_meta = {
        "run_id": "20260314_060013",
        "timestamp_utc": "2026-03-14T06:00:13Z",
        "search_mode": "combo",
        "trade_symbols": ["ETH/BTC"],
        "timeframes": [{"timeframe": "1h", "days": 30}],
    }
    (combo_root / "run_metadata.json").write_text(json.dumps(combo_meta), encoding="utf-8")
    (combo_root / "run_metadata_20260314_060013.json").write_text(json.dumps(combo_meta), encoding="utf-8")
    (combo_root / "param_sweep_top10_20260314_060013.csv").write_text(
        "timeframe,symbol\n1h,ETH/BTC\n",
        encoding="utf-8",
    )
    (combo_root / "btc_regime_ETH-BTC.html").write_text("<html>legacy isolated</html>", encoding="utf-8")

    payload = rebuild_shared_views(artifacts)

    assert payload["ok"] is True
    assert payload["trusted_runs"] == 0
    manifest = json.loads((artifacts / "shared_views_manifest.json").read_text(encoding="utf-8"))
    assert manifest["trusted_runs"] == []
    assert manifest["latest_run_id"] == ""
    registry_payload = json.loads((artifacts / "run_registry.json").read_text(encoding="utf-8"))
    assert registry_payload["runs"] == []
    assert not (artifacts / "param_sweep_top10_20260314_060013.csv").exists()
    assert not (artifacts / "run_metadata_20260314_060013.json").exists()


def test_purge_legacy_outputs_respects_shared_view_manifest_and_quarantines(tmp_path):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    protected = artifacts / "leaderboard.csv"
    protected.write_text("run_id\nr1\n", encoding="utf-8")
    legacy_top10 = artifacts / "param_sweep_top10_legacy.csv"
    legacy_top10.write_text("timeframe\n1h\n", encoding="utf-8")
    legacy_report = artifacts / "btc_regime_ETH-BTC_legacy.html"
    legacy_report.write_text("<html>legacy</html>", encoding="utf-8")
    legacy_cross_run = artifacts / "cross_run_report.json"
    legacy_cross_run.write_text("{}", encoding="utf-8")
    (artifacts / "shared_views_manifest.json").write_text(
        json.dumps({"protected_files": [str(protected)]}),
        encoding="utf-8",
    )

    dry_run = purge_legacy_outputs(artifacts, dry_run=True)
    assert dry_run["candidates"] == 3
    assert protected.exists()
    assert legacy_top10.exists()
    assert legacy_report.exists()
    assert legacy_cross_run.exists()

    payload = purge_legacy_outputs(artifacts, dry_run=False)

    assert payload["ok"] is True
    assert payload["candidates"] == 3
    assert protected.exists()
    assert not legacy_top10.exists()
    assert not legacy_report.exists()
    assert not legacy_cross_run.exists()
    quarantine_dir = tmp_path / "artifacts_legacy_deleted"
    assert (quarantine_dir / legacy_top10.name).exists()
    assert (quarantine_dir / legacy_report.name).exists()
    assert (quarantine_dir / legacy_cross_run.name).exists()
