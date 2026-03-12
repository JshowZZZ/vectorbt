"""Batch queue/runtime API helpers extracted for AWF-146."""

from __future__ import annotations

import csv
from collections import deque
import html
import json
import mimetypes
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys as _sys
import threading
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps
from http import HTTPStatus
from urllib.parse import parse_qs, urlparse


def _cp():
    return _sys.modules.get("scripts.control_panel")

LOG_MAX_LINES = 2000


_MUTABLE_GLOBALS = {
    "PROCESS",
    "TEST_PROCESS",
    "BATCH_PROCESS",
    "SYMBOL_CACHE",
    "TIMEFRAME_CACHE",
    "DATA_REFRESH_THREAD",
}
_PROTECTED_CP_GLOBALS = {
    "_cp",
    "_bind_cp_globals",
    "_sync_cp_globals",
    "_with_cp",
    "_MUTABLE_GLOBALS",
    "_PROTECTED_CP_GLOBALS",
    "try_handle_get",
    "try_handle_post",
    "__all__",
}


def _bind_cp_globals():
    cp = _cp()
    if cp is None:
        raise RuntimeError("scripts.control_panel module not loaded")
    g = globals()
    for key, value in cp.__dict__.items():
        if key.startswith("__") or key in _PROTECTED_CP_GLOBALS:
            continue
        g[key] = value
    return cp


def _sync_cp_globals(cp):
    g = globals()
    for name in _MUTABLE_GLOBALS:
        if name in g:
            setattr(cp, name, g[name])


def _with_cp(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        cp = _bind_cp_globals()
        try:
            return fn(*args, **kwargs)
        finally:
            _sync_cp_globals(cp)

    return wrapper


@_with_cp
def _batch_queue_path():
    return ARTIFACTS / "batch_queue.json"

@_with_cp
def _batch_plan_path():
    return ARTIFACTS / "control_panel_batch_plan.json"

@_with_cp
def _batch_state_path():
    return ARTIFACTS / "batch_state.json"

@_with_cp
def _batch_log_path():
    return ARTIFACTS / "batch_console.log"

@_with_cp
def _batch_default_queue():
    return {
        "version": 1,
        "next_id": 1,
        "updated_utc": _now_iso(),
        "jobs": [],
        "last_exit_code": "",
    }

@_with_cp
def _load_batch_queue():
    queue = _read_json_file(_batch_queue_path(), _batch_default_queue())
    if not isinstance(queue.get("jobs"), list):
        queue["jobs"] = []
    try:
        queue["next_id"] = max(1, int(queue.get("next_id", 1)))
    except Exception:
        queue["next_id"] = 1
    queue.setdefault("version", 1)
    queue.setdefault("last_exit_code", "")
    queue["updated_utc"] = _now_iso()
    return queue

@_with_cp
def _write_batch_queue(queue):
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    queue["updated_utc"] = _now_iso()
    _batch_queue_path().write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")

@_with_cp
def _batch_resolve_config_path(raw):
    config_raw = str(raw or "").strip()
    if not config_raw:
        raise ValueError("config path is required")
    path = Path(config_raw)
    if not path.is_absolute():
        path = (ROOT / path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"config not found: {path}")
    return path

@_with_cp
def _batch_unique_name(queue, base_name):
    existing = {str(job.get("name", "")) for job in queue.get("jobs", [])}
    if base_name not in existing:
        return base_name
    suffix = 2
    while True:
        candidate = f"{base_name}-{suffix}"
        if candidate not in existing:
            return candidate
        suffix += 1

@_with_cp
def _batch_summarize_jobs(jobs):
    summary = {
        "queued": 0,
        "submitted": 0,
        "running": 0,
        "done": 0,
        "failed": 0,
        "skipped_seen_key": 0,
        "cancelled": 0,
    }
    for job in jobs:
        status = str(job.get("status", "")).strip()
        if status in summary:
            summary[status] += 1
    summary["total"] = len(jobs)
    return summary

@_with_cp
def _read_batch_log_tail(max_lines=LOG_MAX_LINES):
    path = _batch_log_path()
    if not path.exists():
        return ""
    lines = deque(maxlen=max_lines)
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            lines.append(line.rstrip("\n"))
    return "\n".join(lines)

@_with_cp
def _sync_batch_queue_with_state(queue):
    state = _read_json_file(_batch_state_path(), {"history": []})
    history = state.get("history")
    if not isinstance(history, list):
        history = []

    changed = False
    jobs_by_name = {}
    for job in queue.get("jobs", []):
        name = str(job.get("name", ""))
        if name:
            jobs_by_name[name] = job

    latest_event_by_name = {}
    for event in history:
        if not isinstance(event, dict):
            continue
        name = str(event.get("job_name", "")).strip()
        if not name:
            continue
        latest_event_by_name[name] = event

    for name, event in latest_event_by_name.items():
        job = jobs_by_name.get(name)
        if job is None:
            continue
        event_status = str(event.get("status", "")).strip()
        event_ts = str(event.get("ts") or _now_iso())
        current_status = str(job.get("status", "queued"))

        if event_status == "running":
            if current_status != "running":
                job["status"] = "running"
                changed = True
            if not job.get("started_utc"):
                job["started_utc"] = event_ts
                changed = True
            continue

        if event_status == "done":
            if current_status != "done":
                job["status"] = "done"
                changed = True
            if not job.get("started_utc"):
                job["started_utc"] = event_ts
                changed = True
            if job.get("finished_utc") != event_ts:
                job["finished_utc"] = event_ts
                changed = True
            run_label = str(event.get("run_label") or "")
            if run_label and job.get("run_label") != run_label:
                job["run_label"] = run_label
                changed = True
            if job.get("error"):
                job["error"] = ""
                changed = True
            continue

        if event_status == "failed":
            if current_status != "failed":
                job["status"] = "failed"
                changed = True
            if not job.get("started_utc"):
                job["started_utc"] = event_ts
                changed = True
            if job.get("finished_utc") != event_ts:
                job["finished_utc"] = event_ts
                changed = True
            err = str(event.get("error") or "")
            if job.get("error") != err:
                job["error"] = err
                changed = True
            continue

        if event_status == "skipped_seen_key":
            if current_status != "skipped_seen_key":
                job["status"] = "skipped_seen_key"
                changed = True
            if not job.get("started_utc"):
                job["started_utc"] = event_ts
                changed = True
            if job.get("finished_utc") != event_ts:
                job["finished_utc"] = event_ts
                changed = True
            if job.get("error"):
                job["error"] = ""
                changed = True

    if not _is_batch_running():
        now_iso = _now_iso()
        for job in queue.get("jobs", []):
            if str(job.get("status", "")) in {"submitted", "running"}:
                job["status"] = "cancelled"
                job["finished_utc"] = now_iso
                changed = True

    return changed

@_with_cp
def _batch_status_payload():
    queue = _load_batch_queue()
    changed = _sync_batch_queue_with_state(queue)

    with BATCH_PROCESS_LOCK:
        global BATCH_PROCESS
        running = _is_batch_running()
        if not running and BATCH_PROCESS is not None and BATCH_PROCESS.poll() is not None:
            rc = BATCH_PROCESS.returncode
            queue["last_exit_code"] = "" if rc is None else str(rc)
            BATCH_PROCESS = None
            changed = True

    if changed:
        _write_batch_queue(queue)

    jobs = sorted(queue.get("jobs", []), key=lambda item: int(item.get("id", 0)))
    summary = _batch_summarize_jobs(jobs)
    return {
        "running": _is_batch_running(),
        "summary": summary,
        "jobs": jobs,
        "state_path": str(_batch_state_path().relative_to(ROOT)),
        "plan_path": str(_batch_plan_path().relative_to(ROOT)),
        "log_path": str(_batch_log_path().relative_to(ROOT)),
        "last_exit_code": str(queue.get("last_exit_code", "")),
        "updated_utc": _now_iso(),
    }

@_with_cp
def _batch_enqueue(payload):
    if not isinstance(payload, dict):
        return False, "invalid payload", None

    workflow = str(payload.get("workflow", "baseline")).strip().lower()
    if workflow not in {"run", "baseline"}:
        return False, "workflow must be run or baseline", None

    mode_raw = payload.get("mode")
    mode = None if mode_raw in (None, "") else str(mode_raw).strip().lower()
    if workflow == "baseline" and mode is not None:
        return False, "mode is only valid for workflow=run", None
    if workflow == "run" and mode not in {None, "combo", "refine"}:
        return False, "mode must be combo or refine", None

    workers = None
    workers_raw = payload.get("workers")
    if workers_raw not in (None, ""):
        try:
            workers = int(workers_raw)
        except Exception:
            return False, "workers must be integer", None
        if workers <= 0:
            return False, "workers must be > 0", None

    try:
        config_path = _batch_resolve_config_path(payload.get("config"))
    except Exception as exc:
        return False, str(exc), None

    queue = _load_batch_queue()
    try:
        job_id = int(queue.get("next_id", 1))
    except Exception:
        job_id = 1
    queue["next_id"] = job_id + 1

    default_name = f"job-{job_id:04d}"
    base_name = str(payload.get("name") or default_name).strip()
    job_name = _batch_unique_name(queue, base_name)
    created_utc = _now_iso()
    job = {
        "id": job_id,
        "name": job_name,
        "workflow": workflow,
        "mode": mode or "",
        "workers": workers,
        "config": str(config_path),
        "status": "queued",
        "created_utc": created_utc,
        "started_utc": "",
        "finished_utc": "",
        "run_label": "",
        "error": "",
    }
    queue["jobs"].append(job)
    _write_batch_queue(queue)
    return True, "job enqueued", job

@_with_cp
def _batch_remove(job_id):
    queue = _load_batch_queue()
    removed = None
    kept = []
    for job in queue.get("jobs", []):
        try:
            current_id = int(job.get("id", -1))
        except Exception:
            current_id = -1
        if current_id != job_id:
            kept.append(job)
            continue
        if str(job.get("status", "")) in {"running", "submitted"}:
            return False, "cannot remove running/submitted job"
        removed = job

    if removed is None:
        return False, "job not found"
    queue["jobs"] = kept
    _write_batch_queue(queue)
    return True, "job removed"

@_with_cp
def _batch_clear():
    if _is_batch_running():
        return False, "batch is running"
    queue = _batch_default_queue()
    _write_batch_queue(queue)
    return True, "queue cleared"

@_with_cp
def _batch_start():
    if _is_running():
        return False, "single run is active"
    with BATCH_PROCESS_LOCK:
        global BATCH_PROCESS
        if _is_batch_running():
            return False, "batch already running"

        queue = _load_batch_queue()
        changed = _sync_batch_queue_with_state(queue)
        pending_jobs = [job for job in queue.get("jobs", []) if str(job.get("status", "")) == "queued"]
        if not pending_jobs:
            if changed:
                _write_batch_queue(queue)
            return False, "no queued jobs"

        plan_jobs = []
        for job in pending_jobs:
            job["status"] = "submitted"
            job["started_utc"] = ""
            job["finished_utc"] = ""
            job["run_label"] = ""
            job["error"] = ""
            plan_jobs.append(
                {
                    "name": job["name"],
                    "workflow": job["workflow"],
                    "config": job["config"],
                    "mode": job["mode"] or None,
                    "workers": job["workers"],
                }
            )
        _write_batch_queue(queue)

        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        _batch_plan_path().write_text(
            json.dumps({"jobs": plan_jobs}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        log_f = _batch_log_path().open("a", encoding="utf-8")
        cmd = [
            _python_path(),
            "-m",
            "autowfo",
            "batch",
            "--plan",
            str(_batch_plan_path()),
            "--cwd",
            str(ROOT),
            "--state",
            str(_batch_state_path()),
            "--min-free-gb",
            str(BATCH_DEFAULT_MIN_FREE_GB),
            "--continue-on-error",
        ]
        BATCH_PROCESS = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            stdout=log_f,
            stderr=subprocess.STDOUT,
        )
    return True, "batch started"

@_with_cp
def _batch_cancel():
    with BATCH_PROCESS_LOCK:
        global BATCH_PROCESS
        if not _is_batch_running():
            return False, "batch is not running"

        proc = BATCH_PROCESS
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        BATCH_PROCESS = None

    queue = _load_batch_queue()
    now_iso = _now_iso()
    changed = False
    for job in queue.get("jobs", []):
        if str(job.get("status", "")) in {"submitted", "running"}:
            job["status"] = "cancelled"
            job["finished_utc"] = now_iso
            changed = True
    if changed:
        _write_batch_queue(queue)
    return True, "batch cancelled"


def try_handle_get(handler, _parsed, path):
    """Handle batch-related GET endpoints. Return True when handled."""
    if path == "/batch/queue.json":
        return handler._send(
            json.dumps(_batch_status_payload(), ensure_ascii=False),
            "application/json; charset=utf-8",
        ) or True
    if path == "/batch/log-tail.txt":
        return handler._send(_read_batch_log_tail(), "text/plain; charset=utf-8") or True
    return False


def try_handle_post(handler, parsed):
    """Handle batch-related POST endpoints. Return True when handled."""
    if parsed.path == "/batch/start":
        ok, msg = _batch_start()
        handler._send(
            json.dumps({"ok": ok, "message": msg}, ensure_ascii=False),
            "application/json; charset=utf-8",
            status=HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST,
        )
        return True
    if parsed.path == "/batch/cancel":
        ok, msg = _batch_cancel()
        handler._send(
            json.dumps({"ok": ok, "message": msg}, ensure_ascii=False),
            "application/json; charset=utf-8",
            status=HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST,
        )
        return True
    if parsed.path == "/batch/clear":
        ok, msg = _batch_clear()
        handler._send(
            json.dumps({"ok": ok, "message": msg}, ensure_ascii=False),
            "application/json; charset=utf-8",
            status=HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST,
        )
        return True
    if parsed.path == "/batch/enqueue":
        try:
            payload = handler._read_json_payload()
            ok, msg, job = _batch_enqueue(payload)
            handler._send(
                json.dumps({"ok": ok, "message": msg, "job": job}, ensure_ascii=False),
                "application/json; charset=utf-8",
                status=HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST,
            )
        except Exception as exc:
            handler._send(
                json.dumps({"ok": False, "message": f"enqueue failed: {exc}"}, ensure_ascii=False),
                "application/json; charset=utf-8",
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
        return True
    if parsed.path == "/batch/remove":
        try:
            payload = handler._read_json_payload()
            job_id = int(payload.get("job_id"))
            ok, msg = _batch_remove(job_id)
            handler._send(
                json.dumps({"ok": ok, "message": msg}, ensure_ascii=False),
                "application/json; charset=utf-8",
                status=HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST,
            )
        except Exception as exc:
            handler._send(
                json.dumps({"ok": False, "message": f"remove failed: {exc}"}, ensure_ascii=False),
                "application/json; charset=utf-8",
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
        return True
    return False

__all__ = [
    "_batch_queue_path",
    "_batch_plan_path",
    "_batch_state_path",
    "_batch_log_path",
    "_batch_default_queue",
    "_load_batch_queue",
    "_write_batch_queue",
    "_batch_resolve_config_path",
    "_batch_unique_name",
    "_batch_summarize_jobs",
    "_read_batch_log_tail",
    "_sync_batch_queue_with_state",
    "_batch_status_payload",
    "_batch_enqueue",
    "_batch_remove",
    "_batch_clear",
    "_batch_start",
    "_batch_cancel",
    "try_handle_get",
    "try_handle_post",
]

