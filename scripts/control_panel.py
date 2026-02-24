
import csv
from collections import deque
import html
import json
import mimetypes
import sqlite3
import os
import re
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
# Ensure project root is importable so `from scripts.autowfo import ...` resolves
# correctly regardless of the working directory the server is launched from.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
ARTIFACTS = ROOT / "artifacts"
STATUS_JSON = ARTIFACTS / "run_status.json"
STATUS_HTML = ARTIFACTS / "run_status.html"
RUN_LOG = ARTIFACTS / "run_console.log"
TEST_STATUS_JSON = ARTIFACTS / "test_status.json"
TEST_LOG = ARTIFACTS / "test_console.log"
DB_PATH = ARTIFACTS / "results.db"
CONFIG_JSON = ARTIFACTS / "sweep_config.json"
CONTROL_JSON = ARTIFACTS / "run_control.json"
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
SCRIPT = ROOT / "scripts" / "run_btc_regime_sweep.py"
CONTROL_PANEL_DIR = ROOT / "scripts" / "control_panel"
STATIC_DIR = CONTROL_PANEL_DIR / "static"
BATCH_DEFAULT_MIN_FREE_GB = 20.0

PROCESS_LOCK = threading.Lock()
PROCESS = None
TEST_PROCESS_LOCK = threading.Lock()
TEST_PROCESS = None
BATCH_PROCESS_LOCK = threading.Lock()
BATCH_PROCESS = None
MAX_ROWS = 5000
LOG_MAX_LINES = 2000

DEFAULT_CONFIG = {
    "search_mode": "combo",
    "combo_sizes": [2, 3, 4],
    "combo_seed": 42,
    "combo_segment_start": 0,
    "combo_segment_size": None,
    "timeframes": [{"timeframe": "3m", "days": 60}],
    "wf_train_days": 120,
    "wf_test_days": 30,
    "wf_step_days": 30,
    "top_n_refine": 50,
    "combo_group_fields": ["indicator_list", "regime_name", "vol_mode"],
    "capital_mode": "shared",
    "init_cash_usdt": 1000,
    "order_size_pct": 0.5,
    "max_concurrent_positions": 2,
    "slippage_bps": 2.0,
    "spread_bps": 2.0,
    "funding_rate_daily": 0.0,
    "trade_symbols": [
        "ETH/BTC",
        "BNB/BTC",
        "SOL/BTC",
    ],
}

SYMBOL_CACHE = {"ts": 0, "symbols": []}
TIMEFRAME_CACHE = {"ts": 0, "mtime": 0, "values": []}
try:
    _data_refresh_interval = int(os.environ.get("AUTOWFO_DATA_REFRESH_INTERVAL_SECONDS", "1800"))
except Exception:
    _data_refresh_interval = 1800
DATA_REFRESH_INTERVAL_SECONDS = max(60, _data_refresh_interval)
DATA_REFRESH_LOCK = threading.Lock()
DATA_REFRESH_THREAD_LOCK = threading.Lock()
DATA_REFRESH_THREAD = None
DATA_REFRESH_STOP = threading.Event()
LIVE_SIGNAL_CONFIG_SUBDIR = "live_signal_configs"
PAPER_FEEDBACK_FILE = "paper_feedback.ndjson"
FEEDBACK_RECOMMEND_DEFAULT_MIN_SAMPLES = 3
ADVANCED_ANALYSIS_DEFAULT_TRIALS = 2000
ADVANCED_ANALYSIS_MAX_TRIALS = 50000
ADVANCED_ANALYSIS_MAX_SAMPLE_SIZE = 10000
DASHBOARD_TOP_N_DEFAULT = 20
DASHBOARD_TOP_N_MIN = 1
DASHBOARD_TOP_N_MAX = 200
DASHBOARD_ERROR_EVENTS_FILE = "dashboard_error_events.ndjson"
DASHBOARD_ERROR_EVENTS_DEFAULT_LIMIT = 100
DASHBOARD_ERROR_EVENTS_MAX_LIMIT = 1000
DASHBOARD_ERROR_EVENTS_MAX_ROWS = 5000
DASHBOARD_ERROR_EVENTS_SINCE_HOURS_MAX = 24 * 30
FEEDBACK_SWEEP_RISK_LIMITS = {
    "tp_stop": (0.0005, 0.2),
    "sl_stop": (0.0005, 0.2),
    "max_hold": (1, 240),
}


def _resolve_static_path(path):
    if not path.startswith("/static/"):
        return None
    rel_path = path[len("/static/"):].strip("/")
    if not rel_path:
        return None
    candidate = (STATIC_DIR / rel_path).resolve()
    static_root = STATIC_DIR.resolve()
    try:
        candidate.relative_to(static_root)
    except ValueError:
        return None
    if not candidate.exists() or not candidate.is_file():
        return None
    return candidate


def _read_static_text(rel_path, fallback=""):
    file_path = STATIC_DIR / rel_path
    if file_path.exists():
        return file_path.read_text(encoding="utf-8")
    return fallback


def _normalize_top_n(value, default=DASHBOARD_TOP_N_DEFAULT):
    try:
        parsed = int(value)
    except Exception:
        parsed = int(default)
    if parsed < DASHBOARD_TOP_N_MIN:
        return DASHBOARD_TOP_N_MIN
    if parsed > DASHBOARD_TOP_N_MAX:
        return DASHBOARD_TOP_N_MAX
    return parsed


def _is_running():
    global PROCESS
    return PROCESS is not None and PROCESS.poll() is None


def _is_test_running():
    global TEST_PROCESS
    return TEST_PROCESS is not None and TEST_PROCESS.poll() is None


def _is_batch_running():
    global BATCH_PROCESS
    return BATCH_PROCESS is not None and BATCH_PROCESS.poll() is None


def _now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _python_path():
    return str(PYTHON if PYTHON.exists() else Path(os.sys.executable))


def _batch_queue_path():
    return ARTIFACTS / "batch_queue.json"


def _batch_plan_path():
    return ARTIFACTS / "control_panel_batch_plan.json"


def _batch_state_path():
    return ARTIFACTS / "batch_state.json"


def _batch_log_path():
    return ARTIFACTS / "batch_console.log"


def _read_json_file(path, default_value):
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(default_value, dict) and isinstance(payload, dict):
                return payload
            if isinstance(default_value, list) and isinstance(payload, list):
                return payload
        except Exception:
            pass
    return default_value


def _relative_path_or_str(path):
    try:
        return path.relative_to(ROOT).as_posix()
    except Exception:
        try:
            return Path(path).as_posix()
        except Exception:
            return str(path).replace("\\", "/")


def _batch_default_queue():
    return {
        "version": 1,
        "next_id": 1,
        "updated_utc": _now_iso(),
        "jobs": [],
        "last_exit_code": "",
    }


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


def _write_batch_queue(queue):
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    queue["updated_utc"] = _now_iso()
    _batch_queue_path().write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")


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


def _read_batch_log_tail(max_lines=LOG_MAX_LINES):
    path = _batch_log_path()
    if not path.exists():
        return ""
    lines = deque(maxlen=max_lines)
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            lines.append(line.rstrip("\n"))
    return "\n".join(lines)


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


def _batch_clear():
    if _is_batch_running():
        return False, "batch is running"
    queue = _batch_default_queue()
    _write_batch_queue(queue)
    return True, "queue cleared"


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


def _coverage_registry_path():
    return ARTIFACTS / "run_registry.json"


def _coverage_slug_text(value):
    text = str(value or "").strip()
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


def _coverage_pairs_to_set(raw_pairs):
    pairs = set()
    if not isinstance(raw_pairs, list):
        return pairs
    for item in raw_pairs:
        if not isinstance(item, dict):
            continue
        timeframe = str(item.get("timeframe", "")).strip()
        symbol = str(item.get("symbol", "")).strip()
        if not timeframe or not symbol:
            continue
        pairs.add((timeframe, symbol))
    return pairs


def _coverage_set_to_pairs(pair_set):
    return [
        {"timeframe": timeframe, "symbol": symbol}
        for timeframe, symbol in sorted(pair_set)
    ]


def _coverage_collect_queued_pairs(queue_payload):
    queued_pairs = set()
    jobs = queue_payload.get("jobs") if isinstance(queue_payload, dict) else []
    if not isinstance(jobs, list):
        return queued_pairs

    active_statuses = {"queued", "submitted", "running"}
    for job in jobs:
        if not isinstance(job, dict):
            continue
        status = str(job.get("status", "")).strip()
        if status not in active_statuses:
            continue

        config_raw = str(job.get("config", "")).strip()
        if not config_raw:
            continue
        config_path = Path(config_raw)
        if not config_path.is_absolute():
            config_path = (ROOT / config_path).resolve()
        if not config_path.exists():
            continue

        config_payload = _read_json_file(config_path, {})
        if not isinstance(config_payload, dict):
            continue

        timeframes = []
        raw_timeframes = config_payload.get("timeframes")
        if isinstance(raw_timeframes, list):
            for item in raw_timeframes:
                if not isinstance(item, dict):
                    continue
                timeframe = str(item.get("timeframe", "")).strip()
                if timeframe:
                    timeframes.append(timeframe)
        if not timeframes:
            continue

        symbols = []
        raw_symbols = config_payload.get("trade_symbols")
        if isinstance(raw_symbols, str):
            raw_symbols = [s.strip() for s in raw_symbols.split(",") if s.strip()]
        if isinstance(raw_symbols, list):
            for symbol_raw in raw_symbols:
                symbol = str(symbol_raw).strip()
                if symbol:
                    symbols.append(symbol)
        if not symbols:
            continue

        for timeframe in timeframes:
            for symbol in symbols:
                queued_pairs.add((timeframe, symbol))

    return queued_pairs


def _coverage_build_days_map(registry_payload, template_config):
    mapping = {}
    runs = registry_payload.get("runs") if isinstance(registry_payload, dict) else None
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

    template_timeframes = template_config.get("timeframes") if isinstance(template_config, dict) else None
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


def _coverage_default_days(template_config):
    timeframes = template_config.get("timeframes") if isinstance(template_config, dict) else None
    if isinstance(timeframes, list):
        for item in timeframes:
            if not isinstance(item, dict):
                continue
            try:
                days = int(item.get("days"))
            except Exception:
                continue
            if days > 0:
                return days
    return 60


def _coverage_matrix_payload():
    registry_payload = _read_json_file(_coverage_registry_path(), {"runs": [], "coverage": {}})
    coverage = registry_payload.get("coverage")
    if not isinstance(coverage, dict):
        coverage = {}

    tested_pairs = _coverage_pairs_to_set(coverage.get("tested_pairs"))
    untested_pairs = _coverage_pairs_to_set(coverage.get("untested_pairs"))
    queued_pairs = _coverage_collect_queued_pairs(_load_batch_queue())

    timeframe_values = set()
    symbol_values = set()
    for timeframe, symbol in tested_pairs | untested_pairs | queued_pairs:
        timeframe_values.add(timeframe)
        symbol_values.add(symbol)

    raw_timeframes = coverage.get("timeframes")
    if isinstance(raw_timeframes, list):
        for raw in raw_timeframes:
            val = str(raw).strip()
            if val:
                timeframe_values.add(val)

    raw_symbols = coverage.get("symbols")
    if isinstance(raw_symbols, list):
        for raw in raw_symbols:
            val = str(raw).strip()
            if val:
                symbol_values.add(val)

    template_cfg = _read_config()
    cfg_timeframes = template_cfg.get("timeframes")
    if isinstance(cfg_timeframes, list):
        for item in cfg_timeframes:
            if not isinstance(item, dict):
                continue
            timeframe = str(item.get("timeframe", "")).strip()
            if timeframe:
                timeframe_values.add(timeframe)

    cfg_symbols = template_cfg.get("trade_symbols")
    if isinstance(cfg_symbols, list):
        for raw in cfg_symbols:
            symbol = str(raw).strip()
            if symbol:
                symbol_values.add(symbol)

    timeframes = sorted(timeframe_values)
    symbols = sorted(symbol_values)
    cells = []
    status_counts = {"tested": 0, "queued": 0, "untested": 0}

    for symbol in symbols:
        for timeframe in timeframes:
            pair = (timeframe, symbol)
            if pair in queued_pairs:
                status = "queued"
            elif pair in tested_pairs:
                status = "tested"
            else:
                status = "untested"
            status_counts[status] += 1
            cells.append({"timeframe": timeframe, "symbol": symbol, "status": status})

    total = len(timeframes) * len(symbols)
    coverage_pct = 0.0 if total == 0 else (len(tested_pairs) / total) * 100.0

    return {
        "generated_utc": _now_iso(),
        "timeframes": timeframes,
        "symbols": symbols,
        "cells": cells,
        "tested_pairs": _coverage_set_to_pairs(tested_pairs),
        "queued_pairs": _coverage_set_to_pairs(queued_pairs),
        "untested_pairs": _coverage_set_to_pairs(untested_pairs),
        "summary": {
            "total": total,
            "tested": status_counts["tested"],
            "queued": status_counts["queued"],
            "untested": status_counts["untested"],
            "tested_pairs": len(tested_pairs),
            "coverage_pct": round(coverage_pct, 2),
        },
    }


def _coverage_enqueue_pair(payload):
    if not isinstance(payload, dict):
        return False, "invalid payload", None

    timeframe = str(payload.get("timeframe", "")).strip()
    symbol = str(payload.get("symbol", "")).strip()
    if not timeframe or not symbol:
        return False, "timeframe and symbol are required", None

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

    active_pairs = _coverage_collect_queued_pairs(_load_batch_queue())
    if (timeframe, symbol) in active_pairs:
        return False, "pair is already queued", None

    registry_payload = _read_json_file(_coverage_registry_path(), {"runs": [], "coverage": {}})
    template_cfg = _read_config()
    days_map = _coverage_build_days_map(registry_payload, template_cfg)
    days = int(days_map.get(timeframe, _coverage_default_days(template_cfg)))

    cfg_payload = json.loads(json.dumps(template_cfg, ensure_ascii=False))
    cfg_payload["timeframes"] = [{"timeframe": timeframe, "days": days}]
    cfg_payload["trade_symbols"] = [symbol]

    planned_dir = ARTIFACTS / "planned_configs"
    planned_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    cfg_name = f"ui_{_coverage_slug_text(timeframe)}_{_coverage_slug_text(symbol)}_{stamp}.json"
    cfg_path = planned_dir / cfg_name
    cfg_path.write_text(json.dumps(cfg_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    enqueue_payload = {
        "name": str(payload.get("name") or f"cov-{_coverage_slug_text(timeframe)}-{_coverage_slug_text(symbol)}"),
        "workflow": workflow,
        "config": str(cfg_path),
    }
    if mode is not None:
        enqueue_payload["mode"] = mode
    if workers is not None:
        enqueue_payload["workers"] = workers

    ok, msg, job = _batch_enqueue(enqueue_payload)
    if not ok:
        return False, msg, None
    return True, "pair enqueued", {"job": job, "config_path": str(cfg_path)}


def _cross_run_payload(top_n=20):
    from scripts.autowfo import cross_run

    registry_path = _coverage_registry_path()
    top_n_i = _normalize_top_n(top_n)
    return cross_run.validate_cross_run_payload(
        cross_run.normalize_cross_run_payload(
            cross_run.build_cross_run_payload(
                artifacts_dir=ARTIFACTS,
                registry_path=registry_path,
                top_n=top_n_i,
            ),
            top_n=top_n_i,
        ),
        require_v1=True,
    )


def _cross_run_cached_payload(top_n=20):
    from scripts.autowfo import cross_run

    payload_path = ARTIFACTS / "cross_run_report.json"
    return cross_run.load_cross_run_payload(
        payload_path=payload_path,
        top_n=_normalize_top_n(top_n),
    )


def _cross_run_generate_report(top_n=20):
    from scripts.autowfo import cross_run

    registry_path = _coverage_registry_path()
    out_html = ARTIFACTS / "cross_run_report.html"
    out_json = ARTIFACTS / "cross_run_report.json"
    payload = cross_run.write_cross_run_reports(
        artifacts_dir=ARTIFACTS,
        registry_path=registry_path,
        out_html_path=out_html,
        out_json_path=out_json,
        top_n=_normalize_top_n(top_n),
    )
    return payload, out_html


def _cross_run_cached_report_html(top_n=20, persist_html=False):
    from scripts.autowfo import cross_run

    payload = _cross_run_cached_payload(top_n=top_n)
    html_text = cross_run.render_cross_run_html(payload)
    out_html = ARTIFACTS / "cross_run_report.html"
    if bool(persist_html):
        out_html.parent.mkdir(parents=True, exist_ok=True)
        out_html.write_text(html_text, encoding="utf-8")
    return payload, html_text, out_html


def _cross_run_cache_fallback_meta(reason, fallback_for, request_id=None):
    live_error = _cross_run_error_details(reason)
    endpoint = str(fallback_for)
    return {
        "used": True,
        "source": "artifacts/cross_run_report.json",
        "reason": str(reason),
        "reason_code": live_error["code"],
        "live_error": live_error,
        "fallback_for": endpoint,
        "endpoint": endpoint,
        "request_id": str(request_id or _new_request_id()),
        "fallback_utc": _now_iso(),
    }


def _new_request_id():
    return uuid.uuid4().hex


def _cross_run_error_code(reason):
    raw_code = getattr(reason, "code", None)
    if isinstance(raw_code, str) and raw_code.strip():
        return raw_code.strip()
    name = reason.__class__.__name__ if reason is not None else "UnknownError"
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", str(name)).lower()
    return snake or "unknown_error"


def _cross_run_error_details(reason):
    error_type = reason.__class__.__name__ if reason is not None else "UnknownError"
    return {
        "code": _cross_run_error_code(reason),
        "type": error_type,
        "message": str(reason),
    }


def _dashboard_error_payload(endpoint, live_exc, message, cache_exc=None, request_id=None):
    resolved_request_id = str(request_id or _new_request_id())
    payload = {
        "ok": False,
        "endpoint": str(endpoint),
        "error_utc": _now_iso(),
        "request_id": resolved_request_id,
        "error_code": _cross_run_error_code(live_exc),
        "live_error": _cross_run_error_details(live_exc),
        "message": str(message),
    }
    if cache_exc is not None:
        payload["cache_error_code"] = _cross_run_error_code(cache_exc)
        payload["cache_error"] = _cross_run_error_details(cache_exc)
    return payload


def _cross_run_validate_payload(payload):
    from scripts.autowfo import cross_run

    return cross_run.validate_cross_run_payload(payload, require_v1=True)


def _write_status(payload):
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    with STATUS_JSON.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _write_test_status(payload):
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    with TEST_STATUS_JSON.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _parse_iso(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _read_control():
    if CONTROL_JSON.exists():
        try:
            return json.loads(CONTROL_JSON.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"paused": False}


def _write_control(paused):
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    CONTROL_JSON.write_text(json.dumps({"paused": bool(paused)}, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_config():
    if CONFIG_JSON.exists():
        try:
            return json.loads(CONFIG_JSON.read_text(encoding="utf-8"))
        except Exception:
            pass
    cfg = DEFAULT_CONFIG.copy()
    if not cfg.get("trade_symbols"):
        cfg["trade_symbols"] = _fetch_top_symbols(limit=10)
    return cfg


def _data_refresh_state_path():
    return ARTIFACTS / "data_refresh_state.json"


def _default_data_refresh_state():
    return {
        "ok": True,
        "reason": "",
        "updated_utc": "",
        "last_refresh_utc": "",
        "next_refresh_utc": "",
        "exchange": "",
        "base_symbol": "",
        "timeframes": [],
        "symbols": [],
        "timeframe_data_end": {},
        "pair_data_end": [],
        "errors": [],
    }


def _read_data_refresh_state():
    state = _read_json_file(_data_refresh_state_path(), _default_data_refresh_state())
    if not isinstance(state, dict):
        state = _default_data_refresh_state()
    template = _default_data_refresh_state()
    for key, val in template.items():
        state.setdefault(key, val)
    if not isinstance(state.get("timeframe_data_end"), dict):
        state["timeframe_data_end"] = {}
    if not isinstance(state.get("pair_data_end"), list):
        state["pair_data_end"] = []
    if not isinstance(state.get("errors"), list):
        state["errors"] = []
    return state


def _write_data_refresh_state(state):
    payload = _default_data_refresh_state()
    if isinstance(state, dict):
        payload.update(state)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    _data_refresh_state_path().write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload


def _resolve_data_refresh_plan(cfg):
    cfg = cfg if isinstance(cfg, dict) else {}
    exchange = str(cfg.get("exchange") or "binance").strip() or "binance"
    base_symbol = str(cfg.get("base_symbol") or "BTC/USDT").strip() or "BTC/USDT"

    timeframes = []
    raw_timeframes = cfg.get("timeframes")
    if isinstance(raw_timeframes, list):
        for item in raw_timeframes:
            if not isinstance(item, dict):
                continue
            timeframe = str(item.get("timeframe", "")).strip()
            if not timeframe:
                continue
            try:
                days = int(item.get("days", 0))
            except Exception:
                days = 0
            if days <= 0:
                days = 1
            timeframes.append({"timeframe": timeframe, "days": days})
    if not timeframes:
        timeframes = [dict(item) for item in DEFAULT_CONFIG.get("timeframes", []) if isinstance(item, dict)]

    symbols = []
    raw_symbols = cfg.get("trade_symbols")
    if isinstance(raw_symbols, str):
        raw_symbols = [s.strip() for s in raw_symbols.split(",") if s.strip()]
    if isinstance(raw_symbols, (list, tuple)):
        for item in raw_symbols:
            symbol = str(item).strip()
            if symbol and symbol not in symbols:
                symbols.append(symbol)
    if not symbols:
        fallback = DEFAULT_CONFIG.get("trade_symbols", [])
        if isinstance(fallback, list):
            symbols = [str(item).strip() for item in fallback if str(item).strip()]

    return {
        "exchange": exchange,
        "base_symbol": base_symbol,
        "timeframes": timeframes,
        "trade_symbols": symbols,
    }


def _refresh_data_cache_now(force=False, reason="auto", refresh_ohlcv_cache_fn=None):
    with DATA_REFRESH_LOCK:
        state = _read_data_refresh_state()
        now_utc = datetime.now(timezone.utc).replace(microsecond=0)
        last_refresh = _parse_iso(state.get("last_refresh_utc"))
        if not force and last_refresh is not None:
            if last_refresh.tzinfo is None:
                last_refresh = last_refresh.replace(tzinfo=timezone.utc)
            elapsed = (now_utc - last_refresh.astimezone(timezone.utc)).total_seconds()
            if elapsed < DATA_REFRESH_INTERVAL_SECONDS:
                state["next_refresh_utc"] = (
                    last_refresh.astimezone(timezone.utc) + timedelta(seconds=DATA_REFRESH_INTERVAL_SECONDS)
                ).replace(microsecond=0).isoformat()
                _write_data_refresh_state(state)
                return state, False

        plan = _resolve_data_refresh_plan(_read_config())
        exchange = plan["exchange"]
        base_symbol = plan["base_symbol"]
        timeframes = plan["timeframes"]
        symbols = plan["trade_symbols"]

        if refresh_ohlcv_cache_fn is None:
            from scripts.autowfo import data as autowfo_data

            cache_format = "parquet" if autowfo_data._has_parquet_engine() else "csv"
            refresh_ohlcv_cache_fn = autowfo_data.refresh_ohlcv_cache
        else:
            cache_format = "csv"

        try:
            refresh_payload = refresh_ohlcv_cache_fn(
                exchange=exchange,
                timeframes=timeframes,
                symbols=symbols,
                base_symbol=base_symbol,
                cache_dir=str(ARTIFACTS / "cache_ccxt"),
                cache_format=cache_format,
            )
            if not isinstance(refresh_payload, dict):
                refresh_payload = {}
            refreshed_state = _default_data_refresh_state()
            refreshed_state["ok"] = True
            refreshed_state["reason"] = str(reason or "")
            refreshed_state["updated_utc"] = now_utc.isoformat()
            refreshed_state["last_refresh_utc"] = now_utc.isoformat()
            refreshed_state["next_refresh_utc"] = (
                now_utc + timedelta(seconds=DATA_REFRESH_INTERVAL_SECONDS)
            ).replace(microsecond=0).isoformat()
            refreshed_state["exchange"] = exchange
            refreshed_state["base_symbol"] = base_symbol
            refreshed_state["timeframes"] = timeframes
            refreshed_state["symbols"] = symbols
            refreshed_state["timeframe_data_end"] = dict(refresh_payload.get("timeframe_data_end") or {})
            refreshed_state["pair_data_end"] = list(refresh_payload.get("pair_data_end") or [])
            refreshed_state["errors"] = list(refresh_payload.get("errors") or [])
            _write_data_refresh_state(refreshed_state)
            return refreshed_state, True
        except Exception as exc:
            errors = list(state.get("errors") or [])
            errors.append(str(exc))
            state["ok"] = False
            state["reason"] = str(reason or "")
            state["updated_utc"] = now_utc.isoformat()
            state["last_refresh_utc"] = now_utc.isoformat()
            state["next_refresh_utc"] = (
                now_utc + timedelta(seconds=DATA_REFRESH_INTERVAL_SECONDS)
            ).replace(microsecond=0).isoformat()
            state["errors"] = errors[-50:]
            _write_data_refresh_state(state)
            return state, False


def _data_refresh_loop():
    while not DATA_REFRESH_STOP.wait(5):
        try:
            _refresh_data_cache_now(force=False, reason="auto")
        except Exception:
            # Keep daemon loop resilient; failures are recorded in refresh state.
            pass


def _ensure_data_refresh_thread():
    global DATA_REFRESH_THREAD
    with DATA_REFRESH_THREAD_LOCK:
        if DATA_REFRESH_THREAD is not None and DATA_REFRESH_THREAD.is_alive():
            return
        DATA_REFRESH_STOP.clear()
        DATA_REFRESH_THREAD = threading.Thread(
            target=_data_refresh_loop,
            name="autowfo-data-refresh",
            daemon=True,
        )
        DATA_REFRESH_THREAD.start()


def _overlay_data_end_from_refresh(rows, refresh_state):
    if not isinstance(rows, list):
        return
    refresh_state = refresh_state if isinstance(refresh_state, dict) else {}
    timeframe_lookup = refresh_state.get("timeframe_data_end")
    if not isinstance(timeframe_lookup, dict):
        timeframe_lookup = {}

    pair_lookup = {}
    raw_pairs = refresh_state.get("pair_data_end")
    if isinstance(raw_pairs, list):
        for item in raw_pairs:
            if not isinstance(item, dict):
                continue
            timeframe = str(item.get("timeframe", "")).strip()
            symbol = str(item.get("symbol", "")).strip()
            data_end = str(item.get("data_end", "")).strip()
            if timeframe and symbol and data_end:
                pair_lookup[(timeframe, symbol)] = data_end

    for row in rows:
        if not isinstance(row, dict):
            continue
        timeframe = str(row.get("timeframe", "")).strip()
        if not timeframe:
            continue
        data_end = ""
        for symbol_key in ("plot_symbol", "symbol", "trade_symbol"):
            symbol = str(row.get(symbol_key, "")).strip()
            if symbol:
                data_end = pair_lookup.get((timeframe, symbol), "")
                if data_end:
                    break
        if not data_end:
            data_end = str(timeframe_lookup.get(timeframe, "")).strip()
        if data_end:
            row["data_end"] = data_end


def _sanitize_config(payload):
    cfg = DEFAULT_CONFIG.copy()
    if not isinstance(payload, dict):
        return cfg
    search_mode = str(payload.get("search_mode", cfg["search_mode"])).lower()
    if search_mode not in {"combo", "refine"}:
        search_mode = cfg["search_mode"]
    cfg["search_mode"] = search_mode

    combo_sizes = payload.get("combo_sizes", cfg["combo_sizes"])
    if isinstance(combo_sizes, str):
        combo_sizes = [s.strip() for s in combo_sizes.split(",") if s.strip()]
    sizes = []
    if isinstance(combo_sizes, (list, tuple)):
        for item in combo_sizes:
            try:
                val = int(item)
            except (TypeError, ValueError):
                continue
            if 1 <= val <= 6:
                sizes.append(val)
    cfg["combo_sizes"] = sizes or cfg["combo_sizes"]

    def _safe_int(value, fallback):
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback

    def _safe_float(value, fallback):
        try:
            return float(value)
        except (TypeError, ValueError):
            return fallback

    cfg["combo_seed"] = _safe_int(payload.get("combo_seed"), cfg["combo_seed"])
    cfg["combo_segment_start"] = _safe_int(payload.get("combo_segment_start"), cfg["combo_segment_start"])
    seg_size = payload.get("combo_segment_size")
    if seg_size in ("", None):
        cfg["combo_segment_size"] = None
    else:
        cfg["combo_segment_size"] = _safe_int(seg_size, cfg["combo_segment_size"])
    cfg["wf_train_days"] = max(1, _safe_int(payload.get("wf_train_days"), cfg["wf_train_days"]))
    cfg["wf_test_days"] = max(1, _safe_int(payload.get("wf_test_days"), cfg["wf_test_days"]))
    cfg["wf_step_days"] = max(1, _safe_int(payload.get("wf_step_days"), cfg["wf_step_days"]))
    cfg["top_n_refine"] = _safe_int(payload.get("top_n_refine"), cfg["top_n_refine"])
    cfg["slippage_bps"] = _safe_float(payload.get("slippage_bps"), cfg["slippage_bps"])
    cfg["spread_bps"] = _safe_float(payload.get("spread_bps"), cfg["spread_bps"])
    cfg["funding_rate_daily"] = _safe_float(payload.get("funding_rate_daily"), cfg["funding_rate_daily"])
    capital_mode = str(payload.get("capital_mode", cfg["capital_mode"])).lower()
    if capital_mode not in {"shared", "per_symbol"}:
        capital_mode = cfg["capital_mode"]
    cfg["capital_mode"] = capital_mode
    cfg["init_cash_usdt"] = _safe_float(payload.get("init_cash_usdt"), cfg["init_cash_usdt"])
    order_size_pct = _safe_float(payload.get("order_size_pct"), cfg["order_size_pct"])
    if order_size_pct > 1:
        order_size_pct = order_size_pct / 100.0
    if order_size_pct <= 0:
        order_size_pct = cfg["order_size_pct"]
    cfg["order_size_pct"] = order_size_pct
    cfg["max_concurrent_positions"] = _safe_int(payload.get("max_concurrent_positions"), cfg["max_concurrent_positions"])

    trade_symbols = payload.get("trade_symbols", cfg["trade_symbols"])
    if isinstance(trade_symbols, str):
        trade_symbols = [s.strip() for s in trade_symbols.split(",") if s.strip()]
    symbols = []
    if isinstance(trade_symbols, (list, tuple)):
        for item in trade_symbols:
            symbol = str(item).strip()
            if symbol:
                symbols.append(symbol)
    cfg["trade_symbols"] = symbols or cfg["trade_symbols"]

    timeframes = payload.get("timeframes")
    tf_list = []
    if isinstance(timeframes, list):
        for item in timeframes:
            if not isinstance(item, dict):
                continue
            tf = str(item.get("timeframe", "")).strip()
            days = _safe_int(item.get("days"), None)
            if tf and days:
                tf_list.append({"timeframe": tf, "days": days})
    if tf_list:
        cfg["timeframes"] = tf_list

    return cfg


def _validate_config_guardrails(cfg):
    if not isinstance(cfg, dict):
        return
    wf_test_days = int(cfg.get("wf_test_days", 0) or 0)
    wf_step_days = int(cfg.get("wf_step_days", 0) or 0)
    if wf_test_days > 0 and wf_step_days > 0 and wf_step_days < wf_test_days:
        raise ValueError(
            f"wf_step_days ({wf_step_days}) must be >= wf_test_days ({wf_test_days}) to avoid overlapping OOS segments"
        )


def _write_config(payload):
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    cfg = _sanitize_config(payload)
    _validate_config_guardrails(cfg)
    CONFIG_JSON.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return cfg


def _fetch_top_symbols(limit=10):
    now_ts = datetime.now(timezone.utc).timestamp()
    if SYMBOL_CACHE["symbols"] and now_ts - SYMBOL_CACHE["ts"] < 600:
        return SYMBOL_CACHE["symbols"][:limit]
    fallback = DEFAULT_CONFIG["trade_symbols"]
    try:
        import ccxt  # type: ignore
    except Exception:
        return fallback[:limit]
    try:
        exchange = ccxt.binance({"enableRateLimit": True})
        tickers = exchange.fetch_tickers()
        pairs = []
        for symbol, data in tickers.items():
            if not symbol.endswith("/BTC"):
                continue
            if any(flag in symbol for flag in ("UP/", "DOWN/", "BULL/", "BEAR/")):
                continue
            vol = data.get("quoteVolume")
            if vol is None:
                vol = data.get("baseVolume")
            if vol is None:
                continue
            pairs.append((symbol, float(vol)))
        pairs.sort(key=lambda x: x[1], reverse=True)
        symbols = [sym for sym, _ in pairs[:max(limit, 10)]]
        if symbols:
            SYMBOL_CACHE["ts"] = now_ts
            SYMBOL_CACHE["symbols"] = symbols
            return symbols[:limit]
    except Exception:
        return fallback[:limit]
    return fallback[:limit]


def _latest_report_path():
    reports = sorted(ARTIFACTS.glob("btc_regime_*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
    return reports[0] if reports else None


def _latest_top10_path():
    tops = sorted(ARTIFACTS.glob("param_sweep_top10_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    return tops[0] if tops else None


def _parse_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _db_available():
    return DB_PATH.exists()


def _db_has_table(table):
    if not _db_available():
        return False
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            )
            return cur.fetchone() is not None
    except Exception:
        return False


def _db_columns(table):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    cols = [row["name"] for row in rows if row["name"] not in ("id", "created_utc")]
    return cols


def _read_db_rows(table, limit=MAX_ROWS, timeframe=None):
    if not _db_has_table(table):
        return None
    where = ""
    params = []
    if timeframe:
        where = " WHERE timeframe = ?"
        params.append(timeframe)
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        columns = _db_columns(table)
        total = conn.execute(
            f"SELECT COUNT(*) FROM {table}{where}", params
        ).fetchone()[0]
        if columns:
            col_sql = ", ".join([f'"{col}"' for col in columns])
        else:
            col_sql = "*"
        query = f"SELECT {col_sql} FROM {table}{where} ORDER BY id DESC LIMIT ?"
        rows = [
            dict(row)
            for row in conn.execute(query, params + [limit]).fetchall()
        ]
    truncated = limit is not None and total > limit
    return {
        "path": str(DB_PATH.relative_to(ROOT)),
        "columns": columns,
        "rows": rows,
        "total": total,
        "truncated": truncated,
    }


def _get_timeframes_db():
    if not _db_has_table("combo_summary"):
        return []
    now_ts = datetime.now(timezone.utc).timestamp()
    if TIMEFRAME_CACHE["values"] and now_ts - TIMEFRAME_CACHE["ts"] < 300:
        return TIMEFRAME_CACHE["values"]
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT DISTINCT timeframe FROM combo_summary WHERE timeframe IS NOT NULL AND timeframe != '' ORDER BY timeframe"
        ).fetchall()
    values = [row[0] for row in rows if row and row[0]]
    TIMEFRAME_CACHE["values"] = values
    TIMEFRAME_CACHE["ts"] = now_ts
    TIMEFRAME_CACHE["mtime"] = 0
    return values


def _get_timeframes(path):
    if path is None or not path.exists():
        return []
    now_ts = datetime.now(timezone.utc).timestamp()
    if TIMEFRAME_CACHE["values"] and now_ts - TIMEFRAME_CACHE["ts"] < 300:
        return TIMEFRAME_CACHE["values"]
    values = set()
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            tf = row.get("timeframe")
            if tf:
                values.add(tf)
    result = sorted(values)
    TIMEFRAME_CACHE["values"] = result
    TIMEFRAME_CACHE["ts"] = now_ts
    TIMEFRAME_CACHE["mtime"] = 0
    return result


def _read_csv_rows(path, limit=MAX_ROWS, timeframe=None):
    if path is None or not path.exists():
        return {"path": "", "columns": [], "rows": [], "total": 0, "truncated": False}
    total = 0
    if limit is None:
        rows = []
    else:
        rows = deque(maxlen=limit)
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames or []
        for row in reader:
            if timeframe and row.get("timeframe") != timeframe:
                continue
            total += 1
            rows.append(row)
    truncated = limit is not None and total > limit
    if isinstance(rows, deque):
        rows = list(rows)
    return {
        "path": str(path.relative_to(ROOT)),
        "columns": columns,
        "rows": rows,
        "total": total,
        "truncated": truncated,
    }


def _pick_top10(rows):
    if not rows:
        return []
    sort_col = "oos_avg_total_return_pct"
    if not any(_parse_float(row.get(sort_col)) is not None for row in rows):
        sort_col = "avg_total_return_pct"
    sorted_rows = sorted(rows, key=lambda r: _parse_float(r.get(sort_col)) or float("-inf"), reverse=True)
    # Deduplicate: keep the first (= best score) occurrence of each unique combo.
    # Identity fingerprint uses all non-metric columns (excludes avg_/sym_/oos_/min_ prefixes).
    _METRIC_PREFIXES = ("avg_", "sym_avg_", "oos_", "min_")
    seen: set = set()
    result = []
    for r in sorted_rows:
        fp = tuple((k, v) for k, v in r.items() if not any(k.startswith(p) for p in _METRIC_PREFIXES))
        if fp not in seen:
            seen.add(fp)
            result.append(r)
        if len(result) >= 10:
            break
    return result


def _get_results_payload(timeframe=None):
    errors = []
    combo_path = ARTIFACTS / "param_sweep_combo_summary.csv"
    try:
        combo = None
        if _db_available():
            combo = _read_db_rows("combo_summary", timeframe=timeframe)
        if combo is None or (combo.get("total", 0) == 0 and combo_path.exists()):
            combo = _read_csv_rows(combo_path, timeframe=timeframe)
    except Exception as exc:
        combo = {"path": "", "columns": [], "rows": [], "total": 0, "truncated": False}
        errors.append(f"讀取組合摘要失敗: {exc}")
    try:
        leaderboard = _read_csv_rows(ARTIFACTS / "leaderboard.csv")
    except Exception as exc:
        leaderboard = {"path": "", "columns": [], "rows": [], "total": 0, "truncated": False}
        errors.append(f"讀取排行榜失敗: {exc}")
    # AWF-107: primary top10 = all-time best from full combo history
    try:
        top10_rows = _pick_top10(combo["rows"]) if combo["rows"] else []
        top10 = {
            "path": combo.get("path", ""),
            "columns": combo.get("columns", []),
            "rows": top10_rows,
            "total": len(top10_rows),
            "truncated": False,
        }
    except Exception as exc:
        top10 = {"path": "", "columns": [], "rows": [], "total": 0, "truncated": False}
        errors.append(f"建立全歷史 Top10 失敗: {exc}")
    # AWF-107: secondary top10_latest_run = latest single-run top10 file (for UI toggle)
    try:
        top10_lr_path = _latest_top10_path()
        top10_latest_run = _read_csv_rows(top10_lr_path, limit=200) if top10_lr_path else {"path": "", "columns": [], "rows": [], "total": 0, "truncated": False}
    except Exception as exc:
        top10_latest_run = {"path": "", "columns": [], "rows": [], "total": 0, "truncated": False}
        errors.append(f"讀取本次 Top10 失敗: {exc}")
    try:
        refresh_state = _read_data_refresh_state()
        _overlay_data_end_from_refresh(combo.get("rows", []), refresh_state)
        _overlay_data_end_from_refresh(top10.get("rows", []), refresh_state)
        _overlay_data_end_from_refresh(top10_latest_run.get("rows", []), refresh_state)
    except Exception as exc:
        refresh_state = _default_data_refresh_state()
        errors.append(f"套用資料新鮮度狀態失敗: {exc}")
    report_path = _latest_report_path()
    timeframes = []
    try:
        timeframes = _get_timeframes_db() if _db_has_table("combo_summary") else _get_timeframes(combo_path)
        if not timeframes and combo_path.exists():
            timeframes = _get_timeframes(combo_path)
    except Exception:
        timeframes = _get_timeframes(combo_path)
    return {
        "generated_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "combo": combo,
        "leaderboard": leaderboard,
        "top10": top10,
        "top10_latest_run": top10_latest_run,
        "latest_report": report_path.name if report_path else "",
        "timeframes": timeframes,
        "data_refresh": {
            "ok": bool(refresh_state.get("ok")),
            "updated_utc": refresh_state.get("updated_utc", ""),
            "last_refresh_utc": refresh_state.get("last_refresh_utc", ""),
            "next_refresh_utc": refresh_state.get("next_refresh_utc", ""),
            "errors": list(refresh_state.get("errors", [])),
        },
        "errors": errors,
    }


def _numeric_series_from_rows(rows, keys):
    values = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        for key in keys:
            num = _parse_float(row.get(key))
            if num is not None:
                values.append(float(num))
                break
    return values


def _percentile(values, pct):
    if not values:
        return None
    sorted_values = sorted(float(v) for v in values)
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    rank = (len(sorted_values) - 1) * (float(pct) / 100.0)
    lo = int(rank)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = rank - lo
    return float(sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac)


def _summarize_numeric(values):
    if not values:
        return {
            "count": 0,
            "min": None,
            "max": None,
            "mean": None,
            "p05": None,
            "p50": None,
            "p95": None,
        }
    count = len(values)
    mean = sum(values) / count
    return {
        "count": int(count),
        "min": float(min(values)),
        "max": float(max(values)),
        "mean": float(mean),
        "p05": _percentile(values, 5),
        "p50": _percentile(values, 50),
        "p95": _percentile(values, 95),
    }


def _build_advanced_results_analysis(rows, n_trials=ADVANCED_ANALYSIS_DEFAULT_TRIALS, sample_size=None, seed=42):
    combo_rows = rows if isinstance(rows, list) else []
    returns = _numeric_series_from_rows(
        combo_rows,
        ["oos_avg_total_return_pct", "avg_total_return_pct", "total_return_pct"],
    )
    drawdowns = _numeric_series_from_rows(
        combo_rows,
        ["oos_avg_max_drawdown_pct", "avg_max_drawdown_pct", "max_drawdown_pct"],
    )
    daily_trades = _numeric_series_from_rows(
        combo_rows,
        ["oos_avg_daily_trades", "avg_daily_trades"],
    )

    monte_carlo = None
    errors = []
    try:
        from scripts.autowfo.benchmark import compute_monte_carlo_return_stats

        monte_carlo = compute_monte_carlo_return_stats(
            returns,
            n_trials=n_trials,
            sample_size=sample_size,
            seed=seed,
        )
    except Exception as exc:
        errors.append(f"monte carlo compute failed: {exc}")

    return {
        "generated_utc": _now_iso(),
        "source_rows": len(combo_rows),
        "params": {
            "n_trials": int(n_trials),
            "sample_size": int(sample_size) if sample_size is not None else None,
            "seed": int(seed),
        },
        "return_distribution": _summarize_numeric(returns),
        "drawdown_distribution": _summarize_numeric(drawdowns),
        "daily_trades_distribution": _summarize_numeric(daily_trades),
        "monte_carlo": monte_carlo,
        "errors": errors,
    }


def _signal_configs_dir():
    return ARTIFACTS / LIVE_SIGNAL_CONFIG_SUBDIR


def _paper_feedback_log_path():
    return ARTIFACTS / PAPER_FEEDBACK_FILE


def _dashboard_error_events_path():
    return ARTIFACTS / DASHBOARD_ERROR_EVENTS_FILE


def _normalize_dashboard_endpoint(value):
    return str(value or "").strip().lstrip("/")


def _normalize_dashboard_error_kind(value):
    raw = str(value or "").strip().lower()
    if raw in {"error", "cache_fallback"}:
        return raw
    return ""


def _normalize_dashboard_error_code(value):
    return str(value or "").strip()


def _normalize_dashboard_status(value):
    if value in ("", None):
        return None
    try:
        parsed = int(value)
    except Exception:
        return None
    if parsed < 0:
        return None
    return parsed


def _normalize_dashboard_message_contains(value):
    return str(value or "").strip().lower()


def _normalize_since_hours(value):
    if value in ("", None):
        return 0
    try:
        parsed = float(value)
    except Exception:
        return 0
    if parsed <= 0:
        return 0
    return min(float(parsed), float(DASHBOARD_ERROR_EVENTS_SINCE_HOURS_MAX))


def _dashboard_error_event_matcher(
    row,
    *,
    endpoint_filter="",
    request_filter="",
    kind_filter="",
    error_code_filter="",
    cache_error_code_filter="",
    status_filter=None,
    message_contains_filter="",
    since_cutoff=None,
):
    if not isinstance(row, dict):
        return False
    if endpoint_filter and _normalize_dashboard_endpoint(row.get("endpoint")) != endpoint_filter:
        return False
    if request_filter and str(row.get("request_id") or "").strip() != request_filter:
        return False
    if kind_filter and _normalize_dashboard_error_kind(row.get("kind")) != kind_filter:
        return False
    if error_code_filter and _normalize_dashboard_error_code(row.get("error_code")) != error_code_filter:
        return False
    if cache_error_code_filter and _normalize_dashboard_error_code(row.get("cache_error_code")) != cache_error_code_filter:
        return False
    if status_filter is not None:
        try:
            row_status = int(row.get("status"))
        except Exception:
            return False
        if row_status != status_filter:
            return False
    if message_contains_filter:
        row_message = str(row.get("message") or "").lower()
        if message_contains_filter not in row_message:
            return False
    if since_cutoff is not None:
        event_ts = _parse_iso(str(row.get("event_utc") or ""))
        if event_ts is None:
            return False
        if event_ts.tzinfo is None:
            event_ts = event_ts.replace(tzinfo=timezone.utc)
        if event_ts < since_cutoff:
            return False
    return True


def _summarize_dashboard_error_events(rows):
    items = rows if isinstance(rows, list) else []
    by_kind = {}
    by_endpoint = {}
    by_error_code = {}
    by_cache_error_code = {}
    for row in items:
        if not isinstance(row, dict):
            continue
        kind = _normalize_dashboard_error_kind(row.get("kind")) or "unknown"
        endpoint = _normalize_dashboard_endpoint(row.get("endpoint")) or "unknown"
        error_code = str(row.get("error_code") or "").strip() or "none"
        cache_error_code = str(row.get("cache_error_code") or "").strip() or "none"
        by_kind[kind] = int(by_kind.get(kind, 0)) + 1
        by_endpoint[endpoint] = int(by_endpoint.get(endpoint, 0)) + 1
        by_error_code[error_code] = int(by_error_code.get(error_code, 0)) + 1
        by_cache_error_code[cache_error_code] = int(by_cache_error_code.get(cache_error_code, 0)) + 1
    return {
        "by_kind": {k: by_kind[k] for k in sorted(by_kind.keys())},
        "by_endpoint": {k: by_endpoint[k] for k in sorted(by_endpoint.keys())},
        "by_error_code": {k: by_error_code[k] for k in sorted(by_error_code.keys())},
        "by_cache_error_code": {k: by_cache_error_code[k] for k in sorted(by_cache_error_code.keys())},
    }


def _trim_dashboard_error_events(max_rows=DASHBOARD_ERROR_EVENTS_MAX_ROWS):
    path = _dashboard_error_events_path()
    if not path.exists():
        return 0
    max_rows_i = _safe_int(max_rows, DASHBOARD_ERROR_EVENTS_MAX_ROWS)
    max_rows_i = max(1, int(max_rows_i))
    total = 0
    lines = deque(maxlen=max_rows_i)
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            raw = line.rstrip("\r\n")
            if not raw:
                continue
            total += 1
            lines.append(raw)
    if total <= max_rows_i:
        return total
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for raw in lines:
            f.write(raw + "\n")
    return len(lines)


def _record_dashboard_error_event(
    *,
    kind,
    endpoint,
    request_id,
    status,
    message,
    error_code="",
    cache_error_code="",
    live_error=None,
    cache_error=None,
    cache_fallback=None,
):
    try:
        status_code = int(status)
    except Exception:
        status_code = 0
    event = {
        "event_utc": _now_iso(),
        "kind": _normalize_dashboard_error_kind(kind) or "error",
        "endpoint": _normalize_dashboard_endpoint(endpoint),
        "request_id": str(request_id or _new_request_id()),
        "status": status_code,
        "message": str(message or ""),
        "error_code": str(error_code or ""),
        "cache_error_code": str(cache_error_code or ""),
    }
    if isinstance(live_error, dict):
        event["live_error"] = live_error
    if isinstance(cache_error, dict):
        event["cache_error"] = cache_error
    if isinstance(cache_fallback, dict):
        event["cache_fallback"] = cache_fallback

    path = _dashboard_error_events_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    _trim_dashboard_error_events()
    return event, path


def _record_dashboard_error_event_safe(**kwargs):
    try:
        return _record_dashboard_error_event(**kwargs)
    except Exception:
        return None


def _read_dashboard_error_events(
    limit=DASHBOARD_ERROR_EVENTS_DEFAULT_LIMIT,
    endpoint=None,
    request_id=None,
    kind=None,
    since_hours=0,
    offset=0,
    error_code=None,
    cache_error_code=None,
    status=None,
    message_contains=None,
):
    path = _dashboard_error_events_path()
    if not path.exists():
        return {
            "rows": [],
            "count": 0,
            "matched_count": 0,
            "total_available": 0,
            "offset": 0,
            "has_more": False,
            "next_offset": None,
            "summary": _summarize_dashboard_error_events([]),
        }

    limit_i = _safe_int(limit, DASHBOARD_ERROR_EVENTS_DEFAULT_LIMIT)
    limit_i = max(1, min(int(limit_i), DASHBOARD_ERROR_EVENTS_MAX_LIMIT))
    offset_i = max(0, _safe_int(offset, 0))
    endpoint_filter = _normalize_dashboard_endpoint(endpoint) if endpoint else ""
    request_filter = str(request_id or "").strip()
    kind_filter = _normalize_dashboard_error_kind(kind)
    error_code_filter = _normalize_dashboard_error_code(error_code)
    cache_error_code_filter = _normalize_dashboard_error_code(cache_error_code)
    status_filter = _normalize_dashboard_status(status)
    message_contains_filter = _normalize_dashboard_message_contains(message_contains)
    since_hours_f = _normalize_since_hours(since_hours)
    since_cutoff = None
    if since_hours_f > 0:
        since_cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours_f)

    matched_rows = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            raw = line.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except Exception:
                continue
            if not isinstance(obj, dict):
                continue
            if not _dashboard_error_event_matcher(
                obj,
                endpoint_filter=endpoint_filter,
                request_filter=request_filter,
                kind_filter=kind_filter,
                error_code_filter=error_code_filter,
                cache_error_code_filter=cache_error_code_filter,
                status_filter=status_filter,
                message_contains_filter=message_contains_filter,
                since_cutoff=since_cutoff,
            ):
                continue
            matched_rows.append(obj)

    newest_first = list(reversed(matched_rows))
    total_available = len(newest_first)
    out = newest_first[offset_i: offset_i + limit_i]
    next_offset = offset_i + len(out)
    has_more = next_offset < total_available
    return {
        "rows": out,
        "count": len(out),
        "matched_count": int(total_available),
        "total_available": int(total_available),
        "offset": int(offset_i),
        "has_more": bool(has_more),
        "next_offset": int(next_offset) if has_more else None,
        "summary": _summarize_dashboard_error_events(matched_rows),
    }


def _clear_dashboard_error_events(
    endpoint=None,
    request_id=None,
    kind=None,
    since_hours=0,
    error_code=None,
    cache_error_code=None,
    status=None,
    message_contains=None,
):
    path = _dashboard_error_events_path()
    if not path.exists():
        return {
            "cleared": 0,
            "remaining": 0,
            "path": _relative_path_or_str(path),
        }

    endpoint_filter = _normalize_dashboard_endpoint(endpoint) if endpoint else ""
    request_filter = str(request_id or "").strip()
    kind_filter = _normalize_dashboard_error_kind(kind)
    error_code_filter = _normalize_dashboard_error_code(error_code)
    cache_error_code_filter = _normalize_dashboard_error_code(cache_error_code)
    status_filter = _normalize_dashboard_status(status)
    message_contains_filter = _normalize_dashboard_message_contains(message_contains)
    since_hours_f = _normalize_since_hours(since_hours)
    since_cutoff = None
    if since_hours_f > 0:
        since_cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours_f)

    clear_all = (
        not endpoint_filter
        and not request_filter
        and not kind_filter
        and not error_code_filter
        and not cache_error_code_filter
        and status_filter is None
        and not message_contains_filter
        and since_cutoff is None
    )
    if clear_all:
        cleared = 0
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.strip():
                    cleared += 1
        path.unlink(missing_ok=True)
        return {
            "cleared": int(cleared),
            "remaining": 0,
            "path": _relative_path_or_str(path),
            "cleared_all": True,
        }

    kept = []
    cleared = 0
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            raw = line.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except Exception:
                continue
            if not isinstance(obj, dict):
                continue
            if _dashboard_error_event_matcher(
                obj,
                endpoint_filter=endpoint_filter,
                request_filter=request_filter,
                kind_filter=kind_filter,
                error_code_filter=error_code_filter,
                cache_error_code_filter=cache_error_code_filter,
                status_filter=status_filter,
                message_contains_filter=message_contains_filter,
                since_cutoff=since_cutoff,
            ):
                cleared += 1
            else:
                kept.append(obj)

    if kept:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            for row in kept:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    else:
        path.unlink(missing_ok=True)
    return {
        "cleared": int(cleared),
        "remaining": int(len(kept)),
        "path": _relative_path_or_str(path),
        "cleared_all": False,
    }


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return int(default)


def _normalize_signal_row(raw_row):
    if not isinstance(raw_row, dict):
        return {}
    skip_keys = {
        "return_pct",
        "max_drawdown_pct",
        "avg_daily_trades_display",
        "avg_hold_hours_display",
        "win_rate_pct",
        "indicator_tags",
        "indicator_params",
    }
    row = {}
    for key, value in raw_row.items():
        key_str = str(key)
        if key_str.startswith("_"):
            continue
        if key_str in skip_keys:
            continue
        row[key_str] = value
    return row


def _pick_signal_source_row(rank=1, timeframe=None):
    payload = _get_results_payload(timeframe=timeframe)
    top10 = payload.get("top10") if isinstance(payload, dict) else {}
    rows = top10.get("rows") if isinstance(top10, dict) else []
    if not isinstance(rows, list) or not rows:
        return None
    idx = max(1, _safe_int(rank, 1)) - 1
    if idx >= len(rows):
        idx = 0
    return _normalize_signal_row(rows[idx])


def _split_indicator_list(value):
    raw = str(value or "").strip()
    if not raw:
        return []
    return [part for part in re.split(r"[,+;|/]", raw) if part and part.strip()]


def _json_friendly_number(value):
    num = _parse_float(value)
    if num is None:
        return value
    if float(num).is_integer():
        return int(num)
    return float(num)


def _signal_param_fields():
    fields = []
    try:
        from scripts.autowfo.constants import INDICATOR_PARAM_FIELDS  # type: ignore

        if isinstance(INDICATOR_PARAM_FIELDS, list):
            fields.extend([str(v) for v in INDICATOR_PARAM_FIELDS if str(v).strip()])
    except Exception:
        pass
    fields.extend(
        [
            "vol_lookback",
            "vol_z",
            "tp_stop",
            "sl_stop",
            "max_hold",
        ]
    )
    return sorted(set(fields))


def _collect_strategy_params(row):
    params = {}
    for key in _signal_param_fields():
        value = row.get(key)
        if value in ("", None):
            continue
        params[key] = _json_friendly_number(value)
    return params


def _metric_snapshot_from_row(row):
    keys = [
        "oos_avg_total_return_pct",
        "avg_total_return_pct",
        "oos_avg_max_drawdown_pct",
        "avg_max_drawdown_pct",
        "oos_avg_win_rate_pct",
        "avg_win_rate_pct",
        "oos_avg_daily_trades",
        "avg_daily_trades",
        "data_end",
    ]
    snapshot = {}
    for key in keys:
        value = row.get(key)
        if value in ("", None):
            continue
        snapshot[key] = _json_friendly_number(value)
    return snapshot


def _build_live_signal_config(row, rank=1):
    row = _normalize_signal_row(row)
    cfg = _read_config()
    indicators = _split_indicator_list(row.get("indicator_list") or row.get("filter_name"))
    timeframe = str(row.get("timeframe") or "").strip()
    if not timeframe:
        raw_tfs = cfg.get("timeframes")
        if isinstance(raw_tfs, list) and raw_tfs:
            first_tf = raw_tfs[0]
            if isinstance(first_tf, dict):
                timeframe = str(first_tf.get("timeframe") or "").strip()
    symbol = str(row.get("plot_symbol") or row.get("symbol") or "").strip()
    if not symbol:
        symbols = cfg.get("trade_symbols")
        if isinstance(symbols, list) and symbols:
            symbol = str(symbols[0]).strip()

    now_utc = _now_iso()
    signal_config_id = "sigcfg_{stamp}_{rank:02d}_{tf}_{sym}".format(
        stamp=datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"),
        rank=max(1, _safe_int(rank, 1)),
        tf=_coverage_slug_text(timeframe),
        sym=_coverage_slug_text(symbol),
    )
    strategy_params = _collect_strategy_params(row)
    risk = {
        "tp_stop": _json_friendly_number(row.get("tp_stop") or cfg.get("tp_stop")),
        "sl_stop": _json_friendly_number(row.get("sl_stop") or cfg.get("sl_stop")),
        "max_hold": _json_friendly_number(row.get("max_hold") or cfg.get("max_hold")),
    }
    execution = {
        "capital_mode": str(cfg.get("capital_mode") or ""),
        "init_cash_usdt": _json_friendly_number(cfg.get("init_cash_usdt")),
        "order_size_pct": _json_friendly_number(cfg.get("order_size_pct")),
        "max_concurrent_positions": _json_friendly_number(cfg.get("max_concurrent_positions")),
        "slippage_bps": _json_friendly_number(cfg.get("slippage_bps")),
        "spread_bps": _json_friendly_number(cfg.get("spread_bps")),
        "funding_rate_daily": _json_friendly_number(cfg.get("funding_rate_daily")),
    }
    return {
        "schema_version": "autowfo.live_signal_config/v1",
        "generated_utc": now_utc,
        "signal_config_id": signal_config_id,
        "source": {
            "origin": "control_panel",
            "rank": max(1, _safe_int(rank, 1)),
            "run_id": str(row.get("run_id") or ""),
            "row_fingerprint": _coverage_slug_text(
                "{}|{}|{}|{}".format(
                    row.get("indicator_list", ""),
                    row.get("regime_name", ""),
                    row.get("vol_mode", ""),
                    row.get("timeframe", ""),
                )
            ),
        },
        "instrument": {
            "symbol": symbol,
            "timeframe": timeframe,
        },
        "strategy": {
            "indicator_list": indicators,
            "indicator_list_raw": str(row.get("indicator_list") or row.get("filter_name") or ""),
            "regime_name": str(row.get("regime_name") or ""),
            "vol_mode": str(row.get("vol_mode") or ""),
            "params": strategy_params,
        },
        "execution": execution,
        "risk": risk,
        "metrics_snapshot": _metric_snapshot_from_row(row),
        "paper_feedback_interface": {
            "post_endpoint": "/signals/paper-feedback",
            "spec_endpoint": "/signals/paper-feedback-spec.json",
            "summary_endpoint": "/signals/paper-feedback-summary.json",
            "diagnostics_endpoint": "/signals/paper-feedback-diagnostics.json",
            "recommendations_endpoint": "/signals/paper-feedback-recommendations.json",
            "export_adjusted_endpoint": "/signals/export-feedback-adjusted-config",
            "enqueue_adjusted_batch_endpoint": "/signals/enqueue-feedback-adjusted-batch",
        },
    }


def _write_live_signal_config(payload, filename_prefix="live_signal_config"):
    if not isinstance(payload, dict):
        raise ValueError("signal config payload must be object")
    instrument = payload.get("instrument") if isinstance(payload.get("instrument"), dict) else {}
    timeframe = str(instrument.get("timeframe") or "").strip()
    symbol = str(instrument.get("symbol") or "").strip()
    prefix = _coverage_slug_text(str(filename_prefix or "live_signal_config"))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = "{prefix}_{stamp}_{tf}_{sym}.json".format(
        prefix=prefix,
        stamp=stamp,
        tf=_coverage_slug_text(timeframe),
        sym=_coverage_slug_text(symbol),
    )
    out_dir = _signal_configs_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / filename
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def _export_live_signal_config(rank=1, timeframe=None, row=None):
    source_row = _normalize_signal_row(row) if isinstance(row, dict) else {}
    if not source_row:
        source_row = _pick_signal_source_row(rank=rank, timeframe=timeframe)
    if not source_row:
        raise ValueError("top combo not available")
    config_payload = _build_live_signal_config(source_row, rank=rank)
    out_path = _write_live_signal_config(config_payload)
    return config_payload, out_path


def _paper_feedback_spec():
    return {
        "schema_version": "autowfo.paper_feedback/v1",
        "endpoint": "/signals/paper-feedback",
        "required_fields": [
            "signal_config_id",
            "timestamp_utc",
            "symbol",
            "timeframe",
            "action",
        ],
        "optional_fields": [
            "entry_price",
            "exit_price",
            "qty",
            "pnl_pct",
            "commission",
            "note",
            "order_id",
            "paper_run_id",
        ],
        "action_enum": [
            "enter_long",
            "exit_long",
            "enter_short",
            "exit_short",
            "hold",
            "flat",
        ],
        "sample_payload": {
            "signal_config_id": "sigcfg_20260219_120000_01_1h_eth-btc",
            "timestamp_utc": "2026-02-19T12:00:00Z",
            "symbol": "ETH/BTC",
            "timeframe": "1h",
            "action": "enter_long",
            "entry_price": 0.03215,
            "qty": 1.25,
            "paper_run_id": "paper-001",
            "note": "filled on paper exchange",
        },
    }


def _validate_feedback_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError("payload must be object")
    required = ["signal_config_id", "timestamp_utc", "symbol", "timeframe", "action"]
    missing = [k for k in required if not str(payload.get(k, "")).strip()]
    if missing:
        raise ValueError("missing required fields: " + ", ".join(missing))

    timestamp = _parse_iso(str(payload.get("timestamp_utc")))
    if timestamp is None:
        raise ValueError("timestamp_utc must be ISO-8601 string")

    action = str(payload.get("action", "")).strip().lower()
    allowed_actions = {"enter_long", "exit_long", "enter_short", "exit_short", "hold", "flat"}
    if action not in allowed_actions:
        raise ValueError("action must be one of: " + ", ".join(sorted(allowed_actions)))

    normalized = {
        "received_utc": _now_iso(),
        "signal_config_id": str(payload.get("signal_config_id")).strip(),
        "timestamp_utc": timestamp.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "symbol": str(payload.get("symbol")).strip(),
        "timeframe": str(payload.get("timeframe")).strip(),
        "action": action,
    }
    optional_num = ["entry_price", "exit_price", "qty", "pnl_pct", "commission"]
    for key in optional_num:
        value = payload.get(key)
        if value in ("", None):
            continue
        parsed = _parse_float(value)
        if parsed is None:
            raise ValueError(f"{key} must be numeric")
        normalized[key] = float(parsed)

    optional_text = ["note", "order_id", "paper_run_id"]
    for key in optional_text:
        value = payload.get(key)
        if value in ("", None):
            continue
        normalized[key] = str(value)

    return normalized


def _record_paper_feedback(payload):
    entry = _validate_feedback_payload(payload)
    path = _paper_feedback_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry, path


def _read_paper_feedback(limit=200):
    path = _paper_feedback_log_path()
    if not path.exists():
        return []
    lines = deque(maxlen=max(1, _safe_int(limit, 200)))
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            raw = line.strip()
            if raw:
                lines.append(raw)
    rows = []
    for raw in lines:
        try:
            obj = json.loads(raw)
        except Exception:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def _paper_feedback_summary(rows):
    items = rows if isinstance(rows, list) else []
    action_counts = {}
    symbol_counts = {}
    timeframe_counts = {}
    pnl_values = []
    latest_ts = None

    for row in items:
        if not isinstance(row, dict):
            continue

        action = str(row.get("action") or "").strip().lower()
        if action:
            action_counts[action] = int(action_counts.get(action, 0)) + 1

        symbol = str(row.get("symbol") or "").strip()
        if symbol:
            symbol_counts[symbol] = int(symbol_counts.get(symbol, 0)) + 1

        timeframe = str(row.get("timeframe") or "").strip()
        if timeframe:
            timeframe_counts[timeframe] = int(timeframe_counts.get(timeframe, 0)) + 1

        pnl = _parse_float(row.get("pnl_pct"))
        if pnl is not None:
            pnl_values.append(float(pnl))

        ts = _parse_iso(str(row.get("timestamp_utc") or row.get("received_utc") or ""))
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

    pnl_summary = {
        "count": 0,
        "mean_pct": None,
        "p05_pct": None,
        "p50_pct": None,
        "p95_pct": None,
        "win_rate_pct": None,
    }
    if pnl_values:
        mean_pct = sum(pnl_values) / len(pnl_values)
        pnl_summary = {
            "count": int(len(pnl_values)),
            "mean_pct": float(mean_pct),
            "p05_pct": _percentile(pnl_values, 5),
            "p50_pct": _percentile(pnl_values, 50),
            "p95_pct": _percentile(pnl_values, 95),
            "win_rate_pct": float(sum(1 for v in pnl_values if v > 0) / len(pnl_values) * 100.0),
        }

    return {
        "total_feedback": int(len(items)),
        "latest_timestamp_utc": latest_ts.replace(microsecond=0).isoformat().replace("+00:00", "Z") if latest_ts else None,
        "action_counts": {k: action_counts[k] for k in sorted(action_counts.keys())},
        "symbol_counts": {k: symbol_counts[k] for k in sorted(symbol_counts.keys())},
        "timeframe_counts": {k: timeframe_counts[k] for k in sorted(timeframe_counts.keys())},
        "pnl_pct": pnl_summary,
    }


def _paper_feedback_diagnostics(rows, top_n=10):
    items = rows if isinstance(rows, list) else []
    top_n_i = max(1, _safe_int(top_n, 10))

    cfg_groups = {}
    action_groups = {}
    symbol_tf_groups = {}

    def _touch_group(bucket, key):
        group = bucket.get(key)
        if group is None:
            group = {
                "count": 0,
                "pnl_values": [],
                "last_ts": None,
            }
            bucket[key] = group
        return group

    for row in items:
        if not isinstance(row, dict):
            continue
        signal_config_id = str(row.get("signal_config_id") or "").strip()
        action = str(row.get("action") or "").strip().lower()
        symbol = str(row.get("symbol") or "").strip()
        timeframe = str(row.get("timeframe") or "").strip()
        pnl = _parse_float(row.get("pnl_pct"))
        ts = _parse_iso(str(row.get("timestamp_utc") or row.get("received_utc") or ""))

        if signal_config_id:
            g = _touch_group(cfg_groups, signal_config_id)
            g["count"] += 1
            if pnl is not None:
                g["pnl_values"].append(float(pnl))
            if ts is not None and (g["last_ts"] is None or ts > g["last_ts"]):
                g["last_ts"] = ts
            if symbol:
                g.setdefault("symbols", set()).add(symbol)
            if timeframe:
                g.setdefault("timeframes", set()).add(timeframe)
            if action:
                g.setdefault("actions", {}).setdefault(action, 0)
                g["actions"][action] += 1

        if action:
            g = _touch_group(action_groups, action)
            g["count"] += 1
            if pnl is not None:
                g["pnl_values"].append(float(pnl))
            if ts is not None and (g["last_ts"] is None or ts > g["last_ts"]):
                g["last_ts"] = ts

        if symbol and timeframe:
            k = f"{symbol}|{timeframe}"
            g = _touch_group(symbol_tf_groups, k)
            g["count"] += 1
            if pnl is not None:
                g["pnl_values"].append(float(pnl))
            if ts is not None and (g["last_ts"] is None or ts > g["last_ts"]):
                g["last_ts"] = ts

    def _finalize_group(key, group, include_identity=False):
        pnl_values = [float(v) for v in group.get("pnl_values", [])]
        pnl_count = len(pnl_values)
        avg_pnl = (sum(pnl_values) / pnl_count) if pnl_count else None
        median_pnl = _percentile(pnl_values, 50) if pnl_count else None
        win_rate = (sum(1 for v in pnl_values if v > 0) / pnl_count * 100.0) if pnl_count else None
        payload = {
            "count": int(group.get("count", 0)),
            "pnl_count": int(pnl_count),
            "avg_pnl_pct": float(avg_pnl) if avg_pnl is not None else None,
            "p50_pnl_pct": float(median_pnl) if median_pnl is not None else None,
            "win_rate_pct": float(win_rate) if win_rate is not None else None,
            "last_timestamp_utc": (
                group["last_ts"].replace(microsecond=0).isoformat().replace("+00:00", "Z")
                if group.get("last_ts") is not None
                else None
            ),
        }
        if include_identity:
            payload["signal_config_id"] = key
            payload["symbols"] = sorted(group.get("symbols", set()))
            payload["timeframes"] = sorted(group.get("timeframes", set()))
            payload["actions"] = {
                k: group.get("actions", {}).get(k, 0)
                for k in sorted(group.get("actions", {}).keys())
            }
        return payload

    cfg_rows = [
        _finalize_group(cfg_id, group, include_identity=True)
        for cfg_id, group in cfg_groups.items()
    ]
    cfg_rows.sort(
        key=lambda r: (
            1 if r.get("avg_pnl_pct") is None else 0,
            0.0 if r.get("avg_pnl_pct") is None else -float(r.get("avg_pnl_pct")),
            -int(r.get("count", 0)),
            str(r.get("signal_config_id", "")),
        )
    )
    cfg_with_pnl = [r for r in cfg_rows if r.get("avg_pnl_pct") is not None]
    worst_rows = sorted(
        cfg_with_pnl,
        key=lambda r: (
            float(r.get("avg_pnl_pct")),
            -int(r.get("count", 0)),
            str(r.get("signal_config_id", "")),
        ),
    )

    action_rows = []
    for action, group in action_groups.items():
        row = _finalize_group(action, group, include_identity=False)
        row["action"] = action
        action_rows.append(row)
    action_rows.sort(key=lambda r: (-int(r.get("count", 0)), str(r.get("action", ""))))

    symbol_tf_rows = []
    for key, group in symbol_tf_groups.items():
        symbol, timeframe = key.split("|", 1)
        row = _finalize_group(key, group, include_identity=False)
        row["symbol"] = symbol
        row["timeframe"] = timeframe
        symbol_tf_rows.append(row)
    symbol_tf_rows.sort(
        key=lambda r: (
            1 if r.get("avg_pnl_pct") is None else 0,
            0.0 if r.get("avg_pnl_pct") is None else -float(r.get("avg_pnl_pct")),
            -int(r.get("count", 0)),
            str(r.get("symbol", "")),
            str(r.get("timeframe", "")),
        )
    )

    return {
        "total_feedback": int(len(items)),
        "signal_config_count": int(len(cfg_rows)),
        "top_signal_configs": cfg_rows[:top_n_i],
        "worst_signal_configs": worst_rows[:top_n_i],
        "action_diagnostics": action_rows,
        "symbol_timeframe_diagnostics": symbol_tf_rows[:top_n_i],
    }


def _feedback_profile_multipliers(profile):
    p = str(profile or "").strip().lower()
    mapping = {
        "defensive": {"tp_stop": 0.90, "sl_stop": 0.85, "max_hold": 0.80},
        "balanced": {"tp_stop": 1.00, "sl_stop": 1.00, "max_hold": 1.00},
        "offensive": {"tp_stop": 1.10, "sl_stop": 1.10, "max_hold": 1.20},
    }
    if p in mapping:
        return p, dict(mapping[p])
    return "balanced", dict(mapping["balanced"])


def _derive_feedback_profile(avg_pnl_pct, win_rate_pct, pnl_count, min_samples=FEEDBACK_RECOMMEND_DEFAULT_MIN_SAMPLES):
    sample_count = max(0, _safe_int(pnl_count, 0))
    min_samples_i = max(1, _safe_int(min_samples, FEEDBACK_RECOMMEND_DEFAULT_MIN_SAMPLES))
    avg_pnl = _parse_float(avg_pnl_pct)
    win_rate = _parse_float(win_rate_pct)

    if sample_count < min_samples_i or avg_pnl is None:
        return "insufficient_data", "insufficient pnl samples"
    if avg_pnl < 0.0 or (win_rate is not None and win_rate < 45.0):
        return "defensive", "negative expectancy or low win-rate"
    if avg_pnl > 0.5 and (win_rate is None or win_rate >= 55.0):
        return "offensive", "positive expectancy with healthy win-rate"
    return "balanced", "stable mixed profile"


def _paper_feedback_recommendations(rows, top_n=10, min_samples=FEEDBACK_RECOMMEND_DEFAULT_MIN_SAMPLES):
    items = rows if isinstance(rows, list) else []
    top_n_i = max(1, _safe_int(top_n, 10))
    min_samples_i = max(1, _safe_int(min_samples, FEEDBACK_RECOMMEND_DEFAULT_MIN_SAMPLES))

    diagnostics = _paper_feedback_diagnostics(items, top_n=max(100, top_n_i * 5))
    rec_rows = []
    for row in diagnostics.get("symbol_timeframe_diagnostics", []):
        profile, reason = _derive_feedback_profile(
            row.get("avg_pnl_pct"),
            row.get("win_rate_pct"),
            row.get("pnl_count"),
            min_samples=min_samples_i,
        )
        _, multipliers = _feedback_profile_multipliers(profile)
        rec_rows.append(
            {
                "symbol": row.get("symbol"),
                "timeframe": row.get("timeframe"),
                "count": row.get("count"),
                "pnl_count": row.get("pnl_count"),
                "avg_pnl_pct": row.get("avg_pnl_pct"),
                "win_rate_pct": row.get("win_rate_pct"),
                "recommended_profile": profile,
                "risk_multipliers": multipliers,
                "reason": reason,
            }
        )

    rec_rows.sort(
        key=lambda r: (
            1 if r.get("avg_pnl_pct") is None else 0,
            0.0 if r.get("avg_pnl_pct") is None else -float(r.get("avg_pnl_pct")),
            -_safe_int(r.get("count"), 0),
            str(r.get("symbol") or ""),
            str(r.get("timeframe") or ""),
        )
    )

    cfg_rows = diagnostics.get("top_signal_configs", [])
    cfg_recommendations = []
    for row in cfg_rows:
        profile, reason = _derive_feedback_profile(
            row.get("avg_pnl_pct"),
            row.get("win_rate_pct"),
            row.get("pnl_count"),
            min_samples=min_samples_i,
        )
        _, multipliers = _feedback_profile_multipliers(profile)
        cfg_recommendations.append(
            {
                "signal_config_id": row.get("signal_config_id"),
                "count": row.get("count"),
                "pnl_count": row.get("pnl_count"),
                "avg_pnl_pct": row.get("avg_pnl_pct"),
                "win_rate_pct": row.get("win_rate_pct"),
                "recommended_profile": profile,
                "risk_multipliers": multipliers,
                "reason": reason,
            }
        )

    return {
        "total_feedback": int(len(items)),
        "min_samples": int(min_samples_i),
        "recommendations": rec_rows[:top_n_i],
        "signal_config_recommendations": cfg_recommendations[:top_n_i],
        "top_signal_configs": diagnostics.get("top_signal_configs", [])[:top_n_i],
        "worst_signal_configs": diagnostics.get("worst_signal_configs", [])[:top_n_i],
    }


def _pick_feedback_recommendation_for_row(row, recommendations_payload):
    if not isinstance(row, dict):
        return None
    if not isinstance(recommendations_payload, dict):
        return None
    symbol = str(row.get("plot_symbol") or row.get("symbol") or "").strip()
    timeframe = str(row.get("timeframe") or "").strip()
    recs = recommendations_payload.get("recommendations")
    if not isinstance(recs, list):
        return None
    for rec in recs:
        if not isinstance(rec, dict):
            continue
        if symbol and timeframe and str(rec.get("symbol") or "").strip() == symbol and str(rec.get("timeframe") or "").strip() == timeframe:
            return rec
    return recs[0] if recs else None


def _apply_feedback_adjustment_to_signal_config(signal_payload, profile="auto", recommendation=None):
    if not isinstance(signal_payload, dict):
        raise ValueError("signal payload must be object")

    payload = json.loads(json.dumps(signal_payload, ensure_ascii=False))
    risk = payload.get("risk")
    if not isinstance(risk, dict):
        risk = {}
        payload["risk"] = risk

    rec = recommendation if isinstance(recommendation, dict) else None
    resolved_profile = str(profile or "auto").strip().lower()
    if resolved_profile in {"", "auto"}:
        if rec and str(rec.get("recommended_profile") or "").strip():
            resolved_profile = str(rec.get("recommended_profile")).strip().lower()
        else:
            resolved_profile = "balanced"
    resolved_profile, multipliers = _feedback_profile_multipliers(resolved_profile)

    original_risk = {
        "tp_stop": _parse_float(risk.get("tp_stop")),
        "sl_stop": _parse_float(risk.get("sl_stop")),
        "max_hold": _parse_float(risk.get("max_hold")),
    }

    adjusted_risk = {}
    for key in ("tp_stop", "sl_stop", "max_hold"):
        base = original_risk.get(key)
        if base is None:
            continue
        mult = _parse_float(multipliers.get(key)) or 1.0
        val = float(base) * float(mult)
        if key == "max_hold":
            risk[key] = max(1, int(round(val)))
        else:
            risk[key] = round(max(0.000001, val), 6)
        adjusted_risk[key] = risk[key]

    src_id = str(payload.get("signal_config_id") or "sigcfg")
    payload["signal_config_id"] = f"{src_id}_fb_{resolved_profile}"
    payload["generated_utc"] = _now_iso()
    payload["feedback_adjustment"] = {
        "applied_utc": _now_iso(),
        "profile": resolved_profile,
        "risk_multipliers": multipliers,
        "original_risk": original_risk,
        "adjusted_risk": adjusted_risk,
        "recommendation": rec,
    }
    return payload


def _export_feedback_adjusted_signal_config(
    profile="auto",
    rank=1,
    timeframe=None,
    row=None,
    recommendation=None,
    min_samples=FEEDBACK_RECOMMEND_DEFAULT_MIN_SAMPLES,
):
    source_row = _normalize_signal_row(row) if isinstance(row, dict) else {}
    if not source_row:
        source_row = _pick_signal_source_row(rank=rank, timeframe=timeframe)
    if not source_row:
        raise ValueError("top combo not available")

    base_payload = _build_live_signal_config(source_row, rank=rank)
    rec = recommendation if isinstance(recommendation, dict) else None
    if rec is None:
        feedback_rows = _read_paper_feedback(limit=1000)
        rec_payload = _paper_feedback_recommendations(
            feedback_rows,
            top_n=20,
            min_samples=min_samples,
        )
        rec = _pick_feedback_recommendation_for_row(source_row, rec_payload)

    adjusted_payload = _apply_feedback_adjustment_to_signal_config(
        base_payload,
        profile=profile,
        recommendation=rec,
    )
    resolved_profile = str(adjusted_payload.get("feedback_adjustment", {}).get("profile") or "balanced")
    out_path = _write_live_signal_config(
        adjusted_payload,
        filename_prefix=f"live_signal_config_feedback_{resolved_profile}",
    )
    return adjusted_payload, out_path, rec


def _build_feedback_adjusted_sweep_config(source_row, adjusted_signal_payload, base_config=None):
    row = _normalize_signal_row(source_row)
    if not row:
        raise ValueError("source row is required")
    if not isinstance(adjusted_signal_payload, dict):
        raise ValueError("adjusted signal payload is required")

    cfg_source = base_config if isinstance(base_config, dict) else _read_config()
    cfg_payload = json.loads(json.dumps(cfg_source, ensure_ascii=False))

    instrument = adjusted_signal_payload.get("instrument") if isinstance(adjusted_signal_payload.get("instrument"), dict) else {}
    timeframe = str(row.get("timeframe") or instrument.get("timeframe") or "").strip()
    symbol = str(row.get("plot_symbol") or row.get("symbol") or instrument.get("symbol") or "").strip()
    if not timeframe or not symbol:
        raise ValueError("timeframe and symbol are required")

    days = _coverage_default_days(cfg_payload)
    raw_timeframes = cfg_payload.get("timeframes")
    if isinstance(raw_timeframes, list):
        for item in raw_timeframes:
            if not isinstance(item, dict):
                continue
            if str(item.get("timeframe", "")).strip() != timeframe:
                continue
            try:
                days_candidate = int(item.get("days"))
            except Exception:
                continue
            if days_candidate > 0:
                days = days_candidate
                break

    cfg_payload["timeframes"] = [{"timeframe": timeframe, "days": int(days)}]
    cfg_payload["trade_symbols"] = [symbol]
    if not str(cfg_payload.get("search_mode", "")).strip():
        cfg_payload["search_mode"] = "combo"

    def _apply_guardrail(field_name, raw_value):
        limits = FEEDBACK_SWEEP_RISK_LIMITS.get(field_name, (None, None))
        min_val, max_val = limits
        parsed = _parse_float(raw_value)
        if parsed is None:
            return None, None
        value = float(parsed)
        clamped = value
        if min_val is not None and clamped < float(min_val):
            clamped = float(min_val)
        if max_val is not None and clamped > float(max_val):
            clamped = float(max_val)
        if field_name == "max_hold":
            clamped = int(round(clamped))
            value = int(round(value))
        else:
            clamped = round(clamped, 6)
            value = round(value, 6)
        if clamped != value:
            return clamped, {
                "field": field_name,
                "input": value,
                "clamped": clamped,
                "min": min_val,
                "max": max_val,
            }
        return clamped, None

    risk = adjusted_signal_payload.get("risk") if isinstance(adjusted_signal_payload.get("risk"), dict) else {}
    warnings = []
    tp_stop, tp_warn = _apply_guardrail("tp_stop", risk.get("tp_stop"))
    sl_stop, sl_warn = _apply_guardrail("sl_stop", risk.get("sl_stop"))
    max_hold, hold_warn = _apply_guardrail("max_hold", risk.get("max_hold"))
    for item in (tp_warn, sl_warn, hold_warn):
        if item is not None:
            warnings.append(item)

    if tp_stop is not None:
        cfg_payload["tp_stops"] = [tp_stop]
    if sl_stop is not None:
        cfg_payload["sl_stops"] = [sl_stop]
    if max_hold is not None:
        cfg_payload["max_holds"] = [max_hold]

    adjustment = adjusted_signal_payload.get("feedback_adjustment")
    if not isinstance(adjustment, dict):
        adjustment = {}
    cfg_payload["feedback_adjustment"] = {
        "generated_utc": _now_iso(),
        "profile": str(adjustment.get("profile") or "balanced"),
        "signal_config_id": str(adjusted_signal_payload.get("signal_config_id") or ""),
        "timeframe": timeframe,
        "symbol": symbol,
        "risk": {
            "tp_stop": tp_stop,
            "sl_stop": sl_stop,
            "max_hold": max_hold,
        },
        "risk_guardrails": warnings,
    }

    return cfg_payload, {
        "timeframe": timeframe,
        "symbol": symbol,
        "days": int(days),
        "tp_stop": tp_stop,
        "sl_stop": sl_stop,
        "max_hold": max_hold,
        "warnings": warnings,
    }


def _enqueue_feedback_adjusted_batch(
    profile="auto",
    rank=1,
    timeframe=None,
    row=None,
    recommendation=None,
    min_samples=FEEDBACK_RECOMMEND_DEFAULT_MIN_SAMPLES,
    workflow="run",
    mode="combo",
    workers=None,
    name=None,
    auto_start=False,
):
    workflow_norm = str(workflow or "run").strip().lower()
    if workflow_norm not in {"run", "baseline"}:
        raise ValueError("workflow must be run or baseline")

    mode_raw = None if mode in (None, "") else str(mode).strip().lower()
    if workflow_norm == "baseline" and mode_raw is not None:
        raise ValueError("mode is only valid for workflow=run")
    if workflow_norm == "run" and mode_raw not in {None, "combo", "refine"}:
        raise ValueError("mode must be combo or refine")
    if workflow_norm == "run" and mode_raw is None:
        mode_raw = "combo"

    workers_i = None
    if workers not in (None, ""):
        workers_i = _safe_int(workers, 0)
        if workers_i <= 0:
            raise ValueError("workers must be > 0")

    source_row = _normalize_signal_row(row) if isinstance(row, dict) else {}
    if not source_row:
        source_row = _pick_signal_source_row(rank=rank, timeframe=timeframe)
    if not source_row:
        raise ValueError("top combo not available")

    adjusted_payload, signal_path, rec = _export_feedback_adjusted_signal_config(
        profile=profile,
        rank=rank,
        timeframe=timeframe,
        row=source_row,
        recommendation=recommendation if isinstance(recommendation, dict) else None,
        min_samples=min_samples,
    )
    cfg_payload, plan_meta = _build_feedback_adjusted_sweep_config(source_row, adjusted_payload)

    resolved_profile = str(adjusted_payload.get("feedback_adjustment", {}).get("profile") or "balanced")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    cfg_name = "feedback_{profile}_{tf}_{sym}_{stamp}.json".format(
        profile=_coverage_slug_text(resolved_profile),
        tf=_coverage_slug_text(plan_meta.get("timeframe")),
        sym=_coverage_slug_text(plan_meta.get("symbol")),
        stamp=stamp,
    )
    planned_dir = ARTIFACTS / "planned_configs"
    planned_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = planned_dir / cfg_name
    cfg_path.write_text(json.dumps(cfg_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    job_name = str(name or "fb-{profile}-{tf}-{sym}".format(
        profile=_coverage_slug_text(resolved_profile),
        tf=_coverage_slug_text(plan_meta.get("timeframe")),
        sym=_coverage_slug_text(plan_meta.get("symbol")),
    ))
    enqueue_payload = {
        "name": job_name,
        "workflow": workflow_norm,
        "config": str(cfg_path),
    }
    if mode_raw is not None:
        enqueue_payload["mode"] = mode_raw
    if workers_i is not None:
        enqueue_payload["workers"] = workers_i

    ok, msg, job = _batch_enqueue(enqueue_payload)
    if not ok:
        raise ValueError(msg)

    started = False
    start_msg = ""
    if bool(auto_start):
        started, start_msg = _batch_start()

    return {
        "job": job,
        "config_path": cfg_path,
        "config_payload": cfg_payload,
        "plan": plan_meta,
        "warnings": list(plan_meta.get("warnings") or []),
        "signal_config_path": signal_path,
        "adjusted_payload": adjusted_payload,
        "recommendation": rec,
        "profile": resolved_profile,
        "batch_started": bool(started),
        "batch_start_message": str(start_msg),
    }


def _start_run():
    global PROCESS
    with PROCESS_LOCK:
        if _is_running():
            return False, "回測已在執行中。"
        if _is_batch_running():
            return False, "Batch 執行中，請先停止 batch。"
        python_path = _python_path()
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        log_f = RUN_LOG.open("a", encoding="utf-8")
        _env = os.environ.copy()
        _env["PYTHONPATH"] = str(ROOT)
        PROCESS = subprocess.Popen(
            [python_path, str(SCRIPT)],
            cwd=str(ROOT),
            env=_env,
            stdout=log_f,
            stderr=subprocess.STDOUT,
        )
        _write_status({
            "run_id": "",
            "stage": "starting",
            "total": "",
            "done": "",
            "remaining": "",
            "skipped": "",
            "percent": "",
            "elapsed": "",
            "eta": "",
            "updated": "",
        })
        return True, "已啟動回測。"


def _start_tests():
    global TEST_PROCESS
    with TEST_PROCESS_LOCK:
        if _is_test_running():
            return False, "單元測試已在執行中。"
        python_path = _python_path()
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        log_f = TEST_LOG.open("a", encoding="utf-8")
        cmd = [
            python_path,
            "-m",
            "pytest",
            "tests/test_run_btc_regime_sweep.py",
            "tests/test_control_panel.py",
        ]
        TEST_PROCESS = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            stdout=log_f,
            stderr=subprocess.STDOUT,
        )
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        _write_test_status({
            "stage": "running",
            "started": now,
            "elapsed": "",
            "return_code": "",
            "updated": now,
        })
        return True, "已啟動單元測試。"


def _stop_tests():
    global TEST_PROCESS
    with TEST_PROCESS_LOCK:
        if not _is_test_running():
            return False, "單元測試未在執行中。"
        TEST_PROCESS.terminate()
        try:
            rc = TEST_PROCESS.wait(timeout=5)
        except Exception:
            rc = None
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        _write_test_status({
            "stage": "stopped",
            "started": "",
            "elapsed": "",
            "return_code": "" if rc is None else str(rc),
            "updated": now,
        })
        return True, "已停止單元測試。"


def _clear_test_log():
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    TEST_LOG.write_text("", encoding="utf-8")


def _read_status():
    if STATUS_JSON.exists():
        try:
            return json.loads(STATUS_JSON.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "run_id": "",
        "stage": "idle" if not _is_running() else "running",
        "total": "",
        "done": "",
        "remaining": "",
        "skipped": "",
        "percent": "",
        "elapsed": "",
        "eta": "",
        "updated": "",
    }


def _read_test_status():
    status = {
        "stage": "idle",
        "started": "",
        "elapsed": "",
        "return_code": "",
        "updated": "",
    }
    if TEST_STATUS_JSON.exists():
        try:
            status.update(json.loads(TEST_STATUS_JSON.read_text(encoding="utf-8")))
        except Exception:
            pass
    now = datetime.now(timezone.utc).replace(microsecond=0)
    with TEST_PROCESS_LOCK:
        if _is_test_running():
            status["stage"] = "running"
        elif TEST_PROCESS is not None:
            rc = TEST_PROCESS.poll()
            if rc is not None and status.get("return_code", "") == "":
                status["return_code"] = str(rc)
                status["stage"] = "finished" if rc == 0 else "failed"
    started_dt = _parse_iso(status.get("started"))
    if started_dt:
        elapsed = now - started_dt
        status["elapsed"] = str(elapsed).split(".")[0]
    status["updated"] = now.isoformat()
    _write_test_status(status)
    return status


def _read_log_tail(max_lines=LOG_MAX_LINES):
    if not RUN_LOG.exists():
        return ""
    lines = deque(maxlen=max_lines)
    with RUN_LOG.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            lines.append(line.rstrip("\n"))
    return "\n".join(lines)


def _read_test_log_tail(max_lines=LOG_MAX_LINES):
    if not TEST_LOG.exists():
        return ""
    lines = deque(maxlen=max_lines)
    with TEST_LOG.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            lines.append(line.rstrip("\n"))
    return "\n".join(lines)


def _log_html():
    content = html.escape(_read_log_tail())
    return f"""<!doctype html>
  <html>
  <head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="5">
  <title>執行紀錄</title>
  <style>
    body {{ font-family: Consolas, monospace; margin: 16px; background: #111; color: #eee; }}
    pre {{ white-space: pre-wrap; }}
    .meta {{ font-family: Arial, sans-serif; color: #aaa; margin-bottom: 8px; }}
    a {{ color: #7cc; }}
  </style>
</head>
<body>
  <div class="meta">顯示最新 {LOG_MAX_LINES} 行，5 秒自動更新。<a href="/log.txt" target="_blank">下載原始 log</a></div>
  <pre>{content}</pre>
  </body>
  </html>"""


def _test_log_html():
    content = html.escape(_read_test_log_tail())
    return f"""<!doctype html>
  <html>
  <head>
    <meta charset="utf-8">
    <meta http-equiv="refresh" content="5">
    <title>單元測試紀錄</title>
    <style>
      body {{ font-family: Consolas, monospace; margin: 16px; background: #111; color: #eee; }}
      pre {{ white-space: pre-wrap; }}
      .meta {{ font-family: Arial, sans-serif; color: #aaa; margin-bottom: 8px; }}
      a {{ color: #7cc; }}
    </style>
  </head>
  <body>
    <div class="meta">顯示最新 {LOG_MAX_LINES} 行，5 秒自動更新。<a href="/tests/log.txt" target="_blank">下載原始 log</a></div>
    <pre>{content}</pre>
  </body>
  </html>"""


INDEX_HTML = """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>回測控制台</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/datatables.net-dt@1.13.8/css/jquery.dataTables.min.css">
  <style>
    body { font-family: "Noto Sans TC", Arial, sans-serif; margin: 24px; color: #111; background: #f7f7f7; }
    h1, h2 { margin: 16px 0 8px; }
    .panel { background: #fff; border: 1px solid #e6e6e6; border-radius: 12px; padding: 16px; margin-bottom: 16px; }
    .row { margin: 8px 0; display: flex; gap: 12px; flex-wrap: wrap; }
    button { padding: 8px 14px; font-size: 14px; border: 1px solid #ddd; border-radius: 8px; cursor: pointer; background: #fafafa; }
    button:hover { background: #f0f0f0; }
    table { border-collapse: collapse; width: 100%; margin-top: 8px; }
    th, td { border: 1px solid #ddd; padding: 6px 8px; text-align: right; }
    th { background: #f3f3f3; text-align: right; }
    td:first-child, th:first-child { text-align: left; }
    .links a { margin-right: 12px; }
    .kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; }
    .kpi { border: 1px solid #ececec; border-radius: 10px; padding: 12px; background: #fafafa; }
    .kpi .label { color: #666; font-size: 12px; }
    .kpi .value { font-size: 18px; font-weight: 600; margin-top: 4px; }
    .pos { color: #0b7a36; }
    .neg { color: #b3122f; }
    .muted { color: #888; }
    .note { font-size: 12px; color: #666; }
    .filter-group { display: flex; gap: 12px; flex-wrap: wrap; align-items: flex-end; }
    .filter-group label { font-size: 12px; color: #555; display: flex; flex-direction: column; gap: 4px; }
    .filter-group input, .filter-group select { padding: 6px 8px; border: 1px solid #ddd; border-radius: 6px; min-width: 120px; }
    .symbol-dropdown { border: 1px solid #ddd; border-radius: 8px; padding: 6px 8px; background: #fafafa; min-width: 220px; }
    .symbol-options { max-height: 160px; overflow-y: auto; display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 6px 12px; padding: 8px 0; }
    .symbol-options label { font-size: 12px; color: #333; display: flex; align-items: center; gap: 6px; }
      .chart-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px; }
      .chart-card { border: 1px solid #ececec; border-radius: 10px; padding: 8px; background: #fff; }
      canvas { width: 100%; height: 320px; }
      .toolbar { display: flex; gap: 12px; flex-wrap: wrap; }
      .log-box { background: #111; color: #eee; padding: 12px; border-radius: 8px; max-height: 240px; overflow: auto; white-space: pre-wrap; }
      .tag-list { display: flex; flex-wrap: wrap; gap: 6px; }
      .tag { background: #eef3ff; color: #1a3a7a; border: 1px solid #d8e3ff; border-radius: 12px; padding: 2px 8px; font-size: 12px; }
      .param-summary { font-size: 12px; color: #333; line-height: 1.4; white-space: normal; }
      .row-expand { cursor: pointer; }
      .detail-wrap { background: #fafafa; border: 1px solid #eee; border-radius: 8px; padding: 12px; }
      .detail-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 6px 12px; }
      .detail-item { font-size: 12px; }
      .detail-label { color: #666; margin-right: 6px; }
      .detail-value { color: #111; font-weight: 600; }
      .text-left { text-align: left; }
    </style>
  </head>
  <body>
    <h1>回測控制台</h1>

    <div class="panel">
    <div class="row">
      <button id="startBtn">開始回測</button>
      <button id="pauseBtn">暫停</button>
      <button id="resumeBtn">繼續</button>
      <button id="clearLogBtn">清空執行紀錄</button>
    </div>
      <div class="row links">
        <a href="/status" target="_blank">狀態頁</a>
        <a id="reportLink" href="/report" target="_blank">最新報告</a>
        <a href="/log" target="_blank">執行紀錄</a>
        <a href="/log.txt" target="_blank">下載紀錄</a>
      </div>
    <table>
      <tr><th>階段</th><td id="stage"></td></tr>
      <tr><th>總組合</th><td id="total"></td></tr>
      <tr><th>已完成</th><td id="done"></td></tr>
      <tr><th>已跳過</th><td id="skipped"></td></tr>
      <tr><th>剩餘</th><td id="remaining"></td></tr>
      <tr><th>進度(%)</th><td id="percent"></td></tr>
      <tr><th>經過時間</th><td id="elapsed"></td></tr>
      <tr><th>預估剩餘</th><td id="eta"></td></tr>
      <tr><th>更新時間</th><td id="updated"></td></tr>
      </table>
    </div>

    <div class="panel">
      <h2>單元測試</h2>
      <div class="row">
        <button id="testStartBtn">執行單元測試</button>
        <button id="testStopBtn">停止測試</button>
        <button id="testClearLogBtn">清空測試紀錄</button>
        <a href="/tests/log" target="_blank">測試紀錄</a>
        <a href="/tests/log.txt" target="_blank">下載測試紀錄</a>
      </div>
      <table>
        <tr><th>狀態</th><td id="testStage"></td></tr>
        <tr><th>開始時間</th><td id="testStarted"></td></tr>
        <tr><th>已耗時</th><td id="testElapsed"></td></tr>
        <tr><th>退出碼</th><td id="testReturnCode"></td></tr>
        <tr><th>更新時間</th><td id="testUpdated"></td></tr>
      </table>
      <div class="note">執行範圍：tests/test_run_btc_regime_sweep.py、tests/test_control_panel.py</div>
      <pre id="testLog" class="log-box"></pre>
    </div>

    <div class="panel">
      <h2>結果總覽</h2>
      <div class="kpi-grid" id="kpis"></div>
      <div class="note" id="dataNote"></div>
    <div class="row toolbar">
      <button id="exportFilteredBtn">匯出篩選結果 CSV</button>
      <button id="exportTopBtn">匯出 Top10 CSV</button>
    </div>
  </div>

  <div class="panel">
    <h2>回測設定</h2>
    <div class="filter-group">
      <label>搜尋模式
        <select id="cfgMode">
          <option value="combo">combo（找組合）</option>
          <option value="refine">refine（細找參數）</option>
        </select>
      </label>
      <label>時間框架
        <input id="cfgTimeframe" type="text" placeholder="例如 3m">
      </label>
        <label>資料天數
          <input id="cfgDays" type="number" min="1" step="1" placeholder="例如 60">
        </label>
        <label>WF 訓練天數
          <input id="cfgWfTrainDays" type="number" min="1" step="1" placeholder="例如 120">
        </label>
        <label>WF 驗證天數
          <input id="cfgWfTestDays" type="number" min="1" step="1" placeholder="例如 30">
        </label>
        <label>WF 步長天數
          <input id="cfgWfStepDays" type="number" min="1" step="1" placeholder="例如 30">
        </label>
        <label>資金模式
          <select id="cfgCapitalMode">
            <option value="shared">共享資金</option>
            <option value="per_symbol">每幣獨立</option>
          </select>
        </label>
        <label>起始資金(USDT/每幣)
          <input id="cfgInitCash" type="number" min="0" step="1" placeholder="例如 1000">
        </label>
        <label>每筆比例(%)
          <input id="cfgOrderSize" type="number" min="0" step="0.1" placeholder="例如 50">
        </label>
        <label>最大同時持倉
          <input id="cfgMaxPositions" type="number" min="1" step="1" placeholder="例如 2">
        </label>
        <label>交易幣對
          <details class="symbol-dropdown" id="cfgSymbolsDropdown">
            <summary id="cfgSymbolsSummary">選擇幣對</summary>
            <div class="symbol-options" id="cfgSymbolsOptions"></div>
          </details>
        <div class="row">
          <button type="button" id="loadTopSymbolsBtn">載入熱門前10</button>
        </div>
        <input id="cfgTradeSymbols" type="text" placeholder="例如 ETH/BTC,BNB/BTC,ADA/BTC">
      </label>
      <label>組合大小
        <input id="cfgComboSizes" type="text" placeholder="例如 2,3,4">
      </label>
        <label>組合種子
          <input id="cfgSeed" type="number" step="1" placeholder="例如 42">
        </label>
        <label>滑點(bps)
          <input id="cfgSlippage" type="number" step="0.1" placeholder="例如 2">
        </label>
        <label>價差(bps)
          <input id="cfgSpread" type="number" step="0.1" placeholder="例如 2">
        </label>
        <label>資金費率/日
          <input id="cfgFunding" type="number" step="0.0001" placeholder="例如 0.0003">
        </label>
        <label>分段起點
          <input id="cfgSegStart" type="number" step="1" placeholder="例如 0">
        </label>
      <label>分段大小
        <input id="cfgSegSize" type="number" step="1" placeholder="留空為全量">
      </label>
      <label>細找 Top N
        <input id="cfgTopN" type="number" step="1" placeholder="例如 50">
      </label>
      <div class="row">
        <button id="saveConfigBtn">儲存設定</button>
        <span class="note" id="configStatus"></span>
      </div>
    </div>
    <div class="note">設定寫入 artifacts/sweep_config.json，開始回測時會自動讀取。</div>
  </div>
  <div class="panel">
    <h2>篩選條件</h2>
    <div class="filter-group">
      <label>時間框架
        <select id="filterTimeframe">
          <option value="all">全部</option>
        </select>
      </label>
      <label>驗證總報酬(%) ≥
        <input id="filterOosReturn" type="number" step="0.1" placeholder="例如 0">
      </label>
      <label>驗證勝率(%) ≥
        <input id="filterOosWinRate" type="number" step="1" placeholder="例如 50">
      </label>
      <label>平均每日交易 ≥
        <input id="filterDailyTrades" type="number" step="0.1" placeholder="例如 5">
      </label>
      <label>驗證最大回撤(%) ≤
        <input id="filterMaxDrawdown" type="number" step="0.1" placeholder="例如 5">
      </label>
      <label>
        <span>OOS > 0</span>
        <input id="filterOosPositive" type="checkbox">
      </label>
    </div>
    <div class="row">
      <button id="applyFilterBtn">套用篩選</button>
      <button id="resetFilterBtn">清除篩選</button>
    </div>
    <div class="note" id="filterNote"></div>
  </div>

  <div class="panel">
    <h2>視覺化</h2>
    <div class="chart-grid">
      <div class="chart-card">
        <div class="note">驗證總報酬(%) vs 驗證最大回撤(%)</div>
        <canvas id="scatterChart" width="600" height="320"></canvas>
      </div>
      <div class="chart-card">
        <div class="note">驗證總報酬(%) 分佈</div>
        <canvas id="histChart" width="600" height="320"></canvas>
      </div>
      <div class="chart-card">
        <div class="note">風險-報酬前緣（驗證總報酬 vs 回撤）</div>
        <canvas id="frontierChart" width="600" height="320"></canvas>
      </div>
    </div>
  </div>

  <div class="panel">
    <h2>Top10（最新）</h2>
    <table id="top10Table">
      <thead></thead>
      <tbody></tbody>
    </table>
  </div>

  <div class="panel">
    <h2>所有組合（可排序/搜尋）</h2>
    <table id="comboTable">
      <thead></thead>
      <tbody></tbody>
    </table>
  </div>

  <div class="panel">
    <h2>歷史排行榜</h2>
    <table id="leaderboardTable">
      <thead></thead>
      <tbody></tbody>
    </table>
  </div>

  <script src="https://cdn.jsdelivr.net/npm/jquery@3.7.1/dist/jquery.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/datatables.net@1.13.8/js/jquery.dataTables.min.js"></script>
  <script src="/app.js"></script>
</body>
</html>
"""

APP_JS = """
    const jq = window.jQuery;
    const hasDataTables = !!(jq && jq.fn && jq.fn.dataTable);
    const LABELS = {
      exchange: '交易所',
      base_symbol: '基準幣對',
      trade_symbols_key: '交易幣對集合',
      timeframe: '時間框架',
      data_days: '資料天數',
      regime_name: '策略型態',
      regime_type: '訊號類型',
      vol_mode: '波動條件',
      regime_rsi_long: 'RSI 回歸多頭門檻',
      regime_rsi_short: 'RSI 回歸空頭門檻',
      filter_name: '指標組合',
      indicator_list: '指標清單',
      indicator_count: '指標數量',
      vol_lookback: '波動回看(根)',
      vol_z: '波動 Z 分數門檻',
      mom_lookback: '動能回看(根)',
      trade_mom_lookback: '交易幣動能回看(根)',
      tp_stop: '獲利%出場',
      sl_stop: '止損',
      max_hold: '最長持有(根)',
      rsi_window: 'RSI 週期',
      rsi_long: 'RSI 多頭門檻',
      rsi_short: 'RSI 空頭門檻',
      bb_width: '布林帶寬度門檻',
      atr_ratio: 'ATR/價格門檻',
      ma_fast: 'MA 快線',
      ma_slow: 'MA 慢線',
      macd_hist_ratio: 'MACD 柱狀比率門檻',
      stoch_long: 'KD 多頭門檻',
      stoch_short: 'KD 空頭門檻',
      obv_lookback: 'OBV 回看(根)',
      volume_lookback: '量能回看(根)',
      volume_z: '量能 Z 分數門檻',
      roc_lookback: 'ROC 回看(根)',
      roc_threshold: 'ROC 門檻',
      mfi_long: 'MFI 多頭門檻',
      mfi_short: 'MFI 空頭門檻',
      cmf_lookback: 'CMF 回看(根)',
      cmf_threshold: 'CMF 門檻',
      vroc_lookback: '量能變化率 回看(根)',
      vroc_threshold: '量能變化率 門檻',
      ad_lookback: 'A/D 回看(根)',
      oos_avg_total_return_pct: '驗證平均總報酬(%)',
      oos_avg_win_rate_pct: '驗證平均勝率(%)',
      oos_avg_avg_trade_pct: '驗證平均每筆(%)',
      oos_avg_max_drawdown_pct: '驗證平均最大回撤(%)',
      oos_avg_position_coverage_pct: '驗證平均持倉覆蓋率(%)',
      oos_avg_total_trades: '驗證平均交易筆數',
      oos_min_total_trades: '驗證最小交易筆數',
      oos_avg_daily_trades: '驗證平均每日交易次數',
        oos_avg_hold_hours: '驗證平均持倉(小時)',
        avg_total_return_pct: '平均總報酬(%)',
        avg_win_rate_pct: '平均勝率(%)',
        avg_avg_trade_pct: '平均每筆(%)',
        avg_max_drawdown_pct: '平均最大回撤(%)',
        avg_position_coverage_pct: '平均持倉覆蓋率(%)',
        avg_daily_trades: '平均每日交易次數',
        avg_total_trades: '平均總交易筆數',
        min_total_trades: '最小總交易筆數',
        avg_hold_hours: '平均持倉(小時)',
        indicator_tags: '指標種類',
        indicator_params: '指標參數摘要',
        return_pct: '總報酬(%)',
        max_drawdown_pct: '最大回撤(%)',
        avg_daily_trades_display: '平均每日交易',
        avg_hold_hours_display: '平均持倉(小時)',
        win_rate_pct: '勝率(%)',
        data_start: '資料開始',
        data_end: '資料結束',
        timestamp_utc: 'UTC 時間',
        run_id: '執行編號',
        plot_symbol: '圖表幣對',
      report_file: '報告檔案'
    };

    const NUM_COLS = new Set([
      'vol_lookback','vol_z','mom_lookback','trade_mom_lookback','tp_stop','sl_stop','max_hold',
      'rsi_window','rsi_long','rsi_short','bb_width','atr_ratio','ma_fast','ma_slow',
      'macd_hist_ratio','stoch_long','stoch_short','obv_lookback','volume_lookback','volume_z',
      'roc_lookback','roc_threshold','mfi_long','mfi_short','cmf_lookback','cmf_threshold',
      'vroc_lookback','vroc_threshold','ad_lookback','indicator_count',
      'oos_avg_total_return_pct','oos_avg_win_rate_pct','oos_avg_avg_trade_pct','oos_avg_max_drawdown_pct',
      'oos_avg_position_coverage_pct','oos_avg_total_trades','oos_min_total_trades','oos_avg_daily_trades',
        'oos_avg_hold_hours',
        'avg_total_return_pct','avg_win_rate_pct','avg_avg_trade_pct','avg_max_drawdown_pct',
        'avg_position_coverage_pct','avg_daily_trades','avg_total_trades','min_total_trades','avg_hold_hours'
      ]);

      const TOP_COLS = [
        'timeframe',
        'data_days',
        'regime_name',
        'indicator_tags',
        'indicator_params',
        'return_pct',
        'max_drawdown_pct',
        'avg_daily_trades_display',
        'avg_hold_hours_display',
        'win_rate_pct'
      ];

      const COMBO_COLS = TOP_COLS;

    const LB_COLS = [
      'timestamp_utc','run_id','plot_symbol','timeframe','data_days',
      'oos_avg_total_return_pct','avg_total_return_pct','avg_daily_trades','avg_hold_hours','min_total_trades','report_file'
    ];

    function parseNumber(val) {
      if (val === null || val === undefined) return null;
      if (typeof val === 'string' && val.trim() === '') return null;
      const num = Number(val);
      if (!Number.isFinite(num)) return null;
      return num;
    }

    function formatNumber(val) {
      const num = parseNumber(val);
      if (num === null) return '';
      return num.toFixed(4).replace(/\.0+$/, '');
    }

    function decodeHtml(text) {
      if (!text) return '';
      const el = document.createElement('textarea');
      el.innerHTML = text;
      return el.value;
    }

    function escapeHtml(text) {
      if (text === null || text === undefined) return '';
      return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    }

    const PARAM_ORDER = [
      'vol_lookback','vol_z','mom_lookback','trade_mom_lookback',
      'rsi_window','rsi_long','rsi_short',
      'bb_width','atr_ratio','ma_fast','ma_slow','macd_hist_ratio',
      'stoch_long','stoch_short','obv_lookback','volume_lookback','volume_z',
      'roc_lookback','roc_threshold','mfi_long','mfi_short',
      'cmf_lookback','cmf_threshold','vroc_lookback','vroc_threshold','ad_lookback',
      'tp_stop','sl_stop','max_hold'
    ];

    const PARAM_SHORT = {
      vol_lookback: 'vol_lb',
      vol_z: 'vol_z',
      mom_lookback: 'mom_lb',
      trade_mom_lookback: 'trade_mom_lb',
      rsi_window: 'rsi',
      rsi_long: 'rsiL',
      rsi_short: 'rsiS',
      bb_width: 'bb',
      atr_ratio: 'atr',
      ma_fast: 'maF',
      ma_slow: 'maS',
      macd_hist_ratio: 'macd',
      stoch_long: 'stochL',
      stoch_short: 'stochS',
      obv_lookback: 'obv',
      volume_lookback: 'volu_lb',
      volume_z: 'volu_z',
      roc_lookback: 'roc_lb',
      roc_threshold: 'roc',
      mfi_long: 'mfiL',
      mfi_short: 'mfiS',
      cmf_lookback: 'cmf_lb',
      cmf_threshold: 'cmf',
      vroc_lookback: 'vroc_lb',
      vroc_threshold: 'vroc',
      ad_lookback: 'ad_lb',
      tp_stop: 'tp',
      sl_stop: 'sl',
      max_hold: 'hold'
    };

    const PARAM_EXCLUDE_PREFIXES = [
      'oos_','avg_','min_','max_','total_','position_','win_','data_',
      'timestamp','run_id','plot_','report_','trade_symbols','base_symbol','exchange','timeframe',
      'regime_','vol_mode','filter_name','indicator_list','indicator_count'
    ];

    function isParamLikeKey(key) {
      if (!key) return false;
      if (PARAM_ORDER.includes(key)) return true;
      const lower = key.toLowerCase();
      if (PARAM_EXCLUDE_PREFIXES.some(p => lower.startsWith(p))) return false;
      return /(lookback|window|threshold|ratio|_long|_short)$/.test(lower);
    }

    function collectParamPairs(row) {
      const pairs = [];
      const seen = new Set();
      PARAM_ORDER.forEach(key => {
        const val = row[key];
        if (val !== null && val !== undefined && val !== '') {
          pairs.push([key, val]);
          seen.add(key);
        }
      });
      Object.keys(row).forEach(key => {
        if (seen.has(key)) return;
        if (!isParamLikeKey(key)) return;
        const val = row[key];
        if (val === null || val === undefined || val === '') return;
        pairs.push([key, val]);
        seen.add(key);
      });
      return pairs;
    }

    function getIndicatorTags(row) {
      const raw = row.indicator_list || row.filter_name || '';
      const decoded = decodeHtml(String(raw));
      if (!decoded) return [];
      const parts = decoded.split(/[,+;|\/]+/).map(s => s.trim()).filter(Boolean);
      if (!parts.length) return [decoded.trim()];
      const unique = [];
      const seen = new Set();
      parts.forEach(p => {
        const clean = p.replace(/[()\[\]]/g, '').trim();
        if (!clean || seen.has(clean)) return;
        seen.add(clean);
        unique.push(clean);
      });
      return unique;
    }

    function buildIndicatorTagsCell(td, row) {
      const tags = getIndicatorTags(row);
      if (!tags.length) {
        td.textContent = '';
        return;
      }
      td.classList.add('text-left');
      const container = document.createElement('div');
      container.className = 'tag-list';
      const visible = tags.slice(0, 6);
      visible.forEach(tag => {
        const span = document.createElement('span');
        span.className = 'tag';
        span.textContent = tag;
        container.appendChild(span);
      });
      const remaining = tags.length - visible.length;
      if (remaining > 0) {
        const span = document.createElement('span');
        span.className = 'tag';
        span.textContent = `+${remaining}`;
        container.appendChild(span);
      }
      td.appendChild(container);
    }

    function buildParamSummaryCell(td, row) {
      const pairs = collectParamPairs(row);
      if (!pairs.length) {
        td.textContent = '';
        return;
      }
      td.classList.add('text-left');
      const text = pairs.map(([key, val]) => {
        const label = PARAM_SHORT[key] || key;
        return `${label}=${formatNumber(val)}`;
      }).join(', ');
      const display = text.length > 120 ? `${text.slice(0, 117)}...` : text;
      const div = document.createElement('div');
      div.className = 'param-summary';
      div.textContent = display;
      if (display !== text) div.title = text;
      td.appendChild(div);
    }

    function getColumnDisplayValue(row, col) {
      if (col === 'indicator_tags') {
        return getIndicatorTags(row).join(' + ');
      }
      if (col === 'indicator_params') {
        const pairs = collectParamPairs(row);
        if (!pairs.length) return '';
        return pairs.map(([key, val]) => {
          const label = PARAM_SHORT[key] || key;
          return `${label}=${formatNumber(val)}`;
        }).join(', ');
      }
      if (col === 'return_pct') {
        const val = pickMetric(row, ['oos_avg_total_return_pct', 'avg_total_return_pct', 'total_return_pct']);
        return val === null ? '' : formatNumber(val);
      }
      if (col === 'max_drawdown_pct') {
        const val = pickMetric(row, ['oos_avg_max_drawdown_pct', 'avg_max_drawdown_pct', 'max_drawdown_pct']);
        return val === null ? '' : formatNumber(val);
      }
      if (col === 'avg_daily_trades_display') {
        const val = pickMetric(row, ['oos_avg_daily_trades', 'avg_daily_trades']);
        return val === null ? '' : formatNumber(val);
      }
      if (col === 'avg_hold_hours_display') {
        const val = pickMetric(row, ['oos_avg_hold_hours', 'avg_hold_hours']);
        return val === null ? '' : formatNumber(val);
      }
      if (col === 'win_rate_pct') {
        const val = pickMetric(row, ['oos_avg_win_rate_pct', 'avg_win_rate_pct', 'win_rate_pct']);
        return val === null ? '' : formatNumber(val);
      }
      const raw = row[col] ?? '';
      if (NUM_COLS.has(col)) {
        return formatNumber(raw);
      }
      return decodeHtml(raw);
    }

    function pickMetric(row, keys) {
      for (const key of keys) {
        const num = parseNumber(row[key]);
        if (num !== null) return num;
      }
      return null;
    }

    function buildDetailElement(row) {
      const wrapper = document.createElement('div');
      wrapper.className = 'detail-wrap';

      const grid = document.createElement('div');
      grid.className = 'detail-grid';

      const pairs = collectParamPairs(row);
      const detailItems = [];

      if (row.indicator_list || row.filter_name) {
        detailItems.push(['指標組合', decodeHtml(row.indicator_list || row.filter_name)]);
      }

      pairs.forEach(([key, val]) => {
        const label = LABELS[key] || key;
        detailItems.push([label, formatNumber(val)]);
      });

      Object.keys(row).forEach(key => {
        if (PARAM_ORDER.includes(key)) return;
        if (key === 'indicator_list' || key === 'filter_name') return;
        if (TOP_COLS.includes(key) || COMBO_COLS.includes(key)) return;
        if (key.startsWith('oos_') || key.startsWith('avg_')) return;
        const val = row[key];
        if (val === null || val === undefined || val === '') return;
        const label = LABELS[key] || key;
        detailItems.push([label, decodeHtml(val)]);
      });

      if (!detailItems.length) {
        const empty = document.createElement('div');
        empty.textContent = '沒有額外參數';
        wrapper.appendChild(empty);
        return wrapper;
      }

      detailItems.forEach(([label, value]) => {
        const item = document.createElement('div');
        item.className = 'detail-item';
        const labelSpan = document.createElement('span');
        labelSpan.className = 'detail-label';
        labelSpan.textContent = `${label}:`;
        const valueSpan = document.createElement('span');
        valueSpan.className = 'detail-value';
        valueSpan.textContent = value;
        item.appendChild(labelSpan);
        item.appendChild(valueSpan);
        grid.appendChild(item);
      });

      wrapper.appendChild(grid);
      return wrapper;
    }

    async function refreshTests() {
      try {
        const res = await fetch('/tests/status.json', { cache: 'no-store' });
        const data = await res.json();
        const mappings = {
          testStage: data.stage ?? '',
          testElapsed: data.elapsed ?? '',
          testReturnCode: data.return_code ?? ''
        };
        for (const [id, val] of Object.entries(mappings)) {
          const el = document.getElementById(id);
          if (el) el.textContent = val;
        }
        const startedEl = document.getElementById('testStarted');
        if (startedEl) {
          const raw = data.started;
          if (raw) {
            const parsed = Date.parse(raw);
            startedEl.textContent = Number.isNaN(parsed) ? raw : new Date(parsed).toLocaleString();
          } else {
            startedEl.textContent = '';
          }
        }
        const updatedEl = document.getElementById('testUpdated');
        if (updatedEl) {
          const raw = data.updated;
          if (raw) {
            const parsed = Date.parse(raw);
            updatedEl.textContent = Number.isNaN(parsed) ? raw : new Date(parsed).toLocaleString();
          } else {
            updatedEl.textContent = '';
          }
        }
        const logRes = await fetch('/tests/log-tail.txt', { cache: 'no-store' });
        if (logRes.ok) {
          const logText = await logRes.text();
          const logEl = document.getElementById('testLog');
          if (logEl) logEl.textContent = logText;
        }
      } catch (e) {}
    }

    function buildTable(tableId, rows, columns, options = {}) {
      const table = document.getElementById(tableId);
      const thead = table.querySelector('thead');
      const tbody = table.querySelector('tbody');
      thead.innerHTML = '';
      tbody.innerHTML = '';
      const cols = columns && columns.length ? columns : (rows.length ? Object.keys(rows[0]) : []);
      const tr = document.createElement('tr');
      cols.forEach(col => {
        const th = document.createElement('th');
        th.textContent = LABELS[col] || col;
        tr.appendChild(th);
      });
      thead.appendChild(tr);

      rows.forEach(row => {
        const tr = document.createElement('tr');
        tr.classList.add('row-expand');
        tr.dataset.row = JSON.stringify(row);
        cols.forEach(col => {
          const td = document.createElement('td');
          if (col === 'indicator_tags') {
            buildIndicatorTagsCell(td, row);
          } else if (col === 'indicator_params') {
            buildParamSummaryCell(td, row);
          } else if (col === 'return_pct') {
            const val = pickMetric(row, ['oos_avg_total_return_pct', 'avg_total_return_pct', 'total_return_pct']);
            if (val !== null) {
              td.textContent = formatNumber(val);
              td.setAttribute('data-order', String(val));
              if (val > 0) td.classList.add('pos');
              if (val < 0) td.classList.add('neg');
            }
          } else if (col === 'max_drawdown_pct') {
            const val = pickMetric(row, ['oos_avg_max_drawdown_pct', 'avg_max_drawdown_pct', 'max_drawdown_pct']);
            if (val !== null) {
              td.textContent = formatNumber(val);
              td.setAttribute('data-order', String(val));
              if (val > 0) td.classList.add('neg');
              if (val < 0) td.classList.add('pos');
            }
          } else if (col === 'avg_daily_trades_display') {
            const val = pickMetric(row, ['oos_avg_daily_trades', 'avg_daily_trades']);
            if (val !== null) {
              td.textContent = formatNumber(val);
              td.setAttribute('data-order', String(val));
            }
          } else if (col === 'avg_hold_hours_display') {
            const val = pickMetric(row, ['oos_avg_hold_hours', 'avg_hold_hours']);
            if (val !== null) {
              td.textContent = formatNumber(val);
              td.setAttribute('data-order', String(val));
            }
          } else if (col === 'win_rate_pct') {
            const val = pickMetric(row, ['oos_avg_win_rate_pct', 'avg_win_rate_pct', 'win_rate_pct']);
            if (val !== null) {
              td.textContent = formatNumber(val);
              td.setAttribute('data-order', String(val));
              if (val > 0) td.classList.add('pos');
            }
          } else {
            const raw = row[col] ?? '';
            if (NUM_COLS.has(col)) {
              const num = Number(raw);
              td.textContent = formatNumber(raw);
              if (!Number.isNaN(num)) {
                td.setAttribute('data-order', String(num));
                if (num > 0) td.classList.add('pos');
                if (num < 0) td.classList.add('neg');
              }
            } else {
              td.textContent = decodeHtml(raw);
            }
          }
          tr.appendChild(td);
        });
        tbody.appendChild(tr);
      });

      if (hasDataTables) {
        if (jq.fn.dataTable.isDataTable(table)) {
          jq(table).DataTable().destroy();
        }
        const defaultOrder = [];
        const returnIdx = cols.indexOf('return_pct');
        const ddIdx = cols.indexOf('max_drawdown_pct');
        if (returnIdx >= 0) defaultOrder.push([returnIdx, 'desc']);
        if (ddIdx >= 0) defaultOrder.push([ddIdx, 'asc']);
        const dt = jq(table).DataTable({
          pageLength: 25,
          order: defaultOrder,
          lengthMenu: [[25, 50, 100, 200], [25, 50, 100, 200]]
        });
        if (options.rowDetails) {
          jq(table).find('tbody').off('click', 'tr').on('click', 'tr', function () {
            if (this.classList.contains('child')) return;
            const row = dt.row(this);
            const node = row.node();
            if (!node || !node.dataset.row) return;
            let rowData = null;
            try {
              rowData = JSON.parse(node.dataset.row);
            } catch (e) {
              return;
            }
            if (row.child.isShown()) {
              row.child.hide();
              this.classList.remove('shown');
            } else {
              row.child(buildDetailElement(rowData)).show();
              this.classList.add('shown');
            }
          });
        }
      }
    }

    function bestMetric(rows, key) {
      let best = null;
      rows.forEach(row => {
        const val = parseNumber(row[key]);
        if (val !== null && (best === null || val > best)) best = val;
      });
      return best;
    }

    function hasNumericMetric(rows, key) {
      return rows.some(row => parseNumber(row[key]) !== null);
    }

    function updateKpis(payload, filteredRows) {
      const rows = payload.combo.rows || [];
      const filtered = filteredRows || rows;
      const kpiContainer = document.getElementById('kpis');
      kpiContainer.innerHTML = '';
      const total = payload.combo.total || 0;
      const bestOos = bestMetric(filtered, 'oos_avg_total_return_pct');
      const bestAvg = bestMetric(filtered, 'avg_total_return_pct');
      const bestDaily = bestMetric(filtered, 'avg_daily_trades');
      const bestHold = bestMetric(filtered, 'avg_hold_hours');
      const latestReport = payload.latest_report ? `/artifacts/${payload.latest_report}` : '';

      const cards = [
        { label: '篩選後組合', value: filtered.length },
        { label: '全部組合', value: total },
        { label: '最佳驗證總報酬(%)', value: bestOos },
        { label: '最佳平均總報酬(%)', value: bestAvg },
        { label: '最佳平均每日交易', value: bestDaily },
        { label: '最佳平均持倉(小時)', value: bestHold },
        { label: '最新報告', value: payload.latest_report || '無' },
      ];

      cards.forEach(card => {
        const div = document.createElement('div');
        div.className = 'kpi';
        const label = document.createElement('div');
        label.className = 'label';
        label.textContent = card.label;
        const value = document.createElement('div');
        value.className = 'value';
        if (typeof card.value === 'number') {
          value.textContent = formatNumber(card.value);
          if (card.value > 0) value.classList.add('pos');
          if (card.value < 0) value.classList.add('neg');
        } else if (card.label === '最新報告' && latestReport) {
          const link = document.createElement('a');
          link.href = latestReport;
          link.textContent = card.value;
          link.target = '_blank';
          value.appendChild(link);
        } else {
          value.textContent = card.value ?? '';
        }
        div.appendChild(label);
        div.appendChild(value);
        kpiContainer.appendChild(div);
      });

      const note = document.getElementById('dataNote');
      if (payload.combo.truncated) {
        note.textContent = `只載入最新 ${payload.combo.rows.length} 筆（總共 ${payload.combo.total} 筆），可調整伺服器限制。`;
      } else {
        note.textContent = `資料更新時間：${payload.generated_utc || ''}`;
      }
      if (!hasNumericMetric(filtered, 'oos_avg_total_return_pct')) {
        note.textContent += '；目前無有效 OOS 指標，已回退顯示平均值（請確認資料天數是否足夠支援 WF 視窗）。';
      }
    }

    function updateTimeframeOptions(rows, available) {
      const select = document.getElementById('filterTimeframe');
      const current = select.value || 'all';
      const values = new Set();
      (available || []).forEach(val => {
        if (val && val !== 'nan') values.add(val);
      });
      rows.forEach(r => {
        if (r.timeframe && r.timeframe !== 'nan') values.add(r.timeframe);
      });
      const sortedValues = Array.from(values).sort();
      select.innerHTML = '<option value="all">全部</option>';
      sortedValues.forEach(val => {
        const opt = document.createElement('option');
        opt.value = val;
        opt.textContent = val;
        select.appendChild(opt);
      });
      if (sortedValues.includes(current)) {
        select.value = current;
      }
    }
    function renderSymbolOptions(options, selected) {
      const container = document.getElementById('cfgSymbolsOptions');
      const summary = document.getElementById('cfgSymbolsSummary');
      if (!container) return;
      const selectedSet = new Set((selected || []).map(s => s.toUpperCase()));
      container.innerHTML = '';
      options.forEach(symbol => {
        const label = document.createElement('label');
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.value = symbol;
        if (selectedSet.has(symbol.toUpperCase())) {
          checkbox.checked = true;
        }
        checkbox.onchange = () => syncSymbolSelection();
        label.appendChild(checkbox);
        const span = document.createElement('span');
        span.textContent = symbol;
        label.appendChild(span);
        container.appendChild(label);
      });
      if (summary) {
        summary.textContent = selected && selected.length ? `已選 ${selected.length} 個幣對` : '選擇幣對';
      }
      syncSymbolSelection();
    }

    function syncSymbolSelection() {
      const container = document.getElementById('cfgSymbolsOptions');
      const summary = document.getElementById('cfgSymbolsSummary');
      const selected = Array.from(container.querySelectorAll('input[type="checkbox"]:checked')).map(el => el.value);
      const input = document.getElementById('cfgTradeSymbols');
      input.value = selected.join(',');
      if (summary) {
        summary.textContent = selected.length ? `已選 ${selected.length} 個幣對` : '選擇幣對';
      }
    }

    async function loadTopSymbols() {
      try {
        const res = await fetch('/symbols/top?limit=10', { cache: 'no-store' });
        const data = await res.json();
        const symbols = data.symbols || [];
        renderSymbolOptions(symbols, symbols);
      } catch (err) {
        alert(`載入熱門幣對失敗: ${err}`);
      }
    }

    async function loadConfig() {
      const status = document.getElementById('configStatus');
      try {
        const res = await fetch('/config.json', { cache: 'no-store' });
        const cfg = await res.json();
        const tf = (cfg.timeframes && cfg.timeframes.length) ? cfg.timeframes[0] : { timeframe: '', days: '' };
        document.getElementById('cfgMode').value = cfg.search_mode || 'combo';
        document.getElementById('cfgTimeframe').value = tf.timeframe || '';
        document.getElementById('cfgDays').value = tf.days ?? '';
        document.getElementById('cfgWfTrainDays').value = cfg.wf_train_days ?? '';
        document.getElementById('cfgWfTestDays').value = cfg.wf_test_days ?? '';
        document.getElementById('cfgWfStepDays').value = cfg.wf_step_days ?? '';
        document.getElementById('cfgCapitalMode').value = cfg.capital_mode || 'shared';
        document.getElementById('cfgInitCash').value = cfg.init_cash_usdt ?? '';
        const orderPct = cfg.order_size_pct ?? '';
        document.getElementById('cfgOrderSize').value = (Number(orderPct) > 0 && Number(orderPct) <= 1) ? (Number(orderPct) * 100) : orderPct;
        document.getElementById('cfgMaxPositions').value = cfg.max_concurrent_positions ?? '';
        document.getElementById('cfgTradeSymbols').value = Array.isArray(cfg.trade_symbols) ? cfg.trade_symbols.join(',') : '';
          document.getElementById('cfgComboSizes').value = Array.isArray(cfg.combo_sizes) ? cfg.combo_sizes.join(',') : '';
          document.getElementById('cfgSeed').value = cfg.combo_seed ?? '';
          document.getElementById('cfgSlippage').value = cfg.slippage_bps ?? '';
          document.getElementById('cfgSpread').value = cfg.spread_bps ?? '';
          document.getElementById('cfgFunding').value = cfg.funding_rate_daily ?? '';
          document.getElementById('cfgSegStart').value = cfg.combo_segment_start ?? '';
          document.getElementById('cfgSegSize').value = cfg.combo_segment_size ?? '';
          document.getElementById('cfgTopN').value = cfg.top_n_refine ?? '';
        const symbols = Array.isArray(cfg.trade_symbols) ? cfg.trade_symbols : [];
        if (symbols.length) {
          renderSymbolOptions(symbols, symbols);
        } else {
          loadTopSymbols();
        }
        if (status) status.textContent = '已載入設定';
      } catch (err) {
        if (status) status.textContent = `載入設定失敗: ${err}`;
      }
    }

    async function saveConfig() {
      const status = document.getElementById('configStatus');
      const timeframe = document.getElementById('cfgTimeframe').value.trim();
      const days = Number(document.getElementById('cfgDays').value);
      const wfTrainRaw = document.getElementById('cfgWfTrainDays').value;
      const wfTestRaw = document.getElementById('cfgWfTestDays').value;
      const wfStepRaw = document.getElementById('cfgWfStepDays').value;
        const comboSizesRaw = document.getElementById('cfgComboSizes').value;
        const tradeSymbolsRaw = document.getElementById('cfgTradeSymbols').value;
        const payload = {
          search_mode: document.getElementById('cfgMode').value || 'combo',
          timeframes: timeframe && days ? [{ timeframe, days }] : [],
          wf_train_days: wfTrainRaw === '' ? null : Number(wfTrainRaw),
          wf_test_days: wfTestRaw === '' ? null : Number(wfTestRaw),
          wf_step_days: wfStepRaw === '' ? null : Number(wfStepRaw),
          capital_mode: document.getElementById('cfgCapitalMode').value || 'shared',
          init_cash_usdt: Number(document.getElementById('cfgInitCash').value),
          order_size_pct: Number(document.getElementById('cfgOrderSize').value),
          max_concurrent_positions: Number(document.getElementById('cfgMaxPositions').value),
          trade_symbols: tradeSymbolsRaw.split(',').map(v => v.trim()).filter(Boolean),
            combo_sizes: comboSizesRaw.split(',').map(v => v.trim()).filter(Boolean),
            combo_seed: Number(document.getElementById('cfgSeed').value),
          slippage_bps: Number(document.getElementById('cfgSlippage').value),
          spread_bps: Number(document.getElementById('cfgSpread').value),
          funding_rate_daily: Number(document.getElementById('cfgFunding').value),
          combo_segment_start: Number(document.getElementById('cfgSegStart').value),
        combo_segment_size: document.getElementById('cfgSegSize').value === '' ? null : Number(document.getElementById('cfgSegSize').value),
        top_n_refine: Number(document.getElementById('cfgTopN').value)
      };
      try {
        const res = await fetch('/config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const result = await res.json();
        if (status) status.textContent = result.message || '已儲存設定';
      } catch (err) {
        if (status) status.textContent = `儲存設定失敗: ${err}`;
      }
    }

    function getFilterValues() {
      return {
        timeframe: document.getElementById('filterTimeframe').value,
        minOosReturn: parseFloat(document.getElementById('filterOosReturn').value),
        minOosWinRate: parseFloat(document.getElementById('filterOosWinRate').value),
        minDailyTrades: parseFloat(document.getElementById('filterDailyTrades').value),
        maxDrawdown: parseFloat(document.getElementById('filterMaxDrawdown').value),
        oosPositive: document.getElementById('filterOosPositive').checked
      };
    }

    function filterRows(rows) {
      const filters = getFilterValues();
      return rows.filter(row => {
        if (filters.timeframe !== 'all' && row.timeframe !== filters.timeframe) return false;
        const oosReturn = pickMetric(row, ['oos_avg_total_return_pct', 'avg_total_return_pct']);
        const oosWin = pickMetric(row, ['oos_avg_win_rate_pct', 'avg_win_rate_pct']);
        const daily = pickMetric(row, ['oos_avg_daily_trades', 'avg_daily_trades']);
        const dd = pickMetric(row, ['oos_avg_max_drawdown_pct', 'avg_max_drawdown_pct']);
        if (!Number.isNaN(filters.minOosReturn) && (oosReturn === null || oosReturn < filters.minOosReturn)) return false;
        if (!Number.isNaN(filters.minOosWinRate) && (oosWin === null || oosWin < filters.minOosWinRate)) return false;
        if (!Number.isNaN(filters.minDailyTrades) && (daily === null || daily < filters.minDailyTrades)) return false;
        if (!Number.isNaN(filters.maxDrawdown) && (dd === null || dd > filters.maxDrawdown)) return false;
        if (filters.oosPositive && (oosReturn === null || oosReturn <= 0)) return false;
        return true;
      });
    }

    function pickTopN(rows, n) {
      if (!rows.length) return [];
      let sortCol = 'oos_avg_total_return_pct';
      if (!rows.some(row => parseNumber(row[sortCol]) !== null)) {
        sortCol = 'avg_total_return_pct';
      }
      return [...rows]
        .sort((a, b) => {
          const bVal = parseNumber(b[sortCol]);
          const aVal = parseNumber(a[sortCol]);
          const bNum = bVal === null ? -Infinity : bVal;
          const aNum = aVal === null ? -Infinity : aVal;
          return bNum - aNum;
        })
        .slice(0, n);
    }

    function renderScatter(canvasId, points) {
      const canvas = document.getElementById(canvasId);
      const ctx = canvas.getContext('2d');
      const w = canvas.width;
      const h = canvas.height;
      ctx.clearRect(0, 0, w, h);
      ctx.fillStyle = '#fdfdfd';
      ctx.fillRect(0, 0, w, h);
      if (!points.length) {
        ctx.fillStyle = '#888';
        ctx.fillText('無資料', 10, 20);
        return;
      }
      const padding = 40;
      const xs = points.map(p => p.x);
      const ys = points.map(p => p.y);
      const minX = Math.min(...xs);
      const maxX = Math.max(...xs);
      const minY = Math.min(...ys);
      const maxY = Math.max(...ys);
      const spanX = maxX - minX || 1;
      const spanY = maxY - minY || 1;

      ctx.strokeStyle = '#bbb';
      ctx.beginPath();
      ctx.moveTo(padding, h - padding);
      ctx.lineTo(w - padding, h - padding);
      ctx.moveTo(padding, h - padding);
      ctx.lineTo(padding, padding);
      ctx.stroke();

      ctx.fillStyle = '#666';
      ctx.fillText('回撤(%)', w - padding - 40, h - padding + 20);
      ctx.save();
      ctx.translate(12, padding);
      ctx.rotate(-Math.PI / 2);
      ctx.fillText('報酬(%)', 0, 0);
      ctx.restore();

      points.forEach(p => {
        const x = padding + ((p.x - minX) / spanX) * (w - padding * 2);
        const y = h - padding - ((p.y - minY) / spanY) * (h - padding * 2);
        ctx.fillStyle = p.y >= 0 ? '#0b7a36' : '#b3122f';
        ctx.beginPath();
        ctx.arc(x, y, 3, 0, Math.PI * 2);
        ctx.fill();
      });
    }

    function renderHistogram(canvasId, values) {
      const canvas = document.getElementById(canvasId);
      const ctx = canvas.getContext('2d');
      const w = canvas.width;
      const h = canvas.height;
      ctx.clearRect(0, 0, w, h);
      ctx.fillStyle = '#fdfdfd';
      ctx.fillRect(0, 0, w, h);
      if (!values.length) {
        ctx.fillStyle = '#888';
        ctx.fillText('無資料', 10, 20);
        return;
      }
      const padding = 40;
      const minVal = Math.min(...values);
      const maxVal = Math.max(...values);
      const bins = 10;
      const span = maxVal - minVal || 1;
      const counts = Array.from({ length: bins }, () => 0);
      values.forEach(val => {
        const idx = Math.min(bins - 1, Math.floor(((val - minVal) / span) * bins));
        counts[idx] += 1;
      });
      const maxCount = Math.max(...counts) || 1;
      const barWidth = (w - padding * 2) / bins;

      ctx.strokeStyle = '#bbb';
      ctx.beginPath();
      ctx.moveTo(padding, h - padding);
      ctx.lineTo(w - padding, h - padding);
      ctx.moveTo(padding, h - padding);
      ctx.lineTo(padding, padding);
      ctx.stroke();
      ctx.fillStyle = '#666';
      ctx.fillText('報酬分佈', w - padding - 50, h - padding + 20);

      counts.forEach((count, i) => {
        const barHeight = (count / maxCount) * (h - padding * 2);
        const x = padding + i * barWidth + 2;
        const y = h - padding - barHeight;
        ctx.fillStyle = '#4c78a8';
        ctx.fillRect(x, y, barWidth - 4, barHeight);
      });
    }

    function renderFrontier(canvasId, points) {
      const canvas = document.getElementById(canvasId);
      const ctx = canvas.getContext('2d');
      const w = canvas.width;
      const h = canvas.height;
      ctx.clearRect(0, 0, w, h);
      ctx.fillStyle = '#fdfdfd';
      ctx.fillRect(0, 0, w, h);
      if (!points.length) {
        ctx.fillStyle = '#888';
        ctx.fillText('無資料', 10, 20);
        return;
      }
      const padding = 40;
      const xs = points.map(p => p.x);
      const ys = points.map(p => p.y);
      const minX = Math.min(...xs);
      const maxX = Math.max(...xs);
      const minY = Math.min(...ys);
      const maxY = Math.max(...ys);
      const spanX = maxX - minX || 1;
      const spanY = maxY - minY || 1;

      ctx.strokeStyle = '#bbb';
      ctx.beginPath();
      ctx.moveTo(padding, h - padding);
      ctx.lineTo(w - padding, h - padding);
      ctx.moveTo(padding, h - padding);
      ctx.lineTo(padding, padding);
      ctx.stroke();

      const sorted = [...points].sort((a, b) => a.x - b.x);
      const frontier = [];
      let bestY = -Infinity;
      sorted.forEach(p => {
        if (p.y > bestY) {
          frontier.push(p);
          bestY = p.y;
        }
      });

      ctx.strokeStyle = '#1f77b4';
      ctx.lineWidth = 2;
      ctx.beginPath();
      frontier.forEach((p, idx) => {
        const x = padding + ((p.x - minX) / spanX) * (w - padding * 2);
        const y = h - padding - ((p.y - minY) / spanY) * (h - padding * 2);
        if (idx === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();

      frontier.forEach(p => {
        const x = padding + ((p.x - minX) / spanX) * (w - padding * 2);
        const y = h - padding - ((p.y - minY) / spanY) * (h - padding * 2);
        ctx.fillStyle = '#1f77b4';
        ctx.beginPath();
        ctx.arc(x, y, 3, 0, Math.PI * 2);
        ctx.fill();
      });
    }

    function exportCsv(filename, rows, columns) {
      if (!rows.length) {
        alert('沒有可匯出的資料。');
        return;
      }
      const cols = columns && columns.length ? columns : Object.keys(rows[0]);
      const lines = [];
      lines.push(cols.join(','));
      rows.forEach(row => {
        const line = cols.map(col => {
          const raw = getColumnDisplayValue(row, col);
          const val = String(raw).replace(/"/g, '""');
          return `"${val}"`;
        }).join(',');
        lines.push(line);
      });
      const blob = new Blob([lines.join('\\n')], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    }

    async function refreshStatus() {
      try {
        const res = await fetch('/status.json', { cache: 'no-store' });
        const data = await res.json();
        for (const k of ['stage','total','done','remaining','skipped','percent','elapsed','eta','updated']) {
          if (k === 'updated') {
            const raw = data[k];
            if (raw) {
              const parsed = Date.parse(raw);
              if (!Number.isNaN(parsed)) {
                document.getElementById(k).textContent = new Date(parsed).toLocaleString();
                continue;
              }
            }
          }
          document.getElementById(k).textContent = data[k] ?? '';
        }
      } catch (e) {}
    }

    let cachedPayload = null;
    let lastFilteredRows = [];
    let lastFilteredColumns = [];
    let lastTopRows = [];
    let lastTopColumns = [];

    function applyFiltersAndRender() {
      if (!cachedPayload) return;
      const comboRows = cachedPayload.combo.rows || [];
      if (!comboRows.length) {
        const note = document.getElementById('dataNote');
        note.textContent = '目前沒有可用資料，請確認回測是否已完成或 CSV 是否存在。';
      }
      updateTimeframeOptions(comboRows, cachedPayload.timeframes || []);
      const filteredRows = filterRows(comboRows);
      const topRows = pickTopN(filteredRows, 10);
      updateKpis(cachedPayload, filteredRows);

      const topCols = (cachedPayload.top10.columns || []).filter(c => TOP_COLS.includes(c));
      const comboCols = (cachedPayload.combo.columns || []).filter(c => COMBO_COLS.includes(c));
      const lbCols = (cachedPayload.leaderboard.columns || []).filter(c => LB_COLS.includes(c));

        const topColsFinal = TOP_COLS;
        const comboColsFinal = COMBO_COLS;
      const lbColsFinal = lbCols.length ? lbCols : (cachedPayload.leaderboard.columns && cachedPayload.leaderboard.columns.length ? cachedPayload.leaderboard.columns : LB_COLS);

        buildTable('top10Table', topRows, topColsFinal, { rowDetails: true });
        buildTable('comboTable', filteredRows, comboColsFinal, { rowDetails: true });
        buildTable('leaderboardTable', cachedPayload.leaderboard.rows || [], lbColsFinal);

      lastFilteredRows = filteredRows;
      lastFilteredColumns = comboColsFinal;
      lastTopRows = topRows;
      lastTopColumns = topColsFinal;

      const points = filteredRows
        .map(r => ({
          x: pickMetric(r, ['oos_avg_max_drawdown_pct', 'avg_max_drawdown_pct']),
          y: pickMetric(r, ['oos_avg_total_return_pct', 'avg_total_return_pct'])
        }))
        .filter(p => p.x !== null && p.y !== null);
      renderScatter('scatterChart', points);

      const histValues = filteredRows
        .map(r => pickMetric(r, ['oos_avg_total_return_pct', 'avg_total_return_pct']))
        .filter(v => v !== null);
      renderHistogram('histChart', histValues);

      renderFrontier('frontierChart', points);

      const note = document.getElementById('filterNote');
      note.textContent = `篩選後 ${filteredRows.length} 筆 / 總共 ${cachedPayload.combo.total || comboRows.length} 筆`;

      const reportLink = document.getElementById('reportLink');
      if (cachedPayload.latest_report) reportLink.href = `/artifacts/${cachedPayload.latest_report}`;
    }

    async function refreshResults() {
      try {
        const tfSelect = document.getElementById('filterTimeframe');
        const tf = tfSelect ? tfSelect.value : 'all';
        const query = tf && tf !== 'all' ? `?timeframe=${encodeURIComponent(tf)}` : '';
        const res = await fetch(`/results.json${query}`, { cache: 'no-store' });
        cachedPayload = await res.json();
        if (cachedPayload.errors && cachedPayload.errors.length) {
          const note = document.getElementById('dataNote');
          note.textContent = cachedPayload.errors.join('；');
        }
        applyFiltersAndRender();
      } catch (e) {
        const note = document.getElementById('dataNote');
        if (note) {
          note.textContent = `讀取資料失敗：${e}`;
        }
      }
    }

    document.getElementById('startBtn').onclick = async () => {
      const res = await fetch('/start', { method: 'POST' });
      const data = await res.json();
      alert(data.message || '已觸發');
      refreshStatus();
    };
    document.getElementById('pauseBtn').onclick = async () => {
      const res = await fetch('/pause', { method: 'POST' });
      const data = await res.json();
      alert(data.message || '已暫停');
      refreshStatus();
    };
    document.getElementById('resumeBtn').onclick = async () => {
      const res = await fetch('/resume', { method: 'POST' });
      const data = await res.json();
      alert(data.message || '已繼續');
      refreshStatus();
    };
    document.getElementById('clearLogBtn').onclick = async () => {
      const res = await fetch('/clear-log', { method: 'POST' });
      const data = await res.json();
      alert(data.message || '已清空');
    };
    document.getElementById('testStartBtn').onclick = async () => {
      const res = await fetch('/tests/start', { method: 'POST' });
      const data = await res.json();
      alert(data.message || '已觸發');
      refreshTests();
    };
    document.getElementById('testStopBtn').onclick = async () => {
      const res = await fetch('/tests/stop', { method: 'POST' });
      const data = await res.json();
      alert(data.message || '已停止');
      refreshTests();
    };
    document.getElementById('testClearLogBtn').onclick = async () => {
      const res = await fetch('/tests/clear-log', { method: 'POST' });
      const data = await res.json();
      alert(data.message || '已清空');
      refreshTests();
    };
    document.getElementById('applyFilterBtn').onclick = () => refreshResults();
    document.getElementById('resetFilterBtn').onclick = () => {
      document.getElementById('filterTimeframe').value = 'all';
      document.getElementById('filterOosReturn').value = '';
      document.getElementById('filterOosWinRate').value = '';
      document.getElementById('filterDailyTrades').value = '';
      document.getElementById('filterMaxDrawdown').value = '';
      document.getElementById('filterOosPositive').checked = false;
      refreshResults();
    };
    document.getElementById('filterTimeframe').onchange = () => refreshResults();
    document.getElementById('exportFilteredBtn').onclick = () => exportCsv('filtered_combos.csv', lastFilteredRows, lastFilteredColumns);
    document.getElementById('exportTopBtn').onclick = () => exportCsv('top10.csv', lastTopRows, lastTopColumns);
    document.getElementById('saveConfigBtn').onclick = () => saveConfig();
    document.getElementById('loadTopSymbolsBtn').onclick = () => loadTopSymbols();

    loadConfig();
    refreshStatus();
    refreshResults();
    refreshTests();
    setInterval(refreshStatus, 5000);
    setInterval(refreshResults, 30000);
    setInterval(refreshTests, 5000);
  """



INDEX_HTML_OFFLINE = INDEX_HTML.replace(
    '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/datatables.net-dt@1.13.8/css/jquery.dataTables.min.css">',
    '',
).replace(
    '<script src="https://cdn.jsdelivr.net/npm/jquery@3.7.1/dist/jquery.min.js"></script>',
    '',
).replace(
    '<script src="https://cdn.jsdelivr.net/npm/datatables.net@1.13.8/js/jquery.dataTables.min.js"></script>',
    '',
)


class Handler(BaseHTTPRequestHandler):
    def _send(self, body, content_type="text/html; charset=utf-8", status=HTTPStatus.OK):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            # Client disconnected; ignore noisy socket errors.
            return

    def _send_with_headers(self, body, content_type="text/html; charset=utf-8", status=HTTPStatus.OK, headers=None):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        if isinstance(headers, dict):
            for key, val in headers.items():
                if key and val is not None:
                    self.send_header(str(key), str(val))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return

    def _read_json_payload(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length > 0 else b"{}"
        return json.loads(body.decode("utf-8"))

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        static_no_cache_headers = {
            "Cache-Control": "no-store, max-age=0, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        }
        if path == "/":
            return self._send_with_headers(
                _read_static_text("index.html", fallback=INDEX_HTML),
                headers=static_no_cache_headers,
            )
        static_path = _resolve_static_path(path)
        if static_path is not None:
            mime, _ = mimetypes.guess_type(str(static_path))
            content_type = mime or "application/octet-stream"
            return self._send_with_headers(
                static_path.read_bytes(),
                f"{content_type}; charset=utf-8" if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"} else content_type,
                headers=static_no_cache_headers,
            )
        if path == "/app.js":
            return self._send_with_headers(
                _read_static_text("js/app.js", fallback=APP_JS),
                "application/javascript; charset=utf-8",
                headers=static_no_cache_headers,
            )
        if path == "/status.json":
            return self._send(json.dumps(_read_status(), ensure_ascii=False), "application/json; charset=utf-8")
        if path == "/tests/status.json":
            return self._send(json.dumps(_read_test_status(), ensure_ascii=False), "application/json; charset=utf-8")
        if path == "/batch/queue.json":
            return self._send(json.dumps(_batch_status_payload(), ensure_ascii=False), "application/json; charset=utf-8")
        if path == "/batch/log-tail.txt":
            return self._send(_read_batch_log_tail(), "text/plain; charset=utf-8")
        if path == "/coverage/matrix.json":
            return self._send(json.dumps(_coverage_matrix_payload(), ensure_ascii=False), "application/json; charset=utf-8")
        if path == "/data/refresh.json":
            return self._send(json.dumps(_read_data_refresh_state(), ensure_ascii=False), "application/json; charset=utf-8")
        if path == "/signals/paper-feedback-spec.json":
            return self._send(json.dumps(_paper_feedback_spec(), ensure_ascii=False), "application/json; charset=utf-8")
        if path == "/signals/paper-feedback.json":
            query = parse_qs(parsed.query)
            limit = 200
            try:
                limit = int(query.get("limit", ["200"])[0])
            except Exception:
                limit = 200
            rows = _read_paper_feedback(limit=limit)
            return self._send(
                json.dumps(
                    {
                        "ok": True,
                        "count": len(rows),
                        "rows": rows,
                        "path": str(_paper_feedback_log_path().relative_to(ROOT)),
                        "updated_utc": _now_iso(),
                    },
                    ensure_ascii=False,
                ),
                "application/json; charset=utf-8",
            )
        if path == "/signals/paper-feedback-summary.json":
            query = parse_qs(parsed.query)
            limit = 500
            try:
                limit = int(query.get("limit", ["500"])[0])
            except Exception:
                limit = 500
            rows = _read_paper_feedback(limit=limit)
            summary = _paper_feedback_summary(rows)
            return self._send(
                json.dumps(
                    {
                        "ok": True,
                        "count": len(rows),
                        "summary": summary,
                        "path": str(_paper_feedback_log_path().relative_to(ROOT)),
                        "updated_utc": _now_iso(),
                    },
                    ensure_ascii=False,
                ),
                "application/json; charset=utf-8",
            )
        if path == "/signals/paper-feedback-diagnostics.json":
            query = parse_qs(parsed.query)
            limit = 1000
            top_n = 10
            try:
                limit = int(query.get("limit", ["1000"])[0])
            except Exception:
                limit = 1000
            try:
                top_n = int(query.get("top_n", ["10"])[0])
            except Exception:
                top_n = 10
            rows = _read_paper_feedback(limit=limit)
            diagnostics = _paper_feedback_diagnostics(rows, top_n=top_n)
            return self._send(
                json.dumps(
                    {
                        "ok": True,
                        "count": len(rows),
                        "diagnostics": diagnostics,
                        "path": str(_paper_feedback_log_path().relative_to(ROOT)),
                        "updated_utc": _now_iso(),
                    },
                    ensure_ascii=False,
                ),
                "application/json; charset=utf-8",
            )
        if path == "/signals/paper-feedback-recommendations.json":
            query = parse_qs(parsed.query)
            limit = 1000
            top_n = 10
            min_samples = FEEDBACK_RECOMMEND_DEFAULT_MIN_SAMPLES
            try:
                limit = int(query.get("limit", ["1000"])[0])
            except Exception:
                limit = 1000
            try:
                top_n = int(query.get("top_n", ["10"])[0])
            except Exception:
                top_n = 10
            try:
                min_samples = int(query.get("min_samples", [str(FEEDBACK_RECOMMEND_DEFAULT_MIN_SAMPLES)])[0])
            except Exception:
                min_samples = FEEDBACK_RECOMMEND_DEFAULT_MIN_SAMPLES
            rows = _read_paper_feedback(limit=limit)
            recommendations = _paper_feedback_recommendations(
                rows,
                top_n=top_n,
                min_samples=min_samples,
            )
            return self._send(
                json.dumps(
                    {
                        "ok": True,
                        "count": len(rows),
                        "recommendations": recommendations,
                        "path": str(_paper_feedback_log_path().relative_to(ROOT)),
                        "updated_utc": _now_iso(),
                    },
                    ensure_ascii=False,
                ),
                "application/json; charset=utf-8",
            )
        if path == "/dashboard/errors.json":
            query = parse_qs(parsed.query)
            limit = _safe_int(query.get("limit", [str(DASHBOARD_ERROR_EVENTS_DEFAULT_LIMIT)])[0], DASHBOARD_ERROR_EVENTS_DEFAULT_LIMIT)
            limit = max(1, min(int(limit), DASHBOARD_ERROR_EVENTS_MAX_LIMIT))
            offset = max(0, _safe_int(query.get("offset", ["0"])[0], 0))
            endpoint = str(query.get("endpoint", [""])[0]).strip()
            request_id = str(query.get("request_id", [""])[0]).strip()
            kind = str(query.get("kind", [""])[0]).strip()
            error_code = str(query.get("error_code", [""])[0]).strip()
            cache_error_code = str(query.get("cache_error_code", [""])[0]).strip()
            status_raw = str(query.get("status", [""])[0]).strip()
            message_contains = str(query.get("message_contains", [""])[0]).strip()
            since_hours_raw = str(query.get("since_hours", [""])[0]).strip()
            rows_payload = _read_dashboard_error_events(
                limit=limit,
                endpoint=endpoint or None,
                request_id=request_id or None,
                kind=kind or None,
                since_hours=since_hours_raw,
                offset=offset,
                error_code=error_code or None,
                cache_error_code=cache_error_code or None,
                status=status_raw,
                message_contains=message_contains or None,
            )
            return self._send(
                json.dumps(
                    {
                        "ok": True,
                        "count": rows_payload["count"],
                        "matched_count": rows_payload["matched_count"],
                        "total_available": rows_payload["total_available"],
                        "offset": rows_payload["offset"],
                        "has_more": rows_payload["has_more"],
                        "next_offset": rows_payload["next_offset"],
                        "rows": rows_payload["rows"],
                        "summary": rows_payload["summary"],
                        "limit": limit,
                        "filters": {
                            "endpoint": endpoint or "",
                            "request_id": request_id or "",
                            "kind": _normalize_dashboard_error_kind(kind),
                            "error_code": _normalize_dashboard_error_code(error_code),
                            "cache_error_code": _normalize_dashboard_error_code(cache_error_code),
                            "status": _normalize_dashboard_status(status_raw),
                            "message_contains": _normalize_dashboard_message_contains(message_contains),
                            "since_hours": _normalize_since_hours(since_hours_raw),
                        },
                        "path": _relative_path_or_str(_dashboard_error_events_path()),
                        "updated_utc": _now_iso(),
                    },
                    ensure_ascii=False,
                ),
                "application/json; charset=utf-8",
            )
        if path == "/dashboard/errors/export.ndjson":
            query = parse_qs(parsed.query)
            limit = _safe_int(query.get("limit", [str(DASHBOARD_ERROR_EVENTS_MAX_ROWS)])[0], DASHBOARD_ERROR_EVENTS_MAX_ROWS)
            limit = max(1, min(int(limit), DASHBOARD_ERROR_EVENTS_MAX_ROWS))
            offset = max(0, _safe_int(query.get("offset", ["0"])[0], 0))
            endpoint = str(query.get("endpoint", [""])[0]).strip()
            request_id = str(query.get("request_id", [""])[0]).strip()
            kind = str(query.get("kind", [""])[0]).strip()
            error_code = str(query.get("error_code", [""])[0]).strip()
            cache_error_code = str(query.get("cache_error_code", [""])[0]).strip()
            status_raw = str(query.get("status", [""])[0]).strip()
            message_contains = str(query.get("message_contains", [""])[0]).strip()
            since_hours_raw = str(query.get("since_hours", [""])[0]).strip()
            rows_payload = _read_dashboard_error_events(
                limit=limit,
                endpoint=endpoint or None,
                request_id=request_id or None,
                kind=kind or None,
                since_hours=since_hours_raw,
                offset=offset,
                error_code=error_code or None,
                cache_error_code=cache_error_code or None,
                status=status_raw,
                message_contains=message_contains or None,
            )
            lines = []
            for row in rows_payload.get("rows", []):
                lines.append(json.dumps(row, ensure_ascii=False))
            body_text = "\n".join(lines)
            if body_text:
                body_text += "\n"
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"dashboard_errors_{stamp}.ndjson"
            return self._send_with_headers(
                body_text,
                "text/plain; charset=utf-8",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                },
            )
        if path == "/dashboard/cross_run.json":
            query = parse_qs(parsed.query)
            top_n = _normalize_top_n(query.get("top_n", [str(DASHBOARD_TOP_N_DEFAULT)])[0])
            request_id = _new_request_id()
            try:
                payload = _cross_run_validate_payload(_cross_run_payload(top_n=top_n))
                payload["payload_source"] = "live"
                payload["request_id"] = request_id
                return self._send(json.dumps(payload, ensure_ascii=False), "application/json; charset=utf-8")
            except Exception as exc:
                cache_exc = None
                try:
                    payload = _cross_run_validate_payload(_cross_run_cached_payload(top_n=top_n))
                    payload["payload_source"] = "cache_fallback"
                    payload["request_id"] = request_id
                    fallback_meta = _cross_run_cache_fallback_meta(
                        reason=exc,
                        fallback_for="dashboard/cross_run.json",
                        request_id=request_id,
                    )
                    payload["cache_fallback"] = fallback_meta
                    _record_dashboard_error_event_safe(
                        kind="cache_fallback",
                        endpoint="dashboard/cross_run.json",
                        request_id=request_id,
                        status=HTTPStatus.OK,
                        message="cross-run payload served from cache fallback",
                        error_code=fallback_meta.get("reason_code", ""),
                        live_error=fallback_meta.get("live_error"),
                        cache_fallback=fallback_meta,
                    )
                    return self._send(json.dumps(payload, ensure_ascii=False), "application/json; charset=utf-8")
                except Exception as fallback_exc:
                    cache_exc = fallback_exc
                error_payload = _dashboard_error_payload(
                    endpoint="dashboard/cross_run.json",
                    live_exc=exc,
                    message=f"cross-run payload failed: {exc}",
                    cache_exc=cache_exc,
                    request_id=request_id,
                )
                _record_dashboard_error_event_safe(
                    kind="error",
                    endpoint=error_payload.get("endpoint", "dashboard/cross_run.json"),
                    request_id=error_payload.get("request_id"),
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                    message=error_payload.get("message", ""),
                    error_code=error_payload.get("error_code", ""),
                    cache_error_code=error_payload.get("cache_error_code", ""),
                    live_error=error_payload.get("live_error"),
                    cache_error=error_payload.get("cache_error"),
                )
                return self._send(
                    json.dumps(error_payload, ensure_ascii=False),
                    "application/json; charset=utf-8",
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                )
        if path == "/dashboard/report":
            report_path = ARTIFACTS / "cross_run_report.html"
            if report_path.exists():
                return self._send(report_path.read_text(encoding="utf-8"))
            try:
                _payload, generated_path = _cross_run_generate_report(top_n=20)
                _cross_run_validate_payload(_payload)
                if generated_path.exists():
                    return self._send(generated_path.read_text(encoding="utf-8"))
            except Exception as exc:
                try:
                    _cached_payload, cached_html, _cached_path = _cross_run_cached_report_html(top_n=20)
                    return self._send(cached_html)
                except Exception:
                    pass
                return self._send(f"Generate report failed: {exc}", status=HTTPStatus.INTERNAL_SERVER_ERROR)
            try:
                _cached_payload, cached_html, _cached_path = _cross_run_cached_report_html(top_n=20)
                return self._send(cached_html)
            except Exception:
                pass
            return self._send("Cross-run report unavailable", status=HTTPStatus.NOT_FOUND)
        if path == "/results.json":
            query = parse_qs(parsed.query)
            timeframe = query.get("timeframe", [None])[0]
            if timeframe == "all":
                timeframe = None
            return self._send(
                json.dumps(_get_results_payload(timeframe=timeframe), ensure_ascii=False),
                "application/json; charset=utf-8",
            )
        if path == "/results/advanced.json":
            query = parse_qs(parsed.query)
            timeframe = query.get("timeframe", [None])[0]
            if timeframe == "all":
                timeframe = None
            n_trials = _safe_int(query.get("n_trials", [str(ADVANCED_ANALYSIS_DEFAULT_TRIALS)])[0], ADVANCED_ANALYSIS_DEFAULT_TRIALS)
            n_trials = max(1, min(int(n_trials), ADVANCED_ANALYSIS_MAX_TRIALS))
            seed = _safe_int(query.get("seed", ["42"])[0], 42)

            sample_size_raw = str(query.get("sample_size", [""])[0]).strip()
            sample_size = None
            if sample_size_raw:
                sample_size_val = _safe_int(sample_size_raw, 0)
                if sample_size_val > 0:
                    sample_size = min(int(sample_size_val), ADVANCED_ANALYSIS_MAX_SAMPLE_SIZE)

            results_payload = _get_results_payload(timeframe=timeframe)
            combo_rows = results_payload.get("combo", {}).get("rows", [])
            analysis = _build_advanced_results_analysis(
                combo_rows,
                n_trials=n_trials,
                sample_size=sample_size,
                seed=seed,
            )
            return self._send(
                json.dumps(
                    {
                        "ok": True,
                        "timeframe": timeframe or "all",
                        "analysis": analysis,
                    },
                    ensure_ascii=False,
                ),
                "application/json; charset=utf-8",
            )
        if path == "/config.json":
            return self._send(json.dumps(_read_config(), ensure_ascii=False), "application/json; charset=utf-8")
        if path == "/control.json":
            return self._send(json.dumps(_read_control(), ensure_ascii=False), "application/json; charset=utf-8")
        if path == "/symbols/top":
            query = parse_qs(parsed.query)
            limit = 10
            try:
                limit = int(query.get("limit", ["10"])[0])
            except Exception:
                limit = 10
            symbols = _fetch_top_symbols(limit=limit)
            return self._send(json.dumps({"symbols": symbols}, ensure_ascii=False), "application/json; charset=utf-8")
        if path == "/status":
            if STATUS_HTML.exists():
                return self._send(STATUS_HTML.read_text(encoding="utf-8"))
            return self._send("找不到狀態頁", status=HTTPStatus.NOT_FOUND)
        if path == "/report":
            report_path = _latest_report_path()
            if report_path and report_path.exists():
                return self._send(report_path.read_text(encoding="utf-8"))
            return self._send("找不到報告", status=HTTPStatus.NOT_FOUND)
        if path == "/log":
            if RUN_LOG.exists():
                return self._send(_log_html(), "text/html; charset=utf-8")
            return self._send("找不到紀錄", status=HTTPStatus.NOT_FOUND)
        if path == "/log.txt":
            if RUN_LOG.exists():
                return self._send(RUN_LOG.read_text(encoding="utf-8"), "text/plain; charset=utf-8")
            return self._send("找不到紀錄", status=HTTPStatus.NOT_FOUND)
        if path == "/tests/log":
            if TEST_LOG.exists():
                return self._send(_test_log_html(), "text/html; charset=utf-8")
            return self._send("找不到測試紀錄", status=HTTPStatus.NOT_FOUND)
        if path == "/tests/log.txt":
            if TEST_LOG.exists():
                return self._send(TEST_LOG.read_text(encoding="utf-8"), "text/plain; charset=utf-8")
            return self._send("找不到測試紀錄", status=HTTPStatus.NOT_FOUND)
        if path == "/tests/log-tail.txt":
            return self._send(_read_test_log_tail(), "text/plain; charset=utf-8")
        if path.startswith("/artifacts/"):
            target = ROOT / path.lstrip("/")
            if target.exists():
                return self._send(target.read_text(encoding="utf-8"))
            return self._send("檔案不存在", status=HTTPStatus.NOT_FOUND)
        return self._send("Not Found", status=HTTPStatus.NOT_FOUND)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/start":
            query = parse_qs(parsed.query)
            refresh_data_raw = str(query.get("refresh_data", ["0"])[0]).strip().lower()
            refresh_data = refresh_data_raw in {"1", "true", "yes", "on"}
            refresh_msg = ""
            refresh_state = None
            if refresh_data:
                refresh_state, refreshed = _refresh_data_cache_now(force=True, reason="start")
                if refreshed:
                    refresh_msg = "（已先更新最新資料）"
                else:
                    refresh_msg = "（資料更新未完成，已沿用現有快取）"
            ok, msg = _start_run()
            payload = {"ok": ok, "message": f"{msg}{refresh_msg}" if refresh_msg else msg}
            if refresh_state is not None:
                payload["data_refresh"] = {
                    "ok": bool(refresh_state.get("ok")),
                    "updated_utc": refresh_state.get("updated_utc", ""),
                    "errors": list(refresh_state.get("errors", [])),
                }
            return self._send(json.dumps(payload, ensure_ascii=False), "application/json; charset=utf-8")
        if parsed.path == "/data/refresh":
            state, refreshed = _refresh_data_cache_now(force=True, reason="manual")
            return self._send(
                json.dumps(
                    {
                        "ok": bool(state.get("ok")),
                        "refreshed": bool(refreshed),
                        "message": "資料快取已更新" if refreshed else "資料快取未更新（間隔限制或沿用現有快取）",
                        "state": state,
                    },
                    ensure_ascii=False,
                ),
                "application/json; charset=utf-8",
            )
        if parsed.path == "/signals/export-top-config":
            try:
                payload = self._read_json_payload()
            except Exception:
                payload = {}
            try:
                rank = _safe_int(payload.get("rank", 1), 1)
                timeframe = str(payload.get("timeframe", "")).strip() or None
                row = payload.get("row")
                signal_payload, out_path = _export_live_signal_config(
                    rank=rank,
                    timeframe=timeframe,
                    row=row if isinstance(row, dict) else None,
                )
                return self._send(
                    json.dumps(
                        {
                            "ok": True,
                            "message": "live signal config exported",
                            "path": str(out_path.relative_to(ROOT)),
                            "signal_config_id": signal_payload.get("signal_config_id", ""),
                            "symbol": signal_payload.get("instrument", {}).get("symbol", ""),
                            "timeframe": signal_payload.get("instrument", {}).get("timeframe", ""),
                        },
                        ensure_ascii=False,
                    ),
                    "application/json; charset=utf-8",
                )
            except ValueError as exc:
                return self._send(
                    json.dumps({"ok": False, "message": str(exc)}, ensure_ascii=False),
                    "application/json; charset=utf-8",
                    status=HTTPStatus.BAD_REQUEST,
                )
            except Exception as exc:
                return self._send(
                    json.dumps({"ok": False, "message": f"export failed: {exc}"}, ensure_ascii=False),
                    "application/json; charset=utf-8",
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                )
        if parsed.path == "/signals/export-feedback-adjusted-config":
            try:
                payload = self._read_json_payload()
            except Exception:
                payload = {}
            try:
                rank = _safe_int(payload.get("rank", 1), 1)
                timeframe = str(payload.get("timeframe", "")).strip() or None
                row = payload.get("row")
                recommendation = payload.get("recommendation")
                profile = str(payload.get("profile", "auto") or "auto").strip().lower()
                min_samples = _safe_int(payload.get("min_samples", FEEDBACK_RECOMMEND_DEFAULT_MIN_SAMPLES), FEEDBACK_RECOMMEND_DEFAULT_MIN_SAMPLES)
                adjusted_payload, out_path, rec = _export_feedback_adjusted_signal_config(
                    profile=profile,
                    rank=rank,
                    timeframe=timeframe,
                    row=row if isinstance(row, dict) else None,
                    recommendation=recommendation if isinstance(recommendation, dict) else None,
                    min_samples=min_samples,
                )
                adjustment = adjusted_payload.get("feedback_adjustment", {})
                return self._send(
                    json.dumps(
                        {
                            "ok": True,
                            "message": "feedback-adjusted live signal config exported",
                            "path": str(out_path.relative_to(ROOT)),
                            "signal_config_id": adjusted_payload.get("signal_config_id", ""),
                            "profile": adjustment.get("profile"),
                            "risk": adjusted_payload.get("risk", {}),
                            "recommendation": rec,
                        },
                        ensure_ascii=False,
                    ),
                    "application/json; charset=utf-8",
                )
            except ValueError as exc:
                return self._send(
                    json.dumps({"ok": False, "message": str(exc)}, ensure_ascii=False),
                    "application/json; charset=utf-8",
                    status=HTTPStatus.BAD_REQUEST,
                )
            except Exception as exc:
                return self._send(
                    json.dumps({"ok": False, "message": f"export failed: {exc}"}, ensure_ascii=False),
                    "application/json; charset=utf-8",
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                )
        if parsed.path == "/signals/enqueue-feedback-adjusted-batch":
            try:
                payload = self._read_json_payload()
            except Exception:
                payload = {}
            try:
                rank = _safe_int(payload.get("rank", 1), 1)
                timeframe = str(payload.get("timeframe", "")).strip() or None
                row = payload.get("row")
                recommendation = payload.get("recommendation")
                profile = str(payload.get("profile", "auto") or "auto").strip().lower()
                min_samples = _safe_int(
                    payload.get("min_samples", FEEDBACK_RECOMMEND_DEFAULT_MIN_SAMPLES),
                    FEEDBACK_RECOMMEND_DEFAULT_MIN_SAMPLES,
                )
                workflow = str(payload.get("workflow", "run") or "run").strip().lower()
                mode = payload.get("mode", "combo")
                workers = payload.get("workers")
                name = payload.get("name")
                auto_start_raw = str(payload.get("auto_start", "")).strip().lower()
                auto_start = auto_start_raw in {"1", "true", "yes", "on"}

                plan_result = _enqueue_feedback_adjusted_batch(
                    profile=profile,
                    rank=rank,
                    timeframe=timeframe,
                    row=row if isinstance(row, dict) else None,
                    recommendation=recommendation if isinstance(recommendation, dict) else None,
                    min_samples=min_samples,
                    workflow=workflow,
                    mode=mode,
                    workers=workers,
                    name=name,
                    auto_start=auto_start,
                )
                adjusted_payload = plan_result.get("adjusted_payload", {})
                return self._send(
                    json.dumps(
                        {
                            "ok": True,
                            "message": "feedback-adjusted batch job enqueued",
                            "job": plan_result.get("job"),
                            "config_path": str(plan_result.get("config_path").relative_to(ROOT)),
                            "signal_config_path": str(plan_result.get("signal_config_path").relative_to(ROOT)),
                            "signal_config_id": adjusted_payload.get("signal_config_id", ""),
                            "profile": plan_result.get("profile"),
                            "recommendation": plan_result.get("recommendation"),
                            "plan": plan_result.get("plan"),
                            "warnings": list(plan_result.get("warnings") or []),
                            "batch_started": bool(plan_result.get("batch_started")),
                            "batch_start_message": plan_result.get("batch_start_message", ""),
                        },
                        ensure_ascii=False,
                    ),
                    "application/json; charset=utf-8",
                )
            except ValueError as exc:
                return self._send(
                    json.dumps({"ok": False, "message": str(exc)}, ensure_ascii=False),
                    "application/json; charset=utf-8",
                    status=HTTPStatus.BAD_REQUEST,
                )
            except Exception as exc:
                return self._send(
                    json.dumps({"ok": False, "message": f"enqueue failed: {exc}"}, ensure_ascii=False),
                    "application/json; charset=utf-8",
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                )
        if parsed.path == "/signals/paper-feedback":
            try:
                payload = self._read_json_payload()
                entry, path = _record_paper_feedback(payload)
                return self._send(
                    json.dumps(
                        {
                            "ok": True,
                            "message": "paper feedback recorded",
                            "entry": entry,
                            "path": str(path.relative_to(ROOT)),
                        },
                        ensure_ascii=False,
                    ),
                    "application/json; charset=utf-8",
                )
            except ValueError as exc:
                return self._send(
                    json.dumps({"ok": False, "message": str(exc)}, ensure_ascii=False),
                    "application/json; charset=utf-8",
                    status=HTTPStatus.BAD_REQUEST,
                )
            except Exception as exc:
                return self._send(
                    json.dumps({"ok": False, "message": f"feedback failed: {exc}"}, ensure_ascii=False),
                    "application/json; charset=utf-8",
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                )
        if parsed.path == "/batch/start":
            ok, msg = _batch_start()
            return self._send(
                json.dumps({"ok": ok, "message": msg}, ensure_ascii=False),
                "application/json; charset=utf-8",
                status=HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST,
            )
        if parsed.path == "/batch/cancel":
            ok, msg = _batch_cancel()
            return self._send(
                json.dumps({"ok": ok, "message": msg}, ensure_ascii=False),
                "application/json; charset=utf-8",
                status=HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST,
            )
        if parsed.path == "/batch/clear":
            ok, msg = _batch_clear()
            return self._send(
                json.dumps({"ok": ok, "message": msg}, ensure_ascii=False),
                "application/json; charset=utf-8",
                status=HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST,
            )
        if parsed.path == "/batch/enqueue":
            try:
                payload = self._read_json_payload()
                ok, msg, job = _batch_enqueue(payload)
                return self._send(
                    json.dumps({"ok": ok, "message": msg, "job": job}, ensure_ascii=False),
                    "application/json; charset=utf-8",
                    status=HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST,
                )
            except Exception as exc:
                return self._send(
                    json.dumps({"ok": False, "message": f"enqueue failed: {exc}"}, ensure_ascii=False),
                    "application/json; charset=utf-8",
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                )
        if parsed.path == "/batch/remove":
            try:
                payload = self._read_json_payload()
                job_id = int(payload.get("job_id"))
                ok, msg = _batch_remove(job_id)
                return self._send(
                    json.dumps({"ok": ok, "message": msg}, ensure_ascii=False),
                    "application/json; charset=utf-8",
                    status=HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST,
                )
            except Exception as exc:
                return self._send(
                    json.dumps({"ok": False, "message": f"remove failed: {exc}"}, ensure_ascii=False),
                    "application/json; charset=utf-8",
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                )
        if parsed.path == "/coverage/enqueue":
            try:
                payload = self._read_json_payload()
                ok, msg, details = _coverage_enqueue_pair(payload)
                return self._send(
                    json.dumps({"ok": ok, "message": msg, "details": details}, ensure_ascii=False),
                    "application/json; charset=utf-8",
                    status=HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST,
                )
            except Exception as exc:
                return self._send(
                    json.dumps({"ok": False, "message": f"coverage enqueue failed: {exc}"}, ensure_ascii=False),
                    "application/json; charset=utf-8",
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                )
        if parsed.path == "/dashboard/errors/clear":
            try:
                payload = self._read_json_payload()
            except Exception:
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            endpoint = str(payload.get("endpoint", "")).strip()
            request_id = str(payload.get("request_id", "")).strip()
            kind = str(payload.get("kind", "")).strip()
            error_code = str(payload.get("error_code", "")).strip()
            cache_error_code = str(payload.get("cache_error_code", "")).strip()
            status_raw = payload.get("status")
            message_contains = str(payload.get("message_contains", "")).strip()
            since_hours_raw = payload.get("since_hours")
            result = _clear_dashboard_error_events(
                endpoint=endpoint or None,
                request_id=request_id or None,
                kind=kind or None,
                since_hours=since_hours_raw,
                error_code=error_code or None,
                cache_error_code=cache_error_code or None,
                status=status_raw,
                message_contains=message_contains or None,
            )
            return self._send(
                json.dumps(
                    {
                        "ok": True,
                        "message": "dashboard error events cleared",
                        "cleared": result.get("cleared", 0),
                        "remaining": result.get("remaining", 0),
                        "cleared_all": bool(result.get("cleared_all", False)),
                        "path": result.get("path", _relative_path_or_str(_dashboard_error_events_path())),
                        "filters": {
                            "endpoint": endpoint or "",
                            "request_id": request_id or "",
                            "kind": _normalize_dashboard_error_kind(kind),
                            "error_code": _normalize_dashboard_error_code(error_code),
                            "cache_error_code": _normalize_dashboard_error_code(cache_error_code),
                            "status": _normalize_dashboard_status(status_raw),
                            "message_contains": _normalize_dashboard_message_contains(message_contains),
                            "since_hours": _normalize_since_hours(since_hours_raw),
                        },
                        "updated_utc": _now_iso(),
                    },
                    ensure_ascii=False,
                ),
                "application/json; charset=utf-8",
            )
        if parsed.path == "/dashboard/report/generate":
            top_n = DASHBOARD_TOP_N_DEFAULT
            request_id = _new_request_id()
            try:
                payload = self._read_json_payload()
                top_n = _normalize_top_n(payload.get("top_n", DASHBOARD_TOP_N_DEFAULT))
            except Exception:
                top_n = DASHBOARD_TOP_N_DEFAULT
            try:
                report_payload, report_path = _cross_run_generate_report(top_n=top_n)
                _cross_run_validate_payload(report_payload)
                return self._send(
                    json.dumps(
                        {
                            "ok": True,
                            "message": "cross-run report generated",
                            "payload_source": "live",
                            "request_id": request_id,
                            "report_path": str(report_path.relative_to(ROOT)),
                            "summary": report_payload.get("summary", {}),
                        },
                        ensure_ascii=False,
                    ),
                    "application/json; charset=utf-8",
                )
            except Exception as exc:
                cache_exc = None
                try:
                    cached_payload, _cached_html, cached_path = _cross_run_cached_report_html(
                        top_n=top_n,
                        persist_html=True,
                    )
                    fallback_meta = _cross_run_cache_fallback_meta(
                        reason=exc,
                        fallback_for="dashboard/report/generate",
                        request_id=request_id,
                    )
                    _record_dashboard_error_event_safe(
                        kind="cache_fallback",
                        endpoint="dashboard/report/generate",
                        request_id=request_id,
                        status=HTTPStatus.OK,
                        message="cross-run report generated from cache fallback",
                        error_code=fallback_meta.get("reason_code", ""),
                        live_error=fallback_meta.get("live_error"),
                        cache_fallback=fallback_meta,
                    )
                    return self._send(
                        json.dumps(
                            {
                                "ok": True,
                                "message": "cross-run report generated from cache fallback",
                                "payload_source": "cache_fallback",
                                "request_id": request_id,
                                "report_path": str(cached_path.relative_to(ROOT)),
                                "summary": cached_payload.get("summary", {}),
                                "cache_fallback": fallback_meta,
                            },
                            ensure_ascii=False,
                        ),
                        "application/json; charset=utf-8",
                    )
                except Exception as fallback_exc:
                    cache_exc = fallback_exc
                error_payload = _dashboard_error_payload(
                    endpoint="dashboard/report/generate",
                    live_exc=exc,
                    message=f"report generation failed: {exc}",
                    cache_exc=cache_exc,
                    request_id=request_id,
                )
                _record_dashboard_error_event_safe(
                    kind="error",
                    endpoint=error_payload.get("endpoint", "dashboard/report/generate"),
                    request_id=error_payload.get("request_id"),
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                    message=error_payload.get("message", ""),
                    error_code=error_payload.get("error_code", ""),
                    cache_error_code=error_payload.get("cache_error_code", ""),
                    live_error=error_payload.get("live_error"),
                    cache_error=error_payload.get("cache_error"),
                )
                return self._send(
                    json.dumps(error_payload, ensure_ascii=False),
                    "application/json; charset=utf-8",
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                )
        if parsed.path == "/tests/start":
            ok, msg = _start_tests()
            return self._send(json.dumps({"ok": ok, "message": msg}, ensure_ascii=False), "application/json; charset=utf-8")
        if parsed.path == "/tests/stop":
            ok, msg = _stop_tests()
            return self._send(json.dumps({"ok": ok, "message": msg}, ensure_ascii=False), "application/json; charset=utf-8")
        if parsed.path == "/pause":
            _write_control(True)
            return self._send(json.dumps({"ok": True, "message": "已暫停回測。"}, ensure_ascii=False), "application/json; charset=utf-8")
        if parsed.path == "/resume":
            _write_control(False)
            return self._send(json.dumps({"ok": True, "message": "已繼續回測。"}, ensure_ascii=False), "application/json; charset=utf-8")
        if parsed.path == "/config":
            try:
                payload = self._read_json_payload()
                cfg = _write_config(payload)
                return self._send(
                    json.dumps({"ok": True, "message": "設定已儲存。", "config": cfg}, ensure_ascii=False),
                    "application/json; charset=utf-8",
                )
            except ValueError as exc:
                return self._send(
                    json.dumps({"ok": False, "message": f"設定不合法: {exc}"}, ensure_ascii=False),
                    "application/json; charset=utf-8",
                    status=HTTPStatus.BAD_REQUEST,
                )
            except Exception as exc:
                return self._send(
                    json.dumps({"ok": False, "message": f"儲存失敗: {exc}"}, ensure_ascii=False),
                    "application/json; charset=utf-8",
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                )
        if parsed.path == "/clear-log":
            try:
                ARTIFACTS.mkdir(parents=True, exist_ok=True)
                RUN_LOG.write_text("", encoding="utf-8")
                return self._send(
                    json.dumps({"ok": True, "message": "已清空執行紀錄。"}, ensure_ascii=False),
                    "application/json; charset=utf-8",
                )
            except Exception as exc:
                return self._send(
                    json.dumps({"ok": False, "message": f"清空失敗: {exc}"}, ensure_ascii=False),
                    "application/json; charset=utf-8",
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                )
        if parsed.path == "/tests/clear-log":
            try:
                _clear_test_log()
                return self._send(
                    json.dumps({"ok": True, "message": "已清空測試紀錄。"}, ensure_ascii=False),
                    "application/json; charset=utf-8",
                )
            except Exception as exc:
                return self._send(
                    json.dumps({"ok": False, "message": f"清空失敗: {exc}"}, ensure_ascii=False),
                    "application/json; charset=utf-8",
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                )
        return self._send("Not Found", status=HTTPStatus.NOT_FOUND)


def main():
    host = "127.0.0.1"
    port = 8787
    _ensure_data_refresh_thread()
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"控制台啟動於 http://{host}:{port}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
