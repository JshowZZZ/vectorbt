"""Export live-signal configuration from analytics top strategies."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _parse_json_object(raw: Any) -> dict:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}
        try:
            value = json.loads(text)
        except Exception:
            return {}
        if isinstance(value, dict):
            return value
    return {}


def _first_indicator(raw: Any) -> str:
    if isinstance(raw, list):
        for item in raw:
            text = str(item).strip()
            if text:
                return text
        return ""
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return ""
        try:
            parsed = json.loads(text)
        except Exception:
            return text
        if isinstance(parsed, list):
            return _first_indicator(parsed)
        if isinstance(parsed, str):
            return parsed.strip()
        return ""
    return ""


def build_live_signal_config_from_combo(combo_row: dict) -> dict:
    if not isinstance(combo_row, dict):
        raise ValueError("combo row must be a dict")

    indicator_params = _parse_json_object(combo_row.get("indicator_params"))
    trigger_indicator = _first_indicator(indicator_params.get("trigger_indicators"))
    action_indicator = _first_indicator(indicator_params.get("action_indicators"))
    if not trigger_indicator or not action_indicator:
        raise ValueError("top strategy missing trigger/action indicators")

    wf_params = {
        "wf_score": combo_row.get("wf_score"),
        "oos_sharpe": combo_row.get("oos_sharpe"),
        "oos_win_rate": combo_row.get("oos_win_rate"),
        "oos_n_trades": combo_row.get("oos_n_trades"),
    }

    return {
        "experiment_id": str(combo_row.get("experiment_id") or ""),
        "trigger_indicator": trigger_indicator,
        "action_indicator": action_indicator,
        "wf_params": wf_params,
        "export_ts": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }


def export_top_signal_config(analytics_store, top_n: int = 1, out_path: str | Path = "artifacts/live_signal_config.json") -> dict:
    try:
        limit_n = int(top_n)
    except Exception:
        limit_n = 1
    limit_n = max(1, limit_n)

    rows = analytics_store.query_all_time_best(limit=limit_n)
    if not rows:
        raise ValueError("no analytics strategies available to export")

    payload = build_live_signal_config_from_combo(rows[0])
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload

