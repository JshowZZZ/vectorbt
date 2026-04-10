"""AUTOWFO CLI facade with command-module dispatch (AWF-147)."""

from __future__ import annotations

import argparse
import importlib
import json
import subprocess
import sys
import time
import tomllib
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from autowfo.commands import batch as cmd_batch
from autowfo.commands import core as _core
from autowfo.commands import core_batch as _core_batch
from autowfo.commands import cron as cmd_cron
from autowfo.commands import gate as cmd_gate
from autowfo.commands import plan as cmd_plan
from autowfo.commands import run as cmd_run
from autowfo.commands import storage as cmd_storage
from autowfo.storage_ops import rebuild_shared_views as _rebuild_shared_views

_ORIG_CORE_RUN_BATCH_JOB_SINGLE = _core._run_batch_job_single
_ORIG_CORE_RUN_BATCH_JOBS_PARALLEL = _core._run_batch_jobs_parallel


# Shared helper re-exports (kept for existing tests/importers).
_utc_now_iso = _core._utc_now_iso
_resolve_path = _core._resolve_path
_load_config = _core._load_config
_json_sha256 = _core._json_sha256
_write_runtime_config = _core._write_runtime_config
_run_module = _core._run_module
_slug_text = _core._slug_text
_extract_registry_untested_pairs = _core._extract_registry_untested_pairs
_compute_coverage_gaps = _core._compute_coverage_gaps
_build_timeframe_days_map = _core._build_timeframe_days_map
_split_csv_fields = _core._split_csv_fields
_safe_float = _core._safe_float
_parse_datetime_utc = _core._parse_datetime_utc
_trim_text = _core._trim_text
_extract_top_entities = _core._extract_top_entities
_build_top_change_lines = _core._build_top_change_lines
_default_cron_notify_state = _core._default_cron_notify_state
_read_cron_notify_state = _core._read_cron_notify_state
_write_cron_notify_state = _core._write_cron_notify_state
_build_freshness_alert = _core._build_freshness_alert
_format_freshness_line = _core._format_freshness_line
_post_json = _core._post_json
_dispatch_cron_notifications = _core._dispatch_cron_notifications
_build_cron_notification_text = _core._build_cron_notification_text
_append_patrol_log = _core._append_patrol_log

_parse_batch_jobs = _core._parse_batch_jobs
_preflight_batch_jobs = _core._preflight_batch_jobs
_load_batch_state = _core._load_batch_state
_write_batch_state = _core._write_batch_state
_latest_run_label = _core._latest_run_label
_list_run_labels = _core._list_run_labels
_resolve_gate_c_target_mode = _core._resolve_gate_c_target_mode
_resolve_gate_c_run_dir = _core._resolve_gate_c_run_dir
_resolve_top10_csv_path = _core._resolve_top10_csv_path
_compute_job_key = _core._compute_job_key


def _resolve_project_version() -> str:
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    try:
        payload = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    except Exception:
        return "0.0.0"

    project = payload.get("project", {}) if isinstance(payload, dict) else {}
    if isinstance(project, dict):
        version = project.get("version")
        if isinstance(version, str) and version.strip():
            return version.strip()

    dynamic = project.get("dynamic") if isinstance(project, dict) else None
    if not (isinstance(dynamic, list) and "version" in dynamic):
        return "0.0.0"

    tool = payload.get("tool", {}) if isinstance(payload, dict) else {}
    setuptools_cfg = tool.get("setuptools", {}) if isinstance(tool, dict) else {}
    dynamic_cfg = setuptools_cfg.get("dynamic", {}) if isinstance(setuptools_cfg, dict) else {}
    version_cfg = dynamic_cfg.get("version", {}) if isinstance(dynamic_cfg, dict) else {}
    attr_path = version_cfg.get("attr") if isinstance(version_cfg, dict) else None
    if not isinstance(attr_path, str) or "." not in attr_path:
        return "0.0.0"

    module_name, attr_name = attr_path.rsplit(".", 1)
    try:
        module = importlib.import_module(module_name)
        value = getattr(module, attr_name)
    except Exception:
        return "0.0.0"
    text = str(value).strip()
    return text or "0.0.0"


AUTOWFO_VERSION = _resolve_project_version()


def _run_workflow(
    cwd: Path,
    config_path: Path,
    workflow: str,
    mode: Optional[str] = None,
    workers: Optional[int] = None,
) -> None:
    return _core._run_workflow(cwd=cwd, config_path=config_path, workflow=workflow, mode=mode, workers=workers)


def _run_batch_job_single(
    idx: int,
    total: int,
    job: Dict[str, Any],
    state: Dict[str, Any],
    state_path: Path,
    lock: Any,
) -> Dict[str, Any]:
    _core_batch._run_workflow = _run_workflow
    return _ORIG_CORE_RUN_BATCH_JOB_SINGLE(
        idx=idx,
        total=total,
        job=job,
        state=state,
        state_path=state_path,
        lock=lock,
    )


def _run_batch_jobs_parallel(
    jobs: List[Dict[str, Any]],
    state: Dict[str, Any],
    state_path: Path,
    parallel_jobs: int,
    continue_on_error: bool,
) -> List[Dict[str, Any]]:
    _core_batch._run_workflow = _run_workflow
    return _ORIG_CORE_RUN_BATCH_JOBS_PARALLEL(
        jobs=jobs,
        state=state,
        state_path=state_path,
        parallel_jobs=parallel_jobs,
        continue_on_error=continue_on_error,
    )


def _run_patrol_cycle(
    cwd: Path,
    registry_path: Path,
    template_config_path: Path,
    plan_out: Path,
    plan_config_dir: Path,
    batch_state_path: Path,
    report_html_path: Path,
    report_json_path: Optional[Path],
    workflow: str = "run",
    mode: Optional[str] = "combo",
    workers: Optional[int] = None,
    max_jobs: int = 0,
    continue_on_error: bool = True,
    parallel_jobs: int = 1,
    top_n: int = 20,
    target_timeframes: Optional[List[str]] = None,
    target_symbols: Optional[List[str]] = None,
    timeframe_days_map: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    _core_batch._run_workflow = _run_workflow
    return _core._run_patrol_cycle(
        cwd=cwd,
        registry_path=registry_path,
        template_config_path=template_config_path,
        plan_out=plan_out,
        plan_config_dir=plan_config_dir,
        batch_state_path=batch_state_path,
        report_html_path=report_html_path,
        report_json_path=report_json_path,
        workflow=workflow,
        mode=mode,
        workers=workers,
        max_jobs=max_jobs,
        continue_on_error=continue_on_error,
        parallel_jobs=parallel_jobs,
        top_n=top_n,
        target_timeframes=target_timeframes,
        target_symbols=target_symbols,
        timeframe_days_map=timeframe_days_map,
    )


def _self():
    return sys.modules[__name__]


def _cmd_run(args: argparse.Namespace) -> int:
    return cmd_run.cmd_run(args, _self())


def _cmd_baseline(args: argparse.Namespace) -> int:
    return cmd_run.cmd_baseline(args, _self())


def _cmd_batch(args: argparse.Namespace) -> int:
    return cmd_batch.cmd_batch(args, _self())


def _cmd_plan(args: argparse.Namespace) -> int:
    return cmd_plan.cmd_plan(args, _self())


def _cmd_discover(args: argparse.Namespace) -> int:
    return cmd_plan.cmd_discover(args, _self())


def _cmd_export_signal(args: argparse.Namespace) -> int:
    return cmd_plan.cmd_export_signal(args, _self())


def _cmd_schedule_signals(args: argparse.Namespace) -> int:
    return cmd_plan.cmd_schedule_signals(args, _self())


def _cmd_report(args: argparse.Namespace) -> int:
    return cmd_plan.cmd_report(args, _self())


def _cmd_export_report(args: argparse.Namespace) -> int:
    return cmd_plan.cmd_export_report(args, _self())


def _cmd_repro(args: argparse.Namespace) -> int:
    return cmd_plan.cmd_repro(args, _self())


def _cmd_pilot_analyze(args: argparse.Namespace) -> int:
    return cmd_plan.cmd_pilot_analyze(args, _self())


def _cmd_pilot_export_config(args: argparse.Namespace) -> int:
    return cmd_plan.cmd_pilot_export_config(args, _self())


def _cmd_pilot_evaluate_promotion(args: argparse.Namespace) -> int:
    return cmd_plan.cmd_pilot_evaluate_promotion(args, _self())


def _cmd_pilot_build_bundle(args: argparse.Namespace) -> int:
    return cmd_plan.cmd_pilot_build_bundle(args, _self())


def _cmd_pilot_build_clue_map(args: argparse.Namespace) -> int:
    return cmd_plan.cmd_pilot_build_clue_map(args, _self())


def _cmd_gate_c(args: argparse.Namespace) -> int:
    return cmd_gate.cmd_gate_c(args, _self())


def _cmd_cron(args: argparse.Namespace) -> int:
    return cmd_cron.cmd_cron(args, _self())


def _cmd_doctor(args: argparse.Namespace) -> int:
    return cmd_storage.cmd_doctor(args, _self())


def _cmd_storage_validate(args: argparse.Namespace) -> int:
    return cmd_storage.cmd_storage_validate(args, _self())


def _cmd_storage_migrate(args: argparse.Namespace) -> int:
    return cmd_storage.cmd_storage_migrate(args, _self())


def _cmd_storage_rebuild_analytics(args: argparse.Namespace) -> int:
    return cmd_storage.cmd_storage_rebuild_analytics(args, _self())


def _cmd_storage_rebuild_shared_views(args: argparse.Namespace) -> int:
    return cmd_storage.cmd_storage_rebuild_shared_views(args, _self())


def _cmd_storage_purge_legacy(args: argparse.Namespace) -> int:
    return cmd_storage.cmd_storage_purge_legacy(args, _self())


def _cmd_storage_rescore(args: argparse.Namespace) -> int:
    return cmd_storage.cmd_storage_rescore(args, _self())


def _cmd_storage_compare_ranking(args: argparse.Namespace) -> int:
    return cmd_storage.cmd_storage_compare_ranking(args, _self())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="autowfo", description="AUTOWFO one-command workflows")
    parser.add_argument("--version", action="version", version=f"autowfo {AUTOWFO_VERSION}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    cli_impl = _self()
    cmd_run.add_run_parsers(subparsers, cli_impl)
    cmd_batch.add_batch_parser(subparsers, cli_impl)
    cmd_plan.add_plan_parsers(subparsers, cli_impl)
    cmd_gate.add_gate_parser(subparsers, cli_impl)
    cmd_cron.add_cron_parser(subparsers, cli_impl)
    cmd_storage.add_storage_parsers(subparsers, cli_impl)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.handler(args))
