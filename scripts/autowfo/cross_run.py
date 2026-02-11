"""Cross-run aggregation helpers for AWF-016/AWF-017d."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe_float(value: Any) -> Optional[float]:
    try:
        num = float(value)
    except (TypeError, ValueError):
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
    root_candidate = artifacts_dir / f"param_sweep_top10_{run_id}.csv"
    if root_candidate.exists():
        return root_candidate

    patterns = [
        f"runs/*/refine/param_sweep_top10_{run_id}.csv",
        f"runs/*/combo/param_sweep_top10_{run_id}.csv",
        f"runs/*/param_sweep_top10_{run_id}.csv",
    ]
    for pattern in patterns:
        matches = sorted(artifacts_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        if matches:
            return matches[0]
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


def _build_combo_stability(artifacts_dir: Path, runs: List[Dict[str, Any]], top_n: int) -> List[Dict[str, Any]]:
    combo_map: Dict[str, Dict[str, Any]] = {}
    for run in runs:
        run_id = str(run.get("run_id", "")).strip()
        if not run_id:
            continue
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
                }
                combo_map[key] = entry
            entry["appearances"] += 1
            entry["run_ids"].append(run_id)
            if oos_ret is not None:
                entry["oos_returns"].append(oos_ret)
            if oos_dd is not None:
                entry["oos_drawdowns"].append(oos_dd)

    rows: List[Dict[str, Any]] = []
    for key, entry in combo_map.items():
        rets: List[float] = entry["oos_returns"]
        dds: List[float] = entry["oos_drawdowns"]
        avg_ret = None if not rets else sum(rets) / len(rets)
        avg_dd = None if not dds else sum(dds) / len(dds)
        best_ret = None if not rets else max(rets)
        rows.append(
            {
                "combo_key": key,
                "appearances": int(entry["appearances"]),
                "avg_oos_return_pct": avg_ret,
                "best_oos_return_pct": best_ret,
                "avg_oos_drawdown_pct": avg_dd,
                "run_ids": sorted(set(entry["run_ids"])),
            }
        )

    rows.sort(
        key=lambda item: (
            -int(item.get("appearances", 0)),
            -(_safe_float(item.get("avg_oos_return_pct")) or float("-inf")),
        )
    )
    return rows[:max(1, int(top_n))]


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
    latest_run = run_history[0] if run_history else {}
    summary = {
        "total_runs": len(run_history),
        "unique_symbols": len(unique_symbols),
        "unique_timeframes": len(unique_timeframes),
        "avg_oos_return_pct": mean_oos,
        "latest_run_id": latest_run.get("run_id"),
        "latest_run_time_utc": latest_run.get("timestamp_utc"),
        "coverage_tested_pairs": tested_pairs_count,
        "coverage_untested_pairs": untested_pairs_count,
        "coverage_pct": coverage_pct,
    }

    return {
        "generated_utc": _now_iso(),
        "registry_path": str(registry_path),
        "summary": summary,
        "run_history": run_history,
        "global_leaderboard": leaderboard_rows[:max(1, int(top_n))],
        "combo_stability": combo_stability,
    }


def render_cross_run_html(payload: Dict[str, Any]) -> str:
    summary = payload.get("summary", {})
    leaderboard = payload.get("global_leaderboard", [])
    combo_rows = payload.get("combo_stability", [])
    history = payload.get("run_history", [])

    def _fmt(value: Any) -> str:
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
        ]
        for row in leaderboard
    ]
    combo_table_rows = [
        [
            row.get("combo_key"),
            row.get("appearances"),
            row.get("avg_oos_return_pct"),
            row.get("best_oos_return_pct"),
            row.get("avg_oos_drawdown_pct"),
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
    <div class="kpi"><b>Coverage %</b>{_fmt(summary.get("coverage_pct"))}</div>
  </div>
  <h2>Global Leaderboard</h2>
  {_table(["run_id", "timestamp_utc", "search_mode", "best_timeframe", "oos_avg_total_return_pct", "avg_total_return_pct"], lb_rows)}
  <h2>Combo Stability</h2>
  {_table(["combo_key", "appearances", "avg_oos_return_pct", "best_oos_return_pct", "avg_oos_drawdown_pct", "run_ids"], combo_table_rows)}
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
    payload = build_cross_run_payload(
        artifacts_dir=artifacts_dir,
        registry_path=registry_path,
        top_n=top_n,
    )
    out_html_path.parent.mkdir(parents=True, exist_ok=True)
    out_html_path.write_text(render_cross_run_html(payload), encoding="utf-8")
    if out_json_path is not None:
        out_json_path.parent.mkdir(parents=True, exist_ok=True)
        out_json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
