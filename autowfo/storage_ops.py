"""Operator-facing storage validation, migration, and rebuild tooling."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from autowfo.analytics import AnalyticsStore, duckdb as analytics_duckdb
from autowfo.artifact_store import ArtifactStore
from autowfo.paper_position import PAPER_POSITIONS_SCHEMA_VERSION, PaperPositionStore
from autowfo import registry as autowfo_registry
from autowfo.scheduler import ExperimentQueue, SchedulerConfig
from autowfo.signal_scheduler import SIGNAL_SCHEDULE_STATE_SCHEMA_VERSION, SignalScheduler
from autowfo.storage_contract import (
    ANALYTICS_STORE_SCHEMA_VERSION,
    RUN_META_SCHEMA_VERSION,
    SCHEDULER_QUEUE_SCHEMA_VERSION,
)


def _read_json(path: Path) -> tuple[Any, str]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig")), ""
    except Exception as exc:
        return None, str(exc)


def _severity_rank(level: str) -> int:
    value = str(level or "").strip().lower()
    if value == "error":
        return 2
    if value == "warn":
        return 1
    return 0


def _component_status(issues: list[dict]) -> str:
    max_rank = 0
    for row in issues:
        max_rank = max(max_rank, _severity_rank(row.get("severity", "")))
    if max_rank >= 2:
        return "error"
    if max_rank == 1:
        return "warn"
    return "ok"


def _issue(component: str, severity: str, message: str, path: Path | None = None) -> dict:
    payload = {
        "component": str(component),
        "severity": str(severity),
        "message": str(message),
    }
    if path is not None:
        payload["path"] = str(path)
    return payload


def _inspect_run_meta(artifacts_dir: Path) -> dict:
    issues: list[dict] = []
    runs_root = artifacts_dir / "experiments"
    total = 0
    versioned = 0
    legacy = 0
    invalid = 0

    for meta_path in sorted(runs_root.glob("*/runs/*/run_meta.json")):
        total += 1
        payload, error = _read_json(meta_path)
        if error:
            invalid += 1
            issues.append(_issue("run_meta", "error", f"unreadable run_meta.json: {error}", meta_path))
            continue
        if not isinstance(payload, dict):
            invalid += 1
            issues.append(_issue("run_meta", "error", "run_meta.json must decode to object", meta_path))
            continue
        schema_version = str(payload.get("schema_version") or "").strip()
        if not schema_version:
            legacy += 1
            issues.append(_issue("run_meta", "warn", "legacy run_meta without schema_version", meta_path))
        elif schema_version != RUN_META_SCHEMA_VERSION:
            issues.append(
                _issue(
                    "run_meta",
                    "warn",
                    f"unexpected run_meta schema_version '{schema_version}'",
                    meta_path,
                )
            )
        else:
            versioned += 1

    return {
        "path": str(runs_root),
        "total_files": total,
        "versioned_files": versioned,
        "legacy_files": legacy,
        "invalid_files": invalid,
        "issues": issues,
        "status": _component_status(issues),
    }


def _inspect_scheduler_queue(artifacts_dir: Path) -> dict:
    queue_path = artifacts_dir / "scheduler_queue.json"
    if not queue_path.exists():
        return {
            "path": str(queue_path),
            "exists": False,
            "items": 0,
            "schema_version": "",
            "issues": [],
            "status": "ok",
        }
    payload, error = _read_json(queue_path)
    issues: list[dict] = []
    if error:
        issues.append(_issue("scheduler_queue", "error", f"unreadable scheduler queue: {error}", queue_path))
        return {
            "path": str(queue_path),
            "exists": True,
            "items": 0,
            "schema_version": "",
            "issues": issues,
            "status": "error",
        }
    if not isinstance(payload, dict):
        issues.append(_issue("scheduler_queue", "error", "scheduler queue must decode to object", queue_path))
        return {
            "path": str(queue_path),
            "exists": True,
            "items": 0,
            "schema_version": "",
            "issues": issues,
            "status": "error",
        }
    items = payload.get("items", [])
    schema_version = str(payload.get("schema_version") or "").strip()
    if not schema_version:
        issues.append(_issue("scheduler_queue", "warn", "legacy scheduler queue without schema_version", queue_path))
    elif schema_version != SCHEDULER_QUEUE_SCHEMA_VERSION:
        issues.append(
            _issue(
                "scheduler_queue",
                "warn",
                f"unexpected scheduler queue schema_version '{schema_version}'",
                queue_path,
            )
        )
    return {
        "path": str(queue_path),
        "exists": True,
        "items": len(items) if isinstance(items, list) else 0,
        "schema_version": schema_version,
        "issues": issues,
        "status": _component_status(issues),
    }


def _inspect_paper_positions(artifacts_dir: Path) -> dict:
    positions_path = artifacts_dir / "paper_positions.json"
    if not positions_path.exists():
        return {
            "path": str(positions_path),
            "exists": False,
            "total_positions": 0,
            "open_positions": 0,
            "schema_version": "",
            "issues": [],
            "status": "ok",
        }
    payload, error = _read_json(positions_path)
    issues: list[dict] = []
    if error:
        issues.append(_issue("paper_positions", "error", f"unreadable paper positions: {error}", positions_path))
        return {
            "path": str(positions_path),
            "exists": True,
            "total_positions": 0,
            "open_positions": 0,
            "schema_version": "",
            "issues": issues,
            "status": "error",
        }
    if isinstance(payload, list):
        schema_version = ""
        issues.append(_issue("paper_positions", "warn", "legacy paper positions list payload", positions_path))
    elif isinstance(payload, dict):
        schema_version = str(payload.get("schema_version") or "").strip()
        if not schema_version:
            issues.append(_issue("paper_positions", "warn", "paper positions missing schema_version", positions_path))
        elif schema_version != PAPER_POSITIONS_SCHEMA_VERSION:
            issues.append(
                _issue(
                    "paper_positions",
                    "warn",
                    f"unexpected paper positions schema_version '{schema_version}'",
                    positions_path,
                )
            )
    else:
        issues.append(_issue("paper_positions", "error", "paper positions must decode to list or object", positions_path))
        return {
            "path": str(positions_path),
            "exists": True,
            "total_positions": 0,
            "open_positions": 0,
            "schema_version": "",
            "issues": issues,
            "status": "error",
        }

    store = PaperPositionStore(positions_path)
    rows = store.list_positions()
    open_rows = [row for row in rows if str(row.get("status") or "").strip() == "open"]
    return {
        "path": str(positions_path),
        "exists": True,
        "total_positions": len(rows),
        "open_positions": len(open_rows),
        "schema_version": schema_version if isinstance(payload, dict) else "",
        "issues": issues,
        "status": _component_status(issues),
    }


def _inspect_signal_scheduler_state(artifacts_dir: Path) -> dict:
    state_path = artifacts_dir / "signal_schedule_state.json"
    if not state_path.exists():
        return {
            "path": str(state_path),
            "exists": False,
            "tracked_experiment_ids": 0,
            "schema_version": "",
            "issues": [],
            "status": "ok",
        }
    payload, error = _read_json(state_path)
    issues: list[dict] = []
    if error:
        issues.append(_issue("signal_scheduler", "error", f"unreadable signal scheduler state: {error}", state_path))
        return {
            "path": str(state_path),
            "exists": True,
            "tracked_experiment_ids": 0,
            "schema_version": "",
            "issues": issues,
            "status": "error",
        }
    if not isinstance(payload, dict):
        issues.append(_issue("signal_scheduler", "error", "signal scheduler state must decode to object", state_path))
        return {
            "path": str(state_path),
            "exists": True,
            "tracked_experiment_ids": 0,
            "schema_version": "",
            "issues": issues,
            "status": "error",
        }
    tracked = payload.get("tracked_experiment_ids")
    if not isinstance(tracked, list):
        tracked = []
    schema_version = str(payload.get("schema_version") or "").strip()
    if not schema_version:
        issues.append(_issue("signal_scheduler", "warn", "legacy signal scheduler state without schema_version", state_path))
    elif schema_version != SIGNAL_SCHEDULE_STATE_SCHEMA_VERSION:
        issues.append(
            _issue(
                "signal_scheduler",
                "warn",
                f"unexpected signal scheduler schema_version '{schema_version}'",
                state_path,
            )
        )
    return {
        "path": str(state_path),
        "exists": True,
        "tracked_experiment_ids": len([v for v in tracked if str(v).strip()]),
        "schema_version": schema_version,
        "issues": issues,
        "status": _component_status(issues),
    }


def _inspect_analytics_store(artifacts_dir: Path) -> dict:
    db_path = artifacts_dir / "analytics.duckdb"
    if not db_path.exists():
        return {
            "path": str(db_path),
            "exists": False,
            "schema_version": "",
            "total_runs": 0,
            "total_combos": 0,
            "issues": [],
            "status": "ok",
        }
    if analytics_duckdb is None:
        issues = [_issue("analytics", "error", "duckdb package is required to inspect analytics store", db_path)]
        return {
            "path": str(db_path),
            "exists": True,
            "schema_version": "",
            "total_runs": 0,
            "total_combos": 0,
            "issues": issues,
            "status": "error",
        }

    conn = analytics_duckdb.connect(str(db_path))
    issues: list[dict] = []
    schema_version = ""
    total_runs = 0
    total_combos = 0
    try:
        tables = {str(row[0]) for row in conn.execute("SHOW TABLES").fetchall()}
        if "combo_results" in tables:
            stats = conn.execute(
                "SELECT COUNT(DISTINCT run_id) AS total_runs, COUNT(*) AS total_combos FROM combo_results"
            ).fetchone()
            if stats:
                total_runs = int(stats[0] or 0)
                total_combos = int(stats[1] or 0)
        if "analytics_metadata" not in tables:
            issues.append(_issue("analytics", "warn", "analytics metadata table missing", db_path))
        else:
            row = conn.execute(
                "SELECT meta_value FROM analytics_metadata WHERE meta_key = 'schema_version' LIMIT 1"
            ).fetchone()
            schema_version = str(row[0] or "").strip() if row else ""
            if not schema_version:
                issues.append(_issue("analytics", "warn", "analytics schema_version missing", db_path))
            elif schema_version != ANALYTICS_STORE_SCHEMA_VERSION:
                issues.append(
                    _issue("analytics", "warn", f"unexpected analytics schema_version '{schema_version}'", db_path)
                )
    except Exception as exc:
        issues.append(_issue("analytics", "error", f"analytics inspection failed: {exc}", db_path))
    finally:
        conn.close()

    return {
        "path": str(db_path),
        "exists": True,
        "schema_version": schema_version,
        "total_runs": total_runs,
        "total_combos": total_combos,
        "issues": issues,
        "status": _component_status(issues),
    }


def _inspect_shared_views(artifacts_dir: Path) -> dict:
    manifest_path = _shared_views_manifest_path(artifacts_dir)
    issues: list[dict] = []
    protected_files: list[str] = []
    latest_run_id = ""
    trusted_runs = 0
    latest_run_root = None

    payload, error = _read_json(manifest_path) if manifest_path.exists() else (None, "")
    if manifest_path.exists():
        if error or not isinstance(payload, dict):
            issues.append(_issue("shared_views", "error", f"unreadable shared views manifest: {error or 'invalid payload'}", manifest_path))
        else:
            trusted = payload.get("trusted_runs")
            trusted_runs = len(trusted) if isinstance(trusted, list) else 0
            latest_run_id = str(payload.get("latest_run_id") or "").strip()
            latest_run_root = str(payload.get("latest_run_root") or "").strip()
            protected_files = [str(row) for row in payload.get("protected_files", []) if str(row).strip()]
            if latest_run_id:
                candidate = Path(latest_run_root) if latest_run_root else artifacts_dir / "runs" / latest_run_id
                if not candidate.exists():
                    issues.append(
                        _issue(
                            "shared_views",
                            "warn",
                            f"latest trusted run root missing for '{latest_run_id}'",
                            candidate,
                        )
                    )
            missing_protected = [row for row in protected_files if not Path(row).exists()]
            for missing_path in missing_protected:
                issues.append(_issue("shared_views", "warn", "protected shared view missing", Path(missing_path)))
    else:
        legacy_candidates = []
        for pattern in LEGACY_ROOT_PATTERNS:
            legacy_candidates.extend(path for path in artifacts_dir.glob(pattern) if path.is_file())
        legacy_candidates = [path for path in legacy_candidates if path.name != manifest_path.name]
        if legacy_candidates:
            issues.append(
                _issue(
                    "shared_views",
                    "warn",
                    "shared views manifest missing while legacy root outputs still exist",
                    artifacts_dir,
                )
            )

    return {
        "path": str(manifest_path),
        "exists": manifest_path.exists(),
        "trusted_runs": int(trusted_runs),
        "latest_run_id": latest_run_id,
        "latest_run_root": latest_run_root or "",
        "protected_files": int(len(protected_files)),
        "issues": issues,
        "status": _component_status(issues),
    }


def validate_storage(artifacts_dir: str | Path = "artifacts") -> dict:
    artifacts = Path(artifacts_dir)
    components = {
        "run_meta": _inspect_run_meta(artifacts),
        "scheduler_queue": _inspect_scheduler_queue(artifacts),
        "paper_positions": _inspect_paper_positions(artifacts),
        "signal_scheduler": _inspect_signal_scheduler_state(artifacts),
        "analytics": _inspect_analytics_store(artifacts),
        "shared_views": _inspect_shared_views(artifacts),
    }
    issues = []
    warn_count = 0
    error_count = 0
    for component in components.values():
        component_issues = component.get("issues", [])
        if isinstance(component_issues, list):
            issues.extend(component_issues)
            for row in component_issues:
                severity = str(row.get("severity") or "").strip().lower()
                if severity == "warn":
                    warn_count += 1
                elif severity == "error":
                    error_count += 1

    run_meta = components["run_meta"]
    summary = {
        "experiments_root": str(artifacts / "experiments"),
        "run_meta_files": int(run_meta.get("total_files", 0)),
        "run_meta_legacy_files": int(run_meta.get("legacy_files", 0)),
        "trusted_runs": int(components["shared_views"].get("trusted_runs", 0)),
        "warnings": int(warn_count),
        "errors": int(error_count),
    }
    return {
        "ok": error_count == 0,
        "needs_migration": bool(warn_count > 0),
        "artifacts_dir": str(artifacts),
        "summary": summary,
        "components": components,
        "issues": issues,
    }


def migrate_storage(artifacts_dir: str | Path = "artifacts", dry_run: bool = False) -> dict:
    artifacts = Path(artifacts_dir)
    actions: list[dict] = []
    errors: list[dict] = []

    for meta_path in sorted((artifacts / "experiments").glob("*/runs/*/run_meta.json")):
        payload, error = _read_json(meta_path)
        if error or not isinstance(payload, dict):
            errors.append(_issue("run_meta", "error", f"cannot migrate run_meta: {error or 'invalid payload'}", meta_path))
            continue
        if str(payload.get("schema_version") or "").strip() == RUN_META_SCHEMA_VERSION:
            continue
        experiment_id = meta_path.parents[2].name
        run_id = meta_path.parent.name
        normalized = dict(payload)
        normalized["schema_version"] = RUN_META_SCHEMA_VERSION
        actions.append({"component": "run_meta", "path": str(meta_path), "action": "rewrite"})
        if not dry_run:
            ArtifactStore(experiment_id, base_dir=artifacts).write_run_meta(run_id, normalized)

    queue_path = artifacts / "scheduler_queue.json"
    queue_payload, queue_error = _read_json(queue_path) if queue_path.exists() else (None, "")
    if queue_path.exists():
        if queue_error or not isinstance(queue_payload, dict):
            errors.append(_issue("scheduler_queue", "error", f"cannot migrate queue: {queue_error or 'invalid payload'}", queue_path))
        elif str(queue_payload.get("schema_version") or "").strip() != SCHEDULER_QUEUE_SCHEMA_VERSION:
            actions.append({"component": "scheduler_queue", "path": str(queue_path), "action": "rewrite"})
            if not dry_run:
                queue = ExperimentQueue(queue_path=queue_path, config=SchedulerConfig.from_file(artifacts / "scheduler.json"))
                queue.rewrite_state()

    positions_path = artifacts / "paper_positions.json"
    positions_payload, positions_error = _read_json(positions_path) if positions_path.exists() else (None, "")
    if positions_path.exists():
        if positions_error:
            errors.append(_issue("paper_positions", "error", f"cannot migrate paper positions: {positions_error}", positions_path))
        elif isinstance(positions_payload, list) or (
            isinstance(positions_payload, dict)
            and str(positions_payload.get("schema_version") or "").strip() != PAPER_POSITIONS_SCHEMA_VERSION
        ):
            actions.append({"component": "paper_positions", "path": str(positions_path), "action": "rewrite"})
            if not dry_run:
                PaperPositionStore(positions_path).rewrite_positions()
        elif not isinstance(positions_payload, dict):
            errors.append(_issue("paper_positions", "error", "cannot migrate invalid paper positions payload", positions_path))

    state_path = artifacts / "signal_schedule_state.json"
    state_payload, state_error = _read_json(state_path) if state_path.exists() else (None, "")
    if state_path.exists():
        if state_error or not isinstance(state_payload, dict):
            errors.append(_issue("signal_scheduler", "error", f"cannot migrate signal scheduler state: {state_error or 'invalid payload'}", state_path))
        elif str(state_payload.get("schema_version") or "").strip() != SIGNAL_SCHEDULE_STATE_SCHEMA_VERSION:
            actions.append({"component": "signal_scheduler", "path": str(state_path), "action": "rewrite"})
            if not dry_run:
                scheduler = SignalScheduler(analytics_store=object(), state_path=state_path)
                scheduler.write_state(scheduler.read_state())

    analytics_info = _inspect_analytics_store(artifacts)
    analytics_path = artifacts / "analytics.duckdb"
    if analytics_path.exists() and analytics_info.get("schema_version") != ANALYTICS_STORE_SCHEMA_VERSION:
        actions.append({"component": "analytics", "path": str(analytics_path), "action": "ensure_metadata"})
        if not dry_run:
            AnalyticsStore(analytics_path).get_metadata()

    post_validation = validate_storage(artifacts)
    return {
        "ok": not errors,
        "dry_run": bool(dry_run),
        "artifacts_dir": str(artifacts),
        "actions": actions,
        "changed_files": len(actions) if not dry_run else 0,
        "errors": errors,
        "post_validation": post_validation,
    }


def rebuild_analytics(artifacts_dir: str | Path = "artifacts") -> dict:
    artifacts = Path(artifacts_dir)
    db_path = artifacts / "analytics.duckdb"
    if db_path.exists():
        db_path.unlink()

    analytics_store = AnalyticsStore(db_path)
    experiments_root = artifacts / "experiments"
    runs_imported = 0
    combos_imported = 0
    experiments_imported: set[str] = set()

    for experiment_dir in sorted(experiments_root.iterdir() if experiments_root.exists() else []):
        if not experiment_dir.is_dir():
            continue
        experiment_id = experiment_dir.name
        store = ArtifactStore(experiment_id, base_dir=artifacts)
        for run_id in store.list_runs():
            if not store.get_run_db_path(run_id).exists():
                continue
            combos_imported += int(analytics_store.update_from_run(experiment_id, run_id, store))
            runs_imported += 1
            experiments_imported.add(experiment_id)

    metadata = analytics_store.get_metadata()
    return {
        "ok": True,
        "artifacts_dir": str(artifacts),
        "db_path": str(db_path),
        "runs_imported": runs_imported,
        "experiments_imported": len(experiments_imported),
        "combos_imported": combos_imported,
        "schema_version": str(metadata.get("schema_version") or ""),
    }


def _iter_trusted_run_roots(artifacts_dir: Path) -> list[Path]:
    runs_root = artifacts_dir / "runs"
    if not runs_root.exists():
        return []
    return sorted(path for path in runs_root.iterdir() if path.is_dir())


def _read_csv_or_empty(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, low_memory=False)


def _latest_run_key(payload: dict) -> tuple[str, str]:
    return (
        str(payload.get("timestamp_utc") or ""),
        str(payload.get("run_id") or ""),
    )


def _shared_views_manifest_path(artifacts_dir: Path) -> Path:
    return artifacts_dir / "shared_views_manifest.json"


def _iter_trusted_run_payloads(artifacts_dir: Path) -> list[dict]:
    payloads: list[dict] = []
    for run_root in _iter_trusted_run_roots(artifacts_dir):
        run_id = run_root.name

        # Phase 44 layout: artifacts/runs/{run_id}/{results,metadata,reports}
        #
        # Pre-Phase 44 isolated pass trees under artifacts/runs/* may contain
        # copied shared-root summaries from the old evidence model. They are
        # no longer treated as trusted inputs for shared-view rebuilds.
        new_layout = {
            "run_id": run_id,
            "run_root": run_root,
            "metadata_path": run_root / "metadata" / "run_metadata.json",
            "metadata_run_path": run_root / "metadata" / f"run_metadata_{run_id}.json",
            "combo_path": run_root / "results" / "param_sweep_combo_summary.csv",
            "symbol_path": run_root / "results" / "param_sweep_symbol_summary.csv",
            "leaderboard_path": run_root / "results" / "leaderboard.csv",
            "top10_path": run_root / "results" / f"param_sweep_top10_{run_id}.csv",
            "reports_dir": run_root / "reports",
        }
        if new_layout["metadata_path"].exists():
            payloads.append(new_layout)
    return payloads


def rebuild_shared_views(artifacts_dir: str | Path = "artifacts") -> dict:
    artifacts = Path(artifacts_dir)
    trusted_runs = []
    issues: list[dict] = []
    combo_frames: list[pd.DataFrame] = []
    symbol_frames: list[pd.DataFrame] = []
    leaderboard_frames: list[pd.DataFrame] = []
    run_entries: list[dict] = []

    for candidate in _iter_trusted_run_payloads(artifacts):
        run_id = str(candidate.get("run_id") or "").strip()
        run_root = Path(candidate["run_root"])
        reports_dir = Path(candidate["reports_dir"])
        metadata_path = Path(candidate["metadata_path"])
        metadata_run_path = Path(candidate["metadata_run_path"])
        combo_path = Path(candidate["combo_path"])
        symbol_path = Path(candidate["symbol_path"])
        leaderboard_path = Path(candidate["leaderboard_path"])
        top10_path = Path(candidate["top10_path"])

        metadata, error = _read_json(metadata_path)
        if error or not isinstance(metadata, dict):
            issues.append(_issue("shared_views", "warn", f"skip {run_id}: unreadable run metadata", metadata_path))
            continue
        if str(metadata.get("run_id") or "") != run_id:
            issues.append(_issue("shared_views", "warn", f"skip {run_id}: metadata run_id mismatch", metadata_path))
            continue
        if not combo_path.exists() or not symbol_path.exists() or not leaderboard_path.exists() or not top10_path.exists():
            issues.append(_issue("shared_views", "warn", f"skip {run_id}: missing required trusted run outputs", run_root))
            continue

        leaderboard_df = _read_csv_or_empty(leaderboard_path)
        if leaderboard_df.empty:
            issues.append(_issue("shared_views", "warn", f"skip {run_id}: empty leaderboard", leaderboard_path))
            continue
        leaderboard_row = leaderboard_df.iloc[-1].to_dict()
        if str(leaderboard_row.get("run_id") or "") != run_id:
            issues.append(_issue("shared_views", "warn", f"skip {run_id}: leaderboard run_id mismatch", leaderboard_path))
            continue

        report_file = str(leaderboard_row.get("report_file") or "").strip()
        if report_file and not (reports_dir / report_file).exists():
            issues.append(_issue("shared_views", "warn", f"skip {run_id}: report file missing", reports_dir / report_file))
            continue

        combo_df = _read_csv_or_empty(combo_path)
        symbol_df = _read_csv_or_empty(symbol_path)
        combo_frames.append(combo_df)
        symbol_frames.append(symbol_df)
        leaderboard_frames.append(leaderboard_df)
        run_entries.append(autowfo_registry._build_run_entry(metadata, leaderboard_row))
        trusted_runs.append(
            {
                "run_id": run_id,
                "timestamp_utc": str(metadata.get("timestamp_utc") or ""),
                "run_root": str(run_root),
                "metadata_path": str(metadata_path),
                "metadata_run_path": str(metadata_run_path),
                "combo_path": str(combo_path),
                "symbol_path": str(symbol_path),
                "leaderboard_path": str(leaderboard_path),
                "top10_path": str(top10_path),
                "report_file": report_file,
            }
        )

    combo_df = pd.concat(combo_frames, ignore_index=True) if combo_frames else pd.DataFrame()
    symbol_df = pd.concat(symbol_frames, ignore_index=True) if symbol_frames else pd.DataFrame()
    leaderboard_df = pd.concat(leaderboard_frames, ignore_index=True) if leaderboard_frames else pd.DataFrame()
    if not leaderboard_df.empty and "timestamp_utc" in leaderboard_df.columns:
        leaderboard_df = leaderboard_df.sort_values("timestamp_utc", ascending=False, kind="stable").reset_index(drop=True)
    run_entries = sorted(run_entries, key=_latest_run_key, reverse=True)
    registry_payload = {
        "updated_utc": run_entries[0]["timestamp_utc"] if run_entries else "",
        "runs": run_entries,
        "coverage": autowfo_registry._build_coverage_map(symbol_df, run_entries),
    }

    combo_out = artifacts / "param_sweep_combo_summary.csv"
    symbol_out = artifacts / "param_sweep_symbol_summary.csv"
    leaderboard_out = artifacts / "leaderboard.csv"
    registry_out = artifacts / "run_registry.json"
    manifest_out = _shared_views_manifest_path(artifacts)
    combo_df.to_csv(combo_out, index=False)
    symbol_df.to_csv(symbol_out, index=False)
    leaderboard_df.to_csv(leaderboard_out, index=False)
    registry_out.write_text(json.dumps(registry_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    latest_payload = max(trusted_runs, key=_latest_run_key) if trusted_runs else None
    copied_latest: list[str] = []
    if latest_payload:
        latest_run_root = Path(latest_payload["run_root"])
        latest_run_id = latest_payload["run_id"]
        latest_meta_src = Path(latest_payload["metadata_path"])
        latest_meta_run_src = Path(latest_payload.get("metadata_run_path") or "")
        latest_top10_src = Path(latest_payload["top10_path"])
        latest_report_src = latest_run_root / str(latest_payload.get("report_file") or "")
        latest_report_run_src = None
        if latest_report_src.name:
            latest_report_run_src = latest_run_root / latest_report_src.name.replace(".html", f"_{latest_run_id}.html")

        compat_files = [
            (latest_meta_src, artifacts / "run_metadata.json"),
            (latest_meta_run_src, artifacts / f"run_metadata_{latest_run_id}.json"),
            (latest_top10_src, artifacts / f"param_sweep_top10_{latest_run_id}.csv"),
        ]
        if latest_report_src and latest_report_src.exists():
            compat_files.append((latest_report_src, artifacts / latest_report_src.name))
        if latest_report_run_src and latest_report_run_src.exists():
            compat_files.append((latest_report_run_src, artifacts / latest_report_run_src.name))
        for src, dest in compat_files:
            if not src.exists():
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            copied_latest.append(str(dest))

    protected_files = [
        str(combo_out),
        str(symbol_out),
        str(leaderboard_out),
        str(registry_out),
        *copied_latest,
    ]
    manifest_payload = {
        "generated_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "trusted_runs": [row["run_id"] for row in trusted_runs],
        "latest_run_id": latest_payload["run_id"] if latest_payload else "",
        "latest_run_root": latest_payload["run_root"] if latest_payload else "",
        "protected_files": protected_files,
    }
    manifest_out.write_text(json.dumps(manifest_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "ok": True,
        "artifacts_dir": str(artifacts),
        "trusted_runs": len(trusted_runs),
        "skipped_runs": len(issues),
        "combo_rows": int(len(combo_df)),
        "symbol_rows": int(len(symbol_df)),
        "leaderboard_rows": int(len(leaderboard_df)),
        "registry_runs": int(len(run_entries)),
        "issues": issues,
        "outputs": {
            "combo_summary": str(combo_out),
            "per_symbol_summary": str(symbol_out),
            "leaderboard": str(leaderboard_out),
            "run_registry": str(registry_out),
            "manifest": str(manifest_out),
            "compatibility_files": copied_latest,
        },
    }


LEGACY_ROOT_PATTERNS = (
    "param_sweep_combo_summary*.csv",
    "param_sweep_symbol_summary*.csv",
    "param_sweep_top10_*.csv",
    "leaderboard.csv",
    "run_registry.json",
    "run_metadata*.json",
    "results.db",
    "run_status.json",
    "run_status.html",
    "run_control.json",
    "btc_regime_*.html",
    "cross_run_report.html",
    "cross_run_report.json",
)


def _load_protected_shared_views(artifacts_dir: Path) -> set[Path]:
    manifest_path = _shared_views_manifest_path(artifacts_dir)
    payload, error = _read_json(manifest_path) if manifest_path.exists() else ({}, "")
    if error or not isinstance(payload, dict):
        return set()
    protected = set()
    for raw in payload.get("protected_files") or []:
        try:
            protected.add(Path(raw).resolve())
        except Exception:
            continue
    return protected


def _unique_quarantine_path(quarantine_dir: Path, source: Path) -> Path:
    candidate = quarantine_dir / source.name
    if not candidate.exists():
        return candidate
    stem = source.stem
    suffix = source.suffix
    index = 1
    while True:
        candidate = quarantine_dir / f"{stem}.{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def purge_legacy_outputs(
    artifacts_dir: str | Path = "artifacts",
    *,
    dry_run: bool = True,
    delete: bool = False,
    quarantine_dir: str | Path | None = None,
) -> dict:
    artifacts = Path(artifacts_dir)
    protected = _load_protected_shared_views(artifacts)
    candidates: list[Path] = []
    seen = set()
    for pattern in LEGACY_ROOT_PATTERNS:
        for path in sorted(artifacts.glob(pattern)):
            resolved = path.resolve()
            if path.is_dir() or resolved in protected or resolved in seen:
                continue
            seen.add(resolved)
            candidates.append(path)

    quarantine_root = None
    if quarantine_dir is not None:
        quarantine_root = Path(quarantine_dir)
    elif not delete:
        quarantine_root = artifacts.parent / "artifacts_legacy_deleted"

    actions = []
    for path in candidates:
        row = {"path": str(path), "action": "delete" if delete else "quarantine"}
        if quarantine_root is not None and not delete:
            row["destination"] = str(_unique_quarantine_path(quarantine_root, path))
        actions.append(row)

    if not dry_run:
        for row in actions:
            source = Path(row["path"])
            if delete:
                source.unlink(missing_ok=True)
                continue
            destination = Path(row["destination"])
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))

    return {
        "ok": True,
        "dry_run": bool(dry_run),
        "delete": bool(delete),
        "artifacts_dir": str(artifacts),
        "quarantine_dir": str(quarantine_root) if quarantine_root is not None else "",
        "protected_files": sorted(str(path) for path in protected),
        "actions": actions,
        "candidates": len(actions),
    }


def format_validation_report(report: dict) -> str:
    summary = report.get("summary", {}) if isinstance(report, dict) else {}
    lines = [
        f"[doctor] artifacts={report.get('artifacts_dir', '')}",
        f"[doctor] ok={bool(report.get('ok'))} needs_migration={bool(report.get('needs_migration'))} "
        f"warnings={int(summary.get('warnings', 0))} errors={int(summary.get('errors', 0))}",
    ]
    components = report.get("components", {}) if isinstance(report, dict) else {}
    for name, payload in components.items():
        if not isinstance(payload, dict):
            continue
        lines.append(
            f"[doctor] {name} status={payload.get('status', 'ok')} "
            f"schema={payload.get('schema_version', '') or '-'} path={payload.get('path', '')}"
        )
    issues = report.get("issues", []) if isinstance(report, dict) else []
    for row in issues[:20]:
        lines.append(
            f"[doctor] {row.get('severity', 'info').upper()} {row.get('component', 'storage')}: {row.get('message', '')}"
        )
    if len(issues) > 20:
        lines.append(f"[doctor] ... {len(issues) - 20} more issue(s)")
    return "\n".join(lines)
