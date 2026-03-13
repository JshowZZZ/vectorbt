"""AWF-115 gate: engine facade no longer re-exports private helpers."""

from __future__ import annotations

import importlib
import inspect

import pytest


SUB_MODULES = [
    "autowfo.engine_helpers",
    "autowfo.engine_runtime",
    "autowfo.engine_report",
    "autowfo.engine_search",
    "autowfo.engine_finalize",
]


def test_engine_facade_exports_only_default_config():
    engine = importlib.import_module("autowfo.engine")
    helpers = importlib.import_module("autowfo.engine_helpers")

    assert hasattr(engine, "DEFAULT_CONFIG")
    assert engine.DEFAULT_CONFIG is helpers.DEFAULT_CONFIG

    private_callables = [
        name
        for name in dir(engine)
        if name.startswith("_") and callable(getattr(engine, name))
    ]
    assert not private_callables, f"engine.py must not export private helpers: {private_callables}"


def test_private_helpers_available_from_source_modules():
    search_mod = importlib.import_module("autowfo.engine_search")
    runtime_mod = importlib.import_module("autowfo.engine_runtime")
    assert callable(getattr(search_mod, "_run_search_for_timeframe"))
    assert callable(getattr(runtime_mod, "_resolve_regime_signals"))


@pytest.mark.parametrize("mod_name", SUB_MODULES)
def test_sub_modules_import_independently(mod_name):
    mod = importlib.import_module(mod_name)
    assert mod is not None


class TestSubModuleLineCount:
    MAX_LINES = 1800

    @pytest.mark.parametrize("mod_name", SUB_MODULES)
    def test_sub_module_line_count(self, mod_name):
        mod = importlib.import_module(mod_name)
        src_file = inspect.getfile(mod)
        with open(src_file, encoding="utf-8") as f:
            line_count = sum(1 for _ in f)
        assert line_count <= self.MAX_LINES, f"{mod_name} has {line_count} lines (limit: {self.MAX_LINES})"


def test_run_finalize_pipeline_is_keyword_only():
    from autowfo.engine_finalize import _run_finalize_pipeline

    sig = inspect.signature(_run_finalize_pipeline)
    for name, param in sig.parameters.items():
        assert param.kind == inspect.Parameter.KEYWORD_ONLY, (
            f"_run_finalize_pipeline param '{name}' is not keyword-only"
        )


def test_build_completion_output_map_returns_dict():
    from autowfo.engine_finalize import _build_completion_output_map

    result = _build_completion_output_map(
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
    assert isinstance(result, dict)
    assert "combo_summary" in result

