"""CLI entrypoint for AUTOWFO workflows."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional


def _load_config(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8-sig")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml  # type: ignore

            payload = yaml.safe_load(text)
        except Exception as exc:
            raise ValueError(
                f"config must be JSON or YAML (install PyYAML for YAML support): {path}"
            ) from exc
    if not isinstance(payload, dict):
        raise ValueError(f"config must decode to object: {path}")
    return payload


def _write_runtime_config(
    cwd: Path,
    config_path: Path,
    mode: Optional[str],
    workers: Optional[int],
) -> Path:
    artifacts_dir = cwd / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    config = _load_config(config_path)
    if mode:
        config["search_mode"] = mode
    if workers is not None:
        config["max_workers"] = int(workers)

    runtime_config_path = artifacts_dir / "sweep_config.json"
    runtime_config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return runtime_config_path


def _run_module(module_name: str, cwd: Path, env: Dict[str, str]) -> None:
    cmd = [sys.executable, "-m", module_name]
    subprocess.run(cmd, cwd=str(cwd), env=env, check=True)


def _cmd_run(args: argparse.Namespace) -> int:
    cwd = Path(args.cwd).resolve()
    config_path = Path(args.config).resolve()
    if not config_path.exists():
        raise FileNotFoundError(f"config not found: {config_path}")

    runtime_config_path = _write_runtime_config(
        cwd=cwd,
        config_path=config_path,
        mode=args.mode,
        workers=args.workers,
    )
    env = os.environ.copy()
    if args.mode:
        env["VBT_SWEEP_MODE"] = args.mode

    print(f"[autowfo] runtime_config={runtime_config_path}")
    print(f"[autowfo] mode={args.mode or 'config_default'} workers={args.workers or 'config_default'}")
    _run_module("scripts.run_btc_regime_sweep", cwd=cwd, env=env)
    return 0


def _cmd_baseline(args: argparse.Namespace) -> int:
    cwd = Path(args.cwd).resolve()
    config_path = Path(args.config).resolve()
    if not config_path.exists():
        raise FileNotFoundError(f"config not found: {config_path}")

    runtime_config_path = _write_runtime_config(
        cwd=cwd,
        config_path=config_path,
        mode=None,
        workers=args.workers,
    )
    env = os.environ.copy()
    print(f"[autowfo] runtime_config={runtime_config_path}")
    print(f"[autowfo] baseline workers={args.workers or 'config_default'}")
    _run_module("scripts.run_autowfo_baseline", cwd=cwd, env=env)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="autowfo", description="AUTOWFO one-command workflows")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run one sweep end-to-end")
    run_parser.add_argument("--config", required=True, help="Path to experiment config (JSON/YAML)")
    run_parser.add_argument(
        "--mode",
        choices=["combo", "refine"],
        default=None,
        help="Override search mode",
    )
    run_parser.add_argument("--workers", type=int, default=None, help="Override max_workers")
    run_parser.add_argument("--cwd", default=".", help="Working directory")
    run_parser.set_defaults(handler=_cmd_run)

    baseline_parser = subparsers.add_parser("baseline", help="Run combo+refine baseline workflow")
    baseline_parser.add_argument("--config", required=True, help="Path to experiment config (JSON/YAML)")
    baseline_parser.add_argument("--workers", type=int, default=None, help="Override max_workers")
    baseline_parser.add_argument("--cwd", default=".", help="Working directory")
    baseline_parser.set_defaults(handler=_cmd_baseline)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.handler(args))
