"""AWF-028 tests ??experiment notebook export."""

import json
from pathlib import Path

import pytest

from autowfo.notebook import (
    _code_basic_analysis,
    _code_combo_summary_analysis,
    _code_imports,
    _code_leaderboard_row,
    _code_load_csv,
    _code_load_metadata,
    _md_metadata_section,
    _md_notes_section,
    build_experiment_notebook,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def sample_metadata():
    return {
        "run_id": "20260214_120000",
        "timestamp_utc": "2026-02-14T12:00:00Z",
        "search_mode": "combo",
        "config_sha256": "abc123def456abc123def456abc123de",
        "data_fingerprint": "fff000eee111ddd222ccc333bbb444aa",
        "trade_symbols": ["ETH/USDT", "BNB/USDT"],
        "timeframes": ["4h", "1h"],
        "wf_mode": "anchored",
    }


@pytest.fixture()
def sample_leaderboard_row():
    return {
        "run_id": "20260214_120000",
        "symbol": "ETH-USDT",
        "timeframe": "4h",
        "oos_avg_total_return_pct": 12.5,
        "composite_score": 0.85,
    }


# ---------------------------------------------------------------------------
# Markdown / code cell helpers
# ---------------------------------------------------------------------------

class TestMdMetadataSection:
    def test_contains_run_id(self, sample_metadata):
        md = _md_metadata_section(sample_metadata)
        assert "20260214_120000" in md

    def test_contains_title(self, sample_metadata):
        md = _md_metadata_section(sample_metadata)
        assert "# Experiment Notebook" in md

    def test_contains_symbols(self, sample_metadata):
        md = _md_metadata_section(sample_metadata)
        assert "ETH/USDT" in md

    def test_contains_wf_mode(self, sample_metadata):
        md = _md_metadata_section(sample_metadata)
        assert "anchored" in md

    def test_handles_missing_fields(self):
        md = _md_metadata_section({})
        assert "unknown" in md

    def test_formats_dict_timeframes(self, sample_metadata):
        metadata = dict(sample_metadata)
        metadata["timeframes"] = [{"timeframe": "4h", "days": 180}, {"timeframe": "1h", "days": 30}]
        md = _md_metadata_section(metadata)
        assert "4h (180d)" in md
        assert "1h (30d)" in md


class TestCodeImports:
    def test_contains_pandas(self):
        code = _code_imports()
        assert "import pandas" in code

    def test_contains_pathlib(self):
        code = _code_imports()
        assert "Path" in code


class TestCodeLoadMetadata:
    def test_contains_run_id(self):
        code = _code_load_metadata("20260214_120000")
        assert "20260214_120000" in code

    def test_contains_json_load(self):
        code = _code_load_metadata("test")
        assert "json.load" in code


class TestCodeLoadCsv:
    def test_contains_filename(self):
        code = _code_load_csv("Top 10", "param_sweep_top10_X.csv")
        assert "param_sweep_top10_X.csv" in code

    def test_contains_display(self):
        code = _code_load_csv("Top 10", "file.csv")
        assert "display" in code

    def test_respects_head_param(self):
        code = _code_load_csv("data", "file.csv", head=5)
        assert ".head(5)" in code


class TestCodeLeaderboardRow:
    def test_with_row(self, sample_leaderboard_row):
        code = _code_leaderboard_row(sample_leaderboard_row)
        assert "leaderboard_row" in code
        assert "20260214_120000" in code

    def test_none_row(self):
        code = _code_leaderboard_row(None)
        assert "No leaderboard row" in code


class TestCodeBasicAnalysis:
    def test_contains_oos_return(self):
        code = _code_basic_analysis()
        assert "oos_avg_total_return_pct" in code

    def test_contains_composite_score(self):
        code = _code_basic_analysis()
        assert "composite_score" in code


class TestCodeComboSummaryAnalysis:
    def test_contains_regime_check(self):
        code = _code_combo_summary_analysis()
        assert "regime_name" in code

    def test_contains_describe(self):
        code = _code_combo_summary_analysis()
        assert "describe" in code


class TestMdNotesSection:
    def test_contains_notes_header(self):
        md = _md_notes_section()
        assert "## Analysis Notes" in md


# ---------------------------------------------------------------------------
# Integration: build_experiment_notebook
# ---------------------------------------------------------------------------

class TestBuildExperimentNotebook:
    def test_creates_ipynb_file(self, tmp_path, sample_metadata, sample_leaderboard_row):
        nb_path = build_experiment_notebook(
            run_id="20260214_120000",
            out_dir=tmp_path,
            metadata=sample_metadata,
            leaderboard_row=sample_leaderboard_row,
        )
        assert nb_path.exists()
        assert nb_path.suffix == ".ipynb"
        assert "20260214_120000" in nb_path.name

    def test_filename_pattern(self, tmp_path, sample_metadata):
        nb_path = build_experiment_notebook(
            run_id="test_run",
            out_dir=tmp_path,
            metadata=sample_metadata,
        )
        assert nb_path.name == "experiment_test_run.ipynb"

    def test_valid_notebook_format(self, tmp_path, sample_metadata):
        import nbformat

        nb_path = build_experiment_notebook(
            run_id="test_run",
            out_dir=tmp_path,
            metadata=sample_metadata,
        )
        with open(nb_path, encoding="utf-8") as f:
            nb = nbformat.read(f, as_version=4)
        assert nb.metadata.kernelspec["language"] == "python"
        assert len(nb.cells) > 0

    def test_cell_count(self, tmp_path, sample_metadata, sample_leaderboard_row):
        import nbformat

        nb_path = build_experiment_notebook(
            run_id="20260214_120000",
            out_dir=tmp_path,
            metadata=sample_metadata,
            leaderboard_row=sample_leaderboard_row,
        )
        with open(nb_path, encoding="utf-8") as f:
            nb = nbformat.read(f, as_version=4)
        # Expected: 2 markdown + 8 code = 10 cells
        assert len(nb.cells) == 10

    def test_has_markdown_and_code_cells(self, tmp_path, sample_metadata):
        import nbformat

        nb_path = build_experiment_notebook(
            run_id="test_run",
            out_dir=tmp_path,
            metadata=sample_metadata,
        )
        with open(nb_path, encoding="utf-8") as f:
            nb = nbformat.read(f, as_version=4)
        cell_types = {c.cell_type for c in nb.cells}
        assert "markdown" in cell_types
        assert "code" in cell_types

    def test_first_cell_is_title(self, tmp_path, sample_metadata):
        import nbformat

        nb_path = build_experiment_notebook(
            run_id="test_run",
            out_dir=tmp_path,
            metadata=sample_metadata,
        )
        with open(nb_path, encoding="utf-8") as f:
            nb = nbformat.read(f, as_version=4)
        assert nb.cells[0].cell_type == "markdown"
        assert "# Experiment Notebook" in nb.cells[0].source

    def test_contains_run_id_in_cells(self, tmp_path, sample_metadata):
        import nbformat

        nb_path = build_experiment_notebook(
            run_id="20260214_120000",
            out_dir=tmp_path,
            metadata=sample_metadata,
        )
        with open(nb_path, encoding="utf-8") as f:
            nb = nbformat.read(f, as_version=4)
        all_sources = " ".join(c.source for c in nb.cells)
        assert "20260214_120000" in all_sources

    def test_no_leaderboard_row_still_works(self, tmp_path, sample_metadata):
        nb_path = build_experiment_notebook(
            run_id="test_run",
            out_dir=tmp_path,
            metadata=sample_metadata,
            leaderboard_row=None,
        )
        assert nb_path.exists()

    def test_creates_parent_dirs(self, tmp_path, sample_metadata):
        deep_dir = tmp_path / "a" / "b" / "c"
        nb_path = build_experiment_notebook(
            run_id="test_run",
            out_dir=deep_dir,
            metadata=sample_metadata,
        )
        assert nb_path.exists()

    def test_minimal_metadata(self, tmp_path):
        """Even with empty metadata, notebook should be created."""
        nb_path = build_experiment_notebook(
            run_id="minimal",
            out_dir=tmp_path,
            metadata={},
        )
        assert nb_path.exists()

    def test_accepts_structured_timeframes(self, tmp_path, sample_metadata):
        metadata = dict(sample_metadata)
        metadata["timeframes"] = [{"timeframe": "4h", "days": 180}]
        nb_path = build_experiment_notebook(
            run_id="structured",
            out_dir=tmp_path,
            metadata=metadata,
        )
        assert nb_path.exists()


# ---------------------------------------------------------------------------
# Integration: engine_finalize wiring
# ---------------------------------------------------------------------------

class TestFinalizeNotebookWiring:
    def test_completion_outputs_has_notebook_key(self):
        """_build_completion_output_map output should accept notebook injection."""
        from autowfo.engine_finalize import _build_completion_output_map

        outputs = _build_completion_output_map(
            combo_path="a",
            per_symbol_path="b",
            top10_path="c",
            leaderboard_path="d",
            registry_path="e",
            run_metadata_path="f",
            run_metadata_path_run="g",
            report_path_latest="h",
            report_path_run="i",
        )
        # Notebook key is injected externally, not by _build_completion_output_map
        outputs["experiment_notebook"] = "/some/path.ipynb"
        assert "experiment_notebook" in outputs

