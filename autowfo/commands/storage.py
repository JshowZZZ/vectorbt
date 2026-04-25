"""Storage operations command handlers and parser wiring."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any


def add_storage_parsers(subparsers: argparse._SubParsersAction[Any], cli_impl: Any) -> None:
    doctor_parser = subparsers.add_parser("doctor", help="Validate AUTOWFO storage health")
    doctor_parser.add_argument("--artifacts-dir", default="artifacts", help="Artifacts root directory")
    doctor_parser.add_argument("--cwd", default=".", help="Working directory")
    doctor_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON payload")
    doctor_parser.set_defaults(handler=cli_impl._cmd_doctor)

    storage_parser = subparsers.add_parser("storage", help="Storage validation, migration, and rebuild tooling")
    storage_subparsers = storage_parser.add_subparsers(dest="storage_command", required=True)

    validate_parser = storage_subparsers.add_parser("validate", help="Validate storage health")
    validate_parser.add_argument("--artifacts-dir", default="artifacts", help="Artifacts root directory")
    validate_parser.add_argument("--cwd", default=".", help="Working directory")
    validate_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON payload")
    validate_parser.set_defaults(handler=cli_impl._cmd_storage_validate)

    migrate_parser = storage_subparsers.add_parser("migrate", help="Normalize storage payloads to current schema versions")
    migrate_parser.add_argument("--artifacts-dir", default="artifacts", help="Artifacts root directory")
    migrate_parser.add_argument("--cwd", default=".", help="Working directory")
    migrate_parser.add_argument("--dry-run", action="store_true", help="Report actions without rewriting files")
    migrate_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON payload")
    migrate_parser.set_defaults(handler=cli_impl._cmd_storage_migrate)

    rebuild_parser = storage_subparsers.add_parser("rebuild-analytics", help="Rebuild analytics.duckdb from experiment runs")
    rebuild_parser.add_argument("--artifacts-dir", default="artifacts", help="Artifacts root directory")
    rebuild_parser.add_argument("--cwd", default=".", help="Working directory")
    rebuild_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON payload")
    rebuild_parser.set_defaults(handler=cli_impl._cmd_storage_rebuild_analytics)

    shared_views_parser = storage_subparsers.add_parser(
        "rebuild-shared-views",
        help="Rebuild shared compatibility views from trusted run roots",
    )
    shared_views_parser.add_argument("--artifacts-dir", default="artifacts", help="Artifacts root directory")
    shared_views_parser.add_argument("--cwd", default=".", help="Working directory")
    shared_views_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON payload")
    shared_views_parser.set_defaults(handler=cli_impl._cmd_storage_rebuild_shared_views)

    purge_parser = storage_subparsers.add_parser(
        "purge-legacy",
        help="Dry-run or quarantine legacy root-level run outputs",
    )
    purge_parser.add_argument("--artifacts-dir", default="artifacts", help="Artifacts root directory")
    purge_parser.add_argument("--cwd", default=".", help="Working directory")
    purge_parser.add_argument("--dry-run", action="store_true", help="Report planned actions without mutating files")
    purge_parser.add_argument("--delete", action="store_true", help="Permanently delete candidates instead of moving them")
    purge_parser.add_argument(
        "--quarantine-dir",
        default="",
        help="Directory used when moving legacy outputs out of the artifacts root",
    )
    purge_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON payload")
    purge_parser.set_defaults(handler=cli_impl._cmd_storage_purge_legacy)

    rescore_parser = storage_subparsers.add_parser(
        "rescore",
        help="Recalculate composite scores and top10 for all trusted runs without re-running search",
    )
    rescore_parser.add_argument("--artifacts-dir", default="artifacts", help="Artifacts root directory")
    rescore_parser.add_argument("--cwd", default=".", help="Working directory")
    rescore_parser.add_argument("--ranking-config", default="", help="Path to ranking config JSON override")
    rescore_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON payload")
    rescore_parser.set_defaults(handler=cli_impl._cmd_storage_rescore)

    compare_parser = storage_subparsers.add_parser(
        "compare-ranking",
        help="Compare a candidate ranking config against trusted runs without re-running search",
    )
    compare_parser.add_argument("--artifacts-dir", default="artifacts", help="Artifacts root directory")
    compare_parser.add_argument("--cwd", default=".", help="Working directory")
    compare_parser.add_argument("--candidate-config", required=True, help="Path to candidate ranking config JSON override")
    compare_parser.add_argument("--baseline-config", default="", help="Optional baseline ranking config JSON override")
    compare_parser.add_argument("--top-n", type=int, default=10, help="Number of ranked rows to compare per run")
    compare_parser.add_argument("--output-json", default="", help="Optional JSON output path")
    compare_parser.add_argument("--output-html", default="", help="Optional HTML output path")
    compare_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON payload")
    compare_parser.set_defaults(handler=cli_impl._cmd_storage_compare_ranking)

    drift_report_parser = storage_subparsers.add_parser(
        "drift-report",
        help="Build execution drift report artifact from frozen AWF-345 protocol inputs",
    )
    drift_report_parser.add_argument("--artifacts-dir", default="artifacts", help="Artifacts root directory")
    drift_report_parser.add_argument("--cwd", default=".", help="Working directory")
    drift_report_parser.add_argument(
        "--protocol-path",
        default="plans/protocols/execution_drift_report_v1.json",
        help="Path to the frozen execution drift report protocol JSON",
    )
    drift_report_parser.add_argument(
        "--output-json",
        default="",
        help="Optional output artifact path (defaults to artifacts/reports/execution_drift_report.json)",
    )
    drift_report_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON payload")
    drift_report_parser.set_defaults(handler=cli_impl._cmd_storage_drift_report)


def _resolve_artifacts_dir(args: argparse.Namespace, cli_impl: Any) -> Path:
    cwd = Path(args.cwd).resolve()
    return cli_impl._resolve_path(cwd, args.artifacts_dir)


def _emit(payload: dict, *, json_output: bool, cli_impl: Any, formatter=None) -> None:
    if json_output:
        print(cli_impl.json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if callable(formatter):
        print(formatter(payload))
    else:
        print(cli_impl.json.dumps(payload, ensure_ascii=False))


def cmd_doctor(args: argparse.Namespace, cli_impl: Any) -> int:
    from autowfo.storage_ops import format_validation_report, validate_storage

    payload = validate_storage(_resolve_artifacts_dir(args, cli_impl))
    _emit(payload, json_output=bool(args.json), cli_impl=cli_impl, formatter=format_validation_report)
    return 0 if payload.get("ok") else 1


def cmd_storage_validate(args: argparse.Namespace, cli_impl: Any) -> int:
    return cmd_doctor(args, cli_impl)


def cmd_storage_migrate(args: argparse.Namespace, cli_impl: Any) -> int:
    from autowfo.storage_ops import migrate_storage

    payload = migrate_storage(_resolve_artifacts_dir(args, cli_impl), dry_run=bool(args.dry_run))
    _emit(payload, json_output=bool(args.json), cli_impl=cli_impl)
    return 0 if payload.get("ok") else 1


def cmd_storage_rebuild_analytics(args: argparse.Namespace, cli_impl: Any) -> int:
    from autowfo.storage_ops import rebuild_analytics

    payload = rebuild_analytics(_resolve_artifacts_dir(args, cli_impl))
    _emit(payload, json_output=bool(args.json), cli_impl=cli_impl)
    return 0 if payload.get("ok") else 1


def cmd_storage_rebuild_shared_views(args: argparse.Namespace, cli_impl: Any) -> int:
    from autowfo.storage_ops import rebuild_shared_views

    payload = rebuild_shared_views(_resolve_artifacts_dir(args, cli_impl))
    _emit(payload, json_output=bool(args.json), cli_impl=cli_impl)
    return 0 if payload.get("ok") else 1


def cmd_storage_purge_legacy(args: argparse.Namespace, cli_impl: Any) -> int:
    from autowfo.storage_ops import purge_legacy_outputs

    quarantine_dir = str(args.quarantine_dir or "").strip()
    payload = purge_legacy_outputs(
        _resolve_artifacts_dir(args, cli_impl),
        dry_run=bool(args.dry_run),
        delete=bool(args.delete),
        quarantine_dir=(cli_impl._resolve_path(Path(args.cwd).resolve(), quarantine_dir) if quarantine_dir else None),
    )
    _emit(payload, json_output=bool(args.json), cli_impl=cli_impl)
    return 0 if payload.get("ok") else 1


def cmd_storage_rescore(args: argparse.Namespace, cli_impl: Any) -> int:
    import json as _json

    from autowfo.storage_ops import rescore_trusted_runs

    ranking_config = None
    config_path = str(getattr(args, "ranking_config", "") or "").strip()
    if config_path:
        resolved = cli_impl._resolve_path(Path(args.cwd).resolve(), config_path)
        ranking_config = _json.loads(resolved.read_text(encoding="utf-8-sig"))

    payload = rescore_trusted_runs(_resolve_artifacts_dir(args, cli_impl), ranking_config=ranking_config)
    _emit(payload, json_output=bool(args.json), cli_impl=cli_impl)
    return 0 if payload.get("ok") else 1


def cmd_storage_compare_ranking(args: argparse.Namespace, cli_impl: Any) -> int:
    import json as _json

    from autowfo.storage_ops import compare_ranking_configs

    cwd = Path(args.cwd).resolve()

    candidate_config_path = cli_impl._resolve_path(cwd, str(args.candidate_config))
    candidate_config = _json.loads(candidate_config_path.read_text(encoding="utf-8-sig"))

    baseline_config = None
    baseline_config_raw = str(getattr(args, "baseline_config", "") or "").strip()
    if baseline_config_raw:
        baseline_path = cli_impl._resolve_path(cwd, baseline_config_raw)
        baseline_config = _json.loads(baseline_path.read_text(encoding="utf-8-sig"))

    output_json = str(getattr(args, "output_json", "") or "").strip()
    output_html = str(getattr(args, "output_html", "") or "").strip()
    payload = compare_ranking_configs(
        _resolve_artifacts_dir(args, cli_impl),
        candidate_config=candidate_config,
        baseline_config=baseline_config,
        top_n=int(getattr(args, "top_n", 10) or 10),
        output_json=(cli_impl._resolve_path(cwd, output_json) if output_json else None),
        output_html=(cli_impl._resolve_path(cwd, output_html) if output_html else None),
    )
    _emit(payload, json_output=bool(args.json), cli_impl=cli_impl)
    return 0 if payload.get("ok") else 1


def cmd_storage_drift_report(args: argparse.Namespace, cli_impl: Any) -> int:
    from autowfo.storage_ops import build_execution_drift_report

    cwd = Path(args.cwd).resolve()
    protocol_path = cli_impl._resolve_path(cwd, str(getattr(args, "protocol_path", "") or ""))
    output_json = str(getattr(args, "output_json", "") or "").strip()
    payload = build_execution_drift_report(
        _resolve_artifacts_dir(args, cli_impl),
        protocol_path=protocol_path,
        output_path=(cli_impl._resolve_path(cwd, output_json) if output_json else None),
    )
    _emit(payload, json_output=bool(args.json), cli_impl=cli_impl)
    return 0 if payload.get("ok") else 1
