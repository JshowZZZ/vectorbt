"""Signal feedback analytics helpers extracted for AWF-146."""

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

FEEDBACK_RECOMMEND_DEFAULT_MIN_SAMPLES = 3


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

@_with_cp
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

@_with_cp
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

@_with_cp
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

@_with_cp
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

@_with_cp
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

@_with_cp
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

@_with_cp
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

@_with_cp
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

@_with_cp
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

__all__ = [
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
]

