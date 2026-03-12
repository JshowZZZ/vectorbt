"""Process/runtime state primitives for control panel."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
import html
import json
import math
import os
from pathlib import Path
import subprocess
import sys as _sys
import threading


DASHBOARD_TOP_N_DEFAULT = 20
DASHBOARD_TOP_N_MIN = 1
DASHBOARD_TOP_N_MAX = 200
LOG_MAX_LINES = 2000


def _cp():
    return _sys.modules.get("scripts.control_panel")


@dataclass
class ProcessManager:
    process_lock: threading.Lock = field(default_factory=threading.Lock)
    test_process_lock: threading.Lock = field(default_factory=threading.Lock)
    batch_process_lock: threading.Lock = field(default_factory=threading.Lock)
    process: object | None = None
    test_process: object | None = None
    batch_process: object | None = None

    def is_running(self) -> bool:
        proc = self.process
        return bool(proc is not None and getattr(proc, "poll", lambda: 1)() is None)

    def is_test_running(self) -> bool:
        proc = self.test_process
        return bool(proc is not None and getattr(proc, "poll", lambda: 1)() is None)

    def is_batch_running(self) -> bool:
        proc = self.batch_process
        return bool(proc is not None and getattr(proc, "poll", lambda: 1)() is None)

    def bind_module(self) -> None:
        cp = _cp()
        if cp is None:
            return
        cp.PROCESS_LOCK = self.process_lock
        cp.TEST_PROCESS_LOCK = self.test_process_lock
        cp.BATCH_PROCESS_LOCK = self.batch_process_lock
        cp.PROCESS = self.process
        cp.TEST_PROCESS = self.test_process
        cp.BATCH_PROCESS = self.batch_process

    def sync_from_module(self) -> None:
        cp = _cp()
        if cp is None:
            return
        self.process_lock = cp.PROCESS_LOCK
        self.test_process_lock = cp.TEST_PROCESS_LOCK
        self.batch_process_lock = cp.BATCH_PROCESS_LOCK
        self.process = cp.PROCESS
        self.test_process = cp.TEST_PROCESS
        self.batch_process = cp.BATCH_PROCESS


DEFAULT_PROCESS_MANAGER = ProcessManager()


def _resolve_static_path(path):
    cp = _cp()
    if cp is None or not path.startswith("/static/"):
        return None
    rel_path = path[len("/static/") :].strip("/")
    if not rel_path:
        return None
    candidate = (cp.STATIC_DIR / rel_path).resolve()
    static_root = cp.STATIC_DIR.resolve()
    try:
        candidate.relative_to(static_root)
    except ValueError:
        return None
    if not candidate.exists() or not candidate.is_file():
        return None
    return candidate


def _read_static_text(rel_path, fallback=""):
    cp = _cp()
    if cp is None:
        return fallback
    file_path = cp.STATIC_DIR / rel_path
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
    cp = _cp()
    return bool(cp is not None and cp.PROCESS is not None and cp.PROCESS.poll() is None)


def _is_test_running():
    cp = _cp()
    return bool(cp is not None and cp.TEST_PROCESS is not None and cp.TEST_PROCESS.poll() is None)


def _is_batch_running():
    cp = _cp()
    return bool(cp is not None and cp.BATCH_PROCESS is not None and cp.BATCH_PROCESS.poll() is None)


def _now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _python_path():
    cp = _cp()
    if cp is None:
        return str(Path(os.sys.executable))
    is_windows = os.name == "nt"
    venv_python = cp.ROOT / ".venv" / ("Scripts" if is_windows else "bin") / ("python.exe" if is_windows else "python")
    return str(venv_python if venv_python.exists() else Path(os.sys.executable))


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


def _safe_json_read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return default


def _parse_utc(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


def _relative_path_or_str(path):
    cp = _cp()
    try:
        return path.relative_to(cp.ROOT).as_posix() if cp is not None else Path(path).as_posix()
    except Exception:
        try:
            return Path(path).as_posix()
        except Exception:
            return str(path).replace("\\", "/")


def _start_run():
    cp = _cp()
    if cp is None:
        return False, "control panel not initialized"
    with cp.PROCESS_LOCK:
        if _is_running():
            return False, "run already in progress"
        if _is_batch_running():
            return False, "batch is running; stop batch first"
        python_path = _python_path()
        cp.ARTIFACTS.mkdir(parents=True, exist_ok=True)
        log_f = cp.RUN_LOG.open("a", encoding="utf-8")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(cp.ROOT)
        cp.PROCESS = subprocess.Popen(
            [python_path, "-m", "autowfo", "run", "--config", str(cp.CONFIG_JSON), "--cwd", str(cp.ROOT)],
            cwd=str(cp.ROOT),
            env=env,
            stdout=log_f,
            stderr=subprocess.STDOUT,
        )
        cp._write_status(
            {
                "run_id": "",
                "stage": "running",
                "started": _now_iso(),
                "elapsed": "",
                "eta": "",
                "processed": 0,
                "total": 0,
                "skipped": 0,
                "updated": _now_iso(),
            }
        )
    return True, "run started"


def _start_tests():
    cp = _cp()
    if cp is None:
        return False, "control panel not initialized"
    with cp.TEST_PROCESS_LOCK:
        if _is_test_running():
            return False, "tests already running"
        python_path = _python_path()
        cp.ARTIFACTS.mkdir(parents=True, exist_ok=True)
        log_f = cp.TEST_LOG.open("a", encoding="utf-8")
        cp.TEST_PROCESS = subprocess.Popen(
            [python_path, "-m", "pytest", "tests", "-q"],
            cwd=str(cp.ROOT),
            stdout=log_f,
            stderr=subprocess.STDOUT,
        )
        cp._write_test_status(
            {
                "stage": "running",
                "started": _now_iso(),
                "elapsed": "",
                "return_code": "",
                "updated": _now_iso(),
            }
        )
    return True, "tests started"


def _stop_tests():
    cp = _cp()
    if cp is None:
        return False, "control panel not initialized"
    with cp.TEST_PROCESS_LOCK:
        if cp.TEST_PROCESS is None or cp.TEST_PROCESS.poll() is not None:
            return False, "tests are not running"
        try:
            cp.TEST_PROCESS.terminate()
            try:
                cp.TEST_PROCESS.wait(timeout=5)
            except Exception:
                cp.TEST_PROCESS.kill()
        except Exception as exc:
            return False, f"stop failed: {exc}"
        finally:
            cp.TEST_PROCESS = None
        cp._write_test_status(
            {
                "stage": "stopped",
                "started": _now_iso(),
                "elapsed": "",
                "return_code": "",
                "updated": _now_iso(),
            }
        )
    return True, "tests stopped"


def _read_status():
    cp = _cp()
    if cp is None:
        return {}
    status = cp._read_json_file(
        cp.STATUS_JSON,
        {"run_id": "", "stage": "idle", "started": "", "elapsed": "", "eta": "", "processed": 0, "total": 0, "skipped": 0, "updated": ""},
    )
    now = datetime.now(timezone.utc).replace(microsecond=0)
    with cp.PROCESS_LOCK:
        if _is_running():
            status["stage"] = "running"
        elif cp.PROCESS is not None:
            rc = cp.PROCESS.poll()
            if rc is not None and status.get("stage") == "running":
                status["stage"] = "finished" if rc == 0 else "failed"
    started_dt = cp._parse_iso(status.get("started"))
    if started_dt:
        status["elapsed"] = str(now - started_dt).split(".")[0]
    status["updated"] = now.isoformat()
    cp._write_status(status)
    return status


def _read_test_status():
    cp = _cp()
    if cp is None:
        return {}
    status = {
        "stage": "idle",
        "started": "",
        "elapsed": "",
        "return_code": "",
        "updated": "",
    }
    if cp.TEST_STATUS_JSON.exists():
        try:
            status.update(json.loads(cp.TEST_STATUS_JSON.read_text(encoding="utf-8")))
        except Exception:
            pass
    now = datetime.now(timezone.utc).replace(microsecond=0)
    with cp.TEST_PROCESS_LOCK:
        if _is_test_running():
            status["stage"] = "running"
        elif cp.TEST_PROCESS is not None:
            rc = cp.TEST_PROCESS.poll()
            if rc is not None and status.get("return_code", "") == "":
                status["return_code"] = str(rc)
                status["stage"] = "finished" if rc == 0 else "failed"
    started_dt = cp._parse_iso(status.get("started"))
    if started_dt:
        status["elapsed"] = str(now - started_dt).split(".")[0]
    status["updated"] = now.isoformat()
    cp._write_test_status(status)
    return status


def _read_log_tail(max_lines=LOG_MAX_LINES):
    cp = _cp()
    if cp is None or not cp.RUN_LOG.exists():
        return ""
    lines = deque(maxlen=max_lines)
    with cp.RUN_LOG.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            lines.append(line.rstrip("\n"))
    return "\n".join(lines)


def _read_test_log_tail(max_lines=LOG_MAX_LINES):
    cp = _cp()
    if cp is None or not cp.TEST_LOG.exists():
        return ""
    lines = deque(maxlen=max_lines)
    with cp.TEST_LOG.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            lines.append(line.rstrip("\n"))
    return "\n".join(lines)


def _clear_test_log():
    cp = _cp()
    if cp is None:
        return
    cp.ARTIFACTS.mkdir(parents=True, exist_ok=True)
    cp.TEST_LOG.write_text("", encoding="utf-8")


def _log_html():
    content = html.escape(_read_log_tail())
    return f"""<!doctype html>
<html>
<head><meta charset="utf-8"><meta http-equiv="refresh" content="5"><title>Run Log</title></head>
<body style="font-family:Consolas,monospace;background:#111;color:#eee;">
  <div>Last {LOG_MAX_LINES} lines. <a href="/log.txt" target="_blank">raw</a></div>
  <pre>{content}</pre>
</body></html>"""


def _test_log_html():
    content = html.escape(_read_test_log_tail())
    return f"""<!doctype html>
<html>
<head><meta charset="utf-8"><meta http-equiv="refresh" content="5"><title>Test Log</title></head>
<body style="font-family:Consolas,monospace;background:#111;color:#eee;">
  <div>Last {LOG_MAX_LINES} lines. <a href="/tests/log.txt" target="_blank">raw</a></div>
  <pre>{content}</pre>
</body></html>"""


def _collect_latest_experiment_run_summary():
    cp = _cp()
    if cp is None:
        return None
    experiments_root = cp.ARTIFACTS / "experiments"
    if not experiments_root.exists():
        return None

    latest_row = None
    latest_ts = None
    for meta_path in experiments_root.glob("*/runs/*/run_meta.json"):
        meta = _safe_json_read(meta_path, None)
        if not isinstance(meta, dict):
            continue
        run_ts_raw = (
            str(meta.get("last_run_utc", "")).strip()
            or str(meta.get("completed_utc", "")).strip()
            or str(meta.get("created_utc", "")).strip()
        )
        run_ts = _parse_utc(run_ts_raw)
        if run_ts is None:
            try:
                run_ts = datetime.fromtimestamp(meta_path.stat().st_mtime, tz=timezone.utc)
            except Exception:
                run_ts = None
        if run_ts is None:
            continue
        if latest_ts is not None and run_ts <= latest_ts:
            continue
        latest_ts = run_ts
        latest_row = {
            "experiment_id": str(meta.get("experiment_id") or meta_path.parents[2].name),
            "run_id": str(meta.get("run_id") or meta_path.parent.name),
            "n_combos": int(meta.get("n_combos", 0) or 0),
            "n_completed": int(meta.get("n_completed", 0) or 0),
            "n_errors": int(meta.get("n_errors", 0) or 0),
            "best_oos_sharpe": meta.get("best_oos_sharpe"),
            "duration_seconds": meta.get("duration_seconds"),
            "completed_utc": run_ts.astimezone(timezone.utc).replace(microsecond=0).isoformat(),
        }
    return latest_row


def _coerce_str_list(value):
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _estimate_discovery_candidates() -> int:
    cp = _cp()
    if cp is None:
        return 0
    pool_path = cp.ARTIFACTS / "discovery_pool.json"
    if not pool_path.exists():
        return 0
    payload = _safe_json_read(pool_path, None)
    if not isinstance(payload, dict):
        return 0

    indicators = _coerce_str_list(payload.get("indicator_ids") or payload.get("indicator_pool"))
    n = len(indicators)
    if n < 2:
        return 0

    size_range = payload.get("combo_size_range", [2, 4])
    try:
        min_k = int(size_range[0])
        max_k = int(size_range[1])
    except Exception:
        min_k, max_k = 2, 4
    min_k = max(1, min_k)
    max_k = max(min_k, max_k)
    total = 0
    for k in range(min_k, min(max_k, n) + 1):
        total += math.comb(n, k)
    return int(total)


def _read_overview_next_action():
    cp = _cp()
    if cp is None:
        return {"scheduler_enabled": False, "queue_depth": 0}

    status = _read_status()
    scheduler_path = cp.ARTIFACTS / "scheduler.json"
    if not scheduler_path.exists():
        return {
            "scheduler_enabled": False,
            "queue_depth": 0,
            "next_experiment_id": None,
            "is_running": False,
            "latest_run_summary": None,
            "discovery_candidates": 0,
            "status_stage": str(status.get("stage", "idle")),
            "updated_utc": _now_iso(),
        }

    try:
        from scripts import control_panel_experiments as cp_experiments

        scheduler_status = cp_experiments._scheduler_runtime_status()
    except Exception:
        scheduler_status = {}
    if not isinstance(scheduler_status, dict):
        scheduler_status = {}

    return {
        "scheduler_enabled": True,
        "queue_depth": int(scheduler_status.get("queue_depth", 0) or 0),
        "next_experiment_id": scheduler_status.get("next_experiment_id"),
        "is_running": bool(scheduler_status.get("is_running", False)),
        "last_error": str(scheduler_status.get("last_error", "") or ""),
        "latest_run_summary": _collect_latest_experiment_run_summary(),
        "discovery_candidates": _estimate_discovery_candidates(),
        "status_stage": str(status.get("stage", "idle")),
        "updated_utc": _now_iso(),
    }


def _read_patrol_history(limit=20):
    def _to_int(value, default=0):
        try:
            return int(value)
        except Exception:
            return int(default)

    cp = _cp()
    if cp is None:
        return {"history": [], "total": 0}

    try:
        limit_n = max(1, int(limit))
    except Exception:
        limit_n = 20

    path = cp.ARTIFACTS / "patrol_log.ndjson"
    if not path.exists():
        return {"history": [], "total": 0}

    rows = []
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except Exception:
        return {"history": [], "total": 0}

    for raw in reversed(lines):
        text = str(raw or "").strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        rows.append(
            {
                "utc": str(payload.get("utc", "")).strip(),
                "tick_generated": _to_int(payload.get("tick_generated", 0), 0),
                "tick_enqueued": _to_int(payload.get("tick_enqueued", 0), 0),
                "runs_executed": _to_int(payload.get("runs_executed", 0), 0),
                "runs_errors": _to_int(payload.get("runs_errors", 0), 0),
                "queue_remaining": _to_int(payload.get("queue_remaining", 0), 0),
            }
        )
        if len(rows) >= limit_n:
            break
    return {"history": rows, "total": len(rows)}


def try_handle_get(handler, _parsed, path):
    if path == "/status.json":
        handler._send(json.dumps(_read_status(), ensure_ascii=False), "application/json; charset=utf-8")
        return True
    if path == "/tests/status.json":
        handler._send(json.dumps(_read_test_status(), ensure_ascii=False), "application/json; charset=utf-8")
        return True
    if path == "/overview/next-action.json":
        handler._send(
            json.dumps(_read_overview_next_action(), ensure_ascii=False),
            "application/json; charset=utf-8",
        )
        return True
    if path == "/overview/patrol-history.json":
        handler._send(
            json.dumps(_read_patrol_history(limit=20), ensure_ascii=False),
            "application/json; charset=utf-8",
        )
        return True
    return False


def try_handle_post(handler, parsed):
    if parsed.path == "/start":
        ok, msg = _start_run()
        handler._send(json.dumps({"ok": ok, "message": msg}, ensure_ascii=False), "application/json; charset=utf-8")
        return True
    if parsed.path == "/tests/start":
        ok, msg = _start_tests()
        handler._send(json.dumps({"ok": ok, "message": msg}, ensure_ascii=False), "application/json; charset=utf-8")
        return True
    if parsed.path == "/tests/stop":
        ok, msg = _stop_tests()
        handler._send(json.dumps({"ok": ok, "message": msg}, ensure_ascii=False), "application/json; charset=utf-8")
        return True
    return False


__all__ = [
    "ProcessManager",
    "DEFAULT_PROCESS_MANAGER",
    "_resolve_static_path",
    "_read_static_text",
    "_normalize_top_n",
    "_is_running",
    "_is_test_running",
    "_is_batch_running",
    "_now_iso",
    "_python_path",
    "_read_json_file",
    "_safe_json_read",
    "_parse_utc",
    "_relative_path_or_str",
    "_start_run",
    "_start_tests",
    "_stop_tests",
    "_read_status",
    "_read_test_status",
    "_read_log_tail",
    "_read_test_log_tail",
    "_clear_test_log",
    "_log_html",
    "_test_log_html",
    "_collect_latest_experiment_run_summary",
    "_estimate_discovery_candidates",
    "_read_overview_next_action",
    "_read_patrol_history",
    "try_handle_get",
    "try_handle_post",
]
