import json
from pathlib import Path

from autowfo.duckdb_smoke import (
    QUERY_FILE_NAMES,
    build_awf342a_smoke_queries,
    write_awf342a_smoke_queries,
)


def test_build_awf342a_smoke_queries_uses_frozen_manifest_paths(tmp_path):
    freqtrade_root = tmp_path / "freqtrade"
    user_data_dir = freqtrade_root / "user_data"
    user_data_dir.mkdir(parents=True)
    config_path = user_data_dir / "config_autowfo_dryrun.json"
    config_path.write_text(json.dumps({"db_url": "sqlite:///tradesv3.dryrun.sqlite"}), encoding="utf-8")

    canonical_bundle = tmp_path / "artifacts" / "freqtrade_bridge" / "bundle_canonical"
    canonical_bundle.mkdir(parents=True)
    summary_path = tmp_path / "artifacts" / "freqtrade_bridge" / "awf331_rerun_summary.json"
    manifest_path = tmp_path / "plans" / "protocols" / "awf338_rerun_input_manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(
            {
                "rerun_output_contract": {
                    "summary_path": str(summary_path),
                },
                "row_scope": {
                    "canonical_lane": {
                        "bundle_dir": str(canonical_bundle),
                    }
                },
                "freqtrade_contract": {
                    "config_path": str(config_path),
                    "pair_mapping": {
                        "ADA/BTC": "ADA/USDT:USDT",
                        "ETH/BTC": "ETH/USDT:USDT",
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    queries = build_awf342a_smoke_queries(manifest_path)

    assert set(queries.keys()) == set(QUERY_FILE_NAMES.keys())
    assert str(summary_path.as_posix()) in queries["summary_counts"]
    assert "aggregate.row_count" in queries["summary_counts"]
    assert str((canonical_bundle / "signals.parquet").as_posix()) in queries["signals_head"]
    assert "LIMIT 10" in queries["signals_head"]
    assert "sqlite_scan" in queries["trade_signal_join_count"]
    assert str((freqtrade_root / "tradesv3.dryrun.sqlite").as_posix()) in queries["trade_signal_join_count"]
    assert "('ADA/BTC', 'ADA/USDT:USDT')" in queries["trade_signal_join_count"]
    assert "('ETH/BTC', 'ETH/USDT:USDT')" in queries["trade_signal_join_count"]


def test_write_awf342a_smoke_queries_creates_expected_files(tmp_path):
    output_dir = tmp_path / "artifacts" / "scratch" / "duckdb_smoke"
    queries = {
        "summary_counts": "select 1;\n",
        "signals_head": "select 2;\n",
        "trade_signal_join_count": "select 3;\n",
    }

    written = write_awf342a_smoke_queries(output_dir, queries)

    assert sorted(path.name for path in written.values()) == sorted(QUERY_FILE_NAMES.values())
    for key, path in written.items():
        assert path.read_text(encoding="utf-8") == queries[key]
