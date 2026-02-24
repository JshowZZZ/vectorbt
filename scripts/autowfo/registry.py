"""Run registry and coverage map helpers for AUTOWFO."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterable, List, Mapping

import pandas as pd


def _load_registry(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {"updated_utc": None, "runs": [], "coverage": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"updated_utc": None, "runs": [], "coverage": {}}
    if not isinstance(payload, dict):
        return {"updated_utc": None, "runs": [], "coverage": {}}
    payload.setdefault("runs", [])
    payload.setdefault("coverage", {})
    return payload


def _safe_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _normalize_str_set(values: Iterable[Any]) -> List[str]:
    output = sorted({str(v) for v in values if v is not None and str(v).strip()})
    return output


def _build_run_entry(
    run_metadata: Mapping[str, Any],
    best_row: Mapping[str, Any],
) -> Dict[str, Any]:
    return {
        "run_id": run_metadata.get("run_id"),
        "timestamp_utc": run_metadata.get("timestamp_utc"),
        "search_mode": run_metadata.get("search_mode"),
        "config_sha256": run_metadata.get("config_sha256"),
        "data_fingerprint": run_metadata.get("data_fingerprint"),
        "timeframes": _safe_list(run_metadata.get("timeframes")),
        "trade_symbols": _safe_list(run_metadata.get("trade_symbols")),
        "best_timeframe": best_row.get("timeframe"),
        "best_data_days": best_row.get("data_days"),
        "avg_total_return_pct": best_row.get("avg_total_return_pct"),
        "oos_avg_total_return_pct": best_row.get("oos_avg_total_return_pct"),
        "bh_return_pct": best_row.get("bh_return_pct"),
        "random_entry_return_pct": best_row.get("random_entry_return_pct"),
        "report_file": best_row.get("report_file"),
    }


def _build_coverage_map(
    per_symbol_df: pd.DataFrame,
    run_entries: List[Mapping[str, Any]],
    *,
    target_timeframes: List[str] | None = None,
    target_symbols: List[str] | None = None,
) -> Dict[str, Any]:
    """Build coverage map from tested data and run entries.

    Parameters
    ----------
    target_timeframes : list[str] | None
        When provided, these timeframes are always included in the
        coverage dimensions (even if no run has ever used them).
    target_symbols : list[str] | None
        When provided, these symbols are always included in the
        coverage dimensions.
    """
    if per_symbol_df.empty:
        tested_pairs: List[Dict[str, str]] = []
    else:
        subset = per_symbol_df.reindex(columns=["timeframe", "symbol"]).dropna()
        tested_pairs = [
            {"timeframe": str(row["timeframe"]), "symbol": str(row["symbol"])}
            for _, row in subset.drop_duplicates().sort_values(["timeframe", "symbol"]).iterrows()
        ]

    timeframe_values = set()
    symbol_values = set()
    for entry in run_entries:
        for timeframe_cfg in _safe_list(entry.get("timeframes")):
            if isinstance(timeframe_cfg, dict):
                timeframe_values.add(timeframe_cfg.get("timeframe"))
            else:
                timeframe_values.add(timeframe_cfg)
        symbol_values.update(_safe_list(entry.get("trade_symbols")))
    for pair in tested_pairs:
        timeframe_values.add(pair["timeframe"])
        symbol_values.add(pair["symbol"])

    # Inject external target dimensions so gaps are visible for
    # timeframes/symbols that have never appeared in any run.
    if target_timeframes:
        timeframe_values.update(target_timeframes)
    if target_symbols:
        symbol_values.update(target_symbols)

    timeframe_list = _normalize_str_set(timeframe_values)
    symbol_list = _normalize_str_set(symbol_values)
    tested_pair_set = {(pair["timeframe"], pair["symbol"]) for pair in tested_pairs}
    untested_pairs = []
    for timeframe in timeframe_list:
        for symbol in symbol_list:
            if (timeframe, symbol) in tested_pair_set:
                continue
            untested_pairs.append({"timeframe": timeframe, "symbol": symbol})

    return {
        "timeframes": timeframe_list,
        "symbols": symbol_list,
        "tested_pairs": tested_pairs,
        "untested_pairs": untested_pairs,
    }


def _update_run_registry(
    registry_path: str,
    run_metadata: Mapping[str, Any],
    best_row: Mapping[str, Any],
    per_symbol_df: pd.DataFrame,
    updated_utc: str,
) -> Dict[str, Any]:
    registry = _load_registry(registry_path)
    run_entry = _build_run_entry(run_metadata, best_row)
    run_id = run_entry.get("run_id")

    runs = [entry for entry in registry.get("runs", []) if entry.get("run_id") != run_id]
    runs.append(run_entry)
    runs = sorted(
        runs,
        key=lambda entry: str(entry.get("timestamp_utc") or ""),
        reverse=True,
    )
    coverage = _build_coverage_map(per_symbol_df, runs)

    payload = {
        "updated_utc": updated_utc,
        "runs": runs,
        "coverage": coverage,
    }
    with open(registry_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return payload
