"""Config read/write submodule for control_panel (AWF-113)."""

import copy
import json
import sys as _sys
from datetime import datetime, timezone
from http import HTTPStatus


_RERUN_CAMPAIGN_PRESETS = (
    {
        "preset_id": "wave0-smoke-1h-60d",
        "title": "Wave 0 Smoke 1h/60d",
        "summary": "Seed the control-panel smoke set before Coverage/Batch execution.",
        "operator_note": "Use Coverage cells individually: baseline for ETH/BTC and SOL/BTC, run combo for BNB/BTC.",
        "recommended_workflow": "mixed",
        "optional": False,
        "patch": {
            "search_mode": "combo",
            "timeframes": [{"timeframe": "1h", "days": 60}],
            "trade_symbols": ["ETH/BTC", "BNB/BTC", "SOL/BTC"],
        },
    },
    {
        "preset_id": "wave2-core-2h-120d",
        "title": "Wave 2 Core 2h/120d",
        "summary": "Restore the core historical evidence pairs from the rerun campaign.",
        "operator_note": "Apply this preset, then run Coverage or Batch in baseline mode.",
        "recommended_workflow": "baseline",
        "optional": False,
        "patch": {
            "search_mode": "combo",
            "timeframes": [{"timeframe": "2h", "days": 120}],
            "trade_symbols": ["BNB/BTC", "SOL/BTC"],
        },
    },
    {
        "preset_id": "wave2-xrp-4h-180d",
        "title": "Wave 2 XRP 4h/180d",
        "summary": "Target the XRP/BTC historical rebuild window from the documented campaign.",
        "operator_note": "Run this preset in baseline mode after Wave 0 coverage smoke is healthy.",
        "recommended_workflow": "baseline",
        "optional": False,
        "patch": {
            "search_mode": "combo",
            "timeframes": [{"timeframe": "4h", "days": 180}],
            "trade_symbols": ["XRP/BTC"],
        },
    },
    {
        "preset_id": "wave2-sol-usdt-2h-120d",
        "title": "Wave 2 SOL/USDT 2h/120d",
        "summary": "Optional non-BTC quote validation track for the historical campaign.",
        "operator_note": "Only run this if the non-BTC quote validation track is still in scope.",
        "recommended_workflow": "baseline",
        "optional": True,
        "patch": {
            "search_mode": "combo",
            "timeframes": [{"timeframe": "2h", "days": 120}],
            "trade_symbols": ["SOL/USDT"],
        },
    },
)


def _cp():
    """Deferred accessor for the main control_panel module."""
    return _sys.modules.get("autowfo.control_panel.server")


def _write_status(payload):
    cp = _cp()
    cp.ARTIFACTS.mkdir(parents=True, exist_ok=True)
    with cp.STATUS_JSON.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _write_test_status(payload):
    cp = _cp()
    cp.ARTIFACTS.mkdir(parents=True, exist_ok=True)
    with cp.TEST_STATUS_JSON.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _parse_iso(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _read_control():
    cp = _cp()
    if cp.CONTROL_JSON.exists():
        try:
            return json.loads(cp.CONTROL_JSON.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"paused": False}


def _write_control(paused):
    cp = _cp()
    cp.ARTIFACTS.mkdir(parents=True, exist_ok=True)
    cp.CONTROL_JSON.write_text(
        json.dumps({"paused": bool(paused)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _deep_merge_dict(base, override):
    merged = copy.deepcopy(base)
    if not isinstance(override, dict):
        return merged
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dict(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _default_config_copy():
    from autowfo.engine_helpers import DEFAULT_CONFIG

    return copy.deepcopy(DEFAULT_CONFIG)


def _normalize_base_config(base_config=None):
    cfg = _default_config_copy()
    if isinstance(base_config, dict):
        cfg = _deep_merge_dict(cfg, base_config)
    return cfg


def _read_config():
    cp = _cp()
    if cp.CONFIG_JSON.exists():
        try:
            cfg = _normalize_base_config(json.loads(cp.CONFIG_JSON.read_text(encoding="utf-8")))
            if not cfg.get("trade_symbols"):
                cfg["trade_symbols"] = _fetch_top_symbols(limit=10)
            return cfg
        except Exception:
            pass
    cfg = _default_config_copy()
    if not cfg.get("trade_symbols"):
        cfg["trade_symbols"] = _fetch_top_symbols(limit=10)
    return cfg


def _sanitize_config(payload, base_config=None):
    cfg = _normalize_base_config(base_config)
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
    cfg["max_concurrent_positions"] = _safe_int(
        payload.get("max_concurrent_positions"), cfg["max_concurrent_positions"]
    )

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


def _validate_config_guardrails(cfg):
    if not isinstance(cfg, dict):
        return
    wf_test_days = int(cfg.get("wf_test_days", 0) or 0)
    wf_step_days = int(cfg.get("wf_step_days", 0) or 0)
    if wf_test_days > 0 and wf_step_days > 0 and wf_step_days < wf_test_days:
        raise ValueError(
            f"wf_step_days ({wf_step_days}) must be >= wf_test_days ({wf_test_days}) to avoid overlapping OOS segments"
        )


def _write_config(payload):
    cp = _cp()
    cp.ARTIFACTS.mkdir(parents=True, exist_ok=True)
    cfg = _sanitize_config(payload, base_config=_read_config())
    _validate_config_guardrails(cfg)
    cp.CONFIG_JSON.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return cfg


def _list_config_presets():
    presets = []
    for item in _RERUN_CAMPAIGN_PRESETS:
        patch = item.get("patch") if isinstance(item, dict) else {}
        presets.append(
            {
                "preset_id": item["preset_id"],
                "title": item["title"],
                "summary": item["summary"],
                "operator_note": item.get("operator_note", ""),
                "recommended_workflow": item.get("recommended_workflow", ""),
                "optional": bool(item.get("optional")),
                "timeframes": copy.deepcopy(patch.get("timeframes", [])),
                "trade_symbols": copy.deepcopy(patch.get("trade_symbols", [])),
            }
        )
    return presets


def _find_config_preset(preset_id):
    target = str(preset_id or "").strip().lower()
    for item in _RERUN_CAMPAIGN_PRESETS:
        if str(item.get("preset_id", "")).strip().lower() == target:
            return item
    return None


def _apply_config_preset(preset_id):
    cp = _cp()
    preset = _find_config_preset(preset_id)
    if preset is None:
        raise ValueError(f"Unknown config preset: {preset_id}")

    cp.ARTIFACTS.mkdir(parents=True, exist_ok=True)
    base_config = _read_config()
    merged_payload = _deep_merge_dict(base_config, preset.get("patch", {}))
    cfg = _sanitize_config(merged_payload, base_config=base_config)
    _validate_config_guardrails(cfg)
    cp.CONFIG_JSON.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return cfg, preset


def _fetch_top_symbols(limit=10):
    cp = _cp()
    from autowfo.engine_helpers import DEFAULT_CONFIG
    now_ts = datetime.now(timezone.utc).timestamp()
    if cp.SYMBOL_CACHE["symbols"] and now_ts - cp.SYMBOL_CACHE["ts"] < 600:
        return cp.SYMBOL_CACHE["symbols"][:limit]
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
            cp.SYMBOL_CACHE["ts"] = now_ts
            cp.SYMBOL_CACHE["symbols"] = symbols
            return symbols[:limit]
    except Exception:
        return fallback[:limit]
    return fallback[:limit]


def try_handle_get(handler, _parsed, path):
    cp = _cp()
    if path == "/config.json":
        handler._send(json.dumps(_read_config(), ensure_ascii=False), "application/json; charset=utf-8")
        return True
    if path == "/config/presets.json":
        handler._send(
            json.dumps({"presets": _list_config_presets()}, ensure_ascii=False),
            "application/json; charset=utf-8",
        )
        return True
    if path == "/control.json":
        handler._send(json.dumps(_read_control(), ensure_ascii=False), "application/json; charset=utf-8")
        return True
    if path == "/symbols/top":
        symbols = _fetch_top_symbols(limit=10)
        cp.SYMBOL_CACHE["symbols"] = symbols
        cp.SYMBOL_CACHE["ts"] = datetime.now(timezone.utc).timestamp()
        handler._send(json.dumps({"symbols": symbols}, ensure_ascii=False), "application/json; charset=utf-8")
        return True
    return False


def try_handle_post(handler, parsed):
    cp = _cp()
    if parsed.path == "/pause":
        _write_control(True)
        handler._send(
            json.dumps({"ok": True, "message": "Run control paused"}, ensure_ascii=False),
            "application/json; charset=utf-8",
        )
        return True
    if parsed.path == "/resume":
        _write_control(False)
        handler._send(
            json.dumps({"ok": True, "message": "Run control resumed"}, ensure_ascii=False),
            "application/json; charset=utf-8",
        )
        return True
    if parsed.path == "/config":
        try:
            payload = handler._read_json_payload()
            cfg = _write_config(payload)
            handler._send(
                json.dumps({"ok": True, "message": "Config saved", "config": cfg}, ensure_ascii=False),
                "application/json; charset=utf-8",
            )
        except ValueError as exc:
            handler._send(
                json.dumps({"ok": False, "message": f"Config validation failed: {exc}"}, ensure_ascii=False),
                "application/json; charset=utf-8",
                status=HTTPStatus.BAD_REQUEST,
            )
        except Exception as exc:
            handler._send(
                json.dumps({"ok": False, "message": f"Failed to save config: {exc}"}, ensure_ascii=False),
                "application/json; charset=utf-8",
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
        return True
    if parsed.path == "/config/apply-preset":
        try:
            payload = handler._read_json_payload()
            cfg, preset = _apply_config_preset(payload.get("preset_id"))
            handler._send(
                json.dumps(
                    {
                        "ok": True,
                        "message": f"Preset applied: {preset['title']}",
                        "preset": {
                            "preset_id": preset["preset_id"],
                            "title": preset["title"],
                        },
                        "config": cfg,
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
                json.dumps({"ok": False, "message": f"Failed to apply preset: {exc}"}, ensure_ascii=False),
                "application/json; charset=utf-8",
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
        return True
    if parsed.path == "/clear-log":
        try:
            cp.ARTIFACTS.mkdir(parents=True, exist_ok=True)
            cp.RUN_LOG.write_text("", encoding="utf-8")
            handler._send(
                json.dumps({"ok": True, "message": "Run log cleared"}, ensure_ascii=False),
                "application/json; charset=utf-8",
            )
        except Exception as exc:
            handler._send(
                json.dumps({"ok": False, "message": f"Failed to clear run log: {exc}"}, ensure_ascii=False),
                "application/json; charset=utf-8",
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
        return True
    if parsed.path == "/tests/clear-log":
        try:
            cp._clear_test_log()
            handler._send(
                json.dumps({"ok": True, "message": "Test log cleared"}, ensure_ascii=False),
                "application/json; charset=utf-8",
            )
        except Exception as exc:
            handler._send(
                json.dumps({"ok": False, "message": f"Failed to clear test log: {exc}"}, ensure_ascii=False),
                "application/json; charset=utf-8",
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
        return True
    return False


__all__ = [
    "_write_status",
    "_write_test_status",
    "_parse_iso",
    "_read_control",
    "_write_control",
    "_deep_merge_dict",
    "_default_config_copy",
    "_normalize_base_config",
    "_read_config",
    "_sanitize_config",
    "_validate_config_guardrails",
    "_write_config",
    "_list_config_presets",
    "_find_config_preset",
    "_apply_config_preset",
    "_fetch_top_symbols",
    "try_handle_get",
    "try_handle_post",
]

