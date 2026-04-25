from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping

from autowfo.paper_dryrun_reconcile import load_freqtrade_config, resolve_freqtrade_db_path

DEFAULT_AWF338_MANIFEST_PATH = Path("plans/protocols/awf338_rerun_input_manifest.json")
DEFAULT_OUTPUT_DIR = Path("artifacts/scratch/duckdb_smoke")

QUERY_FILE_NAMES = {
    "summary_counts": "01_awf331_rerun_summary_counts.sql",
    "signals_head": "02_canonical_signals_head.sql",
    "trade_signal_join_count": "03_trade_signal_join_count.sql",
}


def _load_json(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _sql_literal(value: str | Path) -> str:
    return str(value).replace("\\", "/").replace("'", "''")


def _resolve_awf342a_paths(
    manifest_path: str | Path = DEFAULT_AWF338_MANIFEST_PATH,
    *,
    db_path: str | Path | None = None,
) -> dict[str, object]:
    manifest = _load_json(manifest_path)
    summary_path = Path(str(((manifest.get("rerun_output_contract") or {}).get("summary_path")) or "")).resolve()
    canonical_bundle_dir = Path(
        str((((manifest.get("row_scope") or {}).get("canonical_lane") or {}).get("bundle_dir")) or "")
    ).resolve()
    signals_path = (canonical_bundle_dir / "signals.parquet").resolve()

    freqtrade_contract = dict(manifest.get("freqtrade_contract") or {})
    freqtrade_config_path = freqtrade_contract.get("config_path")
    freqtrade_config = (
        load_freqtrade_config(freqtrade_config_path)
        if freqtrade_config_path and Path(str(freqtrade_config_path)).exists()
        else {}
    )
    sqlite_path = resolve_freqtrade_db_path(
        db_path=db_path,
        freqtrade_config_path=freqtrade_config_path,
        freqtrade_config=freqtrade_config,
    ).resolve()

    pair_mapping = {
        str(source): str(target)
        for source, target in dict(freqtrade_contract.get("pair_mapping") or {}).items()
        if str(source) and str(target)
    }
    return {
        "summary_path": summary_path,
        "signals_path": signals_path,
        "sqlite_path": sqlite_path,
        "pair_mapping": pair_mapping,
    }


def _build_pair_mapping_values_clause(pair_mapping: Mapping[str, str]) -> str:
    rows = [f"    ('{_sql_literal(source)}', '{_sql_literal(target)}')" for source, target in sorted(pair_mapping.items())]
    return ",\n".join(rows)


def build_awf342a_smoke_queries(
    manifest_path: str | Path = DEFAULT_AWF338_MANIFEST_PATH,
    *,
    db_path: str | Path | None = None,
) -> dict[str, str]:
    resolved = _resolve_awf342a_paths(manifest_path, db_path=db_path)
    summary_path = Path(resolved["summary_path"])
    signals_path = Path(resolved["signals_path"])
    sqlite_path = Path(resolved["sqlite_path"])
    pair_mapping = dict(resolved["pair_mapping"])

    summary_counts = f"""-- AWF-342a smoke query: summarize the frozen AWF-339 rerun JSON payload.
SELECT
    aggregate.row_count::BIGINT AS aggregate_row_count,
    array_length(rows)::BIGINT AS rows_array_count,
    aggregate.pair_distinct_count::BIGINT AS pair_distinct_count,
    array_length(aggregate.pairs)::BIGINT AS pairs_array_count
FROM read_json_auto('{_sql_literal(summary_path)}');
"""

    signals_head = f"""-- AWF-342a smoke query: inspect the first 10 frozen signal rows.
SELECT *
FROM read_parquet('{_sql_literal(signals_path)}')
ORDER BY date ASC, pair ASC
LIMIT 10;
"""

    pair_mapping_values = _build_pair_mapping_values_clause(pair_mapping)
    trade_signal_join_count = f"""-- AWF-342a smoke query: count pair+entry-timestamp matches between frozen signals and dry-run trades.
INSTALL sqlite;
LOAD sqlite;

WITH pair_mapping(autowfo_pair, freqtrade_pair) AS (
VALUES
{pair_mapping_values}
),
frozen_signals AS (
    SELECT
        pair,
        CAST(date AS TIMESTAMP) AS entry_timestamp
    FROM read_parquet('{_sql_literal(signals_path)}')
    WHERE COALESCE(enter_long, 0) > 0 OR COALESCE(enter_short, 0) > 0
),
dryrun_trades AS (
    SELECT
        pair_mapping.autowfo_pair AS pair,
        CAST(trades.open_date AS TIMESTAMP) AS entry_timestamp
    FROM sqlite_scan('{_sql_literal(sqlite_path)}', 'trades') AS trades
    INNER JOIN pair_mapping
        ON pair_mapping.freqtrade_pair = trades.pair
)
SELECT COUNT(*) AS trade_signal_join_count
FROM dryrun_trades
INNER JOIN frozen_signals
    ON frozen_signals.pair = dryrun_trades.pair
   AND frozen_signals.entry_timestamp = dryrun_trades.entry_timestamp;
"""

    return {
        "summary_counts": summary_counts,
        "signals_head": signals_head,
        "trade_signal_join_count": trade_signal_join_count,
    }


def write_awf342a_smoke_queries(
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    queries: Mapping[str, str] | None = None,
    *,
    manifest_path: str | Path = DEFAULT_AWF338_MANIFEST_PATH,
    db_path: str | Path | None = None,
) -> dict[str, Path]:
    resolved_output_dir = Path(output_dir)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    query_payload = dict(queries or build_awf342a_smoke_queries(manifest_path, db_path=db_path))
    written: dict[str, Path] = {}
    for key, filename in QUERY_FILE_NAMES.items():
        payload = query_payload[key]
        target = resolved_output_dir / filename
        target.write_text(payload, encoding="utf-8")
        written[key] = target
    return written


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Write AWF-342a DuckDB smoke queries from the frozen rerun manifest.")
    parser.add_argument("--manifest", default=str(DEFAULT_AWF338_MANIFEST_PATH), help="Path to awf338 manifest JSON.")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory where AWF-342a smoke SQL files should be written.",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Optional override for the Freqtrade dry-run SQLite path.",
    )
    return parser


def main() -> int:
    parser = _build_arg_parser()
    args = parser.parse_args()
    write_awf342a_smoke_queries(args.output_dir, manifest_path=args.manifest, db_path=args.db_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
