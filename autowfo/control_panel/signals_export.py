"""Signal export handlers extracted for AWF-160."""

from __future__ import annotations

import json
import re
import sys as _sys
from datetime import datetime, timezone
from functools import wraps
from http import HTTPStatus

from autowfo.control_panel.signals_feedback import (
    FEEDBACK_RECOMMEND_DEFAULT_MIN_SAMPLES,
    _enqueue_feedback_adjusted_batch,
    _export_feedback_adjusted_signal_config,
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
    "try_handle_post_export",
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
def _signal_configs_dir():
    return ARTIFACTS / LIVE_SIGNAL_CONFIG_SUBDIR


@_with_cp
def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return int(default)


@_with_cp
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


@_with_cp
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


@_with_cp
def _split_indicator_list(value):
    raw = str(value or "").strip()
    if not raw:
        return []
    return [part for part in re.split(r"[,+;|/]", raw) if part and part.strip()]


@_with_cp
def _json_friendly_number(value):
    num = _parse_float(value)
    if num is None:
        return value
    if float(num).is_integer():
        return int(num)
    return float(num)


@_with_cp
def _signal_param_fields():
    fields = []
    try:
        from autowfo.constants import INDICATOR_PARAM_FIELDS  # type: ignore

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


@_with_cp
def _collect_strategy_params(row):
    params = {}
    for key in _signal_param_fields():
        value = row.get(key)
        if value in ("", None):
            continue
        params[key] = _json_friendly_number(value)
    return params


@_with_cp
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


@_with_cp
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


@_with_cp
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


@_with_cp
def _export_live_signal_config(rank=1, timeframe=None, row=None):
    source_row = _normalize_signal_row(row) if isinstance(row, dict) else {}
    if not source_row:
        source_row = _pick_signal_source_row(rank=rank, timeframe=timeframe)
    if not source_row:
        raise ValueError("top combo not available")
    config_payload = _build_live_signal_config(source_row, rank=rank)
    out_path = _write_live_signal_config(config_payload)
    return config_payload, out_path


def try_handle_post_export(handler, parsed):
    if parsed.path == "/signals/export-top-config":
        try:
            payload = handler._read_json_payload()
            rank = _safe_int(payload.get("rank", 1), 1)
            timeframe = str(payload.get("timeframe", "")).strip() or None
            row = payload.get("row")
            result = _export_live_signal_config(
                rank=rank,
                timeframe=timeframe,
                row=row if isinstance(row, dict) else None,
            )
            handler._send(
                json.dumps(
                    {
                        "ok": True,
                        "message": "live signal config exported",
                        "signal_config_id": result.get("signal_config_id"),
                        "path": str(result.get("path").relative_to(ROOT)),
                        "source": result.get("source"),
                        "timeframe": result.get("timeframe"),
                        "rank": result.get("rank"),
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
                json.dumps({"ok": False, "message": f"export failed: {exc}"}, ensure_ascii=False),
                "application/json; charset=utf-8",
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
        return True
    if parsed.path == "/signals/export-feedback-adjusted-config":
        try:
            payload = handler._read_json_payload()
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
            adjusted_payload, out_path, rec = _export_feedback_adjusted_signal_config(
                profile=profile,
                rank=rank,
                timeframe=timeframe,
                row=row if isinstance(row, dict) else None,
                recommendation=recommendation if isinstance(recommendation, dict) else None,
                min_samples=min_samples,
            )
            resolved_profile = str(
                (
                    adjusted_payload.get("feedback_adjustment", {})
                    if isinstance(adjusted_payload.get("feedback_adjustment"), dict)
                    else {}
                ).get("profile")
                or profile
                or "balanced"
            ).strip().lower()
            risk_payload = adjusted_payload.get("risk") if isinstance(adjusted_payload.get("risk"), dict) else {}
            handler._send(
                json.dumps(
                    {
                        "ok": True,
                        "message": "feedback-adjusted signal config exported",
                        "signal_config_id": adjusted_payload.get("signal_config_id"),
                        "path": str(out_path.relative_to(ROOT)),
                        "profile": resolved_profile,
                        "source": adjusted_payload.get("source"),
                        "recommendation": rec,
                        "risk": risk_payload,
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
                json.dumps({"ok": False, "message": f"export failed: {exc}"}, ensure_ascii=False),
                "application/json; charset=utf-8",
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
        return True
    if parsed.path == "/signals/enqueue-feedback-adjusted-batch":
        try:
            payload = handler._read_json_payload()
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
            handler._send(
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
            handler._send(
                json.dumps({"ok": False, "message": str(exc)}, ensure_ascii=False),
                "application/json; charset=utf-8",
                status=HTTPStatus.BAD_REQUEST,
            )
        except Exception as exc:
            handler._send(
                json.dumps({"ok": False, "message": f"enqueue failed: {exc}"}, ensure_ascii=False),
                "application/json; charset=utf-8",
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
        return True
    return False


__all__ = [
    "_signal_configs_dir",
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
    "try_handle_post_export",
]

