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
    return _sys.modules.get("autowfo.control_panel.server")


def _runtime():
    cp = _cp()
    return getattr(cp, "RUNTIME", None) if cp is not None else None


def _paths():
    runtime = _runtime()
    return runtime.paths if runtime is not None else None


def _processes():
    runtime = _runtime()
    return runtime.processes if runtime is not None else None


def _sync_runtime_aliases() -> None:
    cp = _cp()
    sync = getattr(cp, "_sync_runtime_aliases", None) if cp is not None else None
    if callable(sync):
        sync()


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
        sync = getattr(cp, "_sync_runtime_from_aliases", None)
        if callable(sync):
            sync("PROCESS", "TEST_PROCESS", "BATCH_PROCESS")

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
    paths = _paths()
    if paths is None or not path.startswith("/static/"):
        return None
    rel_path = path[len("/static/") :].strip("/")
    if not rel_path:
        return None
    candidate = (paths.static_dir / rel_path).resolve()
    static_root = paths.static_dir.resolve()
    try:
        candidate.relative_to(static_root)
    except ValueError:
        return None
    if not candidate.exists() or not candidate.is_file():
        return None
    return candidate


def _read_static_text(rel_path, fallback=""):
    paths = _paths()
    if paths is None:
        return fallback
    file_path = paths.static_dir / rel_path
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
    processes = _processes()
    return bool(processes is not None and processes.is_running())


def _is_test_running():
    processes = _processes()
    return bool(processes is not None and processes.is_test_running())


def _is_batch_running():
    processes = _processes()
    return bool(processes is not None and processes.is_batch_running())


def _now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _python_path():
    paths = _paths()
    if paths is None:
        return str(Path(os.sys.executable))
    is_windows = os.name == "nt"
    venv_python = paths.root / ".venv" / ("Scripts" if is_windows else "bin") / ("python.exe" if is_windows else "python")
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
    paths = _paths()
    try:
        return path.relative_to(paths.root).as_posix() if paths is not None else Path(path).as_posix()
    except Exception:
        try:
            return Path(path).as_posix()
        except Exception:
            return str(path).replace("\\", "/")


def _shared_views_manifest_path():
    paths = _paths()
    artifacts = paths.artifacts if paths is not None else Path("artifacts")
    return artifacts / "shared_views_manifest.json"


def _read_shared_views_manifest():
    manifest_path = _shared_views_manifest_path()
    if not manifest_path.exists():
        return None
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _latest_trusted_run_root():
    payload = _read_shared_views_manifest()
    if not isinstance(payload, dict):
        return None
    latest_run_root = str(payload.get("latest_run_root") or "").strip()
    if latest_run_root:
        run_root = Path(latest_run_root)
        if run_root.exists():
            return run_root
    latest_run_id = str(payload.get("latest_run_id") or "").strip()
    if latest_run_id:
        paths = _paths()
        artifacts = paths.artifacts if paths is not None else Path("artifacts")
        run_root = artifacts / "runs" / latest_run_id
        if run_root.exists():
            return run_root
    return None


def _resolve_trusted_artifact_path(filename: str):
    name = Path(str(filename or "")).name
    if not name or name in {".", ".."}:
        return None
    paths = _paths()
    artifacts = paths.artifacts if paths is not None else Path("artifacts")

    direct = artifacts / name
    if direct.exists() and direct.is_file():
        return direct

    payload = _read_shared_views_manifest()
    if not isinstance(payload, dict):
        return None

    candidate_roots = []
    latest_run_root = _latest_trusted_run_root()
    if latest_run_root is not None:
        candidate_roots.append(latest_run_root)

    trusted_runs = payload.get("trusted_runs")
    if isinstance(trusted_runs, list):
        for run_id in reversed(trusted_runs):
            run_root = artifacts / "runs" / str(run_id)
            if run_root.exists() and run_root not in candidate_roots:
                candidate_roots.append(run_root)

    for run_root in candidate_roots:
        for rel in ("reports", "results", "metadata", ""):
            candidate = run_root / rel / name if rel else run_root / name
            if candidate.exists() and candidate.is_file():
                return candidate
    return None


def _shared_views_source_status():
    manifest_path = _shared_views_manifest_path()
    payload = _read_shared_views_manifest()
    if not isinstance(payload, dict):
        return {
            "mode": "legacy_or_missing",
            "manifest_path": str(manifest_path),
            "manifest_exists": manifest_path.exists(),
            "trusted_runs": 0,
            "latest_run_id": "",
        }
    trusted_runs = payload.get("trusted_runs")
    return {
        "mode": "trusted_derived",
        "manifest_path": str(manifest_path),
        "manifest_exists": True,
        "trusted_runs": len(trusted_runs) if isinstance(trusted_runs, list) else 0,
        "latest_run_id": str(payload.get("latest_run_id") or ""),
    }


def _start_run():
    cp = _cp()
    paths = _paths()
    processes = _processes()
    if cp is None or paths is None or processes is None:
        return False, "control panel not initialized"
    with processes.process_lock:
        if _is_running():
            return False, "run already in progress"
        if _is_batch_running():
            return False, "batch is running; stop batch first"
        python_path = _python_path()
        paths.artifacts.mkdir(parents=True, exist_ok=True)
        log_f = paths.run_log.open("a", encoding="utf-8")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(paths.root)
        processes.process = subprocess.Popen(
            [python_path, "-m", "autowfo", "run", "--config", str(paths.config_json), "--cwd", str(paths.root)],
            cwd=str(paths.root),
            env=env,
            stdout=log_f,
            stderr=subprocess.STDOUT,
        )
        _sync_runtime_aliases()
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
    paths = _paths()
    processes = _processes()
    if cp is None or paths is None or processes is None:
        return False, "control panel not initialized"
    with processes.test_process_lock:
        if _is_test_running():
            return False, "tests already running"
        python_path = _python_path()
        paths.artifacts.mkdir(parents=True, exist_ok=True)
        log_f = paths.test_log.open("a", encoding="utf-8")
        processes.test_process = subprocess.Popen(
            [python_path, "-m", "pytest", "tests", "-q"],
            cwd=str(paths.root),
            stdout=log_f,
            stderr=subprocess.STDOUT,
        )
        _sync_runtime_aliases()
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
    processes = _processes()
    if cp is None or processes is None:
        return False, "control panel not initialized"
    with processes.test_process_lock:
        proc = processes.test_process
        if proc is None or proc.poll() is not None:
            return False, "tests are not running"
        try:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
        except Exception as exc:
            return False, f"stop failed: {exc}"
        finally:
            processes.test_process = None
            _sync_runtime_aliases()
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
    paths = _paths()
    processes = _processes()
    if cp is None or paths is None or processes is None:
        return {}
    status = cp._read_json_file(
        paths.status_json,
        {"run_id": "", "stage": "idle", "started": "", "elapsed": "", "eta": "", "processed": 0, "total": 0, "skipped": 0, "updated": ""},
    )
    now = datetime.now(timezone.utc).replace(microsecond=0)
    with processes.process_lock:
        if _is_running():
            status["stage"] = "running"
        elif processes.process is not None:
            rc = processes.process.poll()
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
    paths = _paths()
    processes = _processes()
    if cp is None or paths is None or processes is None:
        return {}
    status = {
        "stage": "idle",
        "started": "",
        "elapsed": "",
        "return_code": "",
        "updated": "",
    }
    if paths.test_status_json.exists():
        try:
            status.update(json.loads(paths.test_status_json.read_text(encoding="utf-8")))
        except Exception:
            pass
    now = datetime.now(timezone.utc).replace(microsecond=0)
    with processes.test_process_lock:
        if _is_test_running():
            status["stage"] = "running"
        elif processes.test_process is not None:
            rc = processes.test_process.poll()
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
    paths = _paths()
    if paths is None or not paths.run_log.exists():
        return ""
    lines = deque(maxlen=max_lines)
    with paths.run_log.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            lines.append(line.rstrip("\n"))
    return "\n".join(lines)


def _read_test_log_tail(max_lines=LOG_MAX_LINES):
    paths = _paths()
    if paths is None or not paths.test_log.exists():
        return ""
    lines = deque(maxlen=max_lines)
    with paths.test_log.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            lines.append(line.rstrip("\n"))
    return "\n".join(lines)


def _clear_test_log():
    paths = _paths()
    if paths is None:
        return
    paths.artifacts.mkdir(parents=True, exist_ok=True)
    paths.test_log.write_text("", encoding="utf-8")


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
        return {"scheduler_enabled": False, "queue_depth": 0, "source_status": _shared_views_source_status()}

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
            "source_status": _shared_views_source_status(),
            "status_stage": str(status.get("stage", "idle")),
            "updated_utc": _now_iso(),
        }

    try:
        from autowfo.control_panel import experiments as cp_experiments

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
        "source_status": _shared_views_source_status(),
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
    "_shared_views_manifest_path",
    "_read_shared_views_manifest",
    "_latest_trusted_run_root",
    "_resolve_trusted_artifact_path",
    "_shared_views_source_status",
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

