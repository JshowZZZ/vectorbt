"""Coverage matrix planning helpers extracted for AWF-146."""

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
def _coverage_registry_path():
    return ARTIFACTS / "run_registry.json"

@_with_cp
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

@_with_cp
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

@_with_cp
def _coverage_set_to_pairs(pair_set):
    return [
        {"timeframe": timeframe, "symbol": symbol}
        for timeframe, symbol in sorted(pair_set)
    ]

@_with_cp
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

@_with_cp
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

@_with_cp
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

@_with_cp
def _coverage_matrix_payload():
    registry_payload = _read_json_file(_coverage_registry_path(), {"runs": [], "coverage": {}})
    coverage = registry_payload.get("coverage")
    if not isinstance(coverage, dict):
        coverage = {}
    runs = registry_payload.get("runs")
    runs = runs if isinstance(runs, list) else []

    pair_last_tested = {}
    for run in runs:
        if not isinstance(run, dict):
            continue
        ts = run.get("timestamp_utc") or run.get("generated_utc")
        trade_symbols = run.get("trade_symbols") or []
        timeframes_raw = run.get("timeframes") or []
        if not isinstance(trade_symbols, list) or not isinstance(timeframes_raw, list):
            continue
        for sym in trade_symbols:
            for tf_item in timeframes_raw:
                tf = tf_item.get("timeframe") if isinstance(tf_item, dict) else str(tf_item)
                if tf and sym:
                    key = str(tf) + "||" + str(sym)
                    current = pair_last_tested.get(key)
                    if key not in pair_last_tested or (ts and (current is None or ts > current)):
                        pair_last_tested[key] = ts or None

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
            cells.append({
                "timeframe": timeframe,
                "symbol": symbol,
                "status": status,
                "last_tested_utc": pair_last_tested.get(timeframe + "||" + symbol) if status == "tested" else None,
            })

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

@_with_cp
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

@_with_cp
def _coverage_fill_all_gaps(payload):
    """Enqueue all untested cells in the coverage matrix."""
    if not isinstance(payload, dict):
        payload = {}

    workflow = str(payload.get("workflow", "baseline")).strip().lower()
    mode_raw = payload.get("mode")
    mode = None if mode_raw in (None, "") else str(mode_raw).strip().lower()
    workers_raw = payload.get("workers")
    workers = None
    if workers_raw not in (None, ""):
        try:
            workers = int(workers_raw)
        except Exception:
            return False, "workers must be integer", None

    matrix = _coverage_matrix_payload()
    untested = [c for c in matrix.get("cells", []) if c.get("status") == "untested"]
    if not untested:
        return True, "no untested cells", {"enqueued": 0, "skipped": 0, "errors": []}

    enqueued = 0
    skipped = 0
    errors = []
    for cell in untested:
        pair_payload = {
            "timeframe": cell["timeframe"],
            "symbol": cell["symbol"],
            "workflow": workflow,
        }
        if mode is not None:
            pair_payload["mode"] = mode
        if workers is not None:
            pair_payload["workers"] = workers
        ok, msg, _ = _coverage_enqueue_pair(pair_payload)
        if ok:
            enqueued += 1
        elif "already queued" in msg:
            skipped += 1
        else:
            errors.append(f"{cell['timeframe']}?{cell['symbol']}: {msg}")

    summary = {"enqueued": enqueued, "skipped": skipped, "errors": errors}
    ok_overall = len(errors) == 0
    message = f"{enqueued} coverage jobs enqueued" + (f"; {skipped} already queued" if skipped else "")
    if errors:
        message += f"; {len(errors)} errors"
    return ok_overall, message, summary
    """

    summary = {"enqueued": enqueued, "skipped": skipped, "errors": errors}
    ok_overall = len(errors) == 0
    message = f"{enqueued} ?撩??歇?雿?" + (f"嚗skipped} 撌脰歲?? if skipped else "")
    if errors:
        message += f"嚗len(errors)} ?隤?
    return ok_overall, message, summary

"""
def try_handle_get(handler, _parsed, path):
    if path == "/coverage/matrix.json":
        handler._send(
            json.dumps(_coverage_matrix_payload(), ensure_ascii=False),
            "application/json; charset=utf-8",
        )
        return True
    return False


def try_handle_post(handler, parsed):
    if parsed.path == "/coverage/enqueue":
        try:
            payload = handler._read_json_payload()
            ok, msg, details = _coverage_enqueue_pair(payload)
            handler._send(
                json.dumps({"ok": ok, "message": msg, "details": details}, ensure_ascii=False),
                "application/json; charset=utf-8",
                status=HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST,
            )
        except Exception as exc:
            handler._send(
                json.dumps({"ok": False, "message": f"coverage enqueue failed: {exc}"}, ensure_ascii=False),
                "application/json; charset=utf-8",
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
        return True
    if parsed.path == "/coverage/fill-all-gaps":
        try:
            try:
                payload = handler._read_json_payload()
            except Exception:
                payload = {}
            ok, msg, details = _coverage_fill_all_gaps(payload)
            handler._send(
                json.dumps({"ok": ok, "message": msg, "details": details}, ensure_ascii=False),
                "application/json; charset=utf-8",
                status=HTTPStatus.OK,
            )
        except Exception as exc:
            handler._send(
                json.dumps({"ok": False, "message": f"fill-all-gaps failed: {exc}"}, ensure_ascii=False),
                "application/json; charset=utf-8",
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
        return True
    return False


__all__ = [
    "_coverage_registry_path",
    "_coverage_slug_text",
    "_coverage_pairs_to_set",
    "_coverage_set_to_pairs",
    "_coverage_collect_queued_pairs",
    "_coverage_build_days_map",
    "_coverage_default_days",
    "_coverage_matrix_payload",
    "_coverage_enqueue_pair",
    "_coverage_fill_all_gaps",
    "try_handle_get",
    "try_handle_post",
]

