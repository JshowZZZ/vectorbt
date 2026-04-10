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

DEFAULT_TRADE_GATE_POLICY = "flat"
DEFAULT_TRADE_GATE_REFERENCE_DAYS = 180
DEFAULT_TRADE_GATE_MIN_RATIO = 0.75
DEFAULT_CLUE_SCORE_WEIGHTS: Dict[str, float] = {
    "gate_passed_rows": 20.0,
    "stable_positive_rows": 8.0,
    "symbol_supported_ratio": 2.0,
    "trade_supported_ratio": 1.0,
    "single_stable_positive_rows": 15.0,
    "single_gate_passed_rows": 25.0,
}


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


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        val = float(value)
        if np.isnan(val):
            return None
        return int(val)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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


def _sorted_unique_values(values: Iterable[Any]) -> list[Any]:
    normalized = [_safe_json_value(value) for value in values]
    seen = []
    for value in normalized:
        if value in seen:
            continue
        seen.append(value)
    return sorted(seen, key=lambda value: (value is None, str(value)))


def _effective_trade_gate_threshold(
    *,
    min_combo_trades: float,
    trade_gate_policy: str,
    data_days: Any = None,
    trade_gate_reference_days: int = DEFAULT_TRADE_GATE_REFERENCE_DAYS,
    trade_gate_min_ratio: float = DEFAULT_TRADE_GATE_MIN_RATIO,
) -> float:
    base_threshold = max(0.0, float(min_combo_trades))
    policy = str(trade_gate_policy or DEFAULT_TRADE_GATE_POLICY).strip().lower()
    if policy != "window_aware":
        return base_threshold

    reference_days = max(1, int(trade_gate_reference_days))
    floor_ratio = min(1.0, max(0.0, float(trade_gate_min_ratio)))
    requested_days = _safe_int(data_days)
    if requested_days is None or requested_days <= 0:
        return base_threshold
    scaled_ratio = min(float(requested_days) / float(reference_days), 1.0)
    effective_ratio = max(floor_ratio, scaled_ratio)
    return base_threshold * effective_ratio


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


def _build_protocol_summary(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {"row_count": 0, "field_values": {}}
    fields = (
        "indicator_list",
        "regime_name",
        "vol_mode",
        "mom_lookback",
        "trade_mom_lookback",
        "tp_stop",
        "sl_stop",
        "max_hold",
    )
    field_values = {
        field: _sorted_unique_values(row.get(field) for row in rows)
        for field in fields
    }
    return {
        "row_count": int(len(rows)),
        "field_values": field_values,
    }


def _sort_indicator_values(values: Iterable[str]) -> list[str]:
    seen: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.append(text)
    return sorted(seen)


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


def load_analysis_report(path: str | Path) -> Dict[str, Any]:
    report_path = Path(path).resolve()
    payload = json.loads(report_path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("analysis report must decode to an object")
    return payload


def _resolve_base_config_path(config_path: str | Path | None, cwd: str | Path | None = None) -> Path | None:
    if not config_path:
        return None
    path = Path(config_path)
    if path.is_absolute():
        return path if path.exists() else None
    base_dir = Path(cwd or ".").resolve()
    candidate = (base_dir / path).resolve()
    return candidate if candidate.exists() else None


def _extract_analysis_context(analysis_payload: Mapping[str, Any]) -> Dict[str, Any]:
    main_run = analysis_payload.get("main_run") or {}
    diagnostics = list(main_run.get("timeframe_diagnostics") or [])
    first_diag = diagnostics[0] if diagnostics and isinstance(diagnostics[0], dict) else {}
    return {
        "timeframe": first_diag.get("timeframe"),
        "data_days": _safe_int(first_diag.get("data_days") or first_diag.get("requested_data_days")),
        "realized_shared_days": _safe_int(first_diag.get("realized_shared_days")),
    }


def _match_promotion_policy_entry(
    analysis_context: Mapping[str, Any],
    promotion_policy: Mapping[str, Any],
) -> Tuple[str | None, Dict[str, Any] | None]:
    timeframe = analysis_context.get("timeframe")
    data_days = _safe_int(analysis_context.get("data_days"))
    if not isinstance(promotion_policy, Mapping):
        return None, None
    for policy_name, raw_entry in promotion_policy.items():
        if not isinstance(raw_entry, Mapping):
            continue
        policy_timeframe = raw_entry.get("timeframe")
        policy_days = _safe_int(raw_entry.get("data_days"))
        if timeframe == policy_timeframe and data_days == policy_days:
            return str(policy_name), dict(raw_entry)
    return None, None


def evaluate_promotion_verdict(
    analysis_payload: Mapping[str, Any],
    promotion_policy: Mapping[str, Any],
) -> Dict[str, Any]:
    analysis_context = _extract_analysis_context(analysis_payload)
    policy_name, policy_entry = _match_promotion_policy_entry(analysis_context, promotion_policy)
    summary = dict(analysis_payload.get("summary") or {})

    stable_positive_rows = int(summary.get("stable_positive_rows", 0) or 0)
    gate_passed_rows = int(summary.get("gate_passed_rows", 0) or 0)

    verdict = "hold"
    reason = "policy_unmapped"
    if policy_entry is not None:
        policy_kind = str(policy_entry.get("policy_kind") or "").strip().lower()
        if policy_kind == "rejected":
            verdict = "no_go"
            reason = str(policy_entry.get("reason") or "rejected_lane")
        elif gate_passed_rows > 0:
            verdict = "promote" if policy_kind == "promotive" else "hold"
            reason = f"{policy_name}_passed"
        elif stable_positive_rows > 0:
            verdict = "hold"
            reason = f"{policy_name}_stable_but_below_gate"
        else:
            verdict = "no_go"
            reason = f"{policy_name}_no_stable_positive"

    return {
        "analysis_context": analysis_context,
        "matched_policy_name": policy_name,
        "matched_policy": policy_entry,
        "summary": {
            "stable_positive_rows": stable_positive_rows,
            "gate_passed_rows": gate_passed_rows,
        },
        "verdict": verdict,
        "reason": reason,
    }


def build_replay_config_from_analysis(
    analysis_payload: Mapping[str, Any],
    main_run: Mapping[str, Any],
    *,
    cwd: str | Path | None = None,
) -> Dict[str, Any]:
    protocol_summary = (
        (analysis_payload.get("protocol_summary") or {}).get("canonical_gate_passed") or {}
    )
    field_values = protocol_summary.get("field_values") or {}
    if not field_values:
        raise ValueError("analysis report has no canonical gate-passed protocol summary")

    indicator_lists = list(field_values.get("indicator_list") or [])
    if len(indicator_lists) != 1:
        raise ValueError("replay export requires exactly one canonical indicator_list")
    indicator_subset = [token for token in str(indicator_lists[0]).split(",") if token]
    if not indicator_subset:
        raise ValueError("canonical indicator_list is empty")

    base_config: Dict[str, Any] = {}
    metadata = dict(main_run.get("metadata") or {})
    base_config_path = _resolve_base_config_path(metadata.get("config_path"), cwd=cwd)
    if base_config_path is not None:
        payload = json.loads(base_config_path.read_text(encoding="utf-8-sig"))
        if isinstance(payload, dict):
            base_config = payload

    export_config = dict(base_config)
    export_config["search_mode"] = "combo"
    export_config["combo_sizes"] = [len(indicator_subset)]
    export_config["indicator_subset"] = indicator_subset
    export_config["trade_symbols"] = list(metadata.get("trade_symbols") or export_config.get("trade_symbols") or [])
    export_config["timeframes"] = list(metadata.get("timeframes") or export_config.get("timeframes") or [])
    export_config["wf_train_days"] = int(metadata.get("wf_train_days", export_config.get("wf_train_days", 120)) or 120)
    export_config["wf_test_days"] = int(metadata.get("wf_test_days", export_config.get("wf_test_days", 30)) or 30)
    export_config["wf_step_days"] = int(metadata.get("wf_step_days", export_config.get("wf_step_days", 30)) or 30)
    export_config["wf_valid_days"] = int(metadata.get("wf_valid_days", export_config.get("wf_valid_days", 0)) or 0)
    export_config["risk_mode"] = str(export_config.get("risk_mode") or metadata.get("risk_mode") or "fixed_pct")
    export_config["regime_name_filter"] = list(field_values.get("regime_name") or [])
    export_config["max_holds"] = list(field_values.get("max_hold") or [])
    export_config["top_n_refine"] = 0
    export_config["pilot_fixed_indicator_params"] = bool(
        export_config.get("pilot_fixed_indicator_params", True)
    )
    export_config["pilot_single_trend_mom"] = bool(
        export_config.get("pilot_single_trend_mom", True)
    )

    risk_mode = str(export_config.get("risk_mode") or "fixed_pct").strip().lower()
    if risk_mode == "atr_multiple":
        export_config["tp_atr_multipliers"] = list(field_values.get("tp_stop") or [])
        export_config["sl_atr_multipliers"] = list(field_values.get("sl_stop") or [])
    else:
        export_config["tp_stops"] = list(field_values.get("tp_stop") or [])
        export_config["sl_stops"] = list(field_values.get("sl_stop") or [])

    return export_config


def _build_compared_rows(
    main_run: Mapping[str, Any],
    sensitivity_run: Mapping[str, Any],
    *,
    identity_fields: Sequence[str],
    combo_metric_fields: Sequence[str],
    require_all_symbols_nonnegative: bool,
    min_combo_return: float,
    min_combo_trades: float,
    trade_gate_policy: str,
    trade_gate_reference_days: int,
    trade_gate_min_ratio: float,
) -> Tuple[pd.DataFrame, pd.DataFrame, list[Dict[str, Any]], list[Dict[str, Any]], list[Dict[str, Any]], list[Dict[str, Any]], list[Dict[str, Any]]]:
    main_combo = _dedupe_identity_frame(pd.DataFrame(main_run.get("combo_df")), identity_fields)
    sensitivity_combo = _dedupe_identity_frame(pd.DataFrame(sensitivity_run.get("combo_df")), identity_fields)

    main_metric_cols = [field for field in combo_metric_fields if field in main_combo.columns]
    sensitivity_metric_cols = [field for field in combo_metric_fields if field in sensitivity_combo.columns]

    merged = main_combo[list(identity_fields) + main_metric_cols].merge(
        sensitivity_combo[list(identity_fields) + sensitivity_metric_cols],
        on=list(identity_fields),
        suffixes=("_main", "_sens"),
        how="inner",
    )

    main_symbol_support = _group_symbol_support(pd.DataFrame(main_run.get("symbol_oos_df")), identity_fields)
    sensitivity_symbol_support = _group_symbol_support(pd.DataFrame(sensitivity_run.get("symbol_oos_df")), identity_fields)

    compared_rows: list[Dict[str, Any]] = []
    for _, row in merged.iterrows():
        identity_key = _identity_key_from_row(row, identity_fields)
        payload = _identity_payload_from_key(identity_fields, identity_key)

        metric_values: Dict[str, Any] = {}
        for field in combo_metric_fields:
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
        effective_trade_floor = _effective_trade_gate_threshold(
            min_combo_trades=min_combo_trades,
            trade_gate_policy=trade_gate_policy,
            data_days=row.get("data_days"),
            trade_gate_reference_days=trade_gate_reference_days,
            trade_gate_min_ratio=trade_gate_min_ratio,
        )

        passes_symbol_support = (
            has_symbol_support_both
            and support_main.get("all_symbols_nonnegative", False)
            and support_sens.get("all_symbols_nonnegative", False)
            if require_all_symbols_nonnegative
            else has_symbol_support_both
        )
        passes_return_gate = min_return is not None and min_return > float(min_combo_return)
        passes_trade_gate = min_trades is not None and min_trades >= float(effective_trade_floor)
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
                "trade_gate_policy": str(trade_gate_policy or DEFAULT_TRADE_GATE_POLICY),
                "effective_trade_floor": _safe_json_value(effective_trade_floor),
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
    return (
        main_combo,
        sensitivity_combo,
        compared_rows_sorted,
        stable_positive,
        gate_passed,
        canonical_gate_passed,
        redundant_gate_passed,
    )


def build_indicator_clue_map(
    main_run: Mapping[str, Any],
    sensitivity_run: Mapping[str, Any],
    *,
    identity_fields: Iterable[str] = DEFAULT_IDENTITY_FIELDS,
    combo_metric_fields: Iterable[str] = DEFAULT_COMBO_METRIC_FIELDS,
    require_all_symbols_nonnegative: bool = True,
    min_combo_return: float = 0.0,
    min_combo_trades: float = 0.0,
    trade_gate_policy: str = DEFAULT_TRADE_GATE_POLICY,
    trade_gate_reference_days: int = DEFAULT_TRADE_GATE_REFERENCE_DAYS,
    trade_gate_min_ratio: float = DEFAULT_TRADE_GATE_MIN_RATIO,
    top_k: int = 10,
    score_weights: Mapping[str, float] | None = None,
) -> Dict[str, Any]:
    identity_fields_tuple = tuple(identity_fields)
    combo_metric_fields_tuple = tuple(combo_metric_fields)
    weights = dict(DEFAULT_CLUE_SCORE_WEIGHTS)
    if score_weights:
        for key, value in score_weights.items():
            if key in weights:
                weights[key] = float(value)

    _, _, compared_rows_sorted, stable_positive, gate_passed, _, _ = _build_compared_rows(
        main_run=main_run,
        sensitivity_run=sensitivity_run,
        identity_fields=identity_fields_tuple,
        combo_metric_fields=combo_metric_fields_tuple,
        require_all_symbols_nonnegative=require_all_symbols_nonnegative,
        min_combo_return=float(min_combo_return),
        min_combo_trades=float(min_combo_trades),
        trade_gate_policy=str(trade_gate_policy or DEFAULT_TRADE_GATE_POLICY),
        trade_gate_reference_days=int(trade_gate_reference_days),
        trade_gate_min_ratio=float(trade_gate_min_ratio),
    )

    per_indicator: Dict[str, Dict[str, Any]] = {}

    def _indicator_bucket(name: str) -> Dict[str, Any]:
        bucket = per_indicator.get(name)
        if bucket is None:
            bucket = {
                "indicator": name,
                "compared_rows": 0,
                "symbol_supported_rows": 0,
                "trade_supported_rows": 0,
                "stable_positive_rows": 0,
                "gate_passed_rows": 0,
                "single_rows": 0,
                "single_symbol_supported_rows": 0,
                "single_trade_supported_rows": 0,
                "single_stable_positive_rows": 0,
                "single_gate_passed_rows": 0,
                "pair_rows": 0,
                "pair_symbol_supported_rows": 0,
                "pair_trade_supported_rows": 0,
                "pair_stable_positive_rows": 0,
                "pair_gate_passed_rows": 0,
                "partner_indicators": set(),
                "min_return_values": [],
                "min_trades_values": [],
                "min_sharpe_values": [],
            }
            per_indicator[name] = bucket
        return bucket

    for row in compared_rows_sorted:
        indicators = tuple(sorted(set(_indicator_tokens(row.get("indicator_list")))))
        if not indicators:
            continue
        combo_size = len(indicators)
        symbol_supported = bool(row.get("has_symbol_support_both"))
        trade_supported = bool(row.get("passes_trade_gate"))
        stable = bool(row.get("both_positive") and symbol_supported)
        gate = bool(row.get("passes_overall_gate"))
        min_return = _safe_float(row.get("min_return"))
        min_trades = _safe_float(row.get("min_trades"))
        min_sharpe = _safe_float(row.get("min_sharpe"))

        for indicator in indicators:
            bucket = _indicator_bucket(indicator)
            bucket["compared_rows"] += 1
            if symbol_supported:
                bucket["symbol_supported_rows"] += 1
            if trade_supported:
                bucket["trade_supported_rows"] += 1
            if stable:
                bucket["stable_positive_rows"] += 1
            if gate:
                bucket["gate_passed_rows"] += 1
            if combo_size == 1:
                bucket["single_rows"] += 1
                if symbol_supported:
                    bucket["single_symbol_supported_rows"] += 1
                if trade_supported:
                    bucket["single_trade_supported_rows"] += 1
                if stable:
                    bucket["single_stable_positive_rows"] += 1
                if gate:
                    bucket["single_gate_passed_rows"] += 1
            elif combo_size == 2:
                bucket["pair_rows"] += 1
                if symbol_supported:
                    bucket["pair_symbol_supported_rows"] += 1
                if trade_supported:
                    bucket["pair_trade_supported_rows"] += 1
                if stable:
                    bucket["pair_stable_positive_rows"] += 1
                if gate:
                    bucket["pair_gate_passed_rows"] += 1
                for partner in indicators:
                    if partner != indicator:
                        bucket["partner_indicators"].add(partner)
            if min_return is not None:
                bucket["min_return_values"].append(min_return)
            if min_trades is not None:
                bucket["min_trades_values"].append(min_trades)
            if min_sharpe is not None:
                bucket["min_sharpe_values"].append(min_sharpe)

    indicator_rows: list[Dict[str, Any]] = []
    for indicator, bucket in per_indicator.items():
        compared_count = max(1, int(bucket["compared_rows"]))
        symbol_supported_ratio = float(bucket["symbol_supported_rows"]) / float(compared_count)
        trade_supported_ratio = float(bucket["trade_supported_rows"]) / float(compared_count)
        avg_min_return = float(np.mean(bucket["min_return_values"])) if bucket["min_return_values"] else None
        avg_min_trades = float(np.mean(bucket["min_trades_values"])) if bucket["min_trades_values"] else None
        avg_min_sharpe = float(np.mean(bucket["min_sharpe_values"])) if bucket["min_sharpe_values"] else None
        clue_score = (
            weights["gate_passed_rows"] * float(bucket["gate_passed_rows"])
            + weights["stable_positive_rows"] * float(bucket["stable_positive_rows"])
            + weights["symbol_supported_ratio"] * symbol_supported_ratio
            + weights["trade_supported_ratio"] * trade_supported_ratio
            + weights["single_stable_positive_rows"] * float(bucket["single_stable_positive_rows"])
            + weights["single_gate_passed_rows"] * float(bucket["single_gate_passed_rows"])
        )
        indicator_rows.append(
            {
                "indicator": indicator,
                "clue_score": _safe_json_value(clue_score),
                "compared_rows": int(bucket["compared_rows"]),
                "symbol_supported_rows": int(bucket["symbol_supported_rows"]),
                "trade_supported_rows": int(bucket["trade_supported_rows"]),
                "symbol_supported_ratio": _safe_json_value(symbol_supported_ratio),
                "trade_supported_ratio": _safe_json_value(trade_supported_ratio),
                "stable_positive_rows": int(bucket["stable_positive_rows"]),
                "gate_passed_rows": int(bucket["gate_passed_rows"]),
                "single_rows": int(bucket["single_rows"]),
                "single_symbol_supported_rows": int(bucket["single_symbol_supported_rows"]),
                "single_trade_supported_rows": int(bucket["single_trade_supported_rows"]),
                "single_stable_positive_rows": int(bucket["single_stable_positive_rows"]),
                "single_gate_passed_rows": int(bucket["single_gate_passed_rows"]),
                "pair_rows": int(bucket["pair_rows"]),
                "pair_symbol_supported_rows": int(bucket["pair_symbol_supported_rows"]),
                "pair_trade_supported_rows": int(bucket["pair_trade_supported_rows"]),
                "pair_stable_positive_rows": int(bucket["pair_stable_positive_rows"]),
                "pair_gate_passed_rows": int(bucket["pair_gate_passed_rows"]),
                "partner_count": int(len(bucket["partner_indicators"])),
                "partner_indicators": _sort_indicator_values(bucket["partner_indicators"]),
                "avg_min_return": _safe_json_value(avg_min_return),
                "avg_min_trades": _safe_json_value(avg_min_trades),
                "avg_min_sharpe": _safe_json_value(avg_min_sharpe),
            }
        )

    indicator_rows_sorted = sorted(
        indicator_rows,
        key=lambda row: (
            float(row.get("clue_score") or 0.0),
            int(row.get("gate_passed_rows") or 0),
            int(row.get("stable_positive_rows") or 0),
            int(row.get("single_stable_positive_rows") or 0),
            int(row.get("partner_count") or 0),
            float(row.get("avg_min_return") or float("-inf")),
            float(row.get("avg_min_sharpe") or float("-inf")),
            str(row.get("indicator") or ""),
        ),
        reverse=True,
    )
    selected = [row["indicator"] for row in indicator_rows_sorted[: max(0, int(top_k))]]

    return {
        "schema_version": SCHEMA_VERSION,
        "identity_fields": list(identity_fields_tuple),
        "combo_metric_fields": list(combo_metric_fields_tuple),
        "thresholds": {
            "require_all_symbols_nonnegative": bool(require_all_symbols_nonnegative),
            "min_combo_return": float(min_combo_return),
            "min_combo_trades": float(min_combo_trades),
            "trade_gate_policy": str(trade_gate_policy or DEFAULT_TRADE_GATE_POLICY),
            "trade_gate_reference_days": int(trade_gate_reference_days),
            "trade_gate_min_ratio": float(trade_gate_min_ratio),
            "top_k": int(max(0, int(top_k))),
        },
        "score_weights": {key: float(value) for key, value in weights.items()},
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
            "compared_combo_rows": int(len(compared_rows_sorted)),
            "stable_positive_rows": int(len(stable_positive)),
            "gate_passed_rows": int(len(gate_passed)),
            "indicator_count": int(len(indicator_rows_sorted)),
            "selected_indicator_count": int(len(selected)),
        },
        "selected_top_indicators": selected,
        "indicator_rows": indicator_rows_sorted,
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
    trade_gate_policy: str = DEFAULT_TRADE_GATE_POLICY,
    trade_gate_reference_days: int = DEFAULT_TRADE_GATE_REFERENCE_DAYS,
    trade_gate_min_ratio: float = DEFAULT_TRADE_GATE_MIN_RATIO,
    top_n: int = 20,
) -> Dict[str, Any]:
    identity_fields_tuple = tuple(identity_fields)
    combo_metric_fields_tuple = tuple(combo_metric_fields)
    main_combo, sensitivity_combo, compared_rows_sorted, stable_positive, gate_passed, canonical_gate_passed, redundant_gate_passed = _build_compared_rows(
        main_run=main_run,
        sensitivity_run=sensitivity_run,
        identity_fields=identity_fields_tuple,
        combo_metric_fields=combo_metric_fields_tuple,
        require_all_symbols_nonnegative=require_all_symbols_nonnegative,
        min_combo_return=float(min_combo_return),
        min_combo_trades=float(min_combo_trades),
        trade_gate_policy=str(trade_gate_policy or DEFAULT_TRADE_GATE_POLICY),
        trade_gate_reference_days=int(trade_gate_reference_days),
        trade_gate_min_ratio=float(trade_gate_min_ratio),
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "identity_fields": list(identity_fields_tuple),
        "combo_metric_fields": list(combo_metric_fields_tuple),
        "thresholds": {
            "require_all_symbols_nonnegative": bool(require_all_symbols_nonnegative),
            "min_combo_return": float(min_combo_return),
            "min_combo_trades": float(min_combo_trades),
            "trade_gate_policy": str(trade_gate_policy or DEFAULT_TRADE_GATE_POLICY),
            "trade_gate_reference_days": int(trade_gate_reference_days),
            "trade_gate_min_ratio": float(trade_gate_min_ratio),
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
            "compared_combo_rows": int(len(compared_rows_sorted)),
            "symbol_supported_rows": int(sum(1 for row in compared_rows_sorted if row.get("has_symbol_support_both"))),
            "stable_positive_rows": int(len(stable_positive)),
            "gate_passed_rows": int(len(gate_passed)),
            "canonical_gate_passed_rows": int(len(canonical_gate_passed)),
            "redundant_gate_passed_rows": int(len(redundant_gate_passed)),
        },
        "protocol_summary": {
            "canonical_gate_passed": _build_protocol_summary(canonical_gate_passed),
            "redundant_gate_passed": _build_protocol_summary(redundant_gate_passed),
        },
        "top_gate_passed": gate_passed[: max(0, int(top_n))],
        "canonical_gate_passed": canonical_gate_passed[: max(0, int(top_n))],
        "redundant_gate_passed": redundant_gate_passed[: max(0, int(top_n))],
        "top_stable_positive": stable_positive[: max(0, int(top_n))],
    }
