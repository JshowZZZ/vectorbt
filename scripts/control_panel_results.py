"""Results-read helpers extracted for AWF-146."""

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
from scripts.control_panel_state import (
    _log_html,
    _test_log_html,
    _read_log_tail,
    _read_test_log_tail,
)


def _cp():
    return _sys.modules.get("scripts.control_panel")

ADVANCED_ANALYSIS_DEFAULT_TRIALS = 2000
ADVANCED_ANALYSIS_MAX_TRIALS = 50000
ADVANCED_ANALYSIS_MAX_SAMPLE_SIZE = 10000
MAX_ROWS = 5000


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
def _latest_report_path():
    reports = sorted(ARTIFACTS.glob("btc_regime_*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
    return reports[0] if reports else None

@_with_cp
def _latest_top10_path():
    tops = sorted(ARTIFACTS.glob("param_sweep_top10_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    return tops[0] if tops else None

@_with_cp
def _parse_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

@_with_cp
def _db_available():
    return DB_PATH.exists()

@_with_cp
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

@_with_cp
def _db_columns(table):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    cols = [row["name"] for row in rows if row["name"] not in ("id", "created_utc")]
    return cols

@_with_cp
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

@_with_cp
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

@_with_cp
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

@_with_cp
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

@_with_cp
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

@_with_cp
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
        errors.append(f"霈????閬仃?? {exc}")
    try:
        leaderboard = _read_csv_rows(ARTIFACTS / "leaderboard.csv")
    except Exception as exc:
        leaderboard = {"path": "", "columns": [], "rows": [], "total": 0, "truncated": False}
        errors.append(f"霈??銵?憭望?: {exc}")
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
        errors.append(f"撱箇??冽風??Top10 憭望?: {exc}")
    # AWF-107: secondary top10_latest_run = latest single-run top10 file (for UI toggle)
    try:
        top10_lr_path = _latest_top10_path()
        top10_latest_run = _read_csv_rows(top10_lr_path, limit=200) if top10_lr_path else {"path": "", "columns": [], "rows": [], "total": 0, "truncated": False}
    except Exception as exc:
        top10_latest_run = {"path": "", "columns": [], "rows": [], "total": 0, "truncated": False}
        errors.append(f"霈?甈?Top10 憭望?: {exc}")
    try:
        refresh_state = _read_data_refresh_state()
        _overlay_data_end_from_refresh(combo.get("rows", []), refresh_state)
        _overlay_data_end_from_refresh(top10.get("rows", []), refresh_state)
        _overlay_data_end_from_refresh(top10_latest_run.get("rows", []), refresh_state)
    except Exception as exc:
        refresh_state = _default_data_refresh_state()
        errors.append(f"憟鞈??圈悅摨衣??仃?? {exc}")
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

@_with_cp
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

@_with_cp
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

@_with_cp
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

@_with_cp
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


def try_handle_get(handler, parsed, path):
    if path == "/results.json":
        query = parse_qs(parsed.query)
        timeframe = query.get("timeframe", [None])[0]
        if timeframe == "all":
            timeframe = None
        handler._send(
            json.dumps(_get_results_payload(timeframe=timeframe), ensure_ascii=False),
            "application/json; charset=utf-8",
        )
        return True
    if path == "/results/advanced.json":
        query = parse_qs(parsed.query)
        timeframe = query.get("timeframe", [None])[0]
        if timeframe == "all":
            timeframe = None
        n_trials = _safe_int(
            query.get("n_trials", [str(ADVANCED_ANALYSIS_DEFAULT_TRIALS)])[0],
            ADVANCED_ANALYSIS_DEFAULT_TRIALS,
        )
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
        handler._send(
            json.dumps({"ok": True, "timeframe": timeframe or "all", "analysis": analysis}, ensure_ascii=False),
            "application/json; charset=utf-8",
        )
        return True
    if path == "/status":
        return handler._send(_read_static_text("status.html", fallback=STATUS_HTML.read_text(encoding="utf-8"))) or True
    if path == "/report":
        report_path = _latest_report_path()
        if report_path:
            return handler._send(report_path.read_text(encoding="utf-8")) or True
        return handler._send("撠?梯”", status=HTTPStatus.NOT_FOUND) or True
    if path == "/log":
        return handler._send(_log_html()) or True
    if path == "/log.txt":
        return handler._send(_read_log_tail(), "text/plain; charset=utf-8") or True
    if path == "/tests/log":
        return handler._send(_test_log_html()) or True
    if path == "/tests/log.txt":
        return handler._send(_read_test_log_tail(), "text/plain; charset=utf-8") or True
    if path == "/tests/log-tail.txt":
        return handler._send(_read_test_log_tail(), "text/plain; charset=utf-8") or True
    return False

__all__ = [
    "_latest_report_path",
    "_latest_top10_path",
    "_parse_float",
    "_db_available",
    "_db_has_table",
    "_db_columns",
    "_read_db_rows",
    "_get_timeframes_db",
    "_get_timeframes",
    "_read_csv_rows",
    "_pick_top10",
    "_get_results_payload",
    "_numeric_series_from_rows",
    "_percentile",
    "_summarize_numeric",
    "_build_advanced_results_analysis",
    "try_handle_get",
]

