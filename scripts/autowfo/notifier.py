"""Notification dispatcher for AUTOWFO operational events."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request


class NotificationEvent(str, Enum):
    STRATEGY_CHANGED = "STRATEGY_CHANGED"
    POSITION_OPENED = "POSITION_OPENED"
    POSITION_CLOSED = "POSITION_CLOSED"
    PATROL_ANOMALY = "PATROL_ANOMALY"
    PNL_THRESHOLD_HIT = "PNL_THRESHOLD_HIT"


DEFAULT_CONFIG_PATH = Path("artifacts/notifier_config.json")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe_json_read(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _to_event(event_type: NotificationEvent | str) -> NotificationEvent:
    if isinstance(event_type, NotificationEvent):
        return event_type
    return NotificationEvent(str(event_type).strip())


def _post_json(url: str, payload: dict, timeout_seconds: int = 10) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib_request.Request(
        url=url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    with urllib_request.urlopen(req, timeout=timeout_seconds) as resp:  # nosec B310
        status = int(getattr(resp, "status", 200))
        if status >= 400:
            raise RuntimeError(f"http {status}")


def _telegram_text(event_payload: dict) -> str:
    event_type = str(event_payload.get("event_type", "")).strip()
    event_utc = str(event_payload.get("event_utc", "")).strip()
    payload = event_payload.get("payload")
    payload_text = json.dumps(payload if isinstance(payload, dict) else {}, ensure_ascii=False)
    return f"[AUTOWFO] {event_type}\nutc={event_utc}\npayload={payload_text}"


def should_trigger_pnl_threshold(pnl_pct: float, config_path: str | Path = DEFAULT_CONFIG_PATH) -> bool:
    path = Path(config_path)
    if not path.exists():
        return False
    config = _safe_json_read(path)
    raw_threshold = config.get("pnl_threshold_pct")
    try:
        threshold = float(raw_threshold)
    except Exception:
        return False
    if threshold <= 0:
        return False
    try:
        pnl_value = float(pnl_pct)
    except Exception:
        return False
    return abs(pnl_value) >= threshold


def notify(event_type: NotificationEvent | str, payload: dict, config_path: str | Path = DEFAULT_CONFIG_PATH) -> dict:
    path = Path(config_path)
    event = _to_event(event_type)
    out = {
        "ok": True,
        "event_type": event.value,
        "sent": [],
        "skipped": [],
        "errors": [],
    }
    if not path.exists():
        out["skipped"].append("config_missing")
        return out

    config = _safe_json_read(path)
    if not config:
        out["skipped"].append("config_invalid")
        return out

    event_payload = {
        "event_type": event.value,
        "event_utc": _utc_now_iso(),
        "payload": payload if isinstance(payload, dict) else {},
    }

    webhook_cfg = config.get("webhook")
    if isinstance(webhook_cfg, dict) and bool(webhook_cfg.get("enabled")):
        webhook_url = str(webhook_cfg.get("url") or "").strip()
        if webhook_url:
            timeout_seconds = int(webhook_cfg.get("timeout_seconds", 10) or 10)
            try:
                _post_json(webhook_url, event_payload, timeout_seconds=max(1, timeout_seconds))
                out["sent"].append("webhook")
            except (urllib_error.HTTPError, urllib_error.URLError, RuntimeError, ValueError) as exc:
                out["ok"] = False
                out["errors"].append(f"webhook: {exc}")
        else:
            out["skipped"].append("webhook_missing_url")

    telegram_cfg = config.get("telegram")
    if isinstance(telegram_cfg, dict) and bool(telegram_cfg.get("enabled")):
        bot_token = str(telegram_cfg.get("bot_token") or "").strip()
        chat_id = str(telegram_cfg.get("chat_id") or "").strip()
        if bot_token and chat_id:
            tg_payload = {
                "chat_id": chat_id,
                "text": _telegram_text(event_payload),
                "disable_web_page_preview": True,
            }
            parse_mode = str(telegram_cfg.get("parse_mode") or "").strip()
            if parse_mode:
                tg_payload["parse_mode"] = parse_mode
            timeout_seconds = int(telegram_cfg.get("timeout_seconds", 10) or 10)
            tg_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            try:
                _post_json(tg_url, tg_payload, timeout_seconds=max(1, timeout_seconds))
                out["sent"].append("telegram")
            except (urllib_error.HTTPError, urllib_error.URLError, RuntimeError, ValueError) as exc:
                out["ok"] = False
                out["errors"].append(f"telegram: {exc}")
        else:
            out["skipped"].append("telegram_missing_credentials")

    return out
