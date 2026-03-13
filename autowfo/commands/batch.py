"""Batch command handler and parser wiring."""

from __future__ import annotations

import argparse
from pathlib import Path
import threading
from typing import Any


def add_batch_parser(subparsers: argparse._SubParsersAction[Any], cli_impl: Any) -> None:
    batch_parser = subparsers.add_parser("batch", help="Run multi-config batch plan (sequential or parallel)")
    batch_parser.add_argument("--plan", required=True, help="Path to batch plan (JSON/YAML)")
    batch_parser.add_argument("--workers", type=int, default=None, help="Global workers override for all jobs")
    batch_parser.add_argument("--cwd", default=".", help="Working directory")
    batch_parser.add_argument(
        "--state",
        default="artifacts/batch_state.json",
        help="Path to batch state JSON used for crash-safe resume",
    )
    batch_parser.add_argument(
        "--min-free-gb",
        type=float,
        default=20.0,
        help="Preflight minimum free disk (GB); set 0 to disable",
    )
    batch_parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue remaining jobs if one job fails",
    )
    batch_parser.add_argument(
        "--parallel-jobs",
        type=int,
        default=1,
        help="Run up to N batch jobs concurrently (default=1 sequential)",
    )
    batch_parser.set_defaults(handler=cli_impl._cmd_batch)


def cmd_batch(args: argparse.Namespace, cli_impl: Any) -> int:
    cwd = Path(args.cwd).resolve()
    plan_path = Path(args.plan).resolve()
    if not plan_path.exists():
        raise FileNotFoundError(f"batch plan not found: {plan_path}")

    state_path = cli_impl._resolve_path(cwd, args.state)
    plan_payload = cli_impl._load_config(plan_path)
    jobs = cli_impl._parse_batch_jobs(
        plan_payload,
        cwd=cwd,
        plan_path=plan_path,
        workers_override=args.workers,
    )
    cli_impl._preflight_batch_jobs(jobs, min_free_gb=float(args.min_free_gb))

    state = cli_impl._load_batch_state(state_path)
    cli_impl._write_batch_state(state_path, state)

    parallel_jobs = getattr(args, "parallel_jobs", 1) or 1
    total = len(jobs)

    if parallel_jobs > 1:
        print(
            f"[batch] parallel mode: jobs={total} workers={parallel_jobs} "
            f"state={state_path}"
        )
        failed = cli_impl._run_batch_jobs_parallel(
            jobs=jobs,
            state=state,
            state_path=state_path,
            parallel_jobs=parallel_jobs,
            continue_on_error=args.continue_on_error,
        )
        if failed and not args.continue_on_error:
            raise RuntimeError(f"batch had {len(failed)} failure(s)")
        print(
            f"[batch] finished jobs={total} "
            f"seen_keys={len(state['seen_keys'])} "
            f"failures={len(failed)} state={state_path}"
        )
        return 1 if failed else 0

    for idx, job in enumerate(jobs, start=1):
        lock = threading.Lock()
        result = cli_impl._run_batch_job_single(
            idx=idx,
            total=total,
            job=job,
            state=state,
            state_path=state_path,
            lock=lock,
        )
        if result["status"] == "failed":
            if args.continue_on_error:
                continue
            raise RuntimeError(f"batch job failed: {result.get('error', 'unknown')}")

    print(f"[batch] finished jobs={total} seen_keys={len(state['seen_keys'])} state={state_path}")
    return 0

