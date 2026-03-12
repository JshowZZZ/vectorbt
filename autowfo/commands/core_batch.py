"""Batch queue execution helpers for AUTOWFO commands."""

from __future__ import annotations

import json
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

from .core_utils import _json_sha256, _load_config, _utc_now_iso
from .core_workflow import _latest_run_label, _run_workflow

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

