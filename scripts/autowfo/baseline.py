"""Baseline run helpers for AUTOWFO E2E and trigger decision."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

import numpy as np
import pandas as pd


TOP10_RE = re.compile(r"^param_sweep_top10_(\d{8}_\d{6})\.csv$")
RUN_REPORT_SUFFIX_RE = re.compile(r"_\d{8}_\d{6}\.html$")


def _list_artifact_files(artifacts_dir: Path) -> Set[str]:
    if not artifacts_dir.exists():
        return set()
    return {p.name for p in artifacts_dir.iterdir() if p.is_file()}


def _extract_new_run_id(before_files: Set[str], after_files: Set[str]) -> Optional[str]:
    new_files = sorted(after_files - before_files)
    run_ids: List[str] = []
    for name in new_files:
        match = TOP10_RE.match(name)
        if match:
            run_ids.append(match.group(1))
    if run_ids:
        return sorted(run_ids)[-1]
    return None


def _resolve_run_id_from_latest(artifacts_dir: Path) -> Optional[str]:
    candidates: List[Tuple[float, str]] = []
    for path in artifacts_dir.glob("param_sweep_top10_*.csv"):
        match = TOP10_RE.match(path.name)
        if not match:
            continue
        candidates.append((path.stat().st_mtime, match.group(1)))
    if not candidates:
        return None
    return sorted(candidates)[-1][1]


def _copy_if_exists(src: Path, dst: Path) -> bool:
    if not src.exists() or not src.is_file():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(src.read_bytes())
    return True


def _copy_run_outputs(artifacts_dir: Path, target_dir: Path, run_id: str) -> Dict[str, List[str]]:
    copied = {"static": [], "run_specific": [], "reports": []}

    static_names = [
        "param_sweep_combo_summary.csv",
        "param_sweep_symbol_summary.csv",
        "leaderboard.csv",
        "results.db",
        "run_status.json",
        "run_status.html",
    ]
    for name in static_names:
        if _copy_if_exists(artifacts_dir / name, target_dir / name):
            copied["static"].append(name)

    run_specific_names = [
        f"param_sweep_combo_summary_{run_id}.csv",
        f"param_sweep_symbol_summary_{run_id}.csv",
        f"param_sweep_top10_{run_id}.csv",
    ]
    for name in run_specific_names:
        if _copy_if_exists(artifacts_dir / name, target_dir / name):
            copied["run_specific"].append(name)

    for path in artifacts_dir.glob(f"btc_regime_*_{run_id}.html"):
        if _copy_if_exists(path, target_dir / path.name):
            copied["reports"].append(path.name)
    for path in artifacts_dir.glob("btc_regime_*.html"):
        if RUN_REPORT_SUFFIX_RE.search(path.name):
            continue
        if _copy_if_exists(path, target_dir / path.name):
            copied["reports"].append(path.name)

    return copied


def _safe_float(value: object) -> float:
    try:
        val = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return val


def _quality_snapshot(top10_df: pd.DataFrame) -> Dict[str, object]:
    if top10_df.empty:
        return {
            "rows": 0,
            "avg_oos_return_pct": np.nan,
            "avg_oos_drawdown_pct": np.nan,
            "avg_oos_min_total_trades": np.nan,
            "avg_oos_segments": np.nan,
        }
    return {
        "rows": int(len(top10_df)),
        "avg_oos_return_pct": _safe_float(top10_df["oos_avg_total_return_pct"].mean())
        if "oos_avg_total_return_pct" in top10_df.columns
        else np.nan,
        "avg_oos_drawdown_pct": _safe_float(top10_df["oos_avg_max_drawdown_pct"].mean())
        if "oos_avg_max_drawdown_pct" in top10_df.columns
        else np.nan,
        "avg_oos_min_total_trades": _safe_float(top10_df["oos_min_total_trades"].mean())
        if "oos_min_total_trades" in top10_df.columns
        else np.nan,
        "avg_oos_segments": _safe_float(top10_df["oos_segments"].mean())
        if "oos_segments" in top10_df.columns
        else np.nan,
    }


def _comparison_summary(combo_snapshot: Dict[str, object], refine_snapshot: Dict[str, object]) -> Dict[str, object]:
    return {
        "combo_rows": combo_snapshot.get("rows"),
        "refine_rows": refine_snapshot.get("rows"),
        "delta_avg_oos_return_pct": _safe_float(refine_snapshot.get("avg_oos_return_pct"))
        - _safe_float(combo_snapshot.get("avg_oos_return_pct")),
        "delta_avg_oos_drawdown_pct": _safe_float(refine_snapshot.get("avg_oos_drawdown_pct"))
        - _safe_float(combo_snapshot.get("avg_oos_drawdown_pct")),
        "delta_avg_oos_min_total_trades": _safe_float(refine_snapshot.get("avg_oos_min_total_trades"))
        - _safe_float(combo_snapshot.get("avg_oos_min_total_trades")),
        "delta_avg_oos_segments": _safe_float(refine_snapshot.get("avg_oos_segments"))
        - _safe_float(combo_snapshot.get("avg_oos_segments")),
    }


def _ratio(mask: pd.Series) -> float:
    if mask.empty:
        return 0.0
    return float(mask.mean())


def _trigger_decision(top10_df: pd.DataFrame) -> Dict[str, object]:
    if top10_df.empty:
        return {
            "rows": 0,
            "thresholds": {
                "D1_ratio_min": 0.40,
                "D2_ratio_min": 0.30,
                "D3_ratio_min": 0.40,
            },
            "ratios": {"D1": 0.0, "D2": 0.0, "D3": 0.0},
            "rules": {"D1": False, "D2": False, "D3": False},
            "trigger_awf_002b_006": False,
        }

    d1_ratio = _ratio(_to_numeric(top10_df.get("oos_avg_max_drawdown_pct")) <= -20.0)
    d2_ratio = _ratio(_to_numeric(top10_df.get("oos_segments")) < 2.0)
    d3_ratio = _ratio(_to_numeric(top10_df.get("oos_min_total_trades")) < 30.0)

    rules = {
        "D1": d1_ratio >= 0.40,
        "D2": d2_ratio >= 0.30,
        "D3": d3_ratio >= 0.40,
    }
    return {
        "rows": int(len(top10_df)),
        "thresholds": {
            "D1_ratio_min": 0.40,
            "D2_ratio_min": 0.30,
            "D3_ratio_min": 0.40,
        },
        "ratios": {"D1": d1_ratio, "D2": d2_ratio, "D3": d3_ratio},
        "rules": rules,
        "trigger_awf_002b_006": sum(1 for ok in rules.values() if ok) >= 2,
    }


def _to_numeric(series: object) -> pd.Series:
    if isinstance(series, pd.Series):
        return pd.to_numeric(series, errors="coerce")
    return pd.Series(dtype="float64")


def _read_top10_for_run(target_dir: Path, run_id: str) -> pd.DataFrame:
    top_path = target_dir / f"param_sweep_top10_{run_id}.csv"
    if not top_path.exists():
        return pd.DataFrame()
    return pd.read_csv(top_path, low_memory=False)


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _read_run_status(target_dir: Path) -> Dict[str, object]:
    path = target_dir / "run_status.json"
    if not path.exists() or not path.is_file():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload
