"""Plan/discover/report/repro handlers and parser wiring."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, List, Optional


def add_plan_parsers(subparsers: argparse._SubParsersAction[Any], cli_impl: Any) -> None:
    plan_parser = subparsers.add_parser("plan", help="Generate batch plan from run registry coverage gaps")
    plan_parser.add_argument("--registry", default="artifacts/run_registry.json", help="Path to run registry JSON")
    plan_parser.add_argument(
        "--template-config",
        default="artifacts/sweep_config.json",
        help="Template config used to build per-gap configs",
    )
    plan_parser.add_argument(
        "--out-plan",
        default="artifacts/batch_plan.auto.json",
        help="Output path for generated batch plan JSON",
    )
    plan_parser.add_argument(
        "--out-config-dir",
        default="artifacts/planned_configs",
        help="Output directory for generated per-job config JSON files",
    )
    plan_parser.add_argument("--max-jobs", type=int, default=0, help="Limit number of planned jobs (0 means no limit)")
    plan_parser.add_argument("--workflow", choices=["run", "baseline"], default="baseline", help="Workflow type")
    plan_parser.add_argument("--mode", choices=["combo", "refine"], default=None, help="Mode for workflow=run")
    plan_parser.add_argument("--workers", type=int, default=None, help="Optional workers value for each generated job")
    plan_parser.add_argument(
        "--target-timeframes",
        default=None,
        help="Comma-separated target timeframes for coverage (e.g. 1h,2h,4h).",
    )
    plan_parser.add_argument(
        "--target-symbols",
        default=None,
        help="Comma-separated target symbols for coverage (e.g. ETH/USDT,BNB/USDT,SOL/USDT)",
    )
    plan_parser.add_argument(
        "--timeframe-days",
        default=None,
        help="Override days-per-timeframe mapping (e.g. 1h:90,2h:120,4h:180)",
    )
    plan_parser.add_argument("--cwd", default=".", help="Working directory")
    plan_parser.set_defaults(handler=cli_impl._cmd_plan)

    discover_parser = subparsers.add_parser("discover", help="Run one Mode-B discovery tick and enqueue experiments")
    discover_parser.add_argument("--pool", required=True, help="Path to pool config (JSON/YAML)")
    discover_parser.add_argument("--artifacts-dir", default="artifacts", help="Artifacts root directory")
    discover_parser.add_argument("--cwd", default=".", help="Working directory")
    discover_parser.set_defaults(handler=cli_impl._cmd_discover)

    export_signal_parser = subparsers.add_parser(
        "export-signal",
        help="Export top strategy from analytics into live signal config JSON",
    )
    export_signal_parser.add_argument("--top", type=int, default=1, help="Read top-N best strategies and export rank-1")
    export_signal_parser.add_argument(
        "--out",
        default="artifacts/live_signal_config.json",
        help="Output live signal config JSON path",
    )
    export_signal_parser.add_argument("--cwd", default=".", help="Working directory")
    export_signal_parser.set_defaults(handler=cli_impl._cmd_export_signal)

    schedule_signal_parser = subparsers.add_parser(
        "schedule-signals",
        help="Run signal scheduling daemon (auto export and paper switch on strategy change)",
    )
    schedule_signal_parser.add_argument(
        "--interval",
        type=int,
        default=3600,
        help="Scheduler interval in seconds (default: 3600)",
    )
    schedule_signal_parser.add_argument(
        "--max-ticks",
        type=int,
        default=0,
        help="Optional max ticks for bounded run (0 = unlimited)",
    )
    schedule_signal_parser.add_argument(
        "--run-once",
        action="store_true",
        help="Run a single scheduling tick and exit",
    )
    schedule_signal_parser.add_argument("--cwd", default=".", help="Working directory")
    schedule_signal_parser.set_defaults(handler=cli_impl._cmd_schedule_signals)

    report_parser = subparsers.add_parser("report", help="Generate cross-run dashboard report from run registry")
    report_parser.add_argument("--registry", default="artifacts/run_registry.json", help="Path to run registry JSON")
    report_parser.add_argument("--artifacts-dir", default="artifacts", help="Artifacts root directory")
    report_parser.add_argument(
        "--out-html",
        default="artifacts/cross_run_report.html",
        help="Output path for cross-run HTML report",
    )
    report_parser.add_argument(
        "--out-json",
        default="artifacts/cross_run_report.json",
        help="Output path for cross-run JSON payload (set empty to disable)",
    )
    report_parser.add_argument("--top-n", type=int, default=20, help="Top-N rows for leaderboard views")
    report_parser.add_argument("--cwd", default=".", help="Working directory")
    report_parser.set_defaults(handler=cli_impl._cmd_report)

    export_report_parser = subparsers.add_parser(
        "export-report",
        help="Export analytics research report as self-contained HTML",
    )
    export_report_parser.add_argument(
        "--out",
        default="artifacts/research_report.html",
        help="Output report HTML path",
    )
    export_report_parser.add_argument("--cwd", default=".", help="Working directory")
    export_report_parser.set_defaults(handler=cli_impl._cmd_export_report)

    repro_parser = subparsers.add_parser("repro", help="Compare two top-N CSV artifacts for reproducibility")
    repro_parser.add_argument("--reference-top", required=True, help="Reference top-N CSV path")
    repro_parser.add_argument("--candidate-top", required=True, help="Candidate top-N CSV path")
    repro_parser.add_argument(
        "--out-json",
        default="artifacts/reproducibility_report.json",
        help="Output path for reproducibility JSON report",
    )
    repro_parser.add_argument("--top-n", type=int, default=10, help="Top-N rows to compare")
    repro_parser.add_argument(
        "--metric-abs-tolerance",
        type=float,
        default=1e-9,
        help="Absolute tolerance used for metric drift checks",
    )
    repro_parser.add_argument(
        "--identity-fields",
        default="",
        help="Comma-separated identity fields (default uses built-in identity schema)",
    )
    repro_parser.add_argument(
        "--metric-fields",
        default="",
        help="Comma-separated metric fields (default uses built-in reproducibility metrics)",
    )
    repro_parser.add_argument("--cwd", default=".", help="Working directory")
    repro_parser.set_defaults(handler=cli_impl._cmd_repro)

    pilot_parser = subparsers.add_parser(
        "pilot-analyze",
        help="Compare two pilot/subgroup runs and emit a machine-readable stable-candidate report",
    )
    pilot_parser.add_argument("--main-run", required=True, help="Main run id or path to run directory")
    pilot_parser.add_argument("--sensitivity-run", required=True, help="Sensitivity run id or path to run directory")
    pilot_parser.add_argument(
        "--artifacts-dir",
        default="artifacts",
        help="Artifacts root directory used when run ids are provided",
    )
    pilot_parser.add_argument(
        "--out-json",
        default="artifacts/pilot_analysis_report.json",
        help="Output path for machine-readable pilot analysis JSON report",
    )
    pilot_parser.add_argument(
        "--top-n",
        type=int,
        default=20,
        help="Number of top stable/gate-passed rows to include",
    )
    pilot_parser.add_argument(
        "--min-combo-return",
        type=float,
        default=0.0,
        help="Minimum worst-run combo return required to pass the overall gate",
    )
    pilot_parser.add_argument(
        "--min-combo-trades",
        type=float,
        default=0.0,
        help="Minimum worst-run combo average OOS trade count required to pass the overall gate",
    )
    pilot_parser.add_argument(
        "--identity-fields",
        default="",
        help="Comma-separated identity fields (default uses the pilot-analysis identity schema)",
    )
    pilot_parser.add_argument(
        "--allow-negative-symbols",
        action="store_true",
        help="Disable the default all-symbols-nonnegative gate",
    )
    pilot_parser.add_argument("--cwd", default=".", help="Working directory")
    pilot_parser.set_defaults(handler=cli_impl._cmd_pilot_analyze)


def cmd_plan(args: argparse.Namespace, cli_impl: Any) -> int:
    cwd = Path(args.cwd).resolve()
    registry_path = cli_impl._resolve_path(cwd, args.registry)
    template_config_path = cli_impl._resolve_path(cwd, args.template_config)
    out_plan_path = cli_impl._resolve_path(cwd, args.out_plan)
    out_config_dir = cli_impl._resolve_path(cwd, args.out_config_dir)

    if not registry_path.exists():
        raise FileNotFoundError(f"registry not found: {registry_path}")
    if not template_config_path.exists():
        raise FileNotFoundError(f"template config not found: {template_config_path}")

    registry_payload = cli_impl._load_config(registry_path)
    template_config = cli_impl._load_config(template_config_path)

    target_tf_raw = getattr(args, "target_timeframes", None)
    target_sym_raw = getattr(args, "target_symbols", None)
    if target_tf_raw or target_sym_raw:
        target_tf_list = [t.strip() for t in target_tf_raw.split(",") if t.strip()] if target_tf_raw else []
        target_sym_list = [s.strip() for s in target_sym_raw.split(",") if s.strip()] if target_sym_raw else []
        if not target_tf_list or not target_sym_list:
            raise ValueError("--target-timeframes and --target-symbols must both be provided when either is used")
        pairs = cli_impl._compute_coverage_gaps(registry_payload, target_tf_list, target_sym_list)
    else:
        pairs = cli_impl._extract_registry_untested_pairs(registry_payload)

    max_jobs = None if args.max_jobs in (None, 0) else int(args.max_jobs)
    if max_jobs is not None and max_jobs < 0:
        raise ValueError("max-jobs must be >= 0")
    if max_jobs is not None:
        pairs = pairs[:max_jobs]

    workflow = str(args.workflow).strip().lower()
    mode = None if args.mode in (None, "") else str(args.mode).strip().lower()
    if workflow not in {"run", "baseline"}:
        raise ValueError("workflow must be run or baseline")
    if workflow == "baseline" and mode is not None:
        raise ValueError("mode is only valid when workflow=run")
    if workflow == "run" and mode not in {None, "combo", "refine"}:
        raise ValueError("mode must be combo/refine when provided")

    workers = None
    if args.workers is not None:
        workers = int(args.workers)
        if workers <= 0:
            raise ValueError("workers must be > 0")

    timeframe_days = cli_impl._build_timeframe_days_map(registry_payload, template_config)

    tf_days_raw = getattr(args, "timeframe_days", None)
    if tf_days_raw:
        for token in tf_days_raw.split(","):
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
                timeframe_days[tf_part] = days_val

    default_days = 60
    template_timeframes = template_config.get("timeframes")
    if isinstance(template_timeframes, list):
        for item in template_timeframes:
            if not isinstance(item, dict):
                continue
            try:
                d = int(item.get("days"))
            except Exception:
                continue
            if d > 0:
                default_days = d
                break

    out_config_dir.mkdir(parents=True, exist_ok=True)
    jobs = []
    for idx, pair in enumerate(pairs, start=1):
        timeframe = pair["timeframe"]
        symbol = pair["symbol"]
        days = int(timeframe_days.get(timeframe, default_days))

        cfg_payload = cli_impl.json.loads(cli_impl.json.dumps(template_config, ensure_ascii=False))
        cfg_payload["timeframes"] = [{"timeframe": timeframe, "days": days}]
        cfg_payload["trade_symbols"] = [symbol]

        cfg_name = f"{idx:03d}_{cli_impl._slug_text(timeframe)}_{cli_impl._slug_text(symbol)}.json"
        cfg_path = out_config_dir / cfg_name
        cfg_path.write_text(cli_impl.json.dumps(cfg_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        job = {
            "name": f"gap-{idx:03d}-{cli_impl._slug_text(timeframe)}-{cli_impl._slug_text(symbol)}",
            "workflow": workflow,
            "config": str(cfg_path),
        }
        if workflow == "run" and mode is not None:
            job["mode"] = mode
        if workers is not None:
            job["workers"] = workers
        jobs.append(job)

    out_plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_payload = {
        "generated_utc": cli_impl._utc_now_iso(),
        "source_registry": str(registry_path),
        "source_template_config": str(template_config_path),
        "job_count": len(jobs),
        "jobs": jobs,
    }
    out_plan_path.write_text(cli_impl.json.dumps(plan_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[plan] registry={registry_path}")
    print(f"[plan] template_config={template_config_path}")
    print(f"[plan] out_plan={out_plan_path}")
    print(f"[plan] out_config_dir={out_config_dir} jobs={len(jobs)}")
    if not jobs:
        print("[plan] no untested pairs found")
    return 0


def cmd_discover(args: argparse.Namespace, cli_impl: Any) -> int:
    from autowfo.analytics import AnalyticsStore
    from autowfo.discovery_loop import DiscoveryLoop
    from autowfo.scheduler import ExperimentQueue, SchedulerConfig

    cwd = Path(args.cwd).resolve()
    pool_path = cli_impl._resolve_path(cwd, args.pool)
    artifacts_dir = cli_impl._resolve_path(cwd, args.artifacts_dir)

    if not pool_path.exists():
        raise FileNotFoundError(f"pool config not found: {pool_path}")
    pool_config = cli_impl._load_config(pool_path)
    if not isinstance(pool_config, dict):
        raise ValueError("pool config must decode to object")

    artifacts_dir.mkdir(parents=True, exist_ok=True)
    scheduler_config = SchedulerConfig.from_file(artifacts_dir / "scheduler.json")
    scheduler = ExperimentQueue(queue_path=artifacts_dir / "scheduler_queue.json", config=scheduler_config)
    analytics_store = AnalyticsStore(artifacts_dir / "analytics.duckdb")

    loop = DiscoveryLoop(
        pool_config=pool_config,
        scheduler=scheduler,
        analytics_store=analytics_store,
        experiments_root=artifacts_dir / "experiments",
    )
    summary = loop.tick()
    print(cli_impl.json.dumps(summary, ensure_ascii=False))
    return 0


def cmd_export_signal(args: argparse.Namespace, cli_impl: Any) -> int:
    from autowfo.analytics import AnalyticsStore
    from autowfo.signal_exporter import export_top_signal_config

    cwd = Path(args.cwd).resolve()
    out_path = cli_impl._resolve_path(cwd, args.out)
    analytics_store = AnalyticsStore(cwd / "artifacts" / "analytics.duckdb")
    payload = export_top_signal_config(
        analytics_store=analytics_store,
        top_n=int(args.top),
        out_path=out_path,
    )
    print(cli_impl.json.dumps(payload, ensure_ascii=False))
    return 0


def cmd_schedule_signals(args: argparse.Namespace, cli_impl: Any) -> int:
    from autowfo.analytics import AnalyticsStore
    from autowfo.signal_scheduler import SignalScheduler

    cwd = Path(args.cwd).resolve()
    artifacts_dir = cwd / "artifacts"
    interval_seconds = max(1, int(args.interval))
    max_ticks = None
    if int(args.max_ticks) > 0:
        max_ticks = int(args.max_ticks)

    scheduler = SignalScheduler(
        analytics_store=AnalyticsStore(artifacts_dir / "analytics.duckdb"),
        state_path=artifacts_dir / "signal_schedule_state.json",
        export_path=artifacts_dir / "live_signal_config.json",
        positions_path=artifacts_dir / "paper_positions.json",
        schedule_interval_seconds=interval_seconds,
    )
    if bool(args.run_once):
        summary = scheduler.tick()
        print(cli_impl.json.dumps(summary, ensure_ascii=False))
        return 0
    try:
        ticks = scheduler.run_forever(max_ticks=max_ticks)
    except KeyboardInterrupt:
        print("[schedule-signals] interrupted")
        return 130
    print(cli_impl.json.dumps({"ok": True, "ticks": int(ticks)}, ensure_ascii=False))
    return 0


def cmd_report(args: argparse.Namespace, cli_impl: Any) -> int:
    from autowfo import cross_run

    cwd = Path(args.cwd).resolve()
    artifacts_dir = cli_impl._resolve_path(cwd, args.artifacts_dir)
    registry_path = cli_impl._resolve_path(cwd, args.registry)
    out_html_path = cli_impl._resolve_path(cwd, args.out_html)
    out_json_path = cli_impl._resolve_path(cwd, args.out_json) if args.out_json else None

    if not registry_path.exists():
        raise FileNotFoundError(f"registry not found: {registry_path}")
    if not artifacts_dir.exists():
        raise FileNotFoundError(f"artifacts dir not found: {artifacts_dir}")

    payload = cross_run.write_cross_run_reports(
        artifacts_dir=artifacts_dir,
        registry_path=registry_path,
        out_html_path=out_html_path,
        out_json_path=out_json_path,
        top_n=int(args.top_n),
    )
    summary = payload.get("summary", {})
    print(f"[report] registry={registry_path}")
    print(f"[report] artifacts={artifacts_dir}")
    print(f"[report] out_html={out_html_path}")
    if out_json_path is not None:
        print(f"[report] out_json={out_json_path}")
    print(
        "[report] runs={runs} symbols={symbols} timeframes={timeframes} coverage_pct={coverage}".format(
            runs=summary.get("total_runs", 0),
            symbols=summary.get("unique_symbols", 0),
            timeframes=summary.get("unique_timeframes", 0),
            coverage=summary.get("coverage_pct", 0),
        )
    )
    return 0


def cmd_export_report(args: argparse.Namespace, cli_impl: Any) -> int:
    from autowfo.analytics import AnalyticsStore
    from autowfo.report_export import export_html_report

    cwd = Path(args.cwd).resolve()
    out_path = cli_impl._resolve_path(cwd, args.out)
    analytics_store = AnalyticsStore(cwd / "artifacts" / "analytics.duckdb")
    payload = export_html_report(analytics_store=analytics_store, output_path=out_path)
    print(cli_impl.json.dumps(payload, ensure_ascii=False))
    return 0


def cmd_repro(args: argparse.Namespace, cli_impl: Any) -> int:
    import pandas as pd

    from autowfo import reproducibility

    cwd = Path(args.cwd).resolve()
    reference_top = cli_impl._resolve_path(cwd, args.reference_top)
    candidate_top = cli_impl._resolve_path(cwd, args.candidate_top)
    out_json = cli_impl._resolve_path(cwd, args.out_json)

    if not reference_top.exists():
        raise FileNotFoundError(f"reference top csv not found: {reference_top}")
    if not candidate_top.exists():
        raise FileNotFoundError(f"candidate top csv not found: {candidate_top}")

    identity_fields = cli_impl._split_csv_fields(args.identity_fields) or list(reproducibility.DEFAULT_IDENTITY_FIELDS)
    metric_fields = cli_impl._split_csv_fields(args.metric_fields) or list(reproducibility.DEFAULT_METRIC_FIELDS)

    reference_df = pd.read_csv(reference_top, low_memory=False)
    candidate_df = pd.read_csv(candidate_top, low_memory=False)
    payload = reproducibility.compare_top_n_stability(
        reference_df=reference_df,
        candidate_df=candidate_df,
        top_n=int(args.top_n),
        identity_fields=identity_fields,
        metric_fields=metric_fields,
        metric_abs_tolerance=float(args.metric_abs_tolerance),
    )

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(cli_impl.json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[repro] reference={reference_top}")
    print(f"[repro] candidate={candidate_top}")
    print(f"[repro] out_json={out_json}")
    print(
        "[repro] stable={stable} identity_match={identity_match} metric_match={metric_match} "
        "overlap_rows={overlap}/{top_n}".format(
            stable=payload.get("stable"),
            identity_match=payload.get("identity_match"),
            metric_match=payload.get("metric_match"),
            overlap=payload.get("overlap_rows", 0),
            top_n=payload.get("top_n", 0),
        )
    )
    return 0


def cmd_pilot_analyze(args: argparse.Namespace, cli_impl: Any) -> int:
    from autowfo import pilot_analysis

    cwd = Path(args.cwd).resolve()
    artifacts_dir = cli_impl._resolve_path(cwd, args.artifacts_dir)
    out_json = cli_impl._resolve_path(cwd, args.out_json)

    identity_fields = (
        cli_impl._split_csv_fields(args.identity_fields) or list(pilot_analysis.DEFAULT_IDENTITY_FIELDS)
    )
    main_run = pilot_analysis.load_run_analysis_inputs(args.main_run, artifacts_dir=artifacts_dir)
    sensitivity_run = pilot_analysis.load_run_analysis_inputs(args.sensitivity_run, artifacts_dir=artifacts_dir)
    payload = pilot_analysis.compare_pilot_runs(
        main_run=main_run,
        sensitivity_run=sensitivity_run,
        identity_fields=identity_fields,
        require_all_symbols_nonnegative=not bool(args.allow_negative_symbols),
        min_combo_return=float(args.min_combo_return),
        min_combo_trades=float(args.min_combo_trades),
        top_n=int(args.top_n),
    )

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(cli_impl.json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = payload.get("summary", {})
    print(f"[pilot-analyze] main_run={main_run.get('run_id')}")
    print(f"[pilot-analyze] sensitivity_run={sensitivity_run.get('run_id')}")
    print(f"[pilot-analyze] out_json={out_json}")
    print(
        "[pilot-analyze] compared={compared} stable_positive={stable} gate_passed={gate_passed}".format(
            compared=summary.get("compared_combo_rows", 0),
            stable=summary.get("stable_positive_rows", 0),
            gate_passed=summary.get("gate_passed_rows", 0),
        )
    )
    return 0

