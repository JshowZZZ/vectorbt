# AWF-125 Implementation Report

## Header

| Field | Value |
|-------|-------|
| AWF ID | AWF-125 |
| Title | Indicator Plugin System |
| Phase | 20 |
| Codex completion date | 2026-02-27 |
| Spec reference | `plans/AUTOWFO_PHASE20_SPEC.md#AWF-125` |
| Architect review date | 2026-02-27 |
| Review result | ✓ APPROVED |

## 1. Files Created / Modified (Codex)

| Status | File | Reason |
|--------|------|--------|
| created | `scripts/autowfo/indicators/__init__.py` | Implemented plugin auto-discovery and `REGISTRY` construction with warning-based skip on import failure |
| created | `scripts/autowfo/indicators/rsi.py` | Added RSI plugin contract metadata and `compute()` implementation (pandas_ta + pandas fallback) |
| created | `scripts/autowfo/indicators/macd.py` | Added MACD plugin contract metadata and `compute()` implementation (MACD line output) |
| created | `scripts/autowfo/indicators/bb.py` | Added Bollinger Band position plugin with `compute()` returning normalized lower/upper band position |
| created | `scripts/autowfo/indicators/ema.py` | Added EMA distance plugin returning `close / ema - 1` |
| created | `scripts/autowfo/indicators/volume.py` | Added volume ratio plugin returning `volume / rolling_mean(volume)` |
| created | `tests/test_autowfo_indicators.py` | Added regression coverage for all AWF-125 exit criteria |
| modified | `plans/AUTOWFO_TODO.md` | Updated AWF-125 status to `done` and appended session log note |

**Files intentionally NOT touched**:
- `scripts/autowfo/strategy.py` (not modified per spec constraint)
- `scripts/autowfo/strategy_schema.py` (not modified per spec constraint)
- `scripts/autowfo/engine_*.py` (not modified per spec constraint)
- `scripts/control_panel*.py` (not modified per spec constraint)

## 2. Implementation Summary (Codex)

Implemented a new `scripts/autowfo/indicators` package with import-time auto-discovery that scans local plugin files and builds `REGISTRY` by `INDICATOR_ID`. Added five built-in indicator plugins (`RSI`, `MACD`, `BB`, `EMA`, `Volume`) that all expose the required module attributes and implement `compute(ohlcv_df, params) -> pd.Series` without mutating input data. Each plugin uses optional `pandas_ta` when available and falls back to manual pandas calculations to keep behavior robust in minimal environments. Added targeted tests for registry shape, dynamic plugin discovery, syntax-error plugin skip/warning behavior, importability, index alignment, and input immutability.

## 3. Deviations from Spec (Codex)

None.

## 4. Exit Criteria Checklist (Codex)

- [x] `from scripts.autowfo.indicators import REGISTRY` succeeds; `len(REGISTRY) == 5`
- [x] `REGISTRY["RSI"]`, `["MACD"]`, `["BB"]`, `["EMA"]`, `["Volume"]` all accessible
- [x] Adding a 6th `.py` file with valid `INDICATOR_ID` auto-appears in REGISTRY (test this)
- [x] Each `compute()` returns `pd.Series` with index identical to input `ohlcv_df.index`
- [x] Each `compute()` does not modify input `ohlcv_df` in place (test with `.copy()` comparison)
- [x] Plugin with syntax error in its file is skipped with warning, REGISTRY still loads remaining plugins
- [x] All tests: N passed, 0 failed

## 5. Test Results (Codex)

**Verification command run**:

```bash
pytest tests/test_autowfo_indicators.py -v
```

**Result**:

```text
13 passed, 0 failed, 0 errors
```

**New tests added**: 13 tests in `tests/test_autowfo_indicators.py`

**Specific test coverage for exit criteria**:

| Exit criterion | Test name | Result |
|----------------|-----------|--------|
| REGISTRY import + count + named keys | `test_registry_contains_expected_plugins` | pass |
| Add a 6th valid plugin auto-discovered | `test_registry_auto_discovers_new_plugin` | pass |
| Syntax-error plugin skipped with warning | `test_registry_skips_syntax_error_plugin_with_warning` | pass |
| Every plugin `compute()` returns Series with same index | `test_compute_returns_series_with_input_index_and_no_inplace_mutation` | pass |
| `compute()` does not mutate input DataFrame | `test_compute_returns_series_with_input_index_and_no_inplace_mutation` | pass |
| Each plugin independently importable | `test_plugin_module_importable` | pass |

## 6. Cross-Phase Interface Exposure (Codex)

**Interface exposed**:

```python
def compute(ohlcv_df: pd.DataFrame, params: dict) -> pd.Series:
    ...
```

**Consuming phase**: Phase 21, AWF-130 and AWF-131

**Contract test location**: `tests/test_autowfo_indicators.py::test_compute_returns_series_with_input_index_and_no_inplace_mutation`

## 7. Known Issues / Risks (Codex)

None.

## 8. BLOCKER (if applicable) (Codex)

**Status**: NOT BLOCKED

---
# ARCHITECT REVIEW
> Reviewed by: Claude Sonnet 4.6 — 2026-02-27
---

## R1. Architecture Alignment

- [x] Files match AWF spec (no unexpected additions/omissions)
- [x] Module contracts follow Architecture V2 §6
- [x] No unexpected cross-module imports
- [x] Cross-phase interface defined correctly

**Notes**:
- 7 files created, exactly matching spec. No files outside scope were touched.
- All 5 plugins expose `INDICATOR_ID`, `DISPLAY_NAME`, `PARAMS`, `CONDITION_OPERATORS`, `compute()` — contract match.
- Imports are clean: only `pandas`, `numpy`, stdlib, and optional `pandas_ta`. No imports from `strategy.py`, `engine_*.py`, or `control_panel*.py`.
- `__init__.py` uses `f"{__name__}.{path.stem}"` instead of spec's hardcoded `f"scripts.autowfo.indicators.{path.stem}"` — this is an improvement (resilient to package relocation). Acceptable.
- `compute()` signature matches spec exactly: `(ohlcv_df: pd.DataFrame, params: dict) -> pd.Series`.

## R2. Code Quality

- [x] No hardcoded config values
- [x] No circular imports
- [x] Error handling only at boundaries
- [x] Scope limited to AWF — no over-engineering

**Notes**:
- Default params read from `PARAMS` dict via `params.get(key, PARAMS[key]["default"])` — not hardcoded.
- `pandas_ta` import is `try/except` at module level (external library boundary) — correct pattern.
- `pandas_ta` API calls are `try/except` with fallback to manual implementation — reasonable defensive boundary.
- `bb.py:27` and `ema.py:23` guard against zero division with `.replace(0.0, np.nan)` — appropriate.
- No unnecessary abstractions, no helper classes, no extra utilities beyond what's needed.
- `REGISTRY.clear()` in `_discover()` ensures in-place dict update so external references stay valid — good.

## R3. Test Quality

- [x] All exit criteria have corresponding tests
- [x] Edge cases covered (None, NaN, empty) — see note
- [x] Cross-phase interface has contract test
- [x] Test depth is reasonable

**Notes**:
- 13 tests, all passing. Coverage:
  - REGISTRY shape + keys: `test_registry_contains_expected_plugins`
  - Independent importability: `test_plugin_module_importable` (5 parametrized)
  - Contract test (index alignment + no mutation): `test_compute_returns_series_with_input_index_and_no_inplace_mutation` (5 parametrized)
  - Auto-discovery: `test_registry_auto_discovers_new_plugin`
  - Error resilience: `test_registry_skips_syntax_error_plugin_with_warning`
- Auto-discovery test creates temp files in source dir — acceptable since auto-discovery by definition requires files in the actual plugin directory. Cleanup via `finally` is correct.
- Edge case note: No explicit test for empty DataFrame (0 rows) or NaN-filled close column. The spec states "no NaNs guaranteed at head" (caller responsibility), so this is not a spec gap. Acceptable without correction.
- Verified by Architect: `pytest tests/test_autowfo_indicators.py -v` → **13 passed in 4.01s**.

## R4. Review Result

**Result**: ✓ APPROVED

**Correction AWFs issued**: None

**Soft gate status** (⚠️ cross-phase):
- `compute(ohlcv_df, params) -> pd.Series` contract verified. Phase 21 may proceed using this interface: **YES**

