"""Cron command handler and parser wiring."""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import time


def add_cron_parser(subparsers: argparse._SubParsersAction[Any], cli_impl: Any) -> None:
    cron_parser = subparsers.add_parser(
        "cron",
        help="Automated patrol cycle: plan -> batch -> report, optionally repeating on interval",
    )
    cron_parser.add_argument("--registry", default="artifacts/run_registry.json", help="Path to run registry JSON")
    cron_parser.add_argument("--template-config", required=True, help="Template config for plan generation")
    cron_parser.add_argument("--plan-out", default="artifacts/batch_plan.cron.json", help="Output batch plan path")
    cron_parser.add_argument(
        "--plan-config-dir",
        default="artifacts/cron_configs",
        help="Output directory for cron-generated per-job config files",
    )
    cron_parser.add_argument(
        "--batch-state",
        default="artifacts/batch_state.json",
        help="Path to batch state JSON for crash-safe resume",
    )
    cron_parser.add_argument("--report-html", default="artifacts/cross_run_report.html", help="Output report HTML path")
    cron_parser.add_argument("--report-json", default="artifacts/cross_run_report.json", help="Output report JSON path")
    cron_parser.add_argument("--workflow", choices=["run", "baseline"], default="run", help="Workflow per planned job")
    cron_parser.add_argument("--mode", choices=["combo", "refine"], default="combo", help="Mode for workflow=run")
    cron_parser.add_argument("--workers", type=int, default=None, help="Workers override per job")
    cron_parser.add_argument("--max-jobs", type=int, default=0, help="Max jobs per cycle (0=unlimited)")
    cron_parser.add_argument("--top-n", type=int, default=20, help="Top-N for report views")
    cron_parser.add_argument("--parallel-jobs", type=int, default=1, help="Concurrent batch jobs")
    cron_parser.add_argument("--interval", type=int, default=0, help="Minutes between cycles (0 = run once)")
    cron_parser.add_argument(
        "--max-cycles",
        type=int,
        default=1,
        help="Maximum number of patrol cycles (0 = unlimited until interrupted)",
    )
    cron_parser.add_argument("--target-timeframes", default=None, help="Comma-separated target timeframes")
    cron_parser.add_argument("--target-symbols", default=None, help="Comma-separated target symbols")
    cron_parser.add_argument("--timeframe-days", default=None, help="Override days-per-timeframe mapping")
    cron_parser.add_argument(
        "--notify-webhook",
        default=os.environ.get("AUTOWFO_NOTIFY_WEBHOOK", ""),
        help="Comma-separated webhook URLs for cycle notifications",
    )
    cron_parser.add_argument(
        "--notify-telegram-token",
        default=os.environ.get("AUTOWFO_NOTIFY_TELEGRAM_TOKEN", ""),
        help="Telegram bot token for cycle notifications",
    )
    cron_parser.add_argument(
        "--notify-telegram-chat-id",
        default=os.environ.get("AUTOWFO_NOTIFY_TELEGRAM_CHAT_ID", ""),
        help="Telegram chat id for cycle notifications",
    )
    cron_parser.add_argument("--notify-top-n", type=int, default=3, help="Top-N entries for change summary")
    cron_parser.add_argument("--freshness-alert-days", type=int, default=7, help="Stale data alert threshold (days)")
    cron_parser.add_argument(
        "--notify-state",
        default="artifacts/cron_notify_state.json",
        help="Path to notification state JSON",
    )
    cron_parser.add_argument("--cwd", default=".", help="Working directory")
    cron_parser.add_argument(
        "--scheduler-mode",
        action="store_true",
        help="Force scheduler-mode patrol (discovery -> scheduler queue execution loop)",
    )
    cron_parser.add_argument(
        "--max-runs",
        type=int,
        default=None,
        help="Override max runs per scheduler patrol cycle",
    )
    cron_parser.add_argument(
        "--max-cycle-seconds",
        type=int,
        default=3600,
        help="Guardrail timeout for one patrol cycle before forced stop (default: 3600)",
    )
    cron_parser.set_defaults(handler=cli_impl._cmd_cron)


def _load_scheduler_mode(cwd: Path, cli_impl: Any) -> tuple[bool, str, int, bool]:
    scheduler_path = cwd / "artifacts" / "scheduler.json"
    if not scheduler_path.exists():
        return False, "", 5, False
    payload = cli_impl._load_config(scheduler_path)
    if not isinstance(payload, dict):
        return True, "", 5, False
    schedule_cron = str(payload.get("schedule_cron", "") or "").strip()
    try:
        max_runs = int(payload.get("max_runs_per_patrol", 5))
    except Exception:
        max_runs = 5
    max_runs = max(1, max_runs)
    enable_signal_scheduling = bool(payload.get("enable_signal_scheduling", False))
    return True, schedule_cron, max_runs, enable_signal_scheduling


def _default_scheduler_start_date() -> str:
    return (datetime.now(timezone.utc) - timedelta(days=365)).date().isoformat()


def _run_scheduler_queue_once(cwd: Path, cli_impl: Any) -> dict:
    from scripts.autowfo.analytics import AnalyticsStore
    from scripts.autowfo.artifact_store import ArtifactStore
    from scripts.autowfo.data_multi import load_experiment_data
    from scripts.autowfo.experiment import Experiment
    from scripts.autowfo.experiment_runner import ExperimentRunner
    from scripts.autowfo.scheduler import ExperimentQueue, SchedulerConfig

    artifacts_dir = cwd / "artifacts"
    scheduler_config = SchedulerConfig.from_file(artifacts_dir / "scheduler.json")
    scheduler_queue = ExperimentQueue(queue_path=artifacts_dir / "scheduler_queue.json", config=scheduler_config)
    item = scheduler_queue.pop()
    if item is None:
        return {"processed": False, "ok": True, "item": None}

    try:
        exp_cfg = item.get("experiment_config")
        if not isinstance(exp_cfg, dict):
            raise ValueError("queued item missing experiment_config")
        experiment = Experiment.from_dict(exp_cfg)

        config_path = artifacts_dir / "experiments" / experiment.experiment_id / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        experiment.save(config_path)

        start_date = str(item.get("start_date") or exp_cfg.get("start_date") or "").strip() or _default_scheduler_start_date()
        end_date_raw = str(item.get("end_date") or exp_cfg.get("end_date") or "").strip()
        end_date = end_date_raw or None

        trigger_ohlcv, action_ohlcv = load_experiment_data(
            experiment=experiment,
            start_date=start_date,
            end_date=end_date,
            cache_dir=artifacts_dir / "ohlcv",
        )

        runner = ExperimentRunner(
            experiment=experiment,
            trigger_ohlcv=trigger_ohlcv,
            action_ohlcv=action_ohlcv,
            artifact_store=ArtifactStore(experiment.experiment_id, base_dir=artifacts_dir),
            analytics_store=AnalyticsStore(artifacts_dir / "analytics.duckdb"),
        )
        run_result = runner.run()
        return {
            "processed": True,
            "ok": True,
            "item": item,
            "result": {
                "experiment_id": experiment.experiment_id,
                "run_id": run_result.run_id,
                "n_combos": run_result.n_combos,
                "n_completed": run_result.n_completed,
                "n_errors": run_result.n_errors,
            },
        }
    except Exception as exc:
        return {
            "processed": True,
            "ok": False,
            "item": item,
            "error": str(exc),
        }


def _run_scheduler_patrol_cycle(
    cwd: Path,
    cli_impl: Any,
    schedule_cron: str,
    max_runs_per_patrol: int,
    enable_signal_scheduling: bool = False,
) -> dict:
    from scripts.autowfo.analytics import AnalyticsStore
    from scripts.autowfo.discovery_loop import DiscoveryLoop
    from scripts.autowfo.scheduler import ExperimentQueue, SchedulerConfig
    from scripts.autowfo.signal_scheduler import SignalScheduler

    cycle_start_utc = cli_impl._utc_now_iso()
    artifacts_dir = cwd / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    scheduler_config = SchedulerConfig.from_file(artifacts_dir / "scheduler.json")
    scheduler_queue = ExperimentQueue(queue_path=artifacts_dir / "scheduler_queue.json", config=scheduler_config)
    analytics_store = AnalyticsStore(artifacts_dir / "analytics.duckdb")

    discovery_summary = None
    pool_config_path = artifacts_dir / "pool_config.json"
    if pool_config_path.exists():
        pool_config = cli_impl._load_config(pool_config_path)
        if isinstance(pool_config, dict):
            loop = DiscoveryLoop(
                pool_config=pool_config,
                scheduler=scheduler_queue,
                analytics_store=analytics_store,
                experiments_root=artifacts_dir / "experiments",
            )
            discovery_summary = loop.tick()

    runs_processed = 0
    run_outcomes = []
    reached_max_runs = False
    run_ok = True
    error_message = None
    max_runs = max(1, int(max_runs_per_patrol))
    for _ in range(max_runs):
        outcome = _run_scheduler_queue_once(cwd, cli_impl)
        run_outcomes.append(outcome)
        if not outcome.get("processed"):
            break
        runs_processed += 1
        if not bool(outcome.get("ok", True)):
            run_ok = False
            error_message = str(outcome.get("error", "scheduler run failed"))
            break
    queue_remaining = ExperimentQueue(
        queue_path=artifacts_dir / "scheduler_queue.json",
        config=scheduler_config,
    ).size()
    if runs_processed >= max_runs and queue_remaining > 0:
        reached_max_runs = True

    signal_scheduling_tick = None
    if bool(enable_signal_scheduling):
        try:
            signal_scheduler = SignalScheduler(
                analytics_store=analytics_store,
                state_path=artifacts_dir / "signal_schedule_state.json",
                export_path=artifacts_dir / "live_signal_config.json",
                positions_path=artifacts_dir / "paper_positions.json",
            )
            signal_scheduling_tick = signal_scheduler.tick()
        except Exception as exc:
            signal_scheduling_tick = {"ok": False, "error": str(exc)}

    cycle_end_utc = cli_impl._utc_now_iso()
    return {
        "cycle_start_utc": cycle_start_utc,
        "cycle_end_utc": cycle_end_utc,
        "plan_jobs": int((discovery_summary or {}).get("generated", 0)),
        "batch_ok": run_ok,
        "report_ok": True,
        "error": error_message,
        "top_entities": [],
        "scheduler_mode": True,
        "schedule_cron": schedule_cron,
        "max_runs_per_patrol": max_runs,
        "scheduler_runs_processed": runs_processed,
        "reached_max_runs": reached_max_runs,
        "queue_remaining": int(queue_remaining),
        "discovery_tick": discovery_summary,
        "signal_scheduling": {
            "enabled": bool(enable_signal_scheduling),
            "tick": signal_scheduling_tick,
        },
        "scheduler_run_once": run_outcomes[-1] if run_outcomes else {"processed": False, "ok": True, "item": None},
        "scheduler_run_outcomes": run_outcomes,
    }


def cmd_cron(args: argparse.Namespace, cli_impl: Any) -> int:
    cwd = Path(args.cwd).resolve()
    registry_path = cli_impl._resolve_path(cwd, args.registry)
    template_config_path = cli_impl._resolve_path(cwd, args.template_config)
    plan_out = cli_impl._resolve_path(cwd, args.plan_out)
    plan_config_dir = cli_impl._resolve_path(cwd, args.plan_config_dir)
    batch_state_path = cli_impl._resolve_path(cwd, args.batch_state)
    report_html = cli_impl._resolve_path(cwd, args.report_html)
    report_json = cli_impl._resolve_path(cwd, args.report_json) if args.report_json else None

    if not registry_path.exists():
        raise FileNotFoundError(f"registry not found: {registry_path}")
    if not template_config_path.exists():
        raise FileNotFoundError(f"template config not found: {template_config_path}")

    workflow = str(args.workflow).strip().lower()
    mode = None if args.mode in (None, "") else str(args.mode).strip().lower()
    if workflow not in {"run", "baseline"}:
        raise ValueError("workflow must be run or baseline")

    workers = None if args.workers in (None, "") else int(args.workers)
    max_jobs = int(args.max_jobs)
    top_n = int(args.top_n)
    parallel_jobs = max(1, int(args.parallel_jobs))
    interval_minutes = int(args.interval)
    max_cycles = int(args.max_cycles)
    webhook_urls = cli_impl._split_csv_fields(args.notify_webhook)
    telegram_token = str(args.notify_telegram_token or "").strip()
    telegram_chat_id = str(args.notify_telegram_chat_id or "").strip()
    notify_top_n = max(1, int(args.notify_top_n))
    freshness_alert_days = max(1, int(args.freshness_alert_days))
    notify_state_path = cli_impl._resolve_path(cwd, args.notify_state)
    notifications_enabled = bool(webhook_urls or (telegram_token and telegram_chat_id))
    notify_state = cli_impl._read_cron_notify_state(notify_state_path) if notifications_enabled else cli_impl._default_cron_notify_state()

    if (telegram_token and not telegram_chat_id) or (telegram_chat_id and not telegram_token):
        print("[cron:notify] telegram disabled: both --notify-telegram-token and --notify-telegram-chat-id are required")

    target_tf = [t.strip() for t in args.target_timeframes.split(",") if t.strip()] if args.target_timeframes else None
    target_sym = [s.strip() for s in args.target_symbols.split(",") if s.strip()] if args.target_symbols else None

    td_map: Optional[Dict[str, int]] = None
    if args.timeframe_days:
        td_map = {}
        for token in args.timeframe_days.split(","):
            token = token.strip()
            if ":" not in token:
                continue
            tf_part, days_part = token.split(":", 1)
            tf_part = tf_part.strip()
            try:
                days_val = int(days_part.strip())
            except ValueError:
                continue
            if tf_part and days_val > 0:
                td_map[tf_part] = days_val

    cycle_count = 0
    cycle_log: List[Dict[str, Any]] = []
    (
        scheduler_cfg_enabled,
        schedule_cron,
        scheduler_default_max_runs,
        scheduler_signal_scheduling_enabled,
    ) = _load_scheduler_mode(cwd, cli_impl)
    scheduler_mode = bool(args.scheduler_mode) or scheduler_cfg_enabled
    if args.max_runs in (None, ""):
        scheduler_max_runs = scheduler_default_max_runs
    else:
        scheduler_max_runs = max(1, int(args.max_runs))
    max_cycle_seconds = max(1, int(args.max_cycle_seconds or 3600))
    if scheduler_mode:
        print(
            f"[cron] scheduler mode enabled schedule_cron={schedule_cron or 'n/a'} "
            f"max_runs_per_patrol={scheduler_max_runs} "
            f"signal_scheduling={'on' if scheduler_signal_scheduling_enabled else 'off'}"
        )

    while True:
        cycle_count += 1
        print(f"\n{'='*60}")
        print(f"[cron] cycle {cycle_count} started at {cli_impl._utc_now_iso()}")
        print(f"{'='*60}")
        cycle_started = time.perf_counter()

        if scheduler_mode:
            cycle_result = _run_scheduler_patrol_cycle(
                cwd=cwd,
                cli_impl=cli_impl,
                schedule_cron=schedule_cron,
                max_runs_per_patrol=scheduler_max_runs,
                enable_signal_scheduling=scheduler_signal_scheduling_enabled,
            )
        else:
            cycle_result = cli_impl._run_patrol_cycle(
                cwd=cwd,
                registry_path=registry_path,
                template_config_path=template_config_path,
                plan_out=plan_out,
                plan_config_dir=plan_config_dir,
                batch_state_path=batch_state_path,
                report_html_path=report_html,
                report_json_path=report_json,
                workflow=workflow,
                mode=mode,
                workers=workers,
                max_jobs=max_jobs,
                continue_on_error=True,
                parallel_jobs=parallel_jobs,
                top_n=top_n,
                target_timeframes=target_tf,
                target_symbols=target_sym,
                timeframe_days_map=td_map,
            )
        cycle_result["cycle_number"] = cycle_count
        cycle_elapsed = float(time.perf_counter() - cycle_started)
        cycle_result["cycle_elapsed_seconds"] = cycle_elapsed
        timeout_guard_triggered = cycle_elapsed > float(max_cycle_seconds)
        cycle_result["timeout_guard_triggered"] = bool(timeout_guard_triggered)
        try:
            cli_impl._append_patrol_log(cwd, cycle_result)
        except Exception:
            pass
        status = "OK" if cycle_result.get("batch_ok") and cycle_result.get("report_ok") else "PARTIAL"
        print(
            f"[cron] cycle {cycle_count} {status}: "
            f"plan_jobs={cycle_result['plan_jobs']} "
            f"batch_ok={cycle_result['batch_ok']} "
            f"report_ok={cycle_result['report_ok']}"
        )
        if cycle_result.get("error"):
            print(f"[cron] error: {cycle_result['error']}")

        prev_top = notify_state.get("last_top")
        if not isinstance(prev_top, list):
            prev_top = []
        current_top_raw = cycle_result.get("top_entities")
        current_top = current_top_raw if isinstance(current_top_raw, list) else []
        current_top = current_top[:notify_top_n]
        top_change_lines = cli_impl._build_top_change_lines(prev_top, current_top, limit=notify_top_n)
        freshness_alert = cli_impl._build_freshness_alert(cwd / "artifacts", threshold_days=freshness_alert_days)
        cycle_result["top_change_lines"] = top_change_lines
        cycle_result["freshness_alert"] = freshness_alert

        if notifications_enabled:
            notify_status = "ALERT" if status != "OK" or freshness_alert.get("alert") else "OK"
            message_text = cli_impl._build_cron_notification_text(
                cycle_number=cycle_count,
                status=notify_status,
                cycle_result=cycle_result,
                top_change_lines=top_change_lines,
                freshness_alert=freshness_alert,
            )
            notify_payload = {
                "event": "autowfo_cron_cycle",
                "generated_utc": cli_impl._utc_now_iso(),
                "status": notify_status,
                "cycle_number": cycle_count,
                "plan_jobs": cycle_result.get("plan_jobs", 0),
                "batch_ok": bool(cycle_result.get("batch_ok")),
                "report_ok": bool(cycle_result.get("report_ok")),
                "error": cycle_result.get("error"),
                "top_changes": top_change_lines,
                "freshness_alert": freshness_alert,
                "text": message_text,
            }
            notify_errors = cli_impl._dispatch_cron_notifications(
                webhook_urls=webhook_urls,
                telegram_token=telegram_token,
                telegram_chat_id=telegram_chat_id,
                message_text=message_text,
                payload=notify_payload,
            )
            if notify_errors:
                for notify_err in notify_errors:
                    print(f"[cron:notify] ERROR: {notify_err}")
            else:
                print("[cron:notify] sent")
            if current_top:
                notify_state["last_top"] = current_top
            notify_state["last_cycle_number"] = cycle_count
            cli_impl._write_cron_notify_state(notify_state_path, notify_state)

        cycle_log.append(cycle_result)
        log_path = cwd / "artifacts" / "cron_cycle_log.json"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(cli_impl.json.dumps(cycle_log, ensure_ascii=False, indent=2), encoding="utf-8")

        if timeout_guard_triggered:
            print(
                "[cron] warning: cycle exceeded max_cycle_seconds="
                f"{max_cycle_seconds}; elapsed={cycle_elapsed:.2f}s; stopping patrol loop"
            )
            break

        if max_cycles > 0 and cycle_count >= max_cycles:
            print(f"[cron] reached max_cycles={max_cycles}, stopping")
            break

        if interval_minutes <= 0:
            break

        print(f"[cron] sleeping {interval_minutes} minutes until next cycle...")
        time.sleep(interval_minutes * 60)

    return 0
