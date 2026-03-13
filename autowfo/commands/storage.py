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
