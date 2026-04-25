import json
from pathlib import Path

from autowfo.drift_prototypes import (
    QUERY_FILE_NAMES,
    build_awf344_prototype_queries,
    write_awf344_prototype_queries,
)


def test_build_awf344_prototype_queries_targets_summary_and_source_joins(tmp_path):
    summary_path = tmp_path / "artifacts" / "freqtrade_bridge" / "awf331_rerun_summary.json"
    repo_root = tmp_path.resolve()

    queries = build_awf344_prototype_queries(
        summary_path=summary_path,
        repo_root=repo_root,
    )

    assert set(queries.keys()) == set(QUERY_FILE_NAMES.keys())

    row_level_sql = queries["row_level_drift"]
    assert str(summary_path.as_posix()) in row_level_sql
    assert "unnest(summary.rows)" in row_level_sql
    assert "delta_vs_legacy_exact_match_ratio" in row_level_sql
    assert "drift_severity" in row_level_sql

    pair_direction_sql = queries["pair_direction_drift"]
    assert "unnest(summary.pair_direction_rows)" in pair_direction_sql
    assert "rows.exact_match_ratio < 0.6" in pair_direction_sql
    assert "pair_rows.delta <> 0" in pair_direction_sql

    source_join_sql = queries["source_consistency"]
    assert "read_json_auto(" in source_join_sql
    assert "awf339/*/parity_report.json" in source_join_sql
    assert "freqtrade_bridge/*/signal_manifest.json" in source_join_sql
    assert "normalized_parity_report_path" in source_join_sql
    assert str(repo_root.as_posix()) in source_join_sql


def test_write_awf344_prototype_queries_creates_expected_files(tmp_path):
    output_dir = tmp_path / "artifacts" / "scratch" / "duckdb_drift_prototypes"
    queries = {
        "row_level_drift": "select 1;\n",
        "pair_direction_drift": "select 2;\n",
        "source_consistency": "select 3;\n",
    }

    written = write_awf344_prototype_queries(output_dir, queries)

    assert sorted(path.name for path in written.values()) == sorted(QUERY_FILE_NAMES.values())
    for key, path in written.items():
        assert path.read_text(encoding="utf-8") == queries[key]
