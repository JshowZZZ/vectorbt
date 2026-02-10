"""CLI entrypoint for AUTOWFO workflows."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _resolve_path(base: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        path = (base / path).resolve()
    return path


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


def _json_sha256(payload: Dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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


def _run_workflow(
    cwd: Path,
    config_path: Path,
    workflow: str,
    mode: Optional[str] = None,
    workers: Optional[int] = None,
) -> None:
    if workflow not in {"run", "baseline"}:
        raise ValueError(f"Unsupported workflow: {workflow}")

    runtime_config_path = _write_runtime_config(
        cwd=cwd,
        config_path=config_path,
        mode=mode if workflow == "run" else None,
        workers=workers,
    )
    env = os.environ.copy()

    if workflow == "run":
        if mode:
            env["VBT_SWEEP_MODE"] = mode
        print(f"[autowfo] runtime_config={runtime_config_path}")
        print(f"[autowfo] mode={mode or 'config_default'} workers={workers or 'config_default'}")
        _run_module("scripts.run_btc_regime_sweep", cwd=cwd, env=env)
        return

    print(f"[autowfo] runtime_config={runtime_config_path}")
    print(f"[autowfo] baseline workers={workers or 'config_default'}")
    _run_module("scripts.run_autowfo_baseline", cwd=cwd, env=env)


def _cmd_run(args: argparse.Namespace) -> int:
    cwd = Path(args.cwd).resolve()
    config_path = Path(args.config).resolve()
    if not config_path.exists():
        raise FileNotFoundError(f"config not found: {config_path}")

    _run_workflow(
        cwd=cwd,
        config_path=config_path,
        workflow="run",
        mode=args.mode,
        workers=args.workers,
    )
    return 0


def _cmd_baseline(args: argparse.Namespace) -> int:
    cwd = Path(args.cwd).resolve()
    config_path = Path(args.config).resolve()
    if not config_path.exists():
        raise FileNotFoundError(f"config not found: {config_path}")

    _run_workflow(
        cwd=cwd,
        config_path=config_path,
        workflow="baseline",
        mode=None,
        workers=args.workers,
    )
    return 0


def _parse_batch_jobs(
    plan_payload: Dict[str, Any],
    cwd: Path,
    plan_path: Path,
    workers_override: Optional[int],
) -> List[Dict[str, Any]]:
    jobs_raw = plan_payload.get("jobs")
    if not isinstance(jobs_raw, list) or not jobs_raw:
        raise ValueError("batch plan must contain non-empty 'jobs' list")

    defaults = plan_payload.get("defaults")
    if defaults is None:
        defaults = {}
    if not isinstance(defaults, dict):
        raise ValueError("batch plan 'defaults' must be object when provided")

    jobs: List[Dict[str, Any]] = []
    for idx, raw in enumerate(jobs_raw, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"batch job #{idx} must be object")

        name = str(raw.get("name") or f"job-{idx}")
        workflow = str(raw.get("workflow", defaults.get("workflow", "baseline"))).lower()
        if workflow not in {"run", "baseline"}:
            raise ValueError(f"batch job '{name}': workflow must be run|baseline")

        config_value = raw.get("config", defaults.get("config"))
        if not config_value:
            raise ValueError(f"batch job '{name}': missing config path")
        config_path = Path(str(config_value))
        if not config_path.is_absolute():
            config_path = (plan_path.parent / config_path).resolve()

        job_cwd_raw = raw.get("cwd", defaults.get("cwd"))
        if job_cwd_raw:
            job_cwd = Path(str(job_cwd_raw))
            if not job_cwd.is_absolute():
                job_cwd = (cwd / job_cwd).resolve()
        else:
            job_cwd = cwd

        mode_raw = raw.get("mode", defaults.get("mode"))
        mode = None if mode_raw in (None, "") else str(mode_raw).lower()
        if workflow == "baseline" and mode is not None:
            raise ValueError(f"batch job '{name}': mode override only valid for workflow=run")
        if workflow == "run" and mode not in {None, "combo", "refine"}:
            raise ValueError(f"batch job '{name}': mode must be combo|refine when provided")

        worker_raw = workers_override if workers_override is not None else raw.get("workers", defaults.get("workers"))
        workers = None if worker_raw in (None, "") else int(worker_raw)
        if workers is not None and workers <= 0:
            raise ValueError(f"batch job '{name}': workers must be > 0")

        jobs.append(
            {
                "name": name,
                "workflow": workflow,
                "config_path": config_path,
                "cwd": job_cwd,
                "mode": mode,
                "workers": workers,
            }
        )
    return jobs


def _preflight_batch_jobs(jobs: List[Dict[str, Any]], min_free_gb: float) -> None:
    missing_configs = [str(job["config_path"]) for job in jobs if not job["config_path"].exists()]
    if missing_configs:
        msg = "\n".join(missing_configs)
        raise FileNotFoundError(f"batch preflight failed: missing config files\n{msg}")

    missing_cwds = [str(job["cwd"]) for job in jobs if not job["cwd"].exists()]
    if missing_cwds:
        msg = "\n".join(missing_cwds)
        raise FileNotFoundError(f"batch preflight failed: missing cwd paths\n{msg}")

    if min_free_gb <= 0:
        return

    min_free_bytes = int(min_free_gb * (1024**3))
    for cwd in sorted({job["cwd"] for job in jobs}):
        usage = shutil.disk_usage(str(cwd))
        if usage.free < min_free_bytes:
            free_gb = usage.free / (1024**3)
            raise RuntimeError(
                f"batch preflight failed: insufficient disk at {cwd} ({free_gb:.2f}GB < {min_free_gb:.2f}GB)"
            )


def _load_batch_state(path: Path) -> Dict[str, Any]:
    default_state: Dict[str, Any] = {
        "version": 1,
        "created_utc": _utc_now_iso(),
        "updated_utc": _utc_now_iso(),
        "seen_keys": {},
        "history": [],
    }
    if not path.exists():
        return default_state

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default_state

    if not isinstance(payload, dict):
        return default_state
    if not isinstance(payload.get("seen_keys"), dict):
        payload["seen_keys"] = {}
    if not isinstance(payload.get("history"), list):
        payload["history"] = []
    payload.setdefault("version", 1)
    payload.setdefault("created_utc", _utc_now_iso())
    payload["updated_utc"] = _utc_now_iso()
    return payload


def _write_batch_state(path: Path, payload: Dict[str, Any]) -> None:
    payload["updated_utc"] = _utc_now_iso()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _latest_run_label(cwd: Path) -> Optional[str]:
    runs_dir = cwd / "artifacts" / "runs"
    if not runs_dir.exists():
        return None
    candidates = [p for p in runs_dir.iterdir() if p.is_dir()]
    if not candidates:
        return None
    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    return latest.name


def _compute_job_key(job: Dict[str, Any]) -> str:
    config_payload = _load_config(job["config_path"])
    key_payload = {
        "workflow": job["workflow"],
        "mode": job.get("mode"),
        "workers": job.get("workers"),
        "config_sha256": _json_sha256(config_payload),
    }
    return _json_sha256(key_payload)


def _cmd_batch(args: argparse.Namespace) -> int:
    cwd = Path(args.cwd).resolve()
    plan_path = Path(args.plan).resolve()
    if not plan_path.exists():
        raise FileNotFoundError(f"batch plan not found: {plan_path}")

    state_path = _resolve_path(cwd, args.state)
    plan_payload = _load_config(plan_path)
    jobs = _parse_batch_jobs(plan_payload, cwd=cwd, plan_path=plan_path, workers_override=args.workers)
    _preflight_batch_jobs(jobs, min_free_gb=float(args.min_free_gb))

    state = _load_batch_state(state_path)
    _write_batch_state(state_path, state)

    total = len(jobs)
    for idx, job in enumerate(jobs, start=1):
        job_key = _compute_job_key(job)
        label = f"[batch][{idx}/{total}] {job['name']}"

        if job_key in state["seen_keys"]:
            print(f"{label} skip (seen_key={job_key[:12]})")
            state["history"].append(
                {
                    "ts": _utc_now_iso(),
                    "status": "skipped_seen_key",
                    "job_key": job_key,
                    "job_name": job["name"],
                    "workflow": job["workflow"],
                    "config_path": str(job["config_path"]),
                }
            )
            _write_batch_state(state_path, state)
            continue

        print(
            f"{label} start workflow={job['workflow']} "
            f"config={job['config_path']} workers={job['workers'] or 'config_default'}"
        )
        before_label = _latest_run_label(job["cwd"])
        state["history"].append(
            {
                "ts": _utc_now_iso(),
                "status": "running",
                "job_key": job_key,
                "job_name": job["name"],
                "workflow": job["workflow"],
                "config_path": str(job["config_path"]),
            }
        )
        _write_batch_state(state_path, state)

        try:
            _run_workflow(
                cwd=job["cwd"],
                config_path=job["config_path"],
                workflow=job["workflow"],
                mode=job.get("mode"),
                workers=job.get("workers"),
            )
        except Exception as exc:
            state["history"].append(
                {
                    "ts": _utc_now_iso(),
                    "status": "failed",
                    "job_key": job_key,
                    "job_name": job["name"],
                    "workflow": job["workflow"],
                    "config_path": str(job["config_path"]),
                    "error": str(exc),
                }
            )
            _write_batch_state(state_path, state)
            print(f"{label} failed: {exc}")
            if args.continue_on_error:
                continue
            raise

        after_label = _latest_run_label(job["cwd"])
        run_label = after_label if after_label and after_label != before_label else None
        state["seen_keys"][job_key] = {
            "status": "done",
            "job_name": job["name"],
            "workflow": job["workflow"],
            "config_path": str(job["config_path"]),
            "mode": job.get("mode"),
            "workers": job.get("workers"),
            "finished_utc": _utc_now_iso(),
            "run_label": run_label,
        }
        state["history"].append(
            {
                "ts": _utc_now_iso(),
                "status": "done",
                "job_key": job_key,
                "job_name": job["name"],
                "workflow": job["workflow"],
                "config_path": str(job["config_path"]),
                "run_label": run_label,
            }
        )
        _write_batch_state(state_path, state)
        print(f"{label} done run_label={run_label or 'n/a'} seen_key={job_key[:12]}")

    print(f"[batch] finished jobs={total} seen_keys={len(state['seen_keys'])} state={state_path}")
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

    batch_parser = subparsers.add_parser("batch", help="Run multi-config batch plan sequentially")
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
    batch_parser.set_defaults(handler=_cmd_batch)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.handler(args))
