"""Dashboard/cross-run endpoints + error-event helpers for AWF-146."""

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
from autowfo.control_panel.state import _shared_views_source_status


def _cp():
    return _sys.modules.get("autowfo.control_panel.server")

DASHBOARD_ERROR_EVENTS_DEFAULT_LIMIT = 100
DASHBOARD_ERROR_EVENTS_MAX_ROWS = 5000


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
        raise RuntimeError("autowfo.control_panel module not loaded")
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
    sync_runtime = getattr(cp, "_sync_runtime_from_aliases", None)
    if callable(sync_runtime):
        sync_runtime(*_MUTABLE_GLOBALS)


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
def _cross_run_payload(top_n=20):
    from autowfo import cross_run

    registry_path = _coverage_registry_path()
    top_n_i = _normalize_top_n(top_n)
    payload = cross_run.validate_cross_run_payload(
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
    payload["source_status"] = _shared_views_source_status()
    return payload

@_with_cp
def _cross_run_cached_payload(top_n=20):
    from autowfo import cross_run

    payload_path = ARTIFACTS / "cross_run_report.json"
    payload = cross_run.load_cross_run_payload(
        payload_path=payload_path,
        top_n=_normalize_top_n(top_n),
    )
    payload["source_status"] = _shared_views_source_status()
    return payload

@_with_cp
def _cross_run_generate_report(top_n=20):
    from autowfo import cross_run

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
    payload["source_status"] = _shared_views_source_status()
    return payload, out_html

@_with_cp
def _cross_run_cached_report_html(top_n=20, persist_html=False):
    from autowfo import cross_run

    payload = _cross_run_cached_payload(top_n=top_n)
    html_text = cross_run.render_cross_run_html(payload)
    out_html = ARTIFACTS / "cross_run_report.html"
    if bool(persist_html):
        out_html.parent.mkdir(parents=True, exist_ok=True)
        out_html.write_text(html_text, encoding="utf-8")
    return payload, html_text, out_html

@_with_cp
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
        "source_status": _shared_views_source_status(),
    }

@_with_cp
def _new_request_id():
    return uuid.uuid4().hex

@_with_cp
def _cross_run_error_code(reason):
    raw_code = getattr(reason, "code", None)
    if isinstance(raw_code, str) and raw_code.strip():
        return raw_code.strip()
    name = reason.__class__.__name__ if reason is not None else "UnknownError"
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", str(name)).lower()
    return snake or "unknown_error"

@_with_cp
def _cross_run_error_details(reason):
    error_type = reason.__class__.__name__ if reason is not None else "UnknownError"
    return {
        "code": _cross_run_error_code(reason),
        "type": error_type,
        "message": str(reason),
    }

@_with_cp
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

@_with_cp
def _cross_run_validate_payload(payload):
    from autowfo import cross_run

    return cross_run.validate_cross_run_payload(payload, require_v1=True)

@_with_cp
def _dashboard_error_events_path():
    return ARTIFACTS / DASHBOARD_ERROR_EVENTS_FILE

@_with_cp
def _normalize_dashboard_endpoint(value):
    return str(value or "").strip().lstrip("/")

@_with_cp
def _normalize_dashboard_error_kind(value):
    raw = str(value or "").strip().lower()
    if raw in {"error", "cache_fallback"}:
        return raw
    return ""

@_with_cp
def _normalize_dashboard_error_code(value):
    return str(value or "").strip()

@_with_cp
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

@_with_cp
def _normalize_dashboard_message_contains(value):
    return str(value or "").strip().lower()

@_with_cp
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

@_with_cp
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

@_with_cp
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

@_with_cp
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

@_with_cp
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

@_with_cp
def _record_dashboard_error_event_safe(**kwargs):
    try:
        return _record_dashboard_error_event(**kwargs)
    except Exception:
        return None

@_with_cp
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

@_with_cp
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


from autowfo.control_panel.dashboard_routes import try_handle_get, try_handle_post

__all__ = [
    "_cross_run_payload",
    "_cross_run_cached_payload",
    "_cross_run_generate_report",
    "_cross_run_cached_report_html",
    "_cross_run_cache_fallback_meta",
    "_new_request_id",
    "_cross_run_error_code",
    "_cross_run_error_details",
    "_dashboard_error_payload",
    "_cross_run_validate_payload",
    "_dashboard_error_events_path",
    "_normalize_dashboard_endpoint",
    "_normalize_dashboard_error_kind",
    "_normalize_dashboard_error_code",
    "_normalize_dashboard_status",
    "_normalize_dashboard_message_contains",
    "_normalize_since_hours",
    "_dashboard_error_event_matcher",
    "_summarize_dashboard_error_events",
    "_trim_dashboard_error_events",
    "_record_dashboard_error_event",
    "_record_dashboard_error_event_safe",
    "_read_dashboard_error_events",
    "_clear_dashboard_error_events",
    "try_handle_get",
    "try_handle_post",
]


