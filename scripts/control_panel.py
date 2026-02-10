
import csv
from collections import deque
import html
import json
import mimetypes
import sqlite3
import os
import subprocess
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
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


def _write_config(payload):
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    cfg = _sanitize_config(payload)
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
    return sorted(rows, key=lambda r: _parse_float(r.get(sort_col)) or float("-inf"), reverse=True)[:10]


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
    try:
        top10_path = _latest_top10_path()
        top10 = _read_csv_rows(top10_path, limit=200) if top10_path else {"path": "", "columns": [], "rows": [], "total": 0, "truncated": False}
    except Exception as exc:
        top10 = {"path": "", "columns": [], "rows": [], "total": 0, "truncated": False}
        errors.append(f"讀取 Top10 失敗: {exc}")
    if not top10["rows"] and combo["rows"]:
        top10["rows"] = _pick_top10(combo["rows"])
        top10["columns"] = combo["columns"]
        top10["total"] = len(top10["rows"])
        top10["truncated"] = False
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
        "latest_report": report_path.name if report_path else "",
        "timeframes": timeframes,
        "errors": errors,
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
        PROCESS = subprocess.Popen(
            [python_path, str(SCRIPT)],
            cwd=str(ROOT),
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

    def _read_json_payload(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length > 0 else b"{}"
        return json.loads(body.decode("utf-8"))

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/":
            return self._send(_read_static_text("index.html", fallback=INDEX_HTML))
        static_path = _resolve_static_path(path)
        if static_path is not None:
            mime, _ = mimetypes.guess_type(str(static_path))
            content_type = mime or "application/octet-stream"
            return self._send(static_path.read_bytes(), f"{content_type}; charset=utf-8" if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"} else content_type)
        if path == "/app.js":
            return self._send(_read_static_text("js/app.js", fallback=APP_JS), "application/javascript; charset=utf-8")
        if path == "/status.json":
            return self._send(json.dumps(_read_status(), ensure_ascii=False), "application/json; charset=utf-8")
        if path == "/tests/status.json":
            return self._send(json.dumps(_read_test_status(), ensure_ascii=False), "application/json; charset=utf-8")
        if path == "/batch/queue.json":
            return self._send(json.dumps(_batch_status_payload(), ensure_ascii=False), "application/json; charset=utf-8")
        if path == "/batch/log-tail.txt":
            return self._send(_read_batch_log_tail(), "text/plain; charset=utf-8")
        if path == "/results.json":
            query = parse_qs(parsed.query)
            timeframe = query.get("timeframe", [None])[0]
            if timeframe == "all":
                timeframe = None
            return self._send(
                json.dumps(_get_results_payload(timeframe=timeframe), ensure_ascii=False),
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
            ok, msg = _start_run()
            return self._send(json.dumps({"ok": ok, "message": msg}, ensure_ascii=False), "application/json; charset=utf-8")
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
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"控制台啟動於 http://{host}:{port}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
