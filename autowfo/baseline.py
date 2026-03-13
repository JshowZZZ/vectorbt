"""Baseline run helpers for AUTOWFO E2E and trigger decision."""

from __future__ import annotations

import copy
import datetime as dt
from html import escape
import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

import numpy as np
import pandas as pd

from autowfo import ranking as autowfo_ranking
from autowfo import engine_helpers
from autowfo import engine_runtime
from autowfo import engine_search
from autowfo import engine_finalize


TOP10_RE = re.compile(r"^param_sweep_top10_(\d{8}_\d{6})\.csv$")
RUN_REPORT_SUFFIX_RE = re.compile(r"_\d{8}_\d{6}\.html$")
RANKING_MODE_COMPARISON_SCHEMA_VERSION = "1.0.0"

PAIR_IDENTITY_FIELDS = (
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

PAIR_METRIC_FIELDS = (
    "oos_avg_total_return_pct",
    "oos_sharpe_like",
    "oos_return_std",
    "oos_positive_segment_ratio",
    "oos_avg_max_drawdown_pct",
    "oos_min_total_trades",
    "oos_segments",
    "oos_low_trade_penalty",
)


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
        "run_registry.json",
        "results.db",
        "run_status.json",
        "run_status.html",
        "run_metadata.json",
    ]
    for name in static_names:
        if _copy_if_exists(artifacts_dir / name, target_dir / name):
            copied["static"].append(name)

    run_specific_names = [
        f"param_sweep_combo_summary_{run_id}.csv",
        f"param_sweep_symbol_summary_{run_id}.csv",
        f"param_sweep_top10_{run_id}.csv",
        f"run_metadata_{run_id}.json",
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


def _safe_int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _safe_json_value(value: object) -> object:
    if isinstance(value, (np.floating, float)):
        val = float(value)
        if np.isnan(val):
            return None
        return val
    if isinstance(value, (np.integer, int)) and not isinstance(value, bool):
        return int(value)
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, str):
        return value
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return value


def _safe_mean(df: pd.DataFrame, column: str) -> float:
    if column not in df.columns or df.empty:
        return float("nan")
    return _safe_float(df[column].mean())


def _safe_nunique(df: pd.DataFrame, column: str) -> float:
    if column not in df.columns or df.empty:
        return float("nan")
    series = df[column]
    series = series.astype("string").str.strip()
    series = series.replace("", pd.NA).dropna()
    if series.empty:
        return 0.0
    return float(series.nunique())


def _metric_delta(legacy_value: object, composite_value: object) -> float:
    legacy_f = _safe_float(legacy_value)
    composite_f = _safe_float(composite_value)
    if np.isnan(legacy_f) or np.isnan(composite_f):
        return float("nan")
    return composite_f - legacy_f


def _series_or_nan(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns or df.empty:
        return pd.Series(dtype="string")
    return df[column].astype("string").fillna("")


def _combo_signature(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series(dtype="string")
    parts = [
        _series_or_nan(df, "indicator_list"),
        _series_or_nan(df, "regime_name"),
        _series_or_nan(df, "vol_mode"),
    ]
    return parts[0] + "|" + parts[1] + "|" + parts[2]


def _axis_strategy_quality(top_df: pd.DataFrame) -> Dict[str, object]:
    return {
        "avg_oos_return_pct": _safe_json_value(_safe_mean(top_df, "oos_avg_total_return_pct")),
        "avg_oos_sharpe_like": _safe_json_value(_safe_mean(top_df, "oos_sharpe_like")),
        "avg_oos_positive_segment_ratio": _safe_json_value(
            _safe_mean(top_df, "oos_positive_segment_ratio")
        ),
        "avg_oos_drawdown_pct": _safe_json_value(_safe_mean(top_df, "oos_avg_max_drawdown_pct")),
    }


def _axis_sample_sufficiency(top_df: pd.DataFrame) -> Dict[str, object]:
    return {
        "avg_oos_min_total_trades": _safe_json_value(_safe_mean(top_df, "oos_min_total_trades")),
        "avg_oos_segments": _safe_json_value(_safe_mean(top_df, "oos_segments")),
        "avg_oos_low_trade_penalty": _safe_json_value(_safe_mean(top_df, "oos_low_trade_penalty")),
        "avg_oos_low_trade_segment_ratio": _safe_json_value(
            _safe_mean(top_df, "oos_low_trade_segment_ratio")
        ),
    }


def _axis_combo_scarcity(top_df: pd.DataFrame, candidate_df: pd.DataFrame) -> Dict[str, object]:
    rows = int(len(top_df))
    unique_indicator_list_count = _safe_nunique(top_df, "indicator_list")
    unique_regime_count = _safe_nunique(top_df, "regime_name")
    signature = _combo_signature(top_df)
    unique_combo_signature_count = float(signature.nunique()) if not signature.empty else 0.0
    max_combo_signature_share = float("nan")
    if not signature.empty:
        counts = signature.value_counts(normalize=True, dropna=False)
        if not counts.empty:
            max_combo_signature_share = _safe_float(counts.iloc[0])
    return {
        "candidate_pool_rows": int(len(candidate_df)),
        "top_rows": rows,
        "unique_indicator_list_count": _safe_json_value(unique_indicator_list_count),
        "unique_regime_count": _safe_json_value(unique_regime_count),
        "unique_combo_signature_count": _safe_json_value(unique_combo_signature_count),
        "unique_combo_signature_ratio": _safe_json_value(
            unique_combo_signature_count / rows if rows > 0 else float("nan")
        ),
        "max_combo_signature_share": _safe_json_value(max_combo_signature_share),
    }


def _axis_delta(legacy_axis: Dict[str, object], composite_axis: Dict[str, object]) -> Dict[str, object]:
    keys = sorted(set(legacy_axis.keys()) | set(composite_axis.keys()))
    return {
        key: _safe_json_value(_metric_delta(legacy_axis.get(key), composite_axis.get(key)))
        for key in keys
    }


def _row_payload(df: pd.DataFrame, row_id: int, columns: Iterable[str]) -> Dict[str, object]:
    if row_id < 0 or row_id >= len(df):
        return {}
    row = df.iloc[row_id]
    payload = {}
    for col in columns:
        payload[col] = _safe_json_value(row.get(col))
    return payload


def _ranked_rows_payload(
    top_df: pd.DataFrame,
    score_col: str,
    candidate_df: pd.DataFrame,
) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for rank, row_id in enumerate(top_df.index.tolist(), start=1):
        payload = {
            "rank": rank,
            "row_id": int(row_id),
            "score_col": score_col,
            "score": _safe_json_value(top_df.loc[row_id, score_col]) if score_col in top_df.columns else None,
        }
        payload.update(_row_payload(candidate_df, int(row_id), PAIR_IDENTITY_FIELDS + PAIR_METRIC_FIELDS))
        rows.append(payload)
    return rows


def _paired_rows_payload(
    candidate_df: pd.DataFrame,
    legacy_top: pd.DataFrame,
    composite_top: pd.DataFrame,
    legacy_score_col: str,
    composite_score_col: str,
) -> List[Dict[str, object]]:
    legacy_rank = {int(row_id): rank for rank, row_id in enumerate(legacy_top.index.tolist(), start=1)}
    composite_rank = {int(row_id): rank for rank, row_id in enumerate(composite_top.index.tolist(), start=1)}
    legacy_scores = {
        int(row_id): _safe_json_value(legacy_top.loc[row_id, legacy_score_col])
        if legacy_score_col in legacy_top.columns
        else None
        for row_id in legacy_top.index.tolist()
    }
    composite_scores = {
        int(row_id): _safe_json_value(composite_top.loc[row_id, composite_score_col])
        if composite_score_col in composite_top.columns
        else None
        for row_id in composite_top.index.tolist()
    }

    all_row_ids = sorted(set(legacy_rank.keys()) | set(composite_rank.keys()))
    all_row_ids.sort(
        key=lambda row_id: (
            min(legacy_rank.get(row_id, 10**9), composite_rank.get(row_id, 10**9)),
            legacy_rank.get(row_id, 10**9),
            composite_rank.get(row_id, 10**9),
            row_id,
        )
    )

    rows: List[Dict[str, object]] = []
    for row_id in all_row_ids:
        payload = {
            "row_id": int(row_id),
            "rank_legacy": legacy_rank.get(row_id),
            "rank_composite": composite_rank.get(row_id),
            "legacy_score_col": legacy_score_col,
            "legacy_score": legacy_scores.get(row_id),
            "composite_score_col": composite_score_col,
            "composite_score": composite_scores.get(row_id),
        }
        payload.update(_row_payload(candidate_df, row_id, PAIR_IDENTITY_FIELDS + PAIR_METRIC_FIELDS))
        rows.append(payload)
    return rows


def _build_ranking_mode_comparison_report(
    combo_df: pd.DataFrame,
    config_payload: Dict[str, object],
    run_label: str,
    run_id: str,
    generated_utc: Optional[str] = None,
    top_n: int = 10,
) -> Dict[str, object]:
    config = config_payload if isinstance(config_payload, dict) else {}
    timeframe_configs = config.get("timeframes")
    if not isinstance(timeframe_configs, list):
        timeframe_configs = []

    min_avg_daily_trades_target = _safe_float(
        config.get(
            "min_avg_daily_trades_target",
            engine_helpers.DEFAULT_CONFIG.get("min_avg_daily_trades_target", 5.0),
        )
    )
    if np.isnan(min_avg_daily_trades_target) or min_avg_daily_trades_target < 0:
        min_avg_daily_trades_target = 0.0
    min_oos_trades_target = _safe_int(
        config.get("min_oos_trades_target", engine_helpers.DEFAULT_CONFIG.get("min_oos_trades_target", 1)),
        1,
    )
    if min_oos_trades_target < 0:
        min_oos_trades_target = 0

    top_n_effective = _safe_int(config.get("ranking_compare_top_n", top_n), top_n)
    if top_n_effective <= 0:
        top_n_effective = top_n

    candidate_df = combo_df.copy()
    if timeframe_configs:
        candidate_df = engine_finalize._select_current_combo_df(candidate_df, timeframe_configs)

    def _apply_quality_filters(df: pd.DataFrame) -> pd.DataFrame:
        return engine_helpers._apply_quality_filters(
            df,
            min_avg_daily_trades_target=min_avg_daily_trades_target,
            min_oos_trades_target=min_oos_trades_target,
        )

    filtered_df, min_avg_daily_trades_filter = engine_helpers._fallback_activity_filter(
        combo_df_current=candidate_df,
        min_avg_daily_trades_target=min_avg_daily_trades_target,
        apply_quality_filters_fn=_apply_quality_filters,
    )
    filtered_df = filtered_df.reset_index(drop=True)

    base_ranking_config = autowfo_ranking._resolve_ranking_config(config.get("ranking"))
    legacy_ranking_config = copy.deepcopy(base_ranking_config)
    legacy_ranking_config["mode"] = "legacy"
    composite_ranking_config = copy.deepcopy(base_ranking_config)
    composite_ranking_config["mode"] = "composite"

    legacy_top, legacy_score_col = autowfo_ranking._top_by_score(
        filtered_df,
        top_n=top_n_effective,
        tie_break_avg_hold=True,
        ranking_config=legacy_ranking_config,
    )
    composite_top, composite_score_col = autowfo_ranking._top_by_score(
        filtered_df,
        top_n=top_n_effective,
        tie_break_avg_hold=True,
        ranking_config=composite_ranking_config,
    )

    legacy_ids = {int(v) for v in legacy_top.index.tolist()}
    composite_ids = {int(v) for v in composite_top.index.tolist()}
    overlap_ids = legacy_ids & composite_ids

    summary = {
        "candidate_rows": int(len(filtered_df)),
        "legacy_rows": int(len(legacy_top)),
        "composite_rows": int(len(composite_top)),
        "overlap_rows": int(len(overlap_ids)),
        "legacy_only_rows": int(len(legacy_ids - overlap_ids)),
        "composite_only_rows": int(len(composite_ids - overlap_ids)),
        "delta_avg_oos_return_pct": _safe_json_value(
            _metric_delta(
                _safe_mean(legacy_top, "oos_avg_total_return_pct"),
                _safe_mean(composite_top, "oos_avg_total_return_pct"),
            )
        ),
        "delta_avg_oos_sharpe_like": _safe_json_value(
            _metric_delta(
                _safe_mean(legacy_top, "oos_sharpe_like"),
                _safe_mean(composite_top, "oos_sharpe_like"),
            )
        ),
        "delta_avg_oos_min_total_trades": _safe_json_value(
            _metric_delta(
                _safe_mean(legacy_top, "oos_min_total_trades"),
                _safe_mean(composite_top, "oos_min_total_trades"),
            )
        ),
        "delta_avg_oos_low_trade_penalty": _safe_json_value(
            _metric_delta(
                _safe_mean(legacy_top, "oos_low_trade_penalty"),
                _safe_mean(composite_top, "oos_low_trade_penalty"),
            )
        ),
    }

    strategy_legacy = _axis_strategy_quality(legacy_top)
    strategy_composite = _axis_strategy_quality(composite_top)
    sample_legacy = _axis_sample_sufficiency(legacy_top)
    sample_composite = _axis_sample_sufficiency(composite_top)
    scarcity_legacy = _axis_combo_scarcity(legacy_top, filtered_df)
    scarcity_composite = _axis_combo_scarcity(composite_top, filtered_df)

    diagnostic = {
        "strategy_quality": {
            "legacy": strategy_legacy,
            "composite": strategy_composite,
            "delta": _axis_delta(strategy_legacy, strategy_composite),
        },
        "sample_sufficiency": {
            "legacy": sample_legacy,
            "composite": sample_composite,
            "delta": _axis_delta(sample_legacy, sample_composite),
        },
        "combo_scarcity": {
            "legacy": scarcity_legacy,
            "composite": scarcity_composite,
            "delta": _axis_delta(scarcity_legacy, scarcity_composite),
        },
    }

    return {
        "schema_version": RANKING_MODE_COMPARISON_SCHEMA_VERSION,
        "report_type": "ranking_mode_paired_comparison",
        "generated_utc": generated_utc or dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "run_label": run_label,
        "run_id": run_id,
        "settings": {
            "top_n": int(top_n_effective),
            "timeframes": timeframe_configs,
            "min_avg_daily_trades_target": _safe_json_value(min_avg_daily_trades_target),
            "min_oos_trades_target": int(min_oos_trades_target),
            "min_avg_daily_trades_filter": _safe_json_value(min_avg_daily_trades_filter),
        },
        "modes": {
            "legacy": {
                "score_col": legacy_score_col,
                "ranking_config": legacy_ranking_config,
            },
            "composite": {
                "score_col": composite_score_col,
                "ranking_config": composite_ranking_config,
            },
        },
        "summary": summary,
        "diagnostic": diagnostic,
        "paired_rows": _paired_rows_payload(
            filtered_df,
            legacy_top,
            composite_top,
            legacy_score_col,
            composite_score_col,
        ),
        "legacy_top_rows": _ranked_rows_payload(
            legacy_top,
            legacy_score_col,
            filtered_df,
        ),
        "composite_top_rows": _ranked_rows_payload(
            composite_top,
            composite_score_col,
            filtered_df,
        ),
    }


def _format_html_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (float, np.floating)):
        val = float(value)
        if np.isnan(val):
            return ""
        return f"{val:.6g}"
    return escape(str(value))


def _to_html_table(columns: List[str], rows: List[Dict[str, object]]) -> str:
    header_html = "".join(f"<th>{escape(col)}</th>" for col in columns)
    body_rows: List[str] = []
    for row in rows:
        cells = "".join(f"<td>{_format_html_value(row.get(col))}</td>" for col in columns)
        body_rows.append(f"<tr>{cells}</tr>")
    body_html = "".join(body_rows) if body_rows else f"<tr><td colspan=\"{len(columns)}\"></td></tr>"
    return (
        "<table>"
        f"<thead><tr>{header_html}</tr></thead>"
        f"<tbody>{body_html}</tbody>"
        "</table>"
    )


def _axis_rows_for_html(axis_payload: Dict[str, Dict[str, object]]) -> List[Dict[str, object]]:
    legacy = axis_payload.get("legacy", {})
    composite = axis_payload.get("composite", {})
    delta = axis_payload.get("delta", {})
    keys = sorted(set(legacy.keys()) | set(composite.keys()) | set(delta.keys()))
    rows: List[Dict[str, object]] = []
    for key in keys:
        rows.append(
            {
                "metric": key,
                "legacy": legacy.get(key),
                "composite": composite.get(key),
                "delta": delta.get(key),
            }
        )
    return rows


def _render_ranking_mode_comparison_html(report_payload: Dict[str, object]) -> str:
    summary = report_payload.get("summary", {})
    paired_rows = report_payload.get("paired_rows", [])
    legacy_top_rows = report_payload.get("legacy_top_rows", [])
    composite_top_rows = report_payload.get("composite_top_rows", [])
    diagnostic = report_payload.get("diagnostic", {})

    summary_rows = [{"field": key, "value": value} for key, value in summary.items()]
    strategy_rows = _axis_rows_for_html(diagnostic.get("strategy_quality", {}))
    sample_rows = _axis_rows_for_html(diagnostic.get("sample_sufficiency", {}))
    scarcity_rows = _axis_rows_for_html(diagnostic.get("combo_scarcity", {}))

    paired_columns = [
        "row_id",
        "rank_legacy",
        "rank_composite",
        "legacy_score",
        "composite_score",
        "indicator_list",
        "regime_name",
        "vol_mode",
        "oos_avg_total_return_pct",
        "oos_sharpe_like",
        "oos_avg_max_drawdown_pct",
        "oos_min_total_trades",
        "oos_low_trade_penalty",
    ]
    top_columns = [
        "rank",
        "row_id",
        "score",
        "indicator_list",
        "regime_name",
        "vol_mode",
        "oos_avg_total_return_pct",
        "oos_sharpe_like",
        "oos_avg_max_drawdown_pct",
        "oos_min_total_trades",
        "oos_low_trade_penalty",
    ]

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>AUTOWFO Ranking Mode Paired Comparison</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #111; }}
    h1, h2 {{ margin: 16px 0 8px; }}
    table {{ border-collapse: collapse; width: 100%; margin: 8px 0 16px; }}
    th, td {{ border: 1px solid #ddd; padding: 6px 8px; text-align: right; }}
    th {{ background: #f3f3f3; }}
    td:first-child, th:first-child {{ text-align: left; }}
    .meta {{ background: #fafafa; border: 1px solid #eee; padding: 12px; margin-bottom: 12px; }}
  </style>
</head>
<body>
  <h1>AUTOWFO Ranking Mode Paired Comparison</h1>
  <div class="meta">
    <div><strong>schema_version:</strong> {_format_html_value(report_payload.get("schema_version"))}</div>
    <div><strong>generated_utc:</strong> {_format_html_value(report_payload.get("generated_utc"))}</div>
    <div><strong>run_label:</strong> {_format_html_value(report_payload.get("run_label"))}</div>
    <div><strong>run_id:</strong> {_format_html_value(report_payload.get("run_id"))}</div>
  </div>

  <h2>Summary</h2>
  {_to_html_table(["field", "value"], summary_rows)}

  <h2>Diagnostic: Strategy Quality</h2>
  {_to_html_table(["metric", "legacy", "composite", "delta"], strategy_rows)}

  <h2>Diagnostic: Sample Sufficiency</h2>
  {_to_html_table(["metric", "legacy", "composite", "delta"], sample_rows)}

  <h2>Diagnostic: Combo Scarcity</h2>
  {_to_html_table(["metric", "legacy", "composite", "delta"], scarcity_rows)}

  <h2>Paired Rows (legacy vs composite)</h2>
  {_to_html_table(paired_columns, paired_rows if isinstance(paired_rows, list) else [])}

  <h2>Legacy Top Rows</h2>
  {_to_html_table(top_columns, legacy_top_rows if isinstance(legacy_top_rows, list) else [])}

  <h2>Composite Top Rows</h2>
  {_to_html_table(top_columns, composite_top_rows if isinstance(composite_top_rows, list) else [])}
</body>
</html>
"""


def _read_combo_summary_for_run(target_dir: Path, run_id: str) -> pd.DataFrame:
    run_specific = target_dir / f"param_sweep_combo_summary_{run_id}.csv"
    if run_specific.exists():
        return pd.read_csv(run_specific, low_memory=False)
    fallback = target_dir / "param_sweep_combo_summary.csv"
    if fallback.exists():
        return pd.read_csv(fallback, low_memory=False)
    return pd.DataFrame()

