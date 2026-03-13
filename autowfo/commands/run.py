"""Run/baseline command handlers and parser wiring."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any


def add_run_parsers(subparsers: argparse._SubParsersAction[Any], cli_impl: Any) -> None:
    run_parser = subparsers.add_parser("run", help="Run one sweep end-to-end")
    run_parser.add_argument("--config", required=True, help="Path to experiment config (JSON/YAML)")
    run_parser.add_argument("--mode", choices=["combo", "refine"], default=None, help="Override search mode")
    run_parser.add_argument("--workers", type=int, default=None, help="Override max_workers")
    run_parser.add_argument("--cwd", default=".", help="Working directory")
    run_parser.set_defaults(handler=cli_impl._cmd_run)

    baseline_parser = subparsers.add_parser("baseline", help="Run combo+refine baseline workflow")
    baseline_parser.add_argument("--config", required=True, help="Path to experiment config (JSON/YAML)")
    baseline_parser.add_argument("--workers", type=int, default=None, help="Override max_workers")
    baseline_parser.add_argument("--cwd", default=".", help="Working directory")
    baseline_parser.set_defaults(handler=cli_impl._cmd_baseline)


def cmd_run(args: argparse.Namespace, cli_impl: Any) -> int:
    cwd = Path(args.cwd).resolve()
    config_path = Path(args.config).resolve()
    if not config_path.exists():
        raise FileNotFoundError(f"config not found: {config_path}")

    cli_impl._run_workflow(
        cwd=cwd,
        config_path=config_path,
        workflow="run",
        mode=args.mode,
        workers=args.workers,
    )
    return 0


def cmd_baseline(args: argparse.Namespace, cli_impl: Any) -> int:
    cwd = Path(args.cwd).resolve()
    config_path = Path(args.config).resolve()
    if not config_path.exists():
        raise FileNotFoundError(f"config not found: {config_path}")

    cli_impl._run_workflow(
        cwd=cwd,
        config_path=config_path,
        workflow="baseline",
        mode=None,
        workers=args.workers,
    )
    return 0

