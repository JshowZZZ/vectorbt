"""CLI entrypoint for AUTOWFO workflows."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib import error as urllib_error
from urllib import request as urllib_request


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


def _list_run_labels(cwd: Path) -> Set[str]:
    runs_dir = cwd / "artifacts" / "runs"
    if not runs_dir.exists():
        return set()
    return {p.name for p in runs_dir.iterdir() if p.is_dir()}


def _resolve_gate_c_target_mode(
    *,
    workflow: str,
    mode: Optional[str],
    target_mode: Optional[str],
    config_payload: Dict[str, Any],
) -> str:
    if target_mode:
        mode_value = str(target_mode).strip().lower()
    elif workflow == "baseline":
        mode_value = "refine"
    elif mode:
        mode_value = str(mode).strip().lower()
    else:
        mode_value = str(config_payload.get("search_mode", "combo")).strip().lower()
    if mode_value not in {"combo", "refine"}:
        raise ValueError(f"unsupported target mode for Gate C: {mode_value}")
    return mode_value


def _resolve_gate_c_run_dir(cwd: Path, run_label: str, target_mode: str) -> Path:
    run_root = cwd / "artifacts" / "runs" / run_label
    mode_dir = run_root / target_mode
    if mode_dir.exists() and mode_dir.is_dir():
        return mode_dir
    if run_root.exists() and run_root.is_dir():
        return run_root
    raise FileNotFoundError(f"run directory not found for label={run_label} mode={target_mode}")


def _resolve_top10_csv_path(run_dir: Path, run_id: str) -> Path:
    if run_id:
        run_scoped = run_dir / f"param_sweep_top10_{run_id}.csv"
        if run_scoped.exists():
            return run_scoped

    candidates = sorted(run_dir.glob("param_sweep_top10_*.csv"))
    if candidates:
        return candidates[-1]

    plain = run_dir / "param_sweep_top10.csv"
    if plain.exists():
        return plain
    raise FileNotFoundError(f"top-N csv not found under {run_dir}")


def _compute_job_key(job: Dict[str, Any]) -> str:
    config_payload = _load_config(job["config_path"])
    key_payload = {
        "workflow": job["workflow"],
        "mode": job.get("mode"),
        "workers": job.get("workers"),
        "config_sha256": _json_sha256(config_payload),
    }
    return _json_sha256(key_payload)


def _run_batch_job_single(
    *,
    idx,
    total,
    job,
    state,
    state_path,
    lock,
):
    """Execute a single batch job.  Thread-safe when *lock* is provided.

    Returns a dict with ``status`` ('done', 'skipped', 'failed') and
    optional ``error`` message.
    """
    job_key = _compute_job_key(job)
    label = f"[batch][{idx}/{total}] {job['name']}"

    with lock:
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
            return {"status": "skipped", "job_key": job_key}

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

    # Run outside lock — this is the heavy subprocess execution
    try:
        _run_workflow(
            cwd=job["cwd"],
            config_path=job["config_path"],
            workflow=job["workflow"],
            mode=job.get("mode"),
            workers=job.get("workers"),
        )
    except Exception as exc:
        with lock:
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
        return {"status": "failed", "job_key": job_key, "error": str(exc)}

    with lock:
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
    return {"status": "done", "job_key": job_key, "run_label": run_label}


def _run_batch_jobs_parallel(
    *,
    jobs,
    state,
    state_path,
    parallel_jobs,
    continue_on_error,
):
    """Run batch jobs concurrently using ThreadPoolExecutor.

    Each job launches a subprocess via ``_run_workflow``, so the GIL is
    released during execution.  Batch state updates are serialized via
    a threading lock.
    """
    lock = threading.Lock()
    total = len(jobs)
    failed_jobs = []

    with ThreadPoolExecutor(max_workers=parallel_jobs) as executor:
        futures = {
            executor.submit(
                _run_batch_job_single,
                idx=idx,
                total=total,
                job=job,
                state=state,
                state_path=state_path,
                lock=lock,
            ): (idx, job)
            for idx, job in enumerate(jobs, start=1)
        }
        for future in as_completed(futures):
            result = future.result()
            if result["status"] == "failed":
                failed_jobs.append(result)
                if not continue_on_error:
                    # Cancel pending futures (best-effort)
                    for f in futures:
                        f.cancel()
                    raise RuntimeError(
                        f"batch job failed: {result.get('error', 'unknown')}; "
                        f"use --continue-on-error to skip failures"
                    )

    return failed_jobs


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

    parallel_jobs = getattr(args, "parallel_jobs", 1) or 1
    total = len(jobs)

    if parallel_jobs > 1:
        # ---- parallel path (ThreadPoolExecutor + subprocess) ----
        print(
            f"[batch] parallel mode: jobs={total} workers={parallel_jobs} "
            f"state={state_path}"
        )
        failed = _run_batch_jobs_parallel(
            jobs=jobs,
            state=state,
            state_path=state_path,
            parallel_jobs=parallel_jobs,
            continue_on_error=args.continue_on_error,
        )
        if failed and not args.continue_on_error:
            # _run_batch_jobs_parallel already raised; this is a safeguard
            raise RuntimeError(f"batch had {len(failed)} failure(s)")
        print(
            f"[batch] finished jobs={total} "
            f"seen_keys={len(state['seen_keys'])} "
            f"failures={len(failed)} state={state_path}"
        )
        return 1 if failed else 0

    # ---- sequential path (original) ----
    for idx, job in enumerate(jobs, start=1):
        lock = threading.Lock()  # no-op for sequential, reuse _run_batch_job_single
        result = _run_batch_job_single(
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
            raise RuntimeError(
                f"batch job failed: {result.get('error', 'unknown')}"
            )

    print(f"[batch] finished jobs={total} seen_keys={len(state['seen_keys'])} state={state_path}")
    return 0


def _slug_text(value: str) -> str:
    text = str(value).strip()
    if not text:
        return "unknown"
    out_chars = []
    for ch in text:
        if ch.isalnum() or ch in {"-", "_"}:
            out_chars.append(ch)
        else:
            out_chars.append("-")
    slug = "".join(out_chars)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "unknown"


def _extract_registry_untested_pairs(registry_payload: Dict[str, Any]) -> List[Dict[str, str]]:
    coverage = registry_payload.get("coverage")
    if not isinstance(coverage, dict):
        return []
    pairs = coverage.get("untested_pairs")
    if not isinstance(pairs, list):
        return []

    output: List[Dict[str, str]] = []
    seen = set()
    for raw in pairs:
        if not isinstance(raw, dict):
            continue
        timeframe = str(raw.get("timeframe", "")).strip()
        symbol = str(raw.get("symbol", "")).strip()
        if not timeframe or not symbol:
            continue
        key = (timeframe, symbol)
        if key in seen:
            continue
        seen.add(key)
        output.append({"timeframe": timeframe, "symbol": symbol})
    return output


def _compute_coverage_gaps(
    registry_payload: Dict[str, Any],
    target_timeframes: List[str],
    target_symbols: List[str],
) -> List[Dict[str, str]]:
    """Compute gap pairs from target dimensions minus tested pairs.

    Unlike ``_extract_registry_untested_pairs`` which only reads the
    stored ``coverage.untested_pairs``, this function performs a fresh
    cartesian-product calculation using externally supplied target
    dimensions.  This allows detecting gaps for timeframes/symbols that
    have never appeared in any run.
    """
    coverage = registry_payload.get("coverage")
    tested_set: set = set()
    if isinstance(coverage, dict):
        tested_raw = coverage.get("tested_pairs")
        if isinstance(tested_raw, list):
            for pair in tested_raw:
                if not isinstance(pair, dict):
                    continue
                timeframe = str(pair.get("timeframe", "")).strip()
                symbol = str(pair.get("symbol", "")).strip()
                if timeframe and symbol:
                    tested_set.add((timeframe, symbol))

    gaps: List[Dict[str, str]] = []
    for timeframe in sorted(target_timeframes):
        for symbol in sorted(target_symbols):
            if (timeframe, symbol) not in tested_set:
                gaps.append({"timeframe": timeframe, "symbol": symbol})
    return gaps


def _build_timeframe_days_map(
    registry_payload: Dict[str, Any],
    template_config: Dict[str, Any],
) -> Dict[str, int]:
    mapping: Dict[str, int] = {}

    runs = registry_payload.get("runs")
    if isinstance(runs, list):
        for entry in runs:
            if not isinstance(entry, dict):
                continue
            timeframes = entry.get("timeframes")
            if not isinstance(timeframes, list):
                continue
            for item in timeframes:
                if not isinstance(item, dict):
                    continue
                timeframe = str(item.get("timeframe", "")).strip()
                if not timeframe:
                    continue
                try:
                    days = int(item.get("days"))
                except Exception:
                    continue
                if days <= 0:
                    continue
                if timeframe not in mapping:
                    mapping[timeframe] = days

    template_timeframes = template_config.get("timeframes")
    if isinstance(template_timeframes, list):
        for item in template_timeframes:
            if not isinstance(item, dict):
                continue
            timeframe = str(item.get("timeframe", "")).strip()
            if not timeframe:
                continue
            try:
                days = int(item.get("days"))
            except Exception:
                continue
            if days <= 0:
                continue
            if timeframe not in mapping:
                mapping[timeframe] = days

    return mapping


def _cmd_plan(args: argparse.Namespace) -> int:
    cwd = Path(args.cwd).resolve()
    registry_path = _resolve_path(cwd, args.registry)
    template_config_path = _resolve_path(cwd, args.template_config)
    out_plan_path = _resolve_path(cwd, args.out_plan)
    out_config_dir = _resolve_path(cwd, args.out_config_dir)

    if not registry_path.exists():
        raise FileNotFoundError(f"registry not found: {registry_path}")
    if not template_config_path.exists():
        raise FileNotFoundError(f"template config not found: {template_config_path}")

    registry_payload = _load_config(registry_path)
    template_config = _load_config(template_config_path)

    # When --target-timeframes / --target-symbols are provided, compute
    # gaps from the full cartesian product of target dimensions minus
    # already-tested pairs.  This allows detecting gaps for timeframes
    # or symbols that have never appeared in any run (e.g. 1h).
    target_tf_raw = getattr(args, "target_timeframes", None)
    target_sym_raw = getattr(args, "target_symbols", None)
    if target_tf_raw or target_sym_raw:
        target_tf_list = [t.strip() for t in target_tf_raw.split(",") if t.strip()] if target_tf_raw else []
        target_sym_list = [s.strip() for s in target_sym_raw.split(",") if s.strip()] if target_sym_raw else []
        if not target_tf_list or not target_sym_list:
            raise ValueError("--target-timeframes and --target-symbols must both be provided when either is used")
        pairs = _compute_coverage_gaps(registry_payload, target_tf_list, target_sym_list)
    else:
        pairs = _extract_registry_untested_pairs(registry_payload)

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

    timeframe_days = _build_timeframe_days_map(registry_payload, template_config)

    # --timeframe-days overrides (e.g. "1h:90,2h:120")
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

        cfg_payload = json.loads(json.dumps(template_config, ensure_ascii=False))
        cfg_payload["timeframes"] = [{"timeframe": timeframe, "days": days}]
        cfg_payload["trade_symbols"] = [symbol]

        cfg_name = f"{idx:03d}_{_slug_text(timeframe)}_{_slug_text(symbol)}.json"
        cfg_path = out_config_dir / cfg_name
        cfg_path.write_text(json.dumps(cfg_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        job = {
            "name": f"gap-{idx:03d}-{_slug_text(timeframe)}-{_slug_text(symbol)}",
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
        "generated_utc": _utc_now_iso(),
        "source_registry": str(registry_path),
        "source_template_config": str(template_config_path),
        "job_count": len(jobs),
        "jobs": jobs,
    }
    out_plan_path.write_text(json.dumps(plan_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[plan] registry={registry_path}")
    print(f"[plan] template_config={template_config_path}")
    print(f"[plan] out_plan={out_plan_path}")
    print(f"[plan] out_config_dir={out_config_dir} jobs={len(jobs)}")
    if not jobs:
        print("[plan] no untested pairs found")
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    from scripts.autowfo import cross_run

    cwd = Path(args.cwd).resolve()
    artifacts_dir = _resolve_path(cwd, args.artifacts_dir)
    registry_path = _resolve_path(cwd, args.registry)
    out_html_path = _resolve_path(cwd, args.out_html)
    out_json_path = _resolve_path(cwd, args.out_json) if args.out_json else None

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


def _split_csv_fields(raw: Optional[str]) -> List[str]:
    if raw in (None, ""):
        return []
    return [part.strip() for part in str(raw).split(",") if part and str(part).strip()]


def _cmd_repro(args: argparse.Namespace) -> int:
    import pandas as pd

    from scripts.autowfo import reproducibility

    cwd = Path(args.cwd).resolve()
    reference_top = _resolve_path(cwd, args.reference_top)
    candidate_top = _resolve_path(cwd, args.candidate_top)
    out_json = _resolve_path(cwd, args.out_json)

    if not reference_top.exists():
        raise FileNotFoundError(f"reference top csv not found: {reference_top}")
    if not candidate_top.exists():
        raise FileNotFoundError(f"candidate top csv not found: {candidate_top}")

    identity_fields = _split_csv_fields(args.identity_fields) or list(reproducibility.DEFAULT_IDENTITY_FIELDS)
    metric_fields = _split_csv_fields(args.metric_fields) or list(reproducibility.DEFAULT_METRIC_FIELDS)

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
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
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


def _cmd_gate_c(args: argparse.Namespace) -> int:
    import pandas as pd

    from scripts.autowfo import reproducibility

    cwd = Path(args.cwd).resolve()
    config_path = _resolve_path(cwd, args.config)
    out_json = _resolve_path(cwd, args.out_json)
    if not config_path.exists():
        raise FileNotFoundError(f"config not found: {config_path}")

    config_payload = _load_config(config_path)
    workflow = str(args.workflow).strip().lower()
    if workflow not in {"run", "baseline"}:
        raise ValueError("workflow must be run or baseline")

    mode = None if args.mode in (None, "") else str(args.mode).strip().lower()
    if workflow == "baseline" and mode is not None:
        raise ValueError("mode override is only valid for workflow=run")
    if workflow == "run" and mode not in {None, "combo", "refine"}:
        raise ValueError("mode must be combo|refine when provided")

    workers = None if args.workers in (None, "") else int(args.workers)
    if workers is not None and workers <= 0:
        raise ValueError("workers must be > 0")

    target_mode = _resolve_gate_c_target_mode(
        workflow=workflow,
        mode=mode,
        target_mode=args.target_mode,
        config_payload=config_payload,
    )
    identity_fields = _split_csv_fields(args.identity_fields) or list(reproducibility.DEFAULT_IDENTITY_FIELDS)
    metric_fields = _split_csv_fields(args.metric_fields) or list(reproducibility.DEFAULT_METRIC_FIELDS)
    top_n = int(args.top_n)
    metric_abs_tolerance = float(args.metric_abs_tolerance)
    gate_label = str(args.label).strip() if args.label else datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    run_records: List[Dict[str, Any]] = []
    for run_index in (1, 2):
        before_labels: Set[str] = set()
        if workflow == "baseline":
            before_labels = _list_run_labels(cwd)

        _run_workflow(
            cwd=cwd,
            config_path=config_path,
            workflow=workflow,
            mode=mode if workflow == "run" else None,
            workers=workers,
        )

        run_label = ""
        if workflow == "baseline":
            after_labels = _list_run_labels(cwd)
            new_labels = sorted(after_labels - before_labels)
            run_label = new_labels[-1] if new_labels else (_latest_run_label(cwd) or "")
            if not run_label:
                raise RuntimeError("unable to determine run label after baseline workflow execution")
            run_dir = _resolve_gate_c_run_dir(cwd, run_label, target_mode=target_mode)
        else:
            run_dir = (cwd / "artifacts").resolve()

        run_metadata_path = run_dir / "run_metadata.json"
        if not run_metadata_path.exists():
            raise FileNotFoundError(f"run metadata not found: {run_metadata_path}")

        run_metadata = _load_config(run_metadata_path)
        run_id = str(run_metadata.get("run_id", "")).strip()
        top_csv = _resolve_top10_csv_path(run_dir, run_id=run_id)
        schema_validation = reproducibility.validate_run_artifact_schema(run_dir)

        run_records.append(
            {
                "run_index": run_index,
                "run_label": run_label,
                "run_id": run_id,
                "run_dir": str(run_dir),
                "top_csv": str(top_csv),
                "run_metadata_path": str(run_metadata_path),
                "schema_validation": schema_validation,
            }
        )

    reference_df = pd.read_csv(run_records[0]["top_csv"], low_memory=False)
    candidate_df = pd.read_csv(run_records[1]["top_csv"], low_memory=False)
    reproducibility_payload = reproducibility.compare_top_n_stability(
        reference_df=reference_df,
        candidate_df=candidate_df,
        top_n=top_n,
        identity_fields=identity_fields,
        metric_fields=metric_fields,
        metric_abs_tolerance=metric_abs_tolerance,
    )

    schema_valid = all(bool(record["schema_validation"].get("valid")) for record in run_records)
    gate_c_passed = bool(reproducibility_payload.get("stable")) and schema_valid

    report_payload: Dict[str, Any] = {
        "generated_utc": _utc_now_iso(),
        "gate_c_label": gate_label,
        "config_path": str(config_path),
        "workflow": workflow,
        "mode": mode,
        "target_mode": target_mode,
        "workers": workers,
        "top_n": top_n,
        "metric_abs_tolerance": metric_abs_tolerance,
        "identity_fields": identity_fields,
        "metric_fields": metric_fields,
        "runs": run_records,
        "schema_valid": schema_valid,
        "reproducibility": reproducibility_payload,
        "gate_c_passed": gate_c_passed,
    }

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[gate-c] config={config_path}")
    print(f"[gate-c] workflow={workflow} mode={mode or 'config_default'} target_mode={target_mode}")
    print(
        f"[gate-c] run1={run_records[0]['run_label'] or 'n/a'} "
        f"run_dir={run_records[0]['run_dir']} top={run_records[0]['top_csv']}"
    )
    print(
        f"[gate-c] run2={run_records[1]['run_label'] or 'n/a'} "
        f"run_dir={run_records[1]['run_dir']} top={run_records[1]['top_csv']}"
    )
    print(f"[gate-c] out_json={out_json}")
    print(
        "[gate-c] schema_valid={schema_valid} stable={stable} gate_c_passed={gate_c_passed} "
        "overlap_rows={overlap}/{top_n}".format(
            schema_valid=schema_valid,
            stable=reproducibility_payload.get("stable"),
            gate_c_passed=gate_c_passed,
            overlap=reproducibility_payload.get("overlap_rows", 0),
            top_n=top_n,
        )
    )
    return 0


# ---------------------------------------------------------------------------
#  AWF-040: Cron notifications (Webhook / Telegram + Top-N diff + freshness)
# ---------------------------------------------------------------------------


def _safe_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_datetime_utc(raw_value: Any) -> Optional[datetime]:
    text = str(raw_value or "").strip()
    if not text:
        return None

    candidates = [text]
    if " " in text and "T" not in text:
        candidates.insert(0, text.replace(" ", "T"))

    for candidate in candidates:
        try:
            dt = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        except ValueError:
            dt = None
        if dt is not None:
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _trim_text(text: str, max_len: int = 96) -> str:
    raw = str(text or "").strip()
    if len(raw) <= max_len:
        return raw
    return f"{raw[: max_len - 3]}..."


def _extract_top_entities(report_payload: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(report_payload, dict):
        return out

    combo_rows = report_payload.get("combo_stability")
    if isinstance(combo_rows, list):
        for row in combo_rows:
            if not isinstance(row, dict):
                continue
            combo_key = str(row.get("combo_key", "")).strip()
            if not combo_key:
                continue
            out.append(
                {
                    "key": combo_key,
                    "label": combo_key,
                    "kind": "combo",
                    "value": _safe_float(row.get("avg_oos_return_pct")),
                }
            )
            if len(out) >= limit:
                return out

    leaderboard_rows = report_payload.get("global_leaderboard")
    if isinstance(leaderboard_rows, list):
        for row in leaderboard_rows:
            if not isinstance(row, dict):
                continue
            run_id = str(row.get("run_id", "")).strip()
            if not run_id:
                continue
            out.append(
                {
                    "key": run_id,
                    "label": run_id,
                    "kind": "run",
                    "value": _safe_float(row.get("oos_avg_total_return_pct")),
                }
            )
            if len(out) >= limit:
                return out
    return out


def _build_top_change_lines(
    previous_top: List[Dict[str, Any]],
    current_top: List[Dict[str, Any]],
    *,
    limit: int,
) -> List[str]:
    if limit <= 0:
        return []

    prev_rank: Dict[str, int] = {}
    for idx, item in enumerate(previous_top[:limit], start=1):
        key = str(item.get("key", "")).strip()
        if key:
            prev_rank[key] = idx

    lines: List[str] = []
    for idx, item in enumerate(current_top[:limit], start=1):
        key = str(item.get("key", "")).strip()
        label = _trim_text(str(item.get("label", "")).strip())
        value = _safe_float(item.get("value"))

        old_rank = prev_rank.get(key)
        if old_rank is None:
            tag = "NEW"
        elif old_rank == idx:
            tag = "SAME"
        elif old_rank > idx:
            tag = f"UP {old_rank}->{idx}"
        else:
            tag = f"DOWN {old_rank}->{idx}"

        metric = "n/a" if value is None else f"{value:.4f}%"
        lines.append(f"{idx}. [{tag}] {label} ({metric})")

    if not lines:
        lines.append("n/a")
    return lines


def _default_cron_notify_state() -> Dict[str, Any]:
    return {
        "version": 1,
        "updated_utc": _utc_now_iso(),
        "last_top": [],
    }


def _read_cron_notify_state(path: Path) -> Dict[str, Any]:
    state = _default_cron_notify_state()
    if not path.exists():
        return state

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return state
    if not isinstance(payload, dict):
        return state

    raw_last_top = payload.get("last_top")
    last_top: List[Dict[str, Any]] = []
    if isinstance(raw_last_top, list):
        for item in raw_last_top:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key", "")).strip()
            if not key:
                continue
            last_top.append(
                {
                    "key": key,
                    "label": str(item.get("label", key)),
                    "kind": str(item.get("kind", "")).strip() or "combo",
                    "value": _safe_float(item.get("value")),
                }
            )

    state["version"] = int(payload.get("version", 1) or 1)
    state["updated_utc"] = str(payload.get("updated_utc", _utc_now_iso()))
    state["last_top"] = last_top
    return state


def _write_cron_notify_state(path: Path, payload: Dict[str, Any]) -> None:
    state = _default_cron_notify_state()
    state.update(payload if isinstance(payload, dict) else {})
    state["updated_utc"] = _utc_now_iso()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_freshness_alert(artifacts_dir: Path, threshold_days: int) -> Dict[str, Any]:
    threshold_days = max(1, int(threshold_days))
    state_path = artifacts_dir / "data_refresh_state.json"
    now_utc = datetime.now(timezone.utc)
    output: Dict[str, Any] = {
        "checked": False,
        "alert": False,
        "threshold_days": threshold_days,
        "stale": [],
    }
    if not state_path.exists():
        return output

    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return output
    if not isinstance(payload, dict):
        return output

    timeframe_data_end = payload.get("timeframe_data_end")
    if not isinstance(timeframe_data_end, dict):
        return output

    stale_rows: List[Dict[str, Any]] = []
    for timeframe, raw_mark in timeframe_data_end.items():
        dt = _parse_datetime_utc(raw_mark)
        if dt is None:
            continue
        age_seconds = max(0.0, (now_utc - dt).total_seconds())
        age_days = int(age_seconds // 86400)
        if age_days > threshold_days:
            stale_rows.append(
                {
                    "timeframe": str(timeframe),
                    "data_end": str(raw_mark),
                    "days_stale": age_days,
                }
            )

    stale_rows.sort(key=lambda item: int(item.get("days_stale", 0)), reverse=True)
    output["checked"] = True
    output["stale"] = stale_rows
    output["alert"] = bool(stale_rows)
    return output


def _format_freshness_line(freshness_alert: Dict[str, Any]) -> str:
    if not freshness_alert.get("checked"):
        return "freshness=unknown (data_refresh_state missing)"
    if not freshness_alert.get("alert"):
        return "freshness=ok"

    stale_rows = freshness_alert.get("stale")
    if not isinstance(stale_rows, list):
        stale_rows = []
    preview = []
    for row in stale_rows[:3]:
        timeframe = str(row.get("timeframe", "")).strip()
        days = int(row.get("days_stale", 0) or 0)
        if timeframe:
            preview.append(f"{timeframe}:{days}d")
    threshold_days = int(freshness_alert.get("threshold_days", 7) or 7)
    joined = ", ".join(preview) if preview else "n/a"
    return f"freshness=ALERT(>{threshold_days}d) {joined}"


def _post_json(url: str, payload: Dict[str, Any], timeout_seconds: int = 10) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib_request.Request(
        url=url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    with urllib_request.urlopen(req, timeout=timeout_seconds) as resp:  # nosec B310
        status = int(getattr(resp, "status", 200))
        if status >= 400:
            raise RuntimeError(f"http {status}")


def _dispatch_cron_notifications(
    *,
    webhook_urls: List[str],
    telegram_token: str,
    telegram_chat_id: str,
    message_text: str,
    payload: Dict[str, Any],
) -> List[str]:
    errors: List[str] = []

    for webhook_url in webhook_urls:
        try:
            _post_json(webhook_url, payload)
        except Exception as exc:
            errors.append(f"webhook {webhook_url}: {exc}")

    if telegram_token and telegram_chat_id:
        tg_url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
        tg_payload = {
            "chat_id": telegram_chat_id,
            "text": message_text,
            "disable_web_page_preview": True,
        }
        try:
            _post_json(tg_url, tg_payload)
        except (urllib_error.HTTPError, urllib_error.URLError, RuntimeError, ValueError) as exc:
            errors.append(f"telegram: {exc}")
    return errors


def _build_cron_notification_text(
    *,
    cycle_number: int,
    status: str,
    cycle_result: Dict[str, Any],
    top_change_lines: List[str],
    freshness_alert: Dict[str, Any],
) -> str:
    lines = [
        f"[AUTOWFO][cron] cycle {cycle_number} {status}",
        "plan_jobs={plan_jobs} batch_ok={batch_ok} report_ok={report_ok}".format(
            plan_jobs=cycle_result.get("plan_jobs", 0),
            batch_ok=bool(cycle_result.get("batch_ok")),
            report_ok=bool(cycle_result.get("report_ok")),
        ),
        "top:",
    ]
    lines.extend(top_change_lines or ["n/a"])
    lines.append(_format_freshness_line(freshness_alert))
    err = str(cycle_result.get("error") or "").strip()
    if err:
        lines.append(f"error={_trim_text(err, max_len=200)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
#  AWF-027: Automated patrol cycle
# ---------------------------------------------------------------------------


def _run_patrol_cycle(
    cwd: Path,
    registry_path: Path,
    template_config_path: Path,
    plan_out: Path,
    plan_config_dir: Path,
    batch_state_path: Path,
    report_html_path: Path,
    report_json_path: Optional[Path],
    *,
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
    """Execute one plan → batch → report cycle.

    Returns a summary dict with ``plan_jobs``, ``batch_ok``, ``report_ok``,
    ``error`` (None on success).
    """
    result: Dict[str, Any] = {
        "cycle_start_utc": _utc_now_iso(),
        "plan_jobs": 0,
        "batch_ok": False,
        "report_ok": False,
        "error": None,
        "top_entities": [],
    }

    # --- 1. Plan -----------------------------------------------------------
    try:
        registry_payload = _load_config(registry_path)
        template_config = _load_config(template_config_path)

        if target_timeframes and target_symbols:
            pairs = _compute_coverage_gaps(registry_payload, list(target_timeframes), list(target_symbols))
        else:
            pairs = _extract_registry_untested_pairs(registry_payload)

        if max_jobs and max_jobs > 0:
            pairs = pairs[:max_jobs]

        td_map = _build_timeframe_days_map(registry_payload, template_config)
        if timeframe_days_map:
            td_map.update(timeframe_days_map)

        default_days = 60
        template_timeframes_raw = template_config.get("timeframes")
        if isinstance(template_timeframes_raw, list):
            for item in template_timeframes_raw:
                if isinstance(item, dict):
                    try:
                        d = int(item.get("days"))
                    except Exception:
                        continue
                    if d > 0:
                        default_days = d
                        break

        plan_config_dir.mkdir(parents=True, exist_ok=True)
        jobs = []
        for idx, pair in enumerate(pairs, start=1):
            timeframe = pair["timeframe"]
            symbol = pair["symbol"]
            days = int(td_map.get(timeframe, default_days))

            cfg_payload = json.loads(json.dumps(template_config, ensure_ascii=False))
            cfg_payload["timeframes"] = [{"timeframe": timeframe, "days": days}]
            cfg_payload["trade_symbols"] = [symbol]

            cfg_name = f"cron_{idx:03d}_{_slug_text(timeframe)}_{_slug_text(symbol)}.json"
            cfg_path = plan_config_dir / cfg_name
            cfg_path.write_text(json.dumps(cfg_payload, ensure_ascii=False, indent=2), encoding="utf-8")

            job: Dict[str, Any] = {
                "name": f"cron-{idx:03d}-{_slug_text(timeframe)}-{_slug_text(symbol)}",
                "workflow": workflow,
                "config": str(cfg_path),
            }
            if workflow == "run" and mode is not None:
                job["mode"] = mode
            if workers is not None:
                job["workers"] = workers
            jobs.append(job)

        plan_payload = {
            "generated_utc": _utc_now_iso(),
            "source_registry": str(registry_path),
            "source_template_config": str(template_config_path),
            "job_count": len(jobs),
            "jobs": jobs,
        }
        plan_out.parent.mkdir(parents=True, exist_ok=True)
        plan_out.write_text(json.dumps(plan_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        result["plan_jobs"] = len(jobs)
        print(f"[cron:plan] generated {len(jobs)} jobs → {plan_out}")
    except Exception as exc:
        result["error"] = f"plan failed: {exc}"
        print(f"[cron:plan] ERROR: {exc}")
        return result

    # If no jobs, skip batch and go straight to report
    if not jobs:
        print("[cron:plan] no untested pairs — skipping batch")
        result["batch_ok"] = True
    else:
        # --- 2. Batch ----------------------------------------------------------
        try:
            parsed_jobs = _parse_batch_jobs(plan_payload, cwd, plan_out, workers)
            state = _load_batch_state(batch_state_path)

            if parallel_jobs > 1:
                failed = _run_batch_jobs_parallel(
                    jobs=parsed_jobs,
                    state=state,
                    state_path=batch_state_path,
                    parallel_jobs=parallel_jobs,
                    continue_on_error=continue_on_error,
                )
                result["batch_ok"] = not failed
            else:
                all_ok = True
                for idx, job_entry in enumerate(parsed_jobs, start=1):
                    lock = threading.Lock()
                    job_result = _run_batch_job_single(
                        idx=idx,
                        total=len(parsed_jobs),
                        job=job_entry,
                        state=state,
                        state_path=batch_state_path,
                        lock=lock,
                    )
                    if job_result["status"] == "failed":
                        all_ok = False
                        if not continue_on_error:
                            break
                result["batch_ok"] = all_ok
            print(f"[cron:batch] completed {len(jobs)} jobs")
        except Exception as exc:
            result["error"] = f"batch failed: {exc}"
            print(f"[cron:batch] ERROR: {exc}")
            if not continue_on_error:
                return result
            # Still attempt report even if batch partial-failed
            result["batch_ok"] = False

    # --- 3. Report ---------------------------------------------------------
    try:
        from scripts.autowfo import cross_run

        artifacts_dir = cwd / "artifacts"
        if not artifacts_dir.exists():
            artifacts_dir.mkdir(parents=True, exist_ok=True)

        report_payload = cross_run.write_cross_run_reports(
            artifacts_dir=artifacts_dir,
            registry_path=registry_path,
            out_html_path=report_html_path,
            out_json_path=report_json_path,
            top_n=top_n,
        )
        result["top_entities"] = _extract_top_entities(report_payload, limit=max(1, int(top_n)))
        result["report_ok"] = True
        print(f"[cron:report] → {report_html_path}")
    except Exception as exc:
        result["error"] = f"report failed: {exc}"
        print(f"[cron:report] ERROR: {exc}")

    result["cycle_end_utc"] = _utc_now_iso()
    return result


def _cmd_cron(args: argparse.Namespace) -> int:
    """Automated patrol cycle: plan → batch → report, optionally repeating."""
    cwd = Path(args.cwd).resolve()
    registry_path = _resolve_path(cwd, args.registry)
    template_config_path = _resolve_path(cwd, args.template_config)
    plan_out = _resolve_path(cwd, args.plan_out)
    plan_config_dir = _resolve_path(cwd, args.plan_config_dir)
    batch_state_path = _resolve_path(cwd, args.batch_state)
    report_html = _resolve_path(cwd, args.report_html)
    report_json = _resolve_path(cwd, args.report_json) if args.report_json else None

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
    webhook_urls = _split_csv_fields(args.notify_webhook)
    telegram_token = str(args.notify_telegram_token or "").strip()
    telegram_chat_id = str(args.notify_telegram_chat_id or "").strip()
    notify_top_n = max(1, int(args.notify_top_n))
    freshness_alert_days = max(1, int(args.freshness_alert_days))
    notify_state_path = _resolve_path(cwd, args.notify_state)
    notifications_enabled = bool(webhook_urls or (telegram_token and telegram_chat_id))
    notify_state = _read_cron_notify_state(notify_state_path) if notifications_enabled else _default_cron_notify_state()

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

    while True:
        cycle_count += 1
        print(f"\n{'='*60}")
        print(f"[cron] cycle {cycle_count} started at {_utc_now_iso()}")
        print(f"{'='*60}")

        cycle_result = _run_patrol_cycle(
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
        status = "OK" if cycle_result.get("batch_ok") and cycle_result.get("report_ok") else "PARTIAL"
        print(f"[cron] cycle {cycle_count} {status}: "
              f"plan_jobs={cycle_result['plan_jobs']} "
              f"batch_ok={cycle_result['batch_ok']} "
              f"report_ok={cycle_result['report_ok']}")
        if cycle_result.get("error"):
            print(f"[cron] error: {cycle_result['error']}")

        prev_top = notify_state.get("last_top")
        if not isinstance(prev_top, list):
            prev_top = []
        current_top_raw = cycle_result.get("top_entities")
        current_top = current_top_raw if isinstance(current_top_raw, list) else []
        current_top = current_top[:notify_top_n]
        top_change_lines = _build_top_change_lines(prev_top, current_top, limit=notify_top_n)
        freshness_alert = _build_freshness_alert(cwd / "artifacts", threshold_days=freshness_alert_days)
        cycle_result["top_change_lines"] = top_change_lines
        cycle_result["freshness_alert"] = freshness_alert

        if notifications_enabled:
            notify_status = "ALERT" if status != "OK" or freshness_alert.get("alert") else "OK"
            message_text = _build_cron_notification_text(
                cycle_number=cycle_count,
                status=notify_status,
                cycle_result=cycle_result,
                top_change_lines=top_change_lines,
                freshness_alert=freshness_alert,
            )
            notify_payload = {
                "event": "autowfo_cron_cycle",
                "generated_utc": _utc_now_iso(),
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
            notify_errors = _dispatch_cron_notifications(
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
            _write_cron_notify_state(notify_state_path, notify_state)

        cycle_log.append(cycle_result)
        # Persist cycle log
        log_path = cwd / "artifacts" / "cron_cycle_log.json"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(json.dumps(cycle_log, ensure_ascii=False, indent=2), encoding="utf-8")

        if max_cycles > 0 and cycle_count >= max_cycles:
            print(f"[cron] reached max_cycles={max_cycles}, stopping")
            break

        if interval_minutes <= 0:
            break

        print(f"[cron] sleeping {interval_minutes} minutes until next cycle...")
        time.sleep(interval_minutes * 60)

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
    batch_parser.set_defaults(handler=_cmd_batch)

    plan_parser = subparsers.add_parser("plan", help="Generate batch plan from run registry coverage gaps")
    plan_parser.add_argument(
        "--registry",
        default="artifacts/run_registry.json",
        help="Path to run registry JSON",
    )
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
    plan_parser.add_argument(
        "--max-jobs",
        type=int,
        default=0,
        help="Limit number of planned jobs (0 means no limit)",
    )
    plan_parser.add_argument(
        "--workflow",
        choices=["run", "baseline"],
        default="baseline",
        help="Workflow type to use in generated batch jobs",
    )
    plan_parser.add_argument(
        "--mode",
        choices=["combo", "refine"],
        default=None,
        help="Mode for workflow=run",
    )
    plan_parser.add_argument("--workers", type=int, default=None, help="Optional workers value for each generated job")
    plan_parser.add_argument(
        "--target-timeframes",
        default=None,
        help="Comma-separated target timeframes for coverage (e.g. 1h,2h,4h). "
             "When provided together with --target-symbols, gaps are computed "
             "as cartesian product minus already-tested pairs.",
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
    plan_parser.set_defaults(handler=_cmd_plan)

    report_parser = subparsers.add_parser("report", help="Generate cross-run dashboard report from run registry")
    report_parser.add_argument(
        "--registry",
        default="artifacts/run_registry.json",
        help="Path to run registry JSON",
    )
    report_parser.add_argument(
        "--artifacts-dir",
        default="artifacts",
        help="Artifacts root directory",
    )
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
    report_parser.add_argument(
        "--top-n",
        type=int,
        default=20,
        help="Top-N rows for leaderboard and combo-stability views",
    )
    report_parser.add_argument("--cwd", default=".", help="Working directory")
    report_parser.set_defaults(handler=_cmd_report)

    repro_parser = subparsers.add_parser(
        "repro",
        help="Compare two top-N CSV artifacts for reproducibility stability",
    )
    repro_parser.add_argument("--reference-top", required=True, help="Reference top-N CSV path")
    repro_parser.add_argument("--candidate-top", required=True, help="Candidate top-N CSV path")
    repro_parser.add_argument(
        "--out-json",
        default="artifacts/reproducibility_report.json",
        help="Output path for reproducibility JSON report",
    )
    repro_parser.add_argument(
        "--top-n",
        type=int,
        default=10,
        help="Top-N rows to compare",
    )
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
    repro_parser.set_defaults(handler=_cmd_repro)

    gate_c_parser = subparsers.add_parser(
        "gate-c",
        help="Run Gate C reproducibility workflow (dual run + schema validation + top-N comparison)",
    )
    gate_c_parser.add_argument("--config", required=True, help="Path to experiment config (JSON/YAML)")
    gate_c_parser.add_argument(
        "--workflow",
        choices=["run", "baseline"],
        default="run",
        help="Workflow to execute twice for reproducibility checks",
    )
    gate_c_parser.add_argument(
        "--mode",
        choices=["combo", "refine"],
        default=None,
        help="Optional mode override (workflow=run only)",
    )
    gate_c_parser.add_argument(
        "--target-mode",
        choices=["combo", "refine"],
        default=None,
        help="Artifact mode directory used for schema/top-N checks (default: run->mode/config, baseline->refine)",
    )
    gate_c_parser.add_argument("--workers", type=int, default=None, help="Override max_workers")
    gate_c_parser.add_argument(
        "--label",
        default="",
        help="Optional Gate C report label",
    )
    gate_c_parser.add_argument(
        "--out-json",
        default="artifacts/reproducibility/gate_c_report.json",
        help="Output path for Gate C report JSON",
    )
    gate_c_parser.add_argument(
        "--top-n",
        type=int,
        default=10,
        help="Top-N rows to compare",
    )
    gate_c_parser.add_argument(
        "--metric-abs-tolerance",
        type=float,
        default=1e-9,
        help="Absolute tolerance used for metric drift checks",
    )
    gate_c_parser.add_argument(
        "--identity-fields",
        default="",
        help="Comma-separated identity fields (default uses built-in identity schema)",
    )
    gate_c_parser.add_argument(
        "--metric-fields",
        default="",
        help="Comma-separated metric fields (default uses built-in reproducibility metrics)",
    )
    gate_c_parser.add_argument("--cwd", default=".", help="Working directory")
    gate_c_parser.set_defaults(handler=_cmd_gate_c)

    # AWF-027: cron patrol cycle
    cron_parser = subparsers.add_parser(
        "cron",
        help="Automated patrol cycle: plan → batch → report, optionally repeating on interval",
    )
    cron_parser.add_argument(
        "--registry",
        default="artifacts/run_registry.json",
        help="Path to run registry JSON",
    )
    cron_parser.add_argument(
        "--template-config",
        required=True,
        help="Template config for plan generation",
    )
    cron_parser.add_argument(
        "--plan-out",
        default="artifacts/batch_plan.cron.json",
        help="Output path for cron-generated batch plan",
    )
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
    cron_parser.add_argument(
        "--report-html",
        default="artifacts/cross_run_report.html",
        help="Output path for cross-run HTML report",
    )
    cron_parser.add_argument(
        "--report-json",
        default="artifacts/cross_run_report.json",
        help="Output path for cross-run JSON report (empty to disable)",
    )
    cron_parser.add_argument(
        "--workflow",
        choices=["run", "baseline"],
        default="run",
        help="Workflow for each planned job",
    )
    cron_parser.add_argument(
        "--mode",
        choices=["combo", "refine"],
        default="combo",
        help="Mode for workflow=run",
    )
    cron_parser.add_argument("--workers", type=int, default=None, help="Workers override per job")
    cron_parser.add_argument("--max-jobs", type=int, default=0, help="Max jobs per cycle (0=unlimited)")
    cron_parser.add_argument("--top-n", type=int, default=20, help="Top-N for report views")
    cron_parser.add_argument("--parallel-jobs", type=int, default=1, help="Concurrent batch jobs")
    cron_parser.add_argument(
        "--interval",
        type=int,
        default=0,
        help="Minutes between cycles (0 = run once)",
    )
    cron_parser.add_argument(
        "--max-cycles",
        type=int,
        default=1,
        help="Maximum number of patrol cycles (0 = unlimited until interrupted)",
    )
    cron_parser.add_argument(
        "--target-timeframes",
        default=None,
        help="Comma-separated target timeframes (e.g. 1h,2h,4h)",
    )
    cron_parser.add_argument(
        "--target-symbols",
        default=None,
        help="Comma-separated target symbols (e.g. ETH/USDT,BNB/USDT)",
    )
    cron_parser.add_argument(
        "--timeframe-days",
        default=None,
        help="Override days-per-timeframe mapping (e.g. 1h:90,2h:120,4h:180)",
    )
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
    cron_parser.add_argument(
        "--notify-top-n",
        type=int,
        default=3,
        help="Top-N entries used for change summary in notifications",
    )
    cron_parser.add_argument(
        "--freshness-alert-days",
        type=int,
        default=7,
        help="Alert threshold in days for stale timeframe data_end",
    )
    cron_parser.add_argument(
        "--notify-state",
        default="artifacts/cron_notify_state.json",
        help="Path to notification state JSON (stores previous top-N snapshot)",
    )
    cron_parser.add_argument("--cwd", default=".", help="Working directory")
    cron_parser.set_defaults(handler=_cmd_cron)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.handler(args))
