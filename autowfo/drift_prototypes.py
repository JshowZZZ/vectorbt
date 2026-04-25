from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

import duckdb

DEFAULT_SUMMARY_PATH = Path("artifacts/freqtrade_bridge/awf331_rerun_summary.json")
DEFAULT_OUTPUT_DIR = Path("artifacts/scratch/duckdb_drift_prototypes")

QUERY_FILE_NAMES = {
    "row_level_drift": "01_row_level_drift.sql",
    "pair_direction_drift": "02_pair_direction_drift.sql",
    "source_consistency": "03_source_consistency.sql",
}


def _sql_literal(value: str | Path) -> str:
    return str(value).replace("\\", "/").replace("'", "''")


def _normalized_path_sql(column: str) -> str:
    return f"replace({column}, '\\\\', '/')"


def build_awf344_prototype_queries(
    *,
    summary_path: str | Path = DEFAULT_SUMMARY_PATH,
    repo_root: str | Path = Path.cwd(),
) -> dict[str, str]:
    summary_literal = _sql_literal(Path(summary_path))
    repo_root_literal = _sql_literal(Path(repo_root).resolve())

    row_level_drift = f"""-- AWF-344 prototype: flatten row-level drift metrics from the AWF-339 rerun summary.
WITH rows AS (
    SELECT
        row.row_id,
        row.filter_name,
        row.indicator_list,
        row.regime_name,
        row.vol_mode,
        row.timeframe,
        row.data_days,
        row.verdict,
        row.open_match_ratio,
        row.exact_match_ratio,
        row.trade_count_delta,
        row.abs_trade_count_delta,
        row.profit_ratio_abs_delta_mean,
        row.delta_vs_legacy_open_match_ratio,
        row.delta_vs_legacy_exact_match_ratio,
        row.delta_vs_legacy_trade_count_delta,
        CASE
            WHEN row.open_match_ratio < 0.99 OR row.abs_trade_count_delta > 0 THEN 'high'
            WHEN row.exact_match_ratio < 0.60 THEN 'medium'
            ELSE 'low'
        END AS drift_severity
    FROM read_json_auto('{summary_literal}') AS summary,
    unnest(summary.rows) AS t(row)
)
SELECT *
FROM rows
ORDER BY
    CASE drift_severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
    exact_match_ratio ASC,
    open_match_ratio ASC,
    row_id ASC;
"""

    pair_direction_drift = f"""-- AWF-344 prototype: expose pair-direction concentration for rows with the weakest exact parity or any trade-count delta.
WITH rows AS (
    SELECT
        row.row_id,
        row.filter_name,
        row.open_match_ratio,
        row.exact_match_ratio
    FROM read_json_auto('{summary_literal}') AS summary,
    unnest(summary.rows) AS t(row)
),
pair_rows AS (
    SELECT
        pair_row.row_id,
        pair_row.pair,
        pair_row.direction,
        pair_row.autowfo_count,
        pair_row.freqtrade_count,
        pair_row.delta
    FROM read_json_auto('{summary_literal}') AS summary,
    unnest(summary.pair_direction_rows) AS t(pair_row)
)
SELECT
    rows.row_id,
    rows.filter_name,
    pair_rows.pair,
    pair_rows.direction,
    pair_rows.autowfo_count,
    pair_rows.freqtrade_count,
    pair_rows.delta,
    rows.open_match_ratio,
    rows.exact_match_ratio
FROM pair_rows
INNER JOIN rows USING (row_id)
WHERE pair_rows.delta <> 0 OR rows.exact_match_ratio < 0.6
ORDER BY rows.exact_match_ratio ASC, pair_rows.pair ASC, pair_rows.direction ASC;
"""

    source_consistency = f"""-- AWF-344 prototype: prove stable path joins from summary rows to awf339 parity reports and frozen signal manifests.
WITH raw_rows AS (
    SELECT
        row.row_id,
        row.signal_manifest_path,
        row.parity_report_path,
        row.open_match_ratio,
        row.exact_match_ratio,
        row.freqtrade_trade_count
    FROM read_json_auto('{summary_literal}') AS summary,
    unnest(summary.rows) AS t(row)
),
rows AS (
    SELECT
        raw_rows.row_id,
        raw_rows.open_match_ratio,
        raw_rows.exact_match_ratio,
        raw_rows.freqtrade_trade_count,
        replace({_normalized_path_sql('raw_rows.signal_manifest_path')}, '{repo_root_literal}/', '') AS signal_manifest_rel_path,
        replace({_normalized_path_sql('raw_rows.parity_report_path')}, '{repo_root_literal}/', '') AS parity_report_rel_path,
        regexp_extract(
            raw_rows.signal_manifest_path,
            'freqtrade_bridge[\\\\/]([^\\\\/]+)[\\\\/]signal_manifest\\.json',
            1
        ) AS signal_bundle_id,
        regexp_extract(
            raw_rows.parity_report_path,
            'awf339[\\\\/]([^\\\\/]+)[\\\\/]parity_report\\.json',
            1
        ) AS parity_bundle_id
    FROM raw_rows
),
signal_manifests AS (
    SELECT
        {_normalized_path_sql('filename')} AS manifest_filename,
        regexp_extract(filename, 'freqtrade_bridge[\\\\/]([^\\\\/]+)[\\\\/]signal_manifest\\.json', 1) AS signal_bundle_id,
        source.timeframe AS source_timeframe,
        source.pair_count AS manifest_pair_count,
        signals.rows AS signal_rows
    FROM read_json_auto('artifacts/freqtrade_bridge/*/signal_manifest.json', filename = true)
),
parity_reports AS (
    SELECT
        {_normalized_path_sql('filename')} AS parity_filename,
        regexp_extract(filename, 'awf339[\\\\/]([^\\\\/]+)[\\\\/]parity_report\\.json', 1) AS parity_bundle_id,
        trade_comparison.open_match_ratio AS report_open_match_ratio,
        trade_comparison.exact_match_ratio AS report_exact_match_ratio,
        trade_comparison.freqtrade_trade_count AS report_freqtrade_trade_count
    FROM read_json_auto('artifacts/freqtrade_bridge/awf339/*/parity_report.json', filename = true)
)
SELECT
    rows.row_id,
    rows.signal_manifest_rel_path AS normalized_signal_manifest_path,
    rows.parity_report_rel_path AS normalized_parity_report_path,
    rows.signal_bundle_id,
    rows.parity_bundle_id,
    signal_manifests.manifest_filename,
    parity_reports.parity_filename,
    signal_manifests.source_timeframe,
    signal_manifests.manifest_pair_count,
    signal_manifests.signal_rows,
    rows.open_match_ratio,
    parity_reports.report_open_match_ratio,
    rows.exact_match_ratio,
    parity_reports.report_exact_match_ratio,
    rows.freqtrade_trade_count,
    parity_reports.report_freqtrade_trade_count,
    signal_manifests.manifest_filename IS NOT NULL AS signal_manifest_joined,
    parity_reports.parity_filename IS NOT NULL AS parity_report_joined
FROM rows
LEFT JOIN signal_manifests
    ON rows.signal_bundle_id = signal_manifests.signal_bundle_id
LEFT JOIN parity_reports
    ON rows.parity_bundle_id = parity_reports.parity_bundle_id
ORDER BY rows.row_id ASC;
"""

    return {
        "row_level_drift": row_level_drift,
        "pair_direction_drift": pair_direction_drift,
        "source_consistency": source_consistency,
    }


def write_awf344_prototype_queries(
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    queries: Mapping[str, str] | None = None,
    *,
    summary_path: str | Path = DEFAULT_SUMMARY_PATH,
    repo_root: str | Path = Path.cwd(),
) -> dict[str, Path]:
    resolved_output_dir = Path(output_dir)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    payload = dict(queries or build_awf344_prototype_queries(summary_path=summary_path, repo_root=repo_root))
    written: dict[str, Path] = {}
    for key, filename in QUERY_FILE_NAMES.items():
        target = resolved_output_dir / filename
        target.write_text(payload[key], encoding="utf-8")
        written[key] = target
    return written


def _json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def execute_awf344_prototype_queries(
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    *,
    summary_path: str | Path = DEFAULT_SUMMARY_PATH,
    repo_root: str | Path = Path.cwd(),
) -> dict[str, Path]:
    written = write_awf344_prototype_queries(output_dir, summary_path=summary_path, repo_root=repo_root)
    conn = duckdb.connect()
    sample_paths: dict[str, Path] = {}
    try:
        for key, sql_path in written.items():
            sql = sql_path.read_text(encoding="utf-8")
            cursor = conn.execute(sql)
            columns = [item[0] for item in (cursor.description or [])]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
            sample_path = sql_path.with_suffix(".sample.json")
            sample_path.write_text(
                json.dumps([_json_safe(row) for row in rows], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            sample_paths[key] = sample_path
    finally:
        conn.close()
    return sample_paths


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Write and execute AWF-344 DuckDB drift prototype queries.")
    parser.add_argument("--summary-path", default=str(DEFAULT_SUMMARY_PATH), help="Path to awf331 rerun summary JSON.")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory where AWF-344 prototype SQL and sample outputs should be written.",
    )
    parser.add_argument(
        "--repo-root",
        default=str(Path.cwd()),
        help="Repo root used to normalize absolute paths inside the summary.",
    )
    parser.add_argument(
        "--skip-execution",
        action="store_true",
        help="Only write SQL files; do not execute them into sample JSON outputs.",
    )
    return parser


def main() -> int:
    parser = _build_arg_parser()
    args = parser.parse_args()
    write_awf344_prototype_queries(args.output_dir, summary_path=args.summary_path, repo_root=args.repo_root)
    if not args.skip_execution:
        execute_awf344_prototype_queries(args.output_dir, summary_path=args.summary_path, repo_root=args.repo_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
