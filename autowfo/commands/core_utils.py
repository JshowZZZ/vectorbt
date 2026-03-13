"""Shared low-level helpers for AUTOWFO command modules."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def _resolve_path(base: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        path = (base / path).resolve()
    return path

def _load_config(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8-sig")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml  # type: ignore

            payload = yaml.safe_load(text)
        except Exception as exc:
            raise ValueError(
                f"config must be JSON or YAML (install PyYAML for YAML support): {path}"
            ) from exc
    if not isinstance(payload, dict):
        raise ValueError(f"config must decode to object: {path}")
    return payload

def _json_sha256(payload: Dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

def _slug_text(value: str) -> str:
    text = str(value).strip()
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

def _extract_registry_untested_pairs(registry_payload: Dict[str, Any]) -> List[Dict[str, str]]:
    coverage = registry_payload.get("coverage")
    if not isinstance(coverage, dict):
        return []
    pairs = coverage.get("untested_pairs")
    if not isinstance(pairs, list):
        return []

    output: List[Dict[str, str]] = []
    seen = set()
    for raw in pairs:
        if not isinstance(raw, dict):
            continue
        timeframe = str(raw.get("timeframe", "")).strip()
        symbol = str(raw.get("symbol", "")).strip()
        if not timeframe or not symbol:
            continue
        key = (timeframe, symbol)
        if key in seen:
            continue
        seen.add(key)
        output.append({"timeframe": timeframe, "symbol": symbol})
    return output

def _compute_coverage_gaps(
    registry_payload: Dict[str, Any],
    target_timeframes: List[str],
    target_symbols: List[str],
) -> List[Dict[str, str]]:
    """Compute gap pairs from target dimensions minus tested pairs.

    Unlike ``_extract_registry_untested_pairs`` which only reads the
    stored ``coverage.untested_pairs``, this function performs a fresh
    cartesian-product calculation using externally supplied target
    dimensions.  This allows detecting gaps for timeframes/symbols that
    have never appeared in any run.
    """
    coverage = registry_payload.get("coverage")
    tested_set: set = set()
    if isinstance(coverage, dict):
        tested_raw = coverage.get("tested_pairs")
        if isinstance(tested_raw, list):
            for pair in tested_raw:
                if not isinstance(pair, dict):
                    continue
                timeframe = str(pair.get("timeframe", "")).strip()
                symbol = str(pair.get("symbol", "")).strip()
                if timeframe and symbol:
                    tested_set.add((timeframe, symbol))

    gaps: List[Dict[str, str]] = []
    for timeframe in sorted(target_timeframes):
        for symbol in sorted(target_symbols):
            if (timeframe, symbol) not in tested_set:
                gaps.append({"timeframe": timeframe, "symbol": symbol})
    return gaps

def _build_timeframe_days_map(
    registry_payload: Dict[str, Any],
    template_config: Dict[str, Any],
) -> Dict[str, int]:
    mapping: Dict[str, int] = {}

    runs = registry_payload.get("runs")
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

    template_timeframes = template_config.get("timeframes")
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

def _split_csv_fields(raw: Optional[str]) -> List[str]:
    if raw in (None, ""):
        return []
    return [part.strip() for part in str(raw).split(",") if part and str(part).strip()]


