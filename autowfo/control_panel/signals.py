"""Signal export + feedback loop helpers extracted for AWF-146."""

from __future__ import annotations

from collections import deque
import json
import sys as _sys
from functools import wraps
from http import HTTPStatus
from urllib.parse import parse_qs

from autowfo.control_panel.signals_export import (
    _build_live_signal_config,
    _collect_strategy_params,
    _export_live_signal_config,
    _json_friendly_number,
    _metric_snapshot_from_row,
    _normalize_signal_row,
    _pick_signal_source_row,
    _safe_int,
    _signal_configs_dir,
    _signal_param_fields,
    _split_indicator_list,
    _write_live_signal_config,
    try_handle_post_export,
)
from autowfo.control_panel.signals_feedback import (
    FEEDBACK_RECOMMEND_DEFAULT_MIN_SAMPLES,
    _apply_feedback_adjustment_to_signal_config,
    _build_feedback_adjusted_sweep_config,
    _derive_feedback_profile,
    _enqueue_feedback_adjusted_batch,
    _export_feedback_adjusted_signal_config,
    _feedback_profile_multipliers,
    _paper_feedback_diagnostics,
    _paper_feedback_recommendations,
    _paper_feedback_summary,
    _pick_feedback_recommendation_for_row,
)


def _cp():
    return _sys.modules.get("autowfo.control_panel.server")


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
def _paper_feedback_log_path():
    return ARTIFACTS / PAPER_FEEDBACK_FILE


@_with_cp
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


@_with_cp
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


@_with_cp
def _record_paper_feedback(payload):
    entry = _validate_feedback_payload(payload)
    path = _paper_feedback_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry, path


@_with_cp
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


def try_handle_get(handler, parsed, path):
    if path == "/signals/paper-feedback-spec.json":
        handler._send(json.dumps(_paper_feedback_spec(), ensure_ascii=False), "application/json; charset=utf-8")
        return True
    if path == "/signals/paper-feedback.json":
        query = parse_qs(parsed.query)
        try:
            limit = int(query.get("limit", ["200"])[0])
        except Exception:
            limit = 200
        rows = _read_paper_feedback(limit=limit)
        handler._send(
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
        return True
    if path == "/signals/paper-feedback-summary.json":
        query = parse_qs(parsed.query)
        try:
            limit = int(query.get("limit", ["500"])[0])
        except Exception:
            limit = 500
        rows = _read_paper_feedback(limit=limit)
        summary = _paper_feedback_summary(rows)
        handler._send(
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
        return True
    if path == "/signals/paper-feedback-diagnostics.json":
        query = parse_qs(parsed.query)
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
        handler._send(
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
        return True
    if path == "/signals/paper-feedback-recommendations.json":
        query = parse_qs(parsed.query)
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
        recommendations = _paper_feedback_recommendations(rows, top_n=top_n, min_samples=min_samples)
        handler._send(
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
        return True
    return False


def try_handle_post(handler, parsed):
    if try_handle_post_export(handler, parsed):
        return True
    if parsed.path == "/signals/paper-feedback":
        try:
            payload = handler._read_json_payload()
            entry, path = _record_paper_feedback(payload)
            handler._send(
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
            handler._send(
                json.dumps({"ok": False, "message": str(exc)}, ensure_ascii=False),
                "application/json; charset=utf-8",
                status=HTTPStatus.BAD_REQUEST,
            )
        except Exception as exc:
            handler._send(
                json.dumps({"ok": False, "message": f"feedback failed: {exc}"}, ensure_ascii=False),
                "application/json; charset=utf-8",
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
        return True
    return False


__all__ = [
    "_signal_configs_dir",
    "_paper_feedback_log_path",
    "_safe_int",
    "_normalize_signal_row",
    "_pick_signal_source_row",
    "_split_indicator_list",
    "_json_friendly_number",
    "_signal_param_fields",
    "_collect_strategy_params",
    "_metric_snapshot_from_row",
    "_build_live_signal_config",
    "_write_live_signal_config",
    "_export_live_signal_config",
    "_paper_feedback_spec",
    "_validate_feedback_payload",
    "_record_paper_feedback",
    "_read_paper_feedback",
    "_paper_feedback_summary",
    "_paper_feedback_diagnostics",
    "_feedback_profile_multipliers",
    "_derive_feedback_profile",
    "_paper_feedback_recommendations",
    "_pick_feedback_recommendation_for_row",
    "_apply_feedback_adjustment_to_signal_config",
    "_export_feedback_adjusted_signal_config",
    "_build_feedback_adjusted_sweep_config",
    "_enqueue_feedback_adjusted_batch",
    "try_handle_get",
    "try_handle_post",
]

