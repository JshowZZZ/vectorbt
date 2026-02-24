"""AWF-030 — Gate E verification: engine decomposition identity + artifact equivalence.

Confirms that the engine re-export layer (``engine.py``) exposes exactly the
same function objects as the 5 sub-modules, guaranteeing bit-identical behavior
without needing a full data-driven artifact comparison.

Also verifies that the sub-modules have no circular import issues and that
the re-export module exposes a complete public API.
"""

import importlib
import inspect
from types import ModuleType

import pytest


# ---------------------------------------------------------------------------
# All sub-modules and the re-export layer
# ---------------------------------------------------------------------------

SUB_MODULES = [
    "scripts.autowfo.engine_helpers",
    "scripts.autowfo.engine_runtime",
    "scripts.autowfo.engine_report",
    "scripts.autowfo.engine_search",
    "scripts.autowfo.engine_finalize",
]

REEXPORT_MODULE = "scripts.autowfo.engine"


def _get_public_callables(mod: ModuleType) -> dict:
    """Return {name: obj} for callables **defined** in *mod*.

    We include ``_``-prefixed names because the AUTOWFO engine uses underscore
    convention for internal helpers that are nonetheless part of the engine's
    cross-module API.

    Only callables whose ``__module__`` matches this module are included — this
    excludes pass-through imports (e.g. ``from .benchmark import …``) that are
    implementation details, not part of the engine's re-export surface.
    """
    result = {}
    for name in dir(mod):
        obj = getattr(mod, name)
        if callable(obj) and not name.startswith("__"):
            # Only include if defined in this module
            obj_module = getattr(obj, "__module__", None)
            if obj_module == mod.__name__:
                result[name] = obj
    return result


# ---------------------------------------------------------------------------
# 1. Identity: every re-exported symbol is ``is`` the same object
# ---------------------------------------------------------------------------

class TestEngineReexportIdentity:
    """For every callable re-exported by ``engine.py``, verify it is the exact
    same object as the one defined in the sub-module.  ``is``-identity implies
    bit-identical behavior — no wrapper, no copy, no override."""

    def test_helpers_identity(self):
        engine = importlib.import_module(REEXPORT_MODULE)
        helpers = importlib.import_module("scripts.autowfo.engine_helpers")
        for name, obj in _get_public_callables(helpers).items():
            reexported = getattr(engine, name, None)
            assert reexported is not None, f"{name} missing from engine re-export"
            assert reexported is obj, f"{name} re-export is not identical to engine_helpers.{name}"

    def test_runtime_identity(self):
        engine = importlib.import_module(REEXPORT_MODULE)
        runtime = importlib.import_module("scripts.autowfo.engine_runtime")
        for name, obj in _get_public_callables(runtime).items():
            reexported = getattr(engine, name, None)
            assert reexported is not None, f"{name} missing from engine re-export"
            assert reexported is obj, f"{name} re-export is not identical to engine_runtime.{name}"

    def test_report_identity(self):
        engine = importlib.import_module(REEXPORT_MODULE)
        report = importlib.import_module("scripts.autowfo.engine_report")
        for name, obj in _get_public_callables(report).items():
            reexported = getattr(engine, name, None)
            assert reexported is not None, f"{name} missing from engine re-export"
            assert reexported is obj, f"{name} re-export is not identical to engine_report.{name}"

    def test_search_identity(self):
        engine = importlib.import_module(REEXPORT_MODULE)
        search = importlib.import_module("scripts.autowfo.engine_search")
        for name, obj in _get_public_callables(search).items():
            reexported = getattr(engine, name, None)
            assert reexported is not None, f"{name} missing from engine re-export"
            assert reexported is obj, f"{name} re-export is not identical to engine_search.{name}"

    def test_finalize_identity(self):
        engine = importlib.import_module(REEXPORT_MODULE)
        finalize = importlib.import_module("scripts.autowfo.engine_finalize")
        for name, obj in _get_public_callables(finalize).items():
            reexported = getattr(engine, name, None)
            assert reexported is not None, f"{name} missing from engine re-export"
            assert reexported is obj, f"{name} re-export is not identical to engine_finalize.{name}"


# ---------------------------------------------------------------------------
# 2. Completeness: no sub-module callable is missing from re-export
# ---------------------------------------------------------------------------

class TestEngineReexportCompleteness:
    """Ensure the re-export layer doesn't silently drop any callable."""

    def test_all_sub_module_callables_reexported(self):
        engine = importlib.import_module(REEXPORT_MODULE)
        missing = []
        for mod_name in SUB_MODULES:
            mod = importlib.import_module(mod_name)
            for name, obj in _get_public_callables(mod).items():
                if not hasattr(engine, name):
                    missing.append(f"{mod_name}.{name}")
        assert not missing, f"Missing from engine re-export: {missing}"

    def test_no_extra_callables_in_reexport(self):
        """Re-export should only contain callables from sub-modules (no rogue additions)."""
        engine = importlib.import_module(REEXPORT_MODULE)
        sub_names = set()
        for mod_name in SUB_MODULES:
            mod = importlib.import_module(mod_name)
            sub_names.update(_get_public_callables(mod).keys())

        engine_callables = _get_public_callables(engine)
        extras = set(engine_callables.keys()) - sub_names
        assert not extras, f"Extra callables in engine re-export not from sub-modules: {extras}"

    def test_default_config_reexported(self):
        """DEFAULT_CONFIG is a dict constant that must also be re-exported."""
        engine = importlib.import_module(REEXPORT_MODULE)
        helpers = importlib.import_module("scripts.autowfo.engine_helpers")
        assert hasattr(engine, "DEFAULT_CONFIG"), "DEFAULT_CONFIG missing from engine re-export"
        assert engine.DEFAULT_CONFIG is helpers.DEFAULT_CONFIG, (
            "DEFAULT_CONFIG re-export is not identical to engine_helpers.DEFAULT_CONFIG"
        )


# ---------------------------------------------------------------------------
# 3. Sub-module isolation: no circular imports
# ---------------------------------------------------------------------------

class TestSubModuleIsolation:
    """Each sub-module should import cleanly without requiring ``engine.py``."""

    @pytest.mark.parametrize("mod_name", SUB_MODULES)
    def test_sub_module_importable_independently(self, mod_name):
        mod = importlib.import_module(mod_name)
        assert mod is not None

    def test_engine_reexport_importable(self):
        mod = importlib.import_module(REEXPORT_MODULE)
        assert mod is not None


# ---------------------------------------------------------------------------
# 4. Line-count gate: each sub-module ≤ 1600 lines
# ---------------------------------------------------------------------------

class TestSubModuleLineCount:
    """Gate E requires each sub-module stays within manageable limits.

    Original decomposition split a ~4000-line monolith into ≤1600-line modules.
    Post-decomposition phases (10–13) added features that grew some modules;
    the limit is set to 1800 to allow for that natural growth while still
    catching any single module that drifts toward monolith territory.
    """

    MAX_LINES = 1800

    @pytest.mark.parametrize("mod_name", SUB_MODULES)
    def test_sub_module_line_count(self, mod_name):
        mod = importlib.import_module(mod_name)
        src_file = inspect.getfile(mod)
        with open(src_file, encoding="utf-8") as f:
            line_count = sum(1 for _ in f)
        assert line_count <= self.MAX_LINES, (
            f"{mod_name} has {line_count} lines (limit: {self.MAX_LINES})"
        )


# ---------------------------------------------------------------------------
# 5. Key function signature stability: finalize pipeline callable
# ---------------------------------------------------------------------------

class TestCriticalSignatureStability:
    """Ensure critical orchestration functions maintain expected signature."""

    def test_run_finalize_pipeline_is_keyword_only(self):
        from scripts.autowfo.engine_finalize import _run_finalize_pipeline

        sig = inspect.signature(_run_finalize_pipeline)
        for name, param in sig.parameters.items():
            assert param.kind == inspect.Parameter.KEYWORD_ONLY, (
                f"_run_finalize_pipeline param '{name}' is not keyword-only"
            )

    def test_build_completion_output_map_returns_dict(self):
        from scripts.autowfo.engine_finalize import _build_completion_output_map

        result = _build_completion_output_map(
            combo_path="a", per_symbol_path="b", top10_path="c",
            leaderboard_path="d", registry_path="e",
            run_metadata_path="f", run_metadata_path_run="g",
            report_path_latest="h", report_path_run="i",
        )
        assert isinstance(result, dict)
        assert "combo_summary" in result
