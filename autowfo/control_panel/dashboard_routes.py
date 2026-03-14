"""Dashboard/cross-run route handlers extracted for AWF-146."""

from __future__ import annotations

import json
import sys as _sys
from datetime import datetime, timezone
from http import HTTPStatus
from urllib.parse import parse_qs


def _cp():
    return _sys.modules.get("autowfo.control_panel.server")

_PROTECTED_CP_GLOBALS = {
    "_cp",
    "_bind_cp_globals",
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


def try_handle_get(handler, parsed, path):
    _bind_cp_globals()
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
        handler._send(
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
        return True
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
        lines = [json.dumps(row, ensure_ascii=False) for row in rows_payload.get("rows", [])]
        body_text = "\n".join(lines)
        if body_text:
            body_text += "\n"
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"dashboard_errors_{stamp}.ndjson"
        handler._send_with_headers(
            body_text,
            "text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
        return True
    if path == "/dashboard/cross_run.json":
        query = parse_qs(parsed.query)
        top_n = _normalize_top_n(query.get("top_n", [str(DASHBOARD_TOP_N_DEFAULT)])[0])
        request_id = _new_request_id()
        try:
            payload = _cross_run_validate_payload(_cross_run_payload(top_n=top_n))
            payload["payload_source"] = "live"
            payload["request_id"] = request_id
            handler._send(json.dumps(payload, ensure_ascii=False), "application/json; charset=utf-8")
            return True
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
                handler._send(json.dumps(payload, ensure_ascii=False), "application/json; charset=utf-8")
                return True
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
            handler._send(
                json.dumps(error_payload, ensure_ascii=False),
                "application/json; charset=utf-8",
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return True
    if path == "/dashboard/report":
        report_path = ARTIFACTS / "cross_run_report.html"
        if report_path.exists():
            handler._send(report_path.read_text(encoding="utf-8"))
            return True
        try:
            report_payload, generated_path = _cross_run_generate_report(top_n=20)
            _cross_run_validate_payload(report_payload)
            if generated_path.exists():
                handler._send(generated_path.read_text(encoding="utf-8"))
                return True
        except Exception as exc:
            try:
                _cached_payload, cached_html, _cached_path = _cross_run_cached_report_html(top_n=20)
                handler._send(cached_html)
                return True
            except Exception:
                handler._send(f"Generate report failed: {exc}", status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return True
        try:
            _cached_payload, cached_html, _cached_path = _cross_run_cached_report_html(top_n=20)
            handler._send(cached_html)
            return True
        except Exception:
            handler._send("Cross-run report unavailable", status=HTTPStatus.NOT_FOUND)
            return True
    return False


def try_handle_post(handler, parsed):
    _bind_cp_globals()
    if parsed.path == "/dashboard/errors/clear":
        try:
            payload = handler._read_json_payload()
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
        handler._send(
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
        return True
    if parsed.path == "/dashboard/report/generate":
        top_n = DASHBOARD_TOP_N_DEFAULT
        request_id = _new_request_id()
        try:
            payload = handler._read_json_payload()
            top_n = _normalize_top_n(payload.get("top_n", DASHBOARD_TOP_N_DEFAULT))
        except Exception:
            top_n = DASHBOARD_TOP_N_DEFAULT
        try:
            report_payload, report_path = _cross_run_generate_report(top_n=top_n)
            _cross_run_validate_payload(report_payload)
            handler._send(
                json.dumps(
                        {
                            "ok": True,
                            "message": "cross-run report generated",
                            "payload_source": "live",
                            "request_id": request_id,
                            "report_path": str(report_path.relative_to(ROOT)),
                            "summary": report_payload.get("summary", {}),
                            "source_status": report_payload.get("source_status", _shared_views_source_status()),
                        },
                        ensure_ascii=False,
                    ),
                    "application/json; charset=utf-8",
            )
            return True
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
                handler._send(
                    json.dumps(
                        {
                            "ok": True,
                            "message": "cross-run report generated from cache fallback",
                            "payload_source": "cache_fallback",
                            "request_id": request_id,
                            "report_path": str(cached_path.relative_to(ROOT)),
                            "summary": cached_payload.get("summary", {}),
                            "source_status": cached_payload.get("source_status", _shared_views_source_status()),
                            "cache_fallback": fallback_meta,
                        },
                        ensure_ascii=False,
                    ),
                    "application/json; charset=utf-8",
                )
                return True
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
            handler._send(
                json.dumps(error_payload, ensure_ascii=False),
                "application/json; charset=utf-8",
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return True
    return False


__all__ = ["try_handle_get", "try_handle_post"]

