"""Cross-run aggregation helpers for AWF-016/AWF-017d/AWF-025/AWF-026."""

from __future__ import annotations

import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

CROSS_RUN_PAYLOAD_SCHEMA_VERSION = "autowfo.cross_run_payload/v1"
_CROSS_RUN_SUMMARY_DEFAULTS = {
    "total_runs": 0,
    "unique_symbols": 0,
    "unique_timeframes": 0,
    "avg_oos_return_pct": None,
    "avg_bh_return_pct": None,
    "avg_random_return_pct": None,
    "avg_alpha_vs_bh": None,
    "latest_run_id": None,
    "latest_run_time_utc": None,
    "coverage_tested_pairs": 0,
    "coverage_untested_pairs": 0,
    "coverage_pct": 0.0,
}
_CROSS_RUN_REQUIRED_TOP_LEVEL_KEYS = {
    "schema_version",
    "generated_utc",
    "registry_path",
    "summary",
    "run_history",
    "global_leaderboard",
    "combo_stability",
    "per_regime_leaderboard",
    "regime_summary",
}
_CROSS_RUN_REQUIRED_SUMMARY_KEYS = set(_CROSS_RUN_SUMMARY_DEFAULTS.keys())


class CrossRunPayloadValidationError(ValueError):
    """Validation error with machine-readable code for payload contract failures."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = str(code or "payload_validation_error")


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe_float(value: Any) -> Optional[float]:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(num):
        return None
    return num


def _load_registry(path: Path) -> Dict[str, Any]:
    default_payload: Dict[str, Any] = {
        "updated_utc": None,
        "runs": [],
        "coverage": {},
    }
    if not path.exists():
        return default_payload
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default_payload
    if not isinstance(payload, dict):
        return default_payload
    if not isinstance(payload.get("runs"), list):
        payload["runs"] = []
    if not isinstance(payload.get("coverage"), dict):
        payload["coverage"] = {}
    return payload


def _normalize_str_list(values: Iterable[Any]) -> List[str]:
    output = sorted({str(v).strip() for v in values if str(v).strip()})
    return output


def _coverage_pairs_len(payload: Dict[str, Any], key: str) -> int:
    coverage = payload.get("coverage")
    if not isinstance(coverage, dict):
        return 0
    raw = coverage.get(key)
    if not isinstance(raw, list):
        return 0
    count = 0
    for item in raw:
        if not isinstance(item, dict):
            continue
        timeframe = str(item.get("timeframe", "")).strip()
        symbol = str(item.get("symbol", "")).strip()
        if timeframe and symbol:
            count += 1
    return count


def _find_top10_path(artifacts_dir: Path, run_id: str) -> Optional[Path]:
    # Phase 44+: prefer run-scoped workspace paths first.
    workspace_candidate = artifacts_dir / "runs" / run_id / "results" / f"param_sweep_top10_{run_id}.csv"
    if workspace_candidate.exists():
        return workspace_candidate

    # Baseline pass directories (combo/refine copies).
    patterns = [
        f"runs/*/refine/param_sweep_top10_{run_id}.csv",
        f"runs/*/combo/param_sweep_top10_{run_id}.csv",
        f"runs/*/param_sweep_top10_{run_id}.csv",
    ]
    for pattern in patterns:
        matches = sorted(artifacts_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        if matches:
            return matches[0]

    # Legacy fallback: root artifacts directory (pre-Phase 44).
    root_candidate = artifacts_dir / f"param_sweep_top10_{run_id}.csv"
    if root_candidate.exists():
        return root_candidate
    return None


def _read_top10_rows(path: Path) -> List[Dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return [dict(row) for row in reader]
    except Exception:
        return []


def _combo_key(row: Dict[str, str]) -> str:
    indicator_list = str(row.get("indicator_list") or row.get("filter_name") or "").strip()
    regime_name = str(row.get("regime_name") or "").strip()
    vol_mode = str(row.get("vol_mode") or "").strip()
    return f"{indicator_list}|{regime_name}|{vol_mode}"


def _best_oos_return(row: Dict[str, str]) -> Optional[float]:
    for key in ("oos_avg_total_return_pct", "avg_total_return_pct", "return_pct"):
        num = _safe_float(row.get(key))
        if num is not None:
            return num
    return None


def _best_oos_drawdown(row: Dict[str, str]) -> Optional[float]:
    for key in ("oos_avg_max_drawdown_pct", "avg_max_drawdown_pct", "max_drawdown_pct"):
        num = _safe_float(row.get(key))
        if num is not None:
            return num
    return None


def _linear_slope(values: List[float]) -> float:
    """Simple OLS slope for an evenly-spaced series.  Returns 0.0 for <2 points."""
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n
    numer = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    denom = sum((i - x_mean) ** 2 for i in range(n))
    if denom == 0:
        return 0.0
    return numer / denom


def _trend_label(slope: float, threshold: float = 0.05) -> str:
    """Classify trend slope into a human-readable label."""
    if slope > threshold:
        return "improving"
    if slope < -threshold:
        return "declining"
    return "flat"


def _svg_sparkline(values: List[float], width: int = 120, height: int = 24) -> str:
    """Generate an inline SVG sparkline from a list of floats."""
    if not values:
        return ""
    n = len(values)
    v_min = min(values)
    v_max = max(values)
    v_range = v_max - v_min if v_max != v_min else 1.0
    margin = 2
    ew = width - 2 * margin
    eh = height - 2 * margin
    points = []
    for i, v in enumerate(values):
        x = margin + (i / max(n - 1, 1)) * ew
        y = margin + eh - ((v - v_min) / v_range) * eh
        points.append(f"{x:.1f},{y:.1f}")
    polyline = " ".join(points)
    color = "#3498db" if len(values) < 2 else ("#27ae60" if values[-1] >= values[0] else "#e74c3c")
    return (
        f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">'
        f'<polyline fill="none" stroke="{color}" stroke-width="1.5" points="{polyline}"/>'
        f'</svg>'
    )


def _compute_trend_metrics(
    oos_returns: List[float],
) -> Dict[str, Any]:
    """Derive trend metrics from a chronologically-ordered return series."""
    n = len(oos_returns)
    if n == 0:
        return {
            "trend_direction": "flat",
            "slope": 0.0,
            "return_std": None,
            "consistency_pct": None,
            "sparkline": "",
        }
    slope = _linear_slope(oos_returns)
    direction = _trend_label(slope)
    ret_std = None
    if n >= 2:
        mean_ret = sum(oos_returns) / n
        ret_std = round(math.sqrt(sum((v - mean_ret) ** 2 for v in oos_returns) / (n - 1)), 4)
    positive = sum(1 for v in oos_returns if v > 0)
    consistency = round(positive / n * 100.0, 1)
    sparkline = _svg_sparkline(oos_returns)
    return {
        "trend_direction": direction,
        "slope": round(slope, 6),
        "return_std": ret_std,
        "consistency_pct": consistency,
        "sparkline": sparkline,
    }


def _build_combo_stability(artifacts_dir: Path, runs: List[Dict[str, Any]], top_n: int) -> List[Dict[str, Any]]:
    # Ensure runs are sorted chronologically so trend_points are time-ordered
    sorted_runs = sorted(runs, key=lambda r: str(r.get("timestamp_utc") or ""))

    combo_map: Dict[str, Dict[str, Any]] = {}
    for run in sorted_runs:
        run_id = str(run.get("run_id", "")).strip()
        if not run_id:
            continue
        run_ts = str(run.get("timestamp_utc", "")).strip() or None
        top10_path = _find_top10_path(artifacts_dir, run_id)
        if top10_path is None:
            continue
        rows = _read_top10_rows(top10_path)
        if not rows:
            continue

        best_per_combo: Dict[str, Tuple[Optional[float], Optional[float]]] = {}
        for row in rows:
            key = _combo_key(row)
            if key == "||":
                continue
            oos_ret = _best_oos_return(row)
            oos_dd = _best_oos_drawdown(row)
            prev = best_per_combo.get(key)
            if prev is None:
                best_per_combo[key] = (oos_ret, oos_dd)
                continue
            prev_ret = prev[0]
            if prev_ret is None:
                best_per_combo[key] = (oos_ret, oos_dd)
                continue
            if oos_ret is not None and oos_ret > prev_ret:
                best_per_combo[key] = (oos_ret, oos_dd)

        for key, (oos_ret, oos_dd) in best_per_combo.items():
            entry = combo_map.get(key)
            if entry is None:
                entry = {
                    "combo_key": key,
                    "appearances": 0,
                    "run_ids": [],
                    "oos_returns": [],
                    "oos_drawdowns": [],
                    "trend_points": [],
                }
                combo_map[key] = entry
            entry["appearances"] += 1
            entry["run_ids"].append(run_id)
            entry["trend_points"].append({
                "run_id": run_id,
                "timestamp_utc": run_ts,
                "oos_return_pct": oos_ret,
                "oos_drawdown_pct": oos_dd,
            })
            if oos_ret is not None:
                entry["oos_returns"].append(oos_ret)
            if oos_dd is not None:
                entry["oos_drawdowns"].append(oos_dd)

    result_rows: List[Dict[str, Any]] = []
    for key, entry in combo_map.items():
        rets: List[float] = entry["oos_returns"]
        dds: List[float] = entry["oos_drawdowns"]
        avg_ret = None if not rets else sum(rets) / len(rets)
        avg_dd = None if not dds else sum(dds) / len(dds)
        best_ret = None if not rets else max(rets)
        trend = _compute_trend_metrics(rets)
        result_rows.append(
            {
                "combo_key": key,
                "appearances": int(entry["appearances"]),
                "avg_oos_return_pct": avg_ret,
                "best_oos_return_pct": best_ret,
                "avg_oos_drawdown_pct": avg_dd,
                "run_ids": sorted(set(entry["run_ids"])),
                "trend_points": entry["trend_points"],
                "trend_direction": trend["trend_direction"],
                "slope": trend["slope"],
                "return_std": trend["return_std"],
                "consistency_pct": trend["consistency_pct"],
                "sparkline": trend["sparkline"],
            }
        )

    result_rows.sort(
        key=lambda item: (
            -int(item.get("appearances", 0)),
            -(_safe_float(item.get("avg_oos_return_pct")) or float("-inf")),
        )
    )
    return result_rows[:max(1, int(top_n))]


def _parse_regime_from_combo_key(combo_key: str) -> str:
    """Extract ``regime_name`` from a combo_key (``indicator_list|regime_name|vol_mode``)."""
    parts = str(combo_key).split("|")
    return parts[1].strip() if len(parts) >= 2 else ""


def _build_per_regime_leaderboard(
    combo_stability: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """Group *combo_stability* entries by regime_name and return per-regime lists.

    Returns ``{regime_name: [combo_entry, ...]}``, each list sorted descending
    by ``avg_oos_return_pct``.
    """
    regime_groups: Dict[str, List[Dict[str, Any]]] = {}
    for entry in combo_stability:
        regime = _parse_regime_from_combo_key(entry.get("combo_key", ""))
        if not regime:
            continue
        regime_groups.setdefault(regime, []).append(entry)

    # Sort each group by avg_oos_return_pct descending
    for regime in regime_groups:
        regime_groups[regime].sort(
            key=lambda e: -(_safe_float(e.get("avg_oos_return_pct")) or float("-inf"))
        )
    return regime_groups


def _build_regime_summary(
    combo_stability: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Per-regime aggregate stats from combo_stability entries.

    Returns list of ``{regime_name, combo_count, avg_return_pct, avg_drawdown_pct}``
    sorted by regime_name.
    """
    regime_agg: Dict[str, Dict[str, Any]] = {}
    for entry in combo_stability:
        regime = _parse_regime_from_combo_key(entry.get("combo_key", ""))
        if not regime:
            continue
        agg = regime_agg.get(regime)
        if agg is None:
            agg = {"returns": [], "drawdowns": [], "count": 0}
            regime_agg[regime] = agg
        agg["count"] += 1
        ret = _safe_float(entry.get("avg_oos_return_pct"))
        if ret is not None:
            agg["returns"].append(ret)
        dd = _safe_float(entry.get("avg_oos_drawdown_pct"))
        if dd is not None:
            agg["drawdowns"].append(dd)

    rows: List[Dict[str, Any]] = []
    for regime in sorted(regime_agg):
        agg = regime_agg[regime]
        rets = agg["returns"]
        dds = agg["drawdowns"]
        rows.append({
            "regime_name": regime,
            "combo_count": agg["count"],
            "avg_return_pct": round(sum(rets) / len(rets), 4) if rets else None,
            "avg_drawdown_pct": round(sum(dds) / len(dds), 4) if dds else None,
        })
    return rows


def build_cross_run_payload(
    artifacts_dir: Path,
    registry_path: Path,
    top_n: int = 20,
) -> Dict[str, Any]:
    payload = _load_registry(registry_path)
    runs_raw = payload.get("runs")
    runs = runs_raw if isinstance(runs_raw, list) else []
    runs = sorted(runs, key=lambda item: str(item.get("timestamp_utc") or ""), reverse=True)

    unique_symbols = set()
    unique_timeframes = set()
    run_history: List[Dict[str, Any]] = []
    oos_values: List[float] = []
    leaderboard_rows: List[Dict[str, Any]] = []

    for run in runs:
        if not isinstance(run, dict):
            continue
        trade_symbols = run.get("trade_symbols")
        if isinstance(trade_symbols, list):
            for symbol in trade_symbols:
                text = str(symbol).strip()
                if text:
                    unique_symbols.add(text)

        timeframes = run.get("timeframes")
        tf_values = []
        if isinstance(timeframes, list):
            for item in timeframes:
                if isinstance(item, dict):
                    tf = str(item.get("timeframe", "")).strip()
                    if tf:
                        unique_timeframes.add(tf)
                        tf_values.append(tf)
                else:
                    tf = str(item).strip()
                    if tf:
                        unique_timeframes.add(tf)
                        tf_values.append(tf)

        oos_ret = _safe_float(run.get("oos_avg_total_return_pct"))
        avg_ret = _safe_float(run.get("avg_total_return_pct"))
        bh_ret = _safe_float(run.get("bh_return_pct"))
        random_ret = _safe_float(run.get("random_entry_return_pct"))
        alpha_vs_bh = None
        if oos_ret is not None and bh_ret is not None:
            alpha_vs_bh = round(oos_ret - bh_ret, 4)
        if oos_ret is not None:
            oos_values.append(oos_ret)

        history_item = {
            "run_id": run.get("run_id"),
            "timestamp_utc": run.get("timestamp_utc"),
            "search_mode": run.get("search_mode"),
            "best_timeframe": run.get("best_timeframe"),
            "best_data_days": run.get("best_data_days"),
            "oos_avg_total_return_pct": oos_ret,
            "avg_total_return_pct": avg_ret,
            "bh_return_pct": bh_ret,
            "random_entry_return_pct": random_ret,
            "alpha_vs_bh": alpha_vs_bh,
            "trade_symbols": _normalize_str_list(trade_symbols or []),
            "timeframes": _normalize_str_list(tf_values),
            "report_file": run.get("report_file"),
        }
        run_history.append(history_item)
        leaderboard_rows.append(history_item)

    leaderboard_rows.sort(
        key=lambda row: -(_safe_float(row.get("oos_avg_total_return_pct")) or float("-inf"))
    )

    combo_stability = _build_combo_stability(artifacts_dir, runs, top_n=top_n)

    tested_pairs_count = _coverage_pairs_len(payload, "tested_pairs")
    untested_pairs_count = _coverage_pairs_len(payload, "untested_pairs")
    total_pairs = tested_pairs_count + untested_pairs_count
    coverage_pct = 0.0 if total_pairs == 0 else round((tested_pairs_count / total_pairs) * 100.0, 2)

    mean_oos = None if not oos_values else sum(oos_values) / len(oos_values)

    bh_values = [_safe_float(r.get("bh_return_pct")) for r in run_history]
    bh_values = [v for v in bh_values if v is not None]
    mean_bh = None if not bh_values else sum(bh_values) / len(bh_values)

    random_values = [_safe_float(r.get("random_entry_return_pct")) for r in run_history]
    random_values = [v for v in random_values if v is not None]
    mean_random = None if not random_values else sum(random_values) / len(random_values)

    alpha_values = [_safe_float(r.get("alpha_vs_bh")) for r in run_history]
    alpha_values = [v for v in alpha_values if v is not None]
    mean_alpha = None if not alpha_values else sum(alpha_values) / len(alpha_values)

    latest_run = run_history[0] if run_history else {}
    summary = {
        "total_runs": len(run_history),
        "unique_symbols": len(unique_symbols),
        "unique_timeframes": len(unique_timeframes),
        "avg_oos_return_pct": mean_oos,
        "avg_bh_return_pct": mean_bh,
        "avg_random_return_pct": mean_random,
        "avg_alpha_vs_bh": mean_alpha,
        "latest_run_id": latest_run.get("run_id"),
        "latest_run_time_utc": latest_run.get("timestamp_utc"),
        "coverage_tested_pairs": tested_pairs_count,
        "coverage_untested_pairs": untested_pairs_count,
        "coverage_pct": coverage_pct,
    }

    return {
        "schema_version": CROSS_RUN_PAYLOAD_SCHEMA_VERSION,
        "generated_utc": _now_iso(),
        "registry_path": str(registry_path),
        "summary": summary,
        "run_history": run_history,
        "global_leaderboard": leaderboard_rows[:max(1, int(top_n))],
        "combo_stability": combo_stability,
        "per_regime_leaderboard": _build_per_regime_leaderboard(combo_stability),
        "regime_summary": _build_regime_summary(combo_stability),
    }


def _normalize_summary_payload(summary_payload: Any) -> Dict[str, Any]:
    normalized = dict(_CROSS_RUN_SUMMARY_DEFAULTS)
    if not isinstance(summary_payload, dict):
        return normalized
    for key in normalized:
        if key in summary_payload:
            normalized[key] = summary_payload.get(key)
    return normalized


def normalize_cross_run_payload(
    payload: Any,
    top_n: int = 20,
) -> Dict[str, Any]:
    """Normalize legacy/incomplete payloads to the stable v1 contract."""
    try:
        top_n_i = max(1, int(top_n))
    except Exception:
        top_n_i = 20

    normalized: Dict[str, Any] = {
        "schema_version": CROSS_RUN_PAYLOAD_SCHEMA_VERSION,
        "generated_utc": _now_iso(),
        "registry_path": "",
        "summary": dict(_CROSS_RUN_SUMMARY_DEFAULTS),
        "run_history": [],
        "global_leaderboard": [],
        "combo_stability": [],
        "per_regime_leaderboard": {},
        "regime_summary": [],
    }
    if not isinstance(payload, dict):
        return normalized

    schema_version = str(payload.get("schema_version") or "").strip()
    if schema_version and schema_version != CROSS_RUN_PAYLOAD_SCHEMA_VERSION:
        normalized["source_schema_version"] = schema_version

    generated_utc = str(payload.get("generated_utc") or "").strip()
    if generated_utc:
        normalized["generated_utc"] = generated_utc

    registry_path = str(payload.get("registry_path") or "").strip()
    if registry_path:
        normalized["registry_path"] = registry_path

    normalized["summary"] = _normalize_summary_payload(payload.get("summary"))

    run_history = payload.get("run_history")
    if isinstance(run_history, list):
        normalized["run_history"] = run_history

    leaderboard = payload.get("global_leaderboard")
    if isinstance(leaderboard, list):
        normalized["global_leaderboard"] = leaderboard[:top_n_i]

    combo_stability = payload.get("combo_stability")
    if isinstance(combo_stability, list):
        normalized["combo_stability"] = combo_stability

    per_regime_leaderboard = payload.get("per_regime_leaderboard")
    if isinstance(per_regime_leaderboard, dict):
        normalized["per_regime_leaderboard"] = per_regime_leaderboard

    regime_summary = payload.get("regime_summary")
    if isinstance(regime_summary, list):
        normalized["regime_summary"] = regime_summary

    return normalized


def load_cross_run_payload(
    payload_path: Path,
    top_n: int = 20,
) -> Dict[str, Any]:
    if not payload_path.exists():
        raise CrossRunPayloadValidationError(
            code="payload_file_missing",
            message=f"cross-run payload not found: {payload_path}",
        )
    try:
        raw_payload = json.loads(payload_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CrossRunPayloadValidationError(
            code="invalid_json",
            message=f"invalid cross-run payload JSON: {payload_path}",
        ) from exc
    return validate_cross_run_payload(
        normalize_cross_run_payload(raw_payload, top_n=top_n),
        require_v1=True,
    )


def validate_cross_run_payload(
    payload: Any,
    require_v1: bool = True,
) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise CrossRunPayloadValidationError("payload_not_object", "cross-run payload must be object")

    schema_version = str(payload.get("schema_version") or "").strip()
    if require_v1 and schema_version != CROSS_RUN_PAYLOAD_SCHEMA_VERSION:
        raise CrossRunPayloadValidationError(
            "schema_version_mismatch",
            f"schema_version mismatch: expected={CROSS_RUN_PAYLOAD_SCHEMA_VERSION}, got={schema_version or '<empty>'}",
        )

    missing_top_level = sorted(k for k in _CROSS_RUN_REQUIRED_TOP_LEVEL_KEYS if k not in payload)
    if missing_top_level:
        raise CrossRunPayloadValidationError(
            "missing_top_level_keys",
            f"missing top-level keys: {', '.join(missing_top_level)}",
        )

    summary = payload.get("summary")
    if not isinstance(summary, dict):
        raise CrossRunPayloadValidationError("summary_not_object", "summary must be object")
    missing_summary = sorted(k for k in _CROSS_RUN_REQUIRED_SUMMARY_KEYS if k not in summary)
    if missing_summary:
        raise CrossRunPayloadValidationError(
            "missing_summary_keys",
            f"missing summary keys: {', '.join(missing_summary)}",
        )

    if not isinstance(payload.get("run_history"), list):
        raise CrossRunPayloadValidationError("run_history_not_list", "run_history must be list")
    if not isinstance(payload.get("global_leaderboard"), list):
        raise CrossRunPayloadValidationError("global_leaderboard_not_list", "global_leaderboard must be list")
    if not isinstance(payload.get("combo_stability"), list):
        raise CrossRunPayloadValidationError("combo_stability_not_list", "combo_stability must be list")
    if not isinstance(payload.get("per_regime_leaderboard"), dict):
        raise CrossRunPayloadValidationError("per_regime_leaderboard_not_object", "per_regime_leaderboard must be object")
    if not isinstance(payload.get("regime_summary"), list):
        raise CrossRunPayloadValidationError("regime_summary_not_list", "regime_summary must be list")

    return payload


def render_cross_run_html(payload: Dict[str, Any]) -> str:
    summary = payload.get("summary", {})
    leaderboard = payload.get("global_leaderboard", [])
    combo_rows = payload.get("combo_stability", [])
    history = payload.get("run_history", [])
    per_regime_lb = payload.get("per_regime_leaderboard", {})
    regime_summary = payload.get("regime_summary", [])

    def _fmt(value: Any) -> str:
        # Pass through raw HTML (e.g. SVG sparklines)
        if isinstance(value, str) and value.startswith("<svg "):
            return value
        num = _safe_float(value)
        if num is None:
            return "" if value is None else str(value)
        return f"{num:.4f}"

    def _table(headers: List[str], rows: List[List[Any]]) -> str:
        head = "".join(f"<th>{h}</th>" for h in headers)
        body_rows = []
        for row in rows:
            body_rows.append("<tr>" + "".join(f"<td>{_fmt(cell)}</td>" for cell in row) + "</tr>")
        body = "".join(body_rows) if body_rows else f"<tr><td colspan='{len(headers)}'>No data</td></tr>"
        return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"

    lb_rows = [
        [
            row.get("run_id"),
            row.get("timestamp_utc"),
            row.get("search_mode"),
            row.get("best_timeframe"),
            row.get("oos_avg_total_return_pct"),
            row.get("avg_total_return_pct"),
            row.get("bh_return_pct"),
            row.get("random_entry_return_pct"),
            row.get("alpha_vs_bh"),
        ]
        for row in leaderboard
    ]
    # Trend direction unicode arrows
    _trend_arrow = {"improving": "\u2197\ufe0f", "declining": "\u2198\ufe0f", "flat": "\u2192"}
    combo_table_rows = [
        [
            row.get("combo_key"),
            row.get("appearances"),
            row.get("avg_oos_return_pct"),
            row.get("best_oos_return_pct"),
            row.get("avg_oos_drawdown_pct"),
            _trend_arrow.get(row.get("trend_direction", "flat"), "?"),
            row.get("consistency_pct"),
            row.get("return_std"),
            row.get("sparkline") or "",
            ", ".join(row.get("run_ids") or []),
        ]
        for row in combo_rows
    ]
    history_rows = [
        [
            row.get("run_id"),
            row.get("timestamp_utc"),
            row.get("search_mode"),
            ",".join(row.get("timeframes") or []),
            ",".join(row.get("trade_symbols") or []),
            row.get("oos_avg_total_return_pct"),
        ]
        for row in history
    ]

    # AWF-026: Regime summary table
    regime_summary_rows = [
        [
            row.get("regime_name"),
            row.get("combo_count"),
            row.get("avg_return_pct"),
            row.get("avg_drawdown_pct"),
        ]
        for row in regime_summary
    ]

    # AWF-026: Per-regime leaderboard sections
    per_regime_html_parts: List[str] = []
    for regime_name in sorted(per_regime_lb):
        entries = per_regime_lb[regime_name]
        regime_rows = [
            [
                e.get("combo_key"),
                e.get("appearances"),
                e.get("avg_oos_return_pct"),
                e.get("best_oos_return_pct"),
                e.get("avg_oos_drawdown_pct"),
                _trend_arrow.get(e.get("trend_direction", "flat"), "\u2192"),
            ]
            for e in entries
        ]
        regime_table = _table(
            ["combo_key", "appearances", "avg_oos_return_pct", "best_oos_return_pct", "avg_oos_drawdown_pct", "trend"],
            regime_rows,
        )
        per_regime_html_parts.append(f"<h3>{regime_name}</h3>\n  {regime_table}")
    per_regime_html = "\n  ".join(per_regime_html_parts) if per_regime_html_parts else "<p>No regime data available.</p>"

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>AUTOWFO Cross-Run Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 20px; color: #1f2d3d; }}
    h1, h2 {{ margin: 14px 0 8px; }}
    .kpi {{ display: inline-block; margin: 6px 14px 6px 0; padding: 8px 12px; border: 1px solid #d9dde6; border-radius: 8px; background: #f7f9fc; }}
    .kpi b {{ display: block; color: #4a5a6a; font-size: 12px; margin-bottom: 3px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
    th, td {{ border: 1px solid #d9dde6; padding: 6px 8px; font-size: 12px; text-align: left; }}
    th {{ background: #f2f5f9; }}
    .muted {{ color: #6f7f90; font-size: 12px; }}
  </style>
</head>
<body>
  <h1>AUTOWFO Cross-Run Report</h1>
  <div class="muted">Generated UTC: {payload.get("generated_utc")}</div>
  <div>
    <div class="kpi"><b>Total Runs</b>{_fmt(summary.get("total_runs"))}</div>
    <div class="kpi"><b>Unique Symbols</b>{_fmt(summary.get("unique_symbols"))}</div>
    <div class="kpi"><b>Unique Timeframes</b>{_fmt(summary.get("unique_timeframes"))}</div>
    <div class="kpi"><b>Avg OOS Return %</b>{_fmt(summary.get("avg_oos_return_pct"))}</div>
    <div class="kpi"><b>Avg BH Return %</b>{_fmt(summary.get("avg_bh_return_pct"))}</div>
    <div class="kpi"><b>Avg Random Return %</b>{_fmt(summary.get("avg_random_return_pct"))}</div>
    <div class="kpi"><b>Avg Alpha vs BH</b>{_fmt(summary.get("avg_alpha_vs_bh"))}</div>
    <div class="kpi"><b>Coverage %</b>{_fmt(summary.get("coverage_pct"))}</div>
  </div>
  <h2>Global Leaderboard</h2>
  {_table(["run_id", "timestamp_utc", "search_mode", "best_timeframe", "oos_avg_total_return_pct", "avg_total_return_pct", "bh_return_pct", "random_entry_return_pct", "alpha_vs_bh"], lb_rows)}
  <h2>Combo Stability Trends</h2>
  {_table(["combo_key", "appearances", "avg_oos_return_pct", "best_oos_return_pct", "avg_oos_drawdown_pct", "trend", "consistency_%", "return_std", "sparkline", "run_ids"], combo_table_rows)}
  <h2>Regime Summary</h2>
  {_table(["regime_name", "combo_count", "avg_return_pct", "avg_drawdown_pct"], regime_summary_rows)}
  <h2>Per-Regime Leaderboard</h2>
  {per_regime_html}
  <h2>Run History</h2>
  {_table(["run_id", "timestamp_utc", "search_mode", "timeframes", "trade_symbols", "oos_avg_total_return_pct"], history_rows)}
</body>
</html>"""


def write_cross_run_reports(
    artifacts_dir: Path,
    registry_path: Path,
    out_html_path: Path,
    out_json_path: Optional[Path] = None,
    top_n: int = 20,
) -> Dict[str, Any]:
    payload = validate_cross_run_payload(
        normalize_cross_run_payload(
            build_cross_run_payload(
                artifacts_dir=artifacts_dir,
                registry_path=registry_path,
                top_n=top_n,
            ),
            top_n=top_n,
        ),
        require_v1=True,
    )
    out_html_path.parent.mkdir(parents=True, exist_ok=True)
    out_html_path.write_text(render_cross_run_html(payload), encoding="utf-8")
    if out_json_path is not None:
        out_json_path.parent.mkdir(parents=True, exist_ok=True)
        out_json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload

