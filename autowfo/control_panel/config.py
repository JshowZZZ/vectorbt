"""Config read/write submodule for control_panel (AWF-113)."""

import copy
import json
import sys as _sys
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path


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
    {
        "preset_id": "exact-lane-2h-4sym",
        "title": "Exact Lane 2h 4-Symbol",
        "summary": "Replay the frozen exact lane discovered from the 2h BTC-cross cluster.",
        "operator_note": "Use run/combo mode to replay the canonical lane without reopening indicator or symbol exploration.",
        "recommended_workflow": "run",
        "optional": False,
        "bundle_analysis_json_list": (
            "artifacts/reports/pilot_analysis_awf274_anchored_exact_lane.json",
            "artifacts/reports/pilot_analysis_awf264_exact_lane_range120_window_aware.json",
            "artifacts/reports/pilot_analysis_awf264_exact_lane_density_1h_window_aware.json",
        ),
        "promotion_policy": {
            "full_window_gate": {
                "policy_kind": "promotive",
                "timeframe": "2h",
                "data_days": 180,
                "trade_gate_policy": "flat",
                "min_combo_trades": 0.5,
            },
            "short_window_gate": {
                "policy_kind": "supporting",
                "timeframe": "2h",
                "data_days": 120,
                "trade_gate_policy": "window_aware",
                "min_combo_trades": 0.5,
                "trade_gate_reference_days": 180,
                "trade_gate_min_ratio": 0.75,
            },
            "rejected_density_lane": {
                "policy_kind": "rejected",
                "timeframe": "1h",
                "data_days": 180,
                "reason": "awf263_density_follow_up_failed",
            },
        },
        "scope_test_variants": (
            {
                "variant_id": "main",
                "title": "Main 45/30/30",
                "wf_train_days": 45,
                "wf_test_days": 30,
                "wf_step_days": 30,
            },
            {
                "variant_id": "sensitivity",
                "title": "Sensitivity 60/30/30",
                "wf_train_days": 60,
                "wf_test_days": 30,
                "wf_step_days": 30,
            },
        ),
        "patch": {
            "search_mode": "combo",
            "combo_sizes": [3],
            "timeframes": [{"timeframe": "2h", "days": 180}],
            "trade_symbols": ["LTC/BTC", "LINK/BTC", "SOL/BTC", "AVAX/BTC"],
            "indicator_subset": ["mfi", "obv_roc", "atr_ratio"],
            "regime_preset": "pilot_trend_3",
            "regime_name_filter": ["trend_high"],
            "pilot_fixed_indicator_params": True,
            "pilot_single_trend_mom": True,
            "risk_mode": "atr_multiple",
            "tp_atr_multipliers": [1.0, 1.25, 1.5, 1.75, 2.0, 2.25],
            "sl_atr_multipliers": [0.5, 0.75, 1.0, 1.25, 1.5],
            "max_holds": [4],
            "capital_mode": "per_symbol",
            "init_cash_usdt": 1000.0,
            "order_size_pct": 0.5,
            "max_concurrent_positions": 0,
            "top_n_refine": 0,
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


def _config_slug_text(value):
    text = str(value or "").strip().lower()
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
    from autowfo import engine_helpers

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

    indicator_subset = payload.get("indicator_subset", cfg.get("indicator_subset"))
    if isinstance(indicator_subset, str):
        indicator_subset = [s.strip() for s in indicator_subset.split(",") if s.strip()]
    if isinstance(indicator_subset, (list, tuple)):
        cfg["indicator_subset"] = [str(item).strip() for item in indicator_subset if str(item).strip()]

    cfg["regime_preset"] = engine_helpers._normalize_regime_preset(
        payload.get("regime_preset", cfg.get("regime_preset", "full"))
    )
    cfg["regime_name_filter"] = engine_helpers._normalize_regime_name_filter(
        payload.get("regime_name_filter", cfg.get("regime_name_filter"))
    )
    cfg["pilot_fixed_indicator_params"] = bool(
        payload.get("pilot_fixed_indicator_params", cfg.get("pilot_fixed_indicator_params", False))
    )
    cfg["pilot_single_trend_mom"] = bool(
        payload.get("pilot_single_trend_mom", cfg.get("pilot_single_trend_mom", False))
    )
    cfg["risk_mode"] = engine_helpers._normalize_risk_mode(payload.get("risk_mode", cfg.get("risk_mode")))

    def _normalize_float_list(values, fallback):
        raw = values if values is not None else fallback
        if isinstance(raw, str):
            raw = [s.strip() for s in raw.split(",") if s.strip()]
        parsed = []
        if isinstance(raw, (list, tuple)):
            for item in raw:
                try:
                    parsed.append(float(item))
                except (TypeError, ValueError):
                    continue
        return parsed or list(fallback or [])

    def _normalize_int_list(values, fallback):
        raw = values if values is not None else fallback
        if isinstance(raw, str):
            raw = [s.strip() for s in raw.split(",") if s.strip()]
        parsed = []
        if isinstance(raw, (list, tuple)):
            for item in raw:
                try:
                    parsed.append(int(item))
                except (TypeError, ValueError):
                    continue
        return parsed or list(fallback or [])

    cfg["tp_stops"] = _normalize_float_list(payload.get("tp_stops"), cfg.get("tp_stops", []))
    cfg["sl_stops"] = _normalize_float_list(payload.get("sl_stops"), cfg.get("sl_stops", []))
    cfg["tp_atr_multipliers"] = _normalize_float_list(
        payload.get("tp_atr_multipliers"),
        cfg.get("tp_atr_multipliers", []),
    )
    cfg["sl_atr_multipliers"] = _normalize_float_list(
        payload.get("sl_atr_multipliers"),
        cfg.get("sl_atr_multipliers", []),
    )
    cfg["max_holds"] = _normalize_int_list(payload.get("max_holds"), cfg.get("max_holds", []))

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
                entry = {"timeframe": tf, "days": days}
                for key in ("start", "end"):
                    raw = item.get(key)
                    if raw is None:
                        continue
                    text = str(raw).strip()
                    if text:
                        entry[key] = text
                tf_list.append(entry)
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
        scope_test_variants = item.get("scope_test_variants") if isinstance(item, dict) else None
        promotion_policy = item.get("promotion_policy") if isinstance(item, dict) else None
        bundle_analysis_json_list = item.get("bundle_analysis_json_list") if isinstance(item, dict) else None
        presets.append(
            {
                "preset_id": item["preset_id"],
                "title": item["title"],
                "summary": item["summary"],
                "operator_note": item.get("operator_note", ""),
                "recommended_workflow": item.get("recommended_workflow", ""),
                "optional": bool(item.get("optional")),
                "supports_scope_test": bool(scope_test_variants),
                "scope_test_variants": copy.deepcopy(list(scope_test_variants or [])),
                "promotion_policy": copy.deepcopy(promotion_policy or {}),
                "bundle_analysis_json_list": copy.deepcopy(list(bundle_analysis_json_list or [])),
                "timeframes": copy.deepcopy(patch.get("timeframes", [])),
                "trade_symbols": copy.deepcopy(patch.get("trade_symbols", [])),
                "indicator_subset": copy.deepcopy(patch.get("indicator_subset", [])),
                "regime_name_filter": copy.deepcopy(patch.get("regime_name_filter", [])),
            }
        )
    return presets


def _find_config_preset(preset_id):
    target = str(preset_id or "").strip().lower()
    for item in _RERUN_CAMPAIGN_PRESETS:
        if str(item.get("preset_id", "")).strip().lower() == target:
            return item
    return None


def _resolve_runtime_path(path_value):
    cp = _cp()
    path = Path(str(path_value or "").strip())
    if path.is_absolute():
        return path
    return (cp.ROOT / path).resolve()


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


def _preset_planned_configs_dir():
    cp = _cp()
    planned_dir = cp.ARTIFACTS / "planned_configs"
    planned_dir.mkdir(parents=True, exist_ok=True)
    return planned_dir


def _write_preset_planned_config(cfg, prefix):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    cfg_name = f"{_config_slug_text(prefix)}_{stamp}.json"
    cfg_path = _preset_planned_configs_dir() / cfg_name
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return cfg_path


def _resolve_preset_enqueue_workflow(preset, workflow=None, mode=None):
    workflow_raw = workflow if workflow not in (None, "") else preset.get("recommended_workflow", "baseline")
    workflow_norm = str(workflow_raw or "baseline").strip().lower()
    if workflow_norm not in {"run", "baseline"}:
        workflow_norm = "baseline"

    mode_norm = None if mode in (None, "") else str(mode).strip().lower()
    if workflow_norm == "baseline":
        mode_norm = None
    elif mode_norm not in {"combo", "refine"}:
        mode_norm = "combo"
    return workflow_norm, mode_norm


def _normalize_optional_workers(workers):
    if workers in (None, ""):
        return None
    try:
        workers_i = int(workers)
    except (TypeError, ValueError) as exc:
        raise ValueError("workers must be integer") from exc
    if workers_i <= 0:
        raise ValueError("workers must be > 0")
    return workers_i


def _normalize_bool_flag(value, *, default=False):
    if value in (None, ""):
        return bool(default)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError("boolean flag expected")


def _normalize_preset_scope_variants(preset):
    raw_variants = preset.get("scope_test_variants")
    variants = []
    if not isinstance(raw_variants, (list, tuple)):
        return variants
    for item in raw_variants:
        if not isinstance(item, dict):
            continue
        variant_id = _config_slug_text(item.get("variant_id") or item.get("title") or f"variant-{len(variants) + 1}")
        try:
            wf_train_days = max(1, int(item.get("wf_train_days")))
            wf_test_days = max(1, int(item.get("wf_test_days")))
            wf_step_days = max(1, int(item.get("wf_step_days")))
        except (TypeError, ValueError):
            continue
        variants.append(
            {
                "variant_id": variant_id,
                "title": str(item.get("title") or variant_id),
                "wf_train_days": wf_train_days,
                "wf_test_days": wf_test_days,
                "wf_step_days": wf_step_days,
            }
        )
    return variants


def _apply_config_preset_and_enqueue(
    preset_id,
    *,
    workflow=None,
    mode=None,
    workers=None,
    name=None,
    allow_seen_key_reuse=True,
    auto_start=False,
):
    cp = _cp()
    cfg, preset = _apply_config_preset(preset_id)
    workflow_norm, mode_norm = _resolve_preset_enqueue_workflow(preset, workflow=workflow, mode=mode)
    workers_i = _normalize_optional_workers(workers)
    allow_seen_key_reuse = _normalize_bool_flag(allow_seen_key_reuse, default=True)
    auto_start = _normalize_bool_flag(auto_start, default=False)

    preset_slug = _config_slug_text(preset["preset_id"])
    cfg_path = _write_preset_planned_config(cfg, f"preset_{preset_slug}")
    enqueue_payload = {
        "name": str(name or f"preset-{preset_slug}"),
        "workflow": workflow_norm,
        "config": str(cfg_path),
        "allow_seen_key_reuse": allow_seen_key_reuse,
    }
    if mode_norm is not None:
        enqueue_payload["mode"] = mode_norm
    if workers_i is not None:
        enqueue_payload["workers"] = workers_i

    ok, msg, job = cp._batch_enqueue(enqueue_payload)
    if not ok:
        raise ValueError(msg)

    started = False
    start_msg = ""
    if auto_start:
        started, start_msg = cp._batch_start()

    return {
        "preset": {
            "preset_id": preset["preset_id"],
            "title": preset["title"],
            "promotion_policy": copy.deepcopy(preset.get("promotion_policy", {})),
        },
        "config": cfg,
        "config_path": str(cfg_path),
        "job": job,
        "batch_started": bool(started),
        "batch_start_message": str(start_msg),
    }


def _apply_config_preset_scope_test(
    preset_id,
    *,
    workflow=None,
    mode=None,
    workers=None,
    name_prefix=None,
    allow_seen_key_reuse=True,
    auto_start=False,
):
    cp = _cp()
    cfg, preset = _apply_config_preset(preset_id)
    variants = _normalize_preset_scope_variants(preset)
    if not variants:
        raise ValueError(f"Preset does not define scope-test variants: {preset_id}")

    workflow_norm, mode_norm = _resolve_preset_enqueue_workflow(preset, workflow=workflow, mode=mode)
    workers_i = _normalize_optional_workers(workers)
    allow_seen_key_reuse = _normalize_bool_flag(allow_seen_key_reuse, default=True)
    auto_start = _normalize_bool_flag(auto_start, default=False)
    preset_slug = _config_slug_text(preset["preset_id"])
    queue_jobs = []
    variant_details = []
    for variant in variants:
        cfg_variant = _sanitize_config(
            _deep_merge_dict(
                cfg,
                {
                    "wf_train_days": variant["wf_train_days"],
                    "wf_test_days": variant["wf_test_days"],
                    "wf_step_days": variant["wf_step_days"],
                },
            ),
            base_config=cfg,
        )
        _validate_config_guardrails(cfg_variant)
        cfg_path = _write_preset_planned_config(cfg_variant, f"scope_{preset_slug}_{variant['variant_id']}")
        enqueue_payload = {
            "name": str(name_prefix or f"scope-{preset_slug}") + f"-{variant['variant_id']}",
            "workflow": workflow_norm,
            "config": str(cfg_path),
            "allow_seen_key_reuse": allow_seen_key_reuse,
        }
        if mode_norm is not None:
            enqueue_payload["mode"] = mode_norm
        if workers_i is not None:
            enqueue_payload["workers"] = workers_i
        ok, msg, job = cp._batch_enqueue(enqueue_payload)
        if not ok:
            raise ValueError(msg)
        queue_jobs.append(job)
        variant_details.append(
            {
                "variant_id": variant["variant_id"],
                "title": variant["title"],
                "config_path": str(cfg_path),
                "wf_train_days": cfg_variant["wf_train_days"],
                "wf_test_days": cfg_variant["wf_test_days"],
                "wf_step_days": cfg_variant["wf_step_days"],
            }
        )

    started = False
    start_msg = ""
    if auto_start:
        started, start_msg = cp._batch_start()

    return {
        "preset": {
            "preset_id": preset["preset_id"],
            "title": preset["title"],
            "promotion_policy": copy.deepcopy(preset.get("promotion_policy", {})),
        },
        "config": cfg,
        "jobs": queue_jobs,
        "variants": variant_details,
        "batch_started": bool(started),
        "batch_start_message": str(start_msg),
    }


def _evaluate_preset_promotion(preset_id, analysis_json, out_json=None):
    from autowfo import pilot_analysis

    preset = _find_config_preset(preset_id)
    if preset is None:
        raise ValueError(f"Unknown config preset: {preset_id}")
    promotion_policy = copy.deepcopy(preset.get("promotion_policy", {}))
    if not promotion_policy:
        raise ValueError(f"Preset has no promotion policy: {preset_id}")

    analysis_path = _resolve_runtime_path(analysis_json)
    analysis_payload = pilot_analysis.load_analysis_report(analysis_path)
    verdict = pilot_analysis.evaluate_promotion_verdict(analysis_payload, promotion_policy)
    payload = {
        "preset_id": str(preset.get("preset_id") or preset_id),
        "preset_title": str(preset.get("title") or ""),
        "analysis_json": str(analysis_path),
        "promotion_policy": promotion_policy,
        "verdict": verdict,
    }
    if out_json not in (None, ""):
        out_path = _resolve_runtime_path(out_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        payload["out_json"] = str(out_path)
    return payload


def _build_preset_operator_bundle(preset_id, analysis_json_list, out_json=None):
    from autowfo import pilot_analysis

    preset = _find_config_preset(preset_id)
    if preset is None:
        raise ValueError(f"Unknown config preset: {preset_id}")
    promotion_policy = copy.deepcopy(preset.get("promotion_policy", {}))
    if not promotion_policy:
        raise ValueError(f"Preset has no promotion policy: {preset_id}")

    analysis_inputs = [str(item).strip() for item in list(analysis_json_list or []) if str(item).strip()]
    if not analysis_inputs:
        analysis_inputs = [
            str(item).strip()
            for item in list(preset.get("bundle_analysis_json_list") or [])
            if str(item).strip()
        ]
    if not analysis_inputs:
        raise ValueError("at least one analysis_json is required")

    items = []
    for analysis_item in analysis_inputs:
        analysis_path = _resolve_runtime_path(analysis_item)
        analysis_payload = pilot_analysis.load_analysis_report(analysis_path)
        verdict = pilot_analysis.evaluate_promotion_verdict(analysis_payload, promotion_policy)
        items.append(
            {
                "analysis_json": str(analysis_path),
                "analysis_context": verdict.get("analysis_context"),
                "summary": dict((analysis_payload.get("summary") or {})),
                "verdict": verdict,
            }
        )

    payload = {
        "preset_id": str(preset.get("preset_id") or preset_id),
        "preset_title": str(preset.get("title") or ""),
        "promotion_policy": promotion_policy,
        "items": items,
    }
    if out_json not in (None, ""):
        out_path = _resolve_runtime_path(out_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        payload["out_json"] = str(out_path)
    return payload


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
                            "promotion_policy": copy.deepcopy(preset.get("promotion_policy", {})),
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
    if parsed.path == "/config/apply-preset-and-enqueue":
        try:
            payload = handler._read_json_payload()
            result = _apply_config_preset_and_enqueue(
                payload.get("preset_id"),
                workflow=payload.get("workflow"),
                mode=payload.get("mode"),
                workers=payload.get("workers"),
                name=payload.get("name"),
                allow_seen_key_reuse=payload.get("allow_seen_key_reuse", True),
                auto_start=payload.get("auto_start", False),
            )
            handler._send(
                json.dumps(
                    {
                        "ok": True,
                        "message": f"Preset applied and enqueued: {result['preset']['title']}",
                        "details": result,
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
                json.dumps({"ok": False, "message": f"Failed to enqueue preset workflow: {exc}"}, ensure_ascii=False),
                "application/json; charset=utf-8",
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
        return True
    if parsed.path == "/config/apply-preset-scope-test":
        try:
            payload = handler._read_json_payload()
            result = _apply_config_preset_scope_test(
                payload.get("preset_id"),
                workflow=payload.get("workflow"),
                mode=payload.get("mode"),
                workers=payload.get("workers"),
                name_prefix=payload.get("name_prefix"),
                allow_seen_key_reuse=payload.get("allow_seen_key_reuse", True),
                auto_start=payload.get("auto_start", False),
            )
            handler._send(
                json.dumps(
                    {
                        "ok": True,
                        "message": f"Scope-test jobs enqueued: {result['preset']['title']}",
                        "details": result,
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
                json.dumps({"ok": False, "message": f"Failed to enqueue scope-test workflow: {exc}"}, ensure_ascii=False),
                "application/json; charset=utf-8",
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
        return True
    if parsed.path == "/config/evaluate-preset-promotion":
        try:
            payload = handler._read_json_payload()
            result = _evaluate_preset_promotion(
                payload.get("preset_id"),
                payload.get("analysis_json"),
                out_json=payload.get("out_json"),
            )
            handler._send(
                json.dumps(
                    {
                        "ok": True,
                        "message": f"Promotion policy evaluated: {result['preset_title']}",
                        "details": result,
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
                json.dumps({"ok": False, "message": f"Failed to evaluate promotion policy: {exc}"}, ensure_ascii=False),
                "application/json; charset=utf-8",
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
        return True
    if parsed.path == "/config/build-preset-bundle":
        try:
            payload = handler._read_json_payload()
            result = _build_preset_operator_bundle(
                payload.get("preset_id"),
                payload.get("analysis_json_list"),
                out_json=payload.get("out_json"),
            )
            handler._send(
                json.dumps(
                    {
                        "ok": True,
                        "message": f"Operator bundle built: {result['preset_title']}",
                        "details": result,
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
                json.dumps({"ok": False, "message": f"Failed to build operator bundle: {exc}"}, ensure_ascii=False),
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
    "_preset_planned_configs_dir",
    "_write_preset_planned_config",
    "_resolve_preset_enqueue_workflow",
    "_normalize_optional_workers",
    "_normalize_bool_flag",
    "_normalize_preset_scope_variants",
    "_apply_config_preset_and_enqueue",
    "_apply_config_preset_scope_test",
    "_evaluate_preset_promotion",
    "_build_preset_operator_bundle",
    "_fetch_top_symbols",
    "try_handle_get",
    "try_handle_post",
]

