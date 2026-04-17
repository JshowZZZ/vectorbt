from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from autowfo import freqtrade_bridge


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _json_safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if np.isnan(result):
        return None
    return result


def _json_safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _identity_key(selected_row: dict[str, Any], identity_fields: list[str]) -> tuple[Any, ...]:
    return tuple(selected_row.get(field) for field in identity_fields)


def _common_identity_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("indicator_list"),
        row.get("regime_name"),
        row.get("vol_mode"),
        row.get("filter_name"),
    )


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    return float(np.quantile(np.asarray(values, dtype=float), q))


def _distribution(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "count": 0,
            "min": None,
            "p10": None,
            "second_worst": None,
            "mean": None,
            "median": None,
            "max": None,
            "sorted": [],
        }
    sorted_values = sorted(float(value) for value in values)
    second_worst = sorted_values[1] if len(sorted_values) >= 2 else sorted_values[0]
    return {
        "count": len(sorted_values),
        "min": sorted_values[0],
        "p10": _percentile(sorted_values, 0.1),
        "second_worst": second_worst,
        "mean": float(np.mean(sorted_values)),
        "median": float(np.median(sorted_values)),
        "max": sorted_values[-1],
        "sorted": sorted_values,
    }


def _load_scope_entries(scope_manifest: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    row_scope = dict(scope_manifest.get("row_scope") or {})
    identity_fields = list(row_scope.get("identity_fields") or [])
    raw_entries: list[dict[str, Any]] = []
    canonical_lane = dict(row_scope.get("canonical_lane") or {})
    raw_entries.append(
        {
            "scope_label": "canonical",
            "stable_rank": None,
            "bundle_dir": str(canonical_lane.get("bundle_dir") or ""),
            "scope_descriptor": canonical_lane,
        }
    )
    for stable_row in list(row_scope.get("stable_top10") or []):
        stable_rank = _json_safe_int(stable_row.get("rank"))
        raw_entries.append(
            {
                "scope_label": f"stable_top10_rank_{stable_rank}",
                "stable_rank": stable_rank,
                "bundle_dir": str(stable_row.get("bundle_dir") or ""),
                "scope_descriptor": dict(stable_row),
            }
        )

    deduped: dict[tuple[Any, ...], dict[str, Any]] = {}
    for raw_entry in raw_entries:
        bundle_dir = Path(raw_entry["bundle_dir"]).resolve()
        signal_manifest_path = bundle_dir / "signal_manifest.json"
        manifest = freqtrade_bridge.load_signal_bundle_manifest(signal_manifest_path)
        selected_row = dict((manifest.get("analysis") or {}).get("selected_row") or {})
        key = _identity_key(selected_row, identity_fields)
        if key not in deduped:
            deduped[key] = {
                "identity_key": key,
                "identity": {field: selected_row.get(field) for field in identity_fields},
                "selected_row": selected_row,
                "primary_bundle_dir": str(bundle_dir),
                "primary_signal_manifest_path": str(signal_manifest_path),
                "scope_membership": [],
                "source_bundle_dirs": [],
                "stable_ranks": [],
                "legacy_bundle_dir": None,
                "legacy_rank": None,
            }
        record = deduped[key]
        record["scope_membership"].append(raw_entry["scope_label"])
        record["source_bundle_dirs"].append(str(bundle_dir))
        stable_rank = raw_entry["stable_rank"]
        if stable_rank is not None:
            record["stable_ranks"].append(stable_rank)
            if record["legacy_bundle_dir"] is None:
                record["legacy_bundle_dir"] = str(bundle_dir)
                record["legacy_rank"] = stable_rank
        if raw_entry["scope_label"] == "canonical":
            record["primary_bundle_dir"] = str(bundle_dir)
            record["primary_signal_manifest_path"] = str(signal_manifest_path)

    ordered = sorted(
        deduped.values(),
        key=lambda row: (
            0 if "canonical" in row["scope_membership"] else 1,
            min(row["stable_ranks"]) if row["stable_ranks"] else 999,
            row["identity"].get("indicator_list") or "",
        ),
    )
    return identity_fields, ordered


def _build_legacy_index(path: Path) -> tuple[dict[str, dict[str, Any]], dict[tuple[Any, ...], dict[str, Any]]]:
    payload = _load_json(path)
    rows = payload if isinstance(payload, list) else list(payload.get("rows") or [])
    by_bundle_dir: dict[str, dict[str, Any]] = {}
    by_common_identity: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        bundle_dir = str(row.get("bundle_dir") or "").strip()
        if bundle_dir:
            by_bundle_dir[str(Path(bundle_dir).resolve()).lower()] = row
        by_common_identity[_common_identity_key(row)] = row
    return by_bundle_dir, by_common_identity


def _find_legacy_row(
    scope_record: dict[str, Any],
    legacy_by_bundle_dir: dict[str, dict[str, Any]],
    legacy_by_common_identity: dict[tuple[Any, ...], dict[str, Any]],
) -> dict[str, Any] | None:
    legacy_bundle_dir = str(scope_record.get("legacy_bundle_dir") or "").strip()
    if legacy_bundle_dir:
        legacy_row = legacy_by_bundle_dir.get(str(Path(legacy_bundle_dir).resolve()).lower())
        if legacy_row is not None:
            return legacy_row
    return legacy_by_common_identity.get(_common_identity_key(scope_record["selected_row"]))


def _build_row_summary(
    *,
    scope_record: dict[str, Any],
    payload: dict[str, Any],
    legacy_row: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    report = dict(payload.get("parity_report") or {})
    trade_comparison = dict(report.get("trade_comparison") or {})
    freqtrade_summary = dict((report.get("freqtrade") or {}).get("summary") or {})
    autowfo_summary = dict(report.get("autowfo_replay") or {})
    selected_row = dict(scope_record["selected_row"])
    row_id = "+".join(scope_record["scope_membership"])
    row_summary = {
        "row_id": row_id,
        "scope_membership": list(scope_record["scope_membership"]),
        "stable_ranks": sorted(scope_record["stable_ranks"]),
        "primary_bundle_dir": scope_record["primary_bundle_dir"],
        "source_bundle_dirs": list(scope_record["source_bundle_dirs"]),
        "signal_manifest_path": scope_record["primary_signal_manifest_path"],
        "rerun_output_dir": str(Path(payload["backtest_directory"]).resolve()),
        "parity_report_path": str(Path(payload["parity_report_path"]).resolve()),
        "result_path": str(Path(payload["result_path"]).resolve()),
        "strategy_name": payload.get("strategy_name"),
        "verdict": trade_comparison.get("verdict"),
        "autowfo_trade_count": _json_safe_int(trade_comparison.get("autowfo_trade_count")),
        "freqtrade_trade_count": _json_safe_int(trade_comparison.get("freqtrade_trade_count")),
        "trade_count_delta": _json_safe_int(trade_comparison.get("trade_count_delta")),
        "abs_trade_count_delta": abs(_json_safe_int(trade_comparison.get("trade_count_delta")) or 0),
        "exact_match_count": _json_safe_int(trade_comparison.get("exact_match_count")),
        "open_match_count": _json_safe_int(trade_comparison.get("open_match_count")),
        "exact_match_ratio": _json_safe_float(trade_comparison.get("exact_match_ratio")),
        "open_match_ratio": _json_safe_float(trade_comparison.get("open_match_ratio")),
        "profit_ratio_abs_delta_mean": _json_safe_float(trade_comparison.get("profit_ratio_abs_delta_mean")),
        "autowfo_total_return_pct": _json_safe_float(autowfo_summary.get("total_return_pct")),
        "autowfo_trade_count_manifest": _json_safe_int(autowfo_summary.get("trade_count")),
        "ft_profit_total": _json_safe_float(freqtrade_summary.get("profit_total")),
        "ft_profit_total_abs": _json_safe_float(freqtrade_summary.get("profit_total_abs")),
        "ft_total_trades": _json_safe_int(freqtrade_summary.get("total_trades")),
        "ft_winrate": _json_safe_float(freqtrade_summary.get("winrate")),
        "ft_max_drawdown_account": _json_safe_float(freqtrade_summary.get("max_drawdown_account")),
        "indicator_list": selected_row.get("indicator_list"),
        "regime_name": selected_row.get("regime_name"),
        "vol_mode": selected_row.get("vol_mode"),
        "filter_name": selected_row.get("filter_name"),
        "timeframe": selected_row.get("timeframe"),
        "data_days": _json_safe_int(selected_row.get("data_days")),
        "vol_lookback": _json_safe_float(selected_row.get("vol_lookback")),
        "mom_lookback": _json_safe_int(selected_row.get("mom_lookback")),
        "trade_mom_lookback": _json_safe_int(selected_row.get("trade_mom_lookback")),
        "tp_stop": _json_safe_float(selected_row.get("tp_stop")),
        "sl_stop": _json_safe_float(selected_row.get("sl_stop")),
        "max_hold": _json_safe_int(selected_row.get("max_hold")),
        "legacy_reference_rank": _json_safe_int((legacy_row or {}).get("rank") or scope_record.get("legacy_rank")),
        "legacy_reference_bundle_dir": (legacy_row or {}).get("bundle_dir") or scope_record.get("legacy_bundle_dir"),
        "legacy_verdict": (legacy_row or {}).get("verdict"),
        "legacy_exact_match_ratio": _json_safe_float((legacy_row or {}).get("exact_match_ratio")),
        "legacy_open_match_ratio": _json_safe_float((legacy_row or {}).get("open_match_ratio")),
        "legacy_trade_count_delta": _json_safe_int((legacy_row or {}).get("trade_count_delta")),
        "legacy_ft_profit_total": _json_safe_float((legacy_row or {}).get("ft_profit_total")),
        "legacy_ft_total_trades": _json_safe_int((legacy_row or {}).get("ft_total_trades")),
    }
    row_summary["delta_vs_legacy_exact_match_ratio"] = (
        None
        if row_summary["legacy_exact_match_ratio"] is None or row_summary["exact_match_ratio"] is None
        else row_summary["exact_match_ratio"] - row_summary["legacy_exact_match_ratio"]
    )
    row_summary["delta_vs_legacy_open_match_ratio"] = (
        None
        if row_summary["legacy_open_match_ratio"] is None or row_summary["open_match_ratio"] is None
        else row_summary["open_match_ratio"] - row_summary["legacy_open_match_ratio"]
    )
    row_summary["delta_vs_legacy_trade_count_delta"] = (
        None
        if row_summary["legacy_trade_count_delta"] is None or row_summary["trade_count_delta"] is None
        else row_summary["trade_count_delta"] - row_summary["legacy_trade_count_delta"]
    )

    pair_rows: list[dict[str, Any]] = []
    for pair_record in list(trade_comparison.get("per_pair_counts") or []):
        pair_rows.append(
            {
                "row_id": row_id,
                "pair": pair_record.get("pair"),
                "direction": pair_record.get("direction"),
                "autowfo_count": _json_safe_int(pair_record.get("autowfo_count")),
                "freqtrade_count": _json_safe_int(pair_record.get("freqtrade_count")),
                "delta": _json_safe_int(pair_record.get("delta")),
            }
        )
    row_summary["per_pair_counts"] = pair_rows
    return row_summary, pair_rows


def _build_summary_payload(
    *,
    scope_manifest_path: Path,
    scope_manifest: dict[str, Any],
    row_summaries: list[dict[str, Any]],
    pair_direction_rows: list[dict[str, Any]],
    datadir: Path,
    freqtrade_exe: Path,
) -> dict[str, Any]:
    expected_rows = _json_safe_int((scope_manifest.get("row_scope") or {}).get("expected_unique_row_count_after_dedup"))
    row_count = len(row_summaries)
    open_ratios = [row["open_match_ratio"] for row in row_summaries if row.get("open_match_ratio") is not None]
    exact_ratios = [row["exact_match_ratio"] for row in row_summaries if row.get("exact_match_ratio") is not None]
    trade_delta_abs = [float(row["abs_trade_count_delta"]) for row in row_summaries]
    verdict_counts: dict[str, int] = {}
    for row in row_summaries:
        verdict = str(row.get("verdict") or "unknown")
        verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1
    pair_values = sorted(
        {
            str(pair_row.get("pair"))
            for pair_row in pair_direction_rows
            if str(pair_row.get("pair") or "").strip()
        }
    )
    return {
        "schema_version": "1.0.0",
        "awf_id": "AWF-339",
        "name": "awf331_rerun_summary",
        "generated_utc": _utc_now_iso(),
        "source_manifest_path": str(scope_manifest_path.resolve()),
        "freqtrade_exe": str(freqtrade_exe.resolve()),
        "datadir": str(datadir.resolve()),
        "row_scope_validation": {
            "expected_unique_row_count_after_dedup": expected_rows,
            "actual_unique_row_count": row_count,
            "row_count_matches_expectation": (expected_rows == row_count),
            "canonical_overlap_with_stable_rank": _json_safe_int(
                (scope_manifest.get("row_scope") or {}).get("canonical_overlap_with_stable_rank")
            ),
            "scope_membership_labels": [row["scope_membership"] for row in row_summaries],
        },
        "branch_conditions": {
            "open_match_ratio_stop_threshold": 0.5,
            "rows_below_open_match_stop_threshold": [
                row["row_id"]
                for row in row_summaries
                if row.get("open_match_ratio") is not None and row["open_match_ratio"] < 0.5
            ],
            "awf339a_required": any(
                row.get("open_match_ratio") is not None and row["open_match_ratio"] < 0.5
                for row in row_summaries
            ),
        },
        "aggregate": {
            "row_count": row_count,
            "pair_direction_row_count": len(pair_direction_rows),
            "pair_distinct_count": len(pair_values),
            "pairs": pair_values,
            "verdict_counts": verdict_counts,
            "open_match_ratio": _distribution(open_ratios),
            "exact_match_ratio": _distribution(exact_ratios),
            "abs_trade_count_delta": _distribution(trade_delta_abs),
            "legacy_comparison": {
                "rows_with_legacy_reference": sum(1 for row in row_summaries if row.get("legacy_reference_bundle_dir")),
                "rows_with_improved_open_match_ratio": sum(
                    1
                    for row in row_summaries
                    if row.get("delta_vs_legacy_open_match_ratio") is not None
                    and row["delta_vs_legacy_open_match_ratio"] > 0
                ),
                "rows_with_improved_exact_match_ratio": sum(
                    1
                    for row in row_summaries
                    if row.get("delta_vs_legacy_exact_match_ratio") is not None
                    and row["delta_vs_legacy_exact_match_ratio"] > 0
                ),
                "max_abs_delta_vs_legacy_trade_count_delta": (
                    None
                    if not row_summaries
                    else max(
                        abs(float(row["delta_vs_legacy_trade_count_delta"]))
                        for row in row_summaries
                        if row.get("delta_vs_legacy_trade_count_delta") is not None
                    )
                    if any(row.get("delta_vs_legacy_trade_count_delta") is not None for row in row_summaries)
                    else None
                ),
            },
        },
        "rows": row_summaries,
        "pair_direction_rows": pair_direction_rows,
    }


def _run_awf339(
    *,
    scope_manifest_path: Path,
    datadir: Path,
    freqtrade_exe: Path,
    output_root: Path,
    summary_path: Path,
    legacy_summary_path: Path,
) -> dict[str, Any]:
    scope_manifest = _load_json(scope_manifest_path)
    identity_fields, scope_records = _load_scope_entries(scope_manifest)
    expected_rows = _json_safe_int((scope_manifest.get("row_scope") or {}).get("expected_unique_row_count_after_dedup"))
    if expected_rows is not None and len(scope_records) != expected_rows:
        raise RuntimeError(
            f"AWF-339 row scope mismatch: expected {expected_rows} unique rows after dedup, got {len(scope_records)}"
        )
    legacy_by_bundle_dir, legacy_by_common_identity = _build_legacy_index(legacy_summary_path)

    row_summaries: list[dict[str, Any]] = []
    pair_direction_rows: list[dict[str, Any]] = []
    print(f"[awf339] identity_fields={','.join(identity_fields)}")
    print(f"[awf339] unique_row_count={len(scope_records)}")
    for index, scope_record in enumerate(scope_records, start=1):
        manifest_path = Path(scope_record["primary_signal_manifest_path"]).resolve()
        out_dir = output_root / manifest_path.parent.name
        manifest = freqtrade_bridge.load_signal_bundle_manifest(manifest_path)
        print(f"[awf339] rerun {index}/{len(scope_records)} -> {manifest_path.parent.name}")
        payload = freqtrade_bridge.run_freqtrade_cross_check(
            manifest,
            manifest_path=manifest_path,
            out_dir=out_dir,
            datadir=datadir,
            freqtrade_exe=freqtrade_exe,
            execute=True,
        )
        legacy_row = _find_legacy_row(scope_record, legacy_by_bundle_dir, legacy_by_common_identity)
        row_summary, pair_rows = _build_row_summary(
            scope_record=scope_record,
            payload=payload,
            legacy_row=legacy_row,
        )
        row_summaries.append(row_summary)
        pair_direction_rows.extend(pair_rows)

    summary_payload = _build_summary_payload(
        scope_manifest_path=scope_manifest_path,
        scope_manifest=scope_manifest,
        row_summaries=row_summaries,
        pair_direction_rows=pair_direction_rows,
        datadir=datadir,
        freqtrade_exe=freqtrade_exe,
    )
    _write_json(summary_path, summary_payload)
    return summary_payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run AWF-339 parity rerun and write awf331_rerun_summary.json")
    parser.add_argument(
        "--scope-manifest",
        default=str(ROOT / "plans" / "protocols" / "awf338_rerun_input_manifest.json"),
        help="Path to the frozen AWF-338 rerun input manifest",
    )
    parser.add_argument(
        "--legacy-summary",
        default=str(ROOT / "artifacts" / "freqtrade_bridge" / "awf331_stable_top10_summary.json"),
        help="Path to the pre-fix AWF-331 summary used for delta comparison",
    )
    parser.add_argument(
        "--datadir",
        default="E:/Project/freqtrade/user_data/data/binance",
        help="Freqtrade datadir root",
    )
    parser.add_argument(
        "--freqtrade-exe",
        default="E:/Project/freqtrade/.venv/Scripts/freqtrade.exe",
        help="Freqtrade executable path",
    )
    parser.add_argument(
        "--output-root",
        default=str(ROOT / "artifacts" / "freqtrade_bridge" / "awf339"),
        help="Directory that will store per-row rerun outputs",
    )
    parser.add_argument(
        "--summary-path",
        default=str(ROOT / "artifacts" / "freqtrade_bridge" / "awf331_rerun_summary.json"),
        help="Path for the AWF-339 aggregate summary JSON",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary_payload = _run_awf339(
        scope_manifest_path=Path(args.scope_manifest).resolve(),
        datadir=Path(args.datadir).resolve(),
        freqtrade_exe=Path(args.freqtrade_exe).resolve(),
        output_root=Path(args.output_root).resolve(),
        summary_path=Path(args.summary_path).resolve(),
        legacy_summary_path=Path(args.legacy_summary).resolve(),
    )
    aggregate = dict(summary_payload.get("aggregate") or {})
    branch_conditions = dict(summary_payload.get("branch_conditions") or {})
    print(f"[awf339] summary_path={Path(args.summary_path).resolve()}")
    print(f"[awf339] row_count={aggregate.get('row_count')} pair_distinct_count={aggregate.get('pair_distinct_count')}")
    print(
        "[awf339] open_match_min={min_ratio} exact_match_p10={p10_ratio} awf339a_required={awf339a_required}".format(
            min_ratio=((aggregate.get("open_match_ratio") or {}).get("min")),
            p10_ratio=((aggregate.get("exact_match_ratio") or {}).get("p10")),
            awf339a_required=branch_conditions.get("awf339a_required"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
