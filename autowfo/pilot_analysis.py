"""Pilot/subgroup analysis contract helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Sequence, Tuple

import numpy as np
import pandas as pd


SCHEMA_VERSION = "1.0.0"

DEFAULT_IDENTITY_FIELDS: Tuple[str, ...] = (
    "timeframe",
    "data_days",
    "indicator_list",
    "regime_name",
    "vol_mode",
    "filter_name",
    "vol_lookback",
    "mom_lookback",
    "trade_mom_lookback",
    "tp_stop",
    "sl_stop",
    "max_hold",
)

DEFAULT_COMBO_METRIC_FIELDS: Tuple[str, ...] = (
    "oos_avg_total_return_pct",
    "oos_sharpe_like",
    "oos_avg_total_trades",
)

DEFAULT_SYMBOL_METRIC_FIELDS: Tuple[str, ...] = (
    "oos_avg_total_return_pct",
    "oos_avg_total_trades",
    "oos_positive_segment_ratio",
    "oos_segments",
)


def _indicator_tokens(value: Any) -> Tuple[str, ...]:
    if value is None:
        return tuple()
    return tuple(token for token in str(value).split(",") if token)


def _safe_json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (float, np.floating)):
        val = float(value)
        return None if np.isnan(val) else val
    if isinstance(value, (int, np.integer)):
        return int(value)
    return value


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (float, np.floating)):
        val = float(value)
        return None if np.isnan(val) else val
    if isinstance(value, (int, np.integer)):
        return float(value)
    try:
        val = float(value)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(val) else val


def _identity_key_from_row(row: pd.Series, identity_fields: Sequence[str]) -> Tuple[Any, ...]:
    return tuple(_safe_json_value(row.get(field)) for field in identity_fields)


def _identity_payload_from_key(identity_fields: Sequence[str], key: Sequence[Any]) -> Dict[str, Any]:
    return {field: value for field, value in zip(identity_fields, key)}


def _dedupe_identity_frame(df: pd.DataFrame, identity_fields: Sequence[str]) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=list(identity_fields))
    seen = set()
    keep_rows = []
    for idx, row in df.iterrows():
        key = _identity_key_from_row(row, identity_fields)
        if key in seen:
            continue
        seen.add(key)
        keep_rows.append(idx)
    if not keep_rows:
        return pd.DataFrame(columns=df.columns)
    return df.loc[keep_rows].copy()


def _summary_stats(values: pd.Series) -> Dict[str, Any]:
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    if numeric.empty:
        return {
            "min": None,
            "mean": None,
        }
    return {
        "min": _safe_json_value(float(numeric.min())),
        "mean": _safe_json_value(float(numeric.mean())),
    }


def _symbol_support_summary(symbol_df: pd.DataFrame) -> Dict[str, Any]:
    if symbol_df is None or symbol_df.empty:
        return {
            "symbol_count": 0,
            "nonnegative_count": 0,
            "positive_count": 0,
            "all_symbols_nonnegative": False,
            "all_symbols_positive": False,
            "return_stats": {"min": None, "mean": None},
            "trade_stats": {"min": None, "mean": None},
        }

    returns = pd.to_numeric(symbol_df.get("oos_avg_total_return_pct"), errors="coerce")
    trades = pd.to_numeric(symbol_df.get("oos_avg_total_trades"), errors="coerce")
    valid_returns = returns.dropna()

    nonnegative_count = int((valid_returns >= 0).sum())
    positive_count = int((valid_returns > 0).sum())
    symbol_count = int(len(symbol_df))

    return {
        "symbol_count": symbol_count,
        "nonnegative_count": nonnegative_count,
        "positive_count": positive_count,
        "all_symbols_nonnegative": bool(symbol_count > 0 and nonnegative_count == symbol_count),
        "all_symbols_positive": bool(symbol_count > 0 and positive_count == symbol_count),
        "return_stats": _summary_stats(returns),
        "trade_stats": _summary_stats(trades),
    }


def _group_symbol_support(symbol_df: pd.DataFrame, identity_fields: Sequence[str]) -> Dict[Tuple[Any, ...], Dict[str, Any]]:
    if symbol_df is None or symbol_df.empty:
        return {}
    grouped: Dict[Tuple[Any, ...], list[int]] = {}
    for idx, row in symbol_df.iterrows():
        key = _identity_key_from_row(row, identity_fields)
        grouped.setdefault(key, []).append(idx)
    result: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    for key, indices in grouped.items():
        result[key] = _symbol_support_summary(symbol_df.loc[indices])
    return result


def _signature_float(value: Any, digits: int = 12) -> Any:
    safe = _safe_float(value)
    if safe is None:
        return None
    return round(float(safe), digits)


def _canonical_redundancy_signature(row: Mapping[str, Any]) -> Tuple[Any, ...]:
    support_main = row.get("symbol_support_main") or {}
    support_sens = row.get("symbol_support_sens") or {}
    return (
        row.get("timeframe"),
        row.get("data_days"),
        row.get("regime_name"),
        row.get("vol_mode"),
        row.get("tp_stop"),
        row.get("sl_stop"),
        row.get("max_hold"),
        _signature_float(row.get("min_return")),
        _signature_float(row.get("min_trades")),
        _signature_float(row.get("min_sharpe")),
        support_main.get("symbol_count"),
        support_main.get("nonnegative_count"),
        support_main.get("positive_count"),
        _signature_float((support_main.get("return_stats") or {}).get("min")),
        _signature_float((support_main.get("return_stats") or {}).get("mean")),
        _signature_float((support_main.get("trade_stats") or {}).get("min")),
        _signature_float((support_main.get("trade_stats") or {}).get("mean")),
        support_sens.get("symbol_count"),
        support_sens.get("nonnegative_count"),
        support_sens.get("positive_count"),
        _signature_float((support_sens.get("return_stats") or {}).get("min")),
        _signature_float((support_sens.get("return_stats") or {}).get("mean")),
        _signature_float((support_sens.get("trade_stats") or {}).get("min")),
        _signature_float((support_sens.get("trade_stats") or {}).get("mean")),
    )


def _annotate_canonical_gate_passed(rows: Sequence[Dict[str, Any]]) -> Tuple[list[Dict[str, Any]], list[Dict[str, Any]]]:
    canonical_rows: list[Dict[str, Any]] = []
    redundant_rows: list[Dict[str, Any]] = []
    ordered_rows = sorted(
        rows,
        key=lambda row: (
            len(_indicator_tokens(row.get("indicator_list"))),
            str(row.get("indicator_list") or ""),
        ),
    )
    for row in ordered_rows:
        indicator_set = frozenset(_indicator_tokens(row.get("indicator_list")))
        signature = _canonical_redundancy_signature(row)
        row["is_canonical_family"] = True
        row["redundant_of"] = None
        row["canonical_indicator_list"] = row.get("indicator_list")
        row["canonical_reason"] = "unique_gate_passed_family"
        matched = None
        for base_row in canonical_rows:
            base_set = frozenset(_indicator_tokens(base_row.get("indicator_list")))
            if not base_set.issubset(indicator_set):
                continue
            if _canonical_redundancy_signature(base_row) != signature:
                continue
            matched = base_row
            break
        if matched is not None:
            row["is_canonical_family"] = False
            row["redundant_of"] = _identity_key_from_row(pd.Series(matched), DEFAULT_IDENTITY_FIELDS)
            row["canonical_indicator_list"] = matched.get("indicator_list")
            row["canonical_reason"] = "evidence_equivalent_superset"
            redundant_rows.append(row)
            continue
        canonical_rows.append(row)
    return canonical_rows, redundant_rows


def _resolve_run_root(path_or_run_id: str | Path, artifacts_dir: str | Path | None = None) -> Path:
    path = Path(path_or_run_id)
    if path.exists():
        return path.resolve()
    if artifacts_dir is None:
        raise FileNotFoundError(f"run dir not found: {path_or_run_id}")
    run_root = Path(artifacts_dir).resolve() / "runs" / str(path_or_run_id)
    if not run_root.exists():
        raise FileNotFoundError(f"run dir not found: {run_root}")
    return run_root


def load_run_analysis_inputs(path_or_run_id: str | Path, *, artifacts_dir: str | Path | None = None) -> Dict[str, Any]:
    run_root = _resolve_run_root(path_or_run_id, artifacts_dir=artifacts_dir)
    results_dir = run_root / "results"
    metadata_dir = run_root / "metadata"

    combo_path = results_dir / "param_sweep_combo_summary.csv"
    symbol_oos_path = results_dir / "param_sweep_symbol_oos_summary.csv"
    if not combo_path.exists():
        raise FileNotFoundError(f"combo summary not found: {combo_path}")
    if not symbol_oos_path.exists():
        raise FileNotFoundError(f"symbol oos summary not found: {symbol_oos_path}")

    run_id = run_root.name
    metadata_path = metadata_dir / f"run_metadata_{run_id}.json"
    if not metadata_path.exists():
        metadata_path = metadata_dir / "run_metadata.json"

    metadata: Dict[str, Any] = {}
    if metadata_path.exists():
        payload = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
        if isinstance(payload, dict):
            metadata = payload

    return {
        "run_root": run_root,
        "run_id": run_id,
        "combo_df": pd.read_csv(combo_path, low_memory=False),
        "symbol_oos_df": pd.read_csv(symbol_oos_path, low_memory=False),
        "metadata": metadata,
    }


def compare_pilot_runs(
    main_run: Mapping[str, Any],
    sensitivity_run: Mapping[str, Any],
    *,
    identity_fields: Iterable[str] = DEFAULT_IDENTITY_FIELDS,
    combo_metric_fields: Iterable[str] = DEFAULT_COMBO_METRIC_FIELDS,
    require_all_symbols_nonnegative: bool = True,
    min_combo_return: float = 0.0,
    min_combo_trades: float = 0.0,
    top_n: int = 20,
) -> Dict[str, Any]:
    identity_fields_tuple = tuple(identity_fields)
    combo_metric_fields_tuple = tuple(combo_metric_fields)

    main_combo = _dedupe_identity_frame(pd.DataFrame(main_run.get("combo_df")), identity_fields_tuple)
    sensitivity_combo = _dedupe_identity_frame(pd.DataFrame(sensitivity_run.get("combo_df")), identity_fields_tuple)

    main_metric_cols = [field for field in combo_metric_fields_tuple if field in main_combo.columns]
    sensitivity_metric_cols = [field for field in combo_metric_fields_tuple if field in sensitivity_combo.columns]

    merged = main_combo[list(identity_fields_tuple) + main_metric_cols].merge(
        sensitivity_combo[list(identity_fields_tuple) + sensitivity_metric_cols],
        on=list(identity_fields_tuple),
        suffixes=("_main", "_sens"),
        how="inner",
    )

    main_symbol_support = _group_symbol_support(pd.DataFrame(main_run.get("symbol_oos_df")), identity_fields_tuple)
    sensitivity_symbol_support = _group_symbol_support(pd.DataFrame(sensitivity_run.get("symbol_oos_df")), identity_fields_tuple)

    compared_rows = []
    for _, row in merged.iterrows():
        identity_key = _identity_key_from_row(row, identity_fields_tuple)
        payload = _identity_payload_from_key(identity_fields_tuple, identity_key)

        metric_values: Dict[str, Any] = {}
        for field in combo_metric_fields_tuple:
            metric_values[f"{field}_main"] = _safe_json_value(row.get(f"{field}_main"))
            metric_values[f"{field}_sens"] = _safe_json_value(row.get(f"{field}_sens"))

        main_return = _safe_float(row.get("oos_avg_total_return_pct_main"))
        sens_return = _safe_float(row.get("oos_avg_total_return_pct_sens"))
        main_trades = _safe_float(row.get("oos_avg_total_trades_main"))
        sens_trades = _safe_float(row.get("oos_avg_total_trades_sens"))
        main_sharpe = _safe_float(row.get("oos_sharpe_like_main"))
        sens_sharpe = _safe_float(row.get("oos_sharpe_like_sens"))

        support_main = main_symbol_support.get(identity_key)
        support_sens = sensitivity_symbol_support.get(identity_key)
        has_symbol_support_main = support_main is not None
        has_symbol_support_sens = support_sens is not None
        has_symbol_support_both = has_symbol_support_main and has_symbol_support_sens
        if support_main is None:
            support_main = _symbol_support_summary(pd.DataFrame())
        if support_sens is None:
            support_sens = _symbol_support_summary(pd.DataFrame())

        both_positive = (main_return is not None and main_return > 0) and (sens_return is not None and sens_return > 0)
        min_return = None if main_return is None or sens_return is None else min(main_return, sens_return)
        min_trades = None if main_trades is None or sens_trades is None else min(main_trades, sens_trades)
        min_sharpe = None if main_sharpe is None or sens_sharpe is None else min(main_sharpe, sens_sharpe)

        passes_symbol_support = (
            has_symbol_support_both
            and support_main.get("all_symbols_nonnegative", False)
            and support_sens.get("all_symbols_nonnegative", False)
            if require_all_symbols_nonnegative
            else has_symbol_support_both
        )
        passes_return_gate = min_return is not None and min_return > float(min_combo_return)
        passes_trade_gate = min_trades is not None and min_trades >= float(min_combo_trades)
        passes_overall_gate = bool(both_positive and passes_symbol_support and passes_return_gate and passes_trade_gate)

        payload.update(metric_values)
        payload.update(
            {
                "both_positive": bool(both_positive),
                "min_return": _safe_json_value(min_return),
                "min_trades": _safe_json_value(min_trades),
                "min_sharpe": _safe_json_value(min_sharpe),
                "has_symbol_support_main": bool(has_symbol_support_main),
                "has_symbol_support_sens": bool(has_symbol_support_sens),
                "has_symbol_support_both": bool(has_symbol_support_both),
                "symbol_support_main": support_main,
                "symbol_support_sens": support_sens,
                "passes_symbol_support_gate": bool(passes_symbol_support),
                "passes_return_gate": bool(passes_return_gate),
                "passes_trade_gate": bool(passes_trade_gate),
                "passes_overall_gate": bool(passes_overall_gate),
            }
        )
        compared_rows.append(payload)

    compared_rows_sorted = sorted(
        compared_rows,
        key=lambda row: (
            1 if row.get("passes_overall_gate") else 0,
            1 if row.get("has_symbol_support_both") else 0,
            1 if row.get("both_positive") else 0,
            float(row.get("min_return") or float("-inf")),
            float(row.get("min_sharpe") or float("-inf")),
            float(row.get("min_trades") or float("-inf")),
        ),
        reverse=True,
    )

    stable_positive = [
        row for row in compared_rows_sorted if row.get("both_positive") and row.get("has_symbol_support_both")
    ]
    gate_passed = [row for row in compared_rows_sorted if row.get("passes_overall_gate")]
    canonical_gate_passed, redundant_gate_passed = _annotate_canonical_gate_passed(gate_passed)

    return {
        "schema_version": SCHEMA_VERSION,
        "identity_fields": list(identity_fields_tuple),
        "combo_metric_fields": list(combo_metric_fields_tuple),
        "thresholds": {
            "require_all_symbols_nonnegative": bool(require_all_symbols_nonnegative),
            "min_combo_return": float(min_combo_return),
            "min_combo_trades": float(min_combo_trades),
            "top_n": int(max(0, int(top_n))),
        },
        "main_run": {
            "run_id": main_run.get("run_id"),
            "run_root": str(main_run.get("run_root")),
            "timeframe_diagnostics": list((main_run.get("metadata") or {}).get("timeframe_diagnostics", [])),
        },
        "sensitivity_run": {
            "run_id": sensitivity_run.get("run_id"),
            "run_root": str(sensitivity_run.get("run_root")),
            "timeframe_diagnostics": list((sensitivity_run.get("metadata") or {}).get("timeframe_diagnostics", [])),
        },
        "summary": {
            "main_combo_rows": int(len(main_combo)),
            "sensitivity_combo_rows": int(len(sensitivity_combo)),
            "compared_combo_rows": int(len(compared_rows)),
            "symbol_supported_rows": int(sum(1 for row in compared_rows if row.get("has_symbol_support_both"))),
            "stable_positive_rows": int(len(stable_positive)),
            "gate_passed_rows": int(len(gate_passed)),
            "canonical_gate_passed_rows": int(len(canonical_gate_passed)),
            "redundant_gate_passed_rows": int(len(redundant_gate_passed)),
        },
        "top_gate_passed": gate_passed[: max(0, int(top_n))],
        "canonical_gate_passed": canonical_gate_passed[: max(0, int(top_n))],
        "redundant_gate_passed": redundant_gate_passed[: max(0, int(top_n))],
        "top_stable_positive": stable_positive[: max(0, int(top_n))],
    }
