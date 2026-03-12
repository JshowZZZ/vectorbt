# AWF-133 Implementation Report

## Header

| Field | Value |
|-------|-------|
| AWF ID | AWF-133 |
| Title | Dual-Direction Signal Tests |
| Phase | 21 |
| Codex completion date | 2026-02-27 |
| Spec reference | `plans/AUTOWFO_PHASE21_SPEC.md#AWF-133` |
| Architect review date | 2026-02-28 |
| Review result | APPROVED |

## 1. Files Created / Modified (Codex)

| Status | File | Reason |
|--------|------|--------|
| created | `tests/test_autowfo_dual_direction.py` | Added integration tests covering dual-direction pipeline behavior across `Experiment.expand_grid()` + `compose()` + `ExperimentRunner` + SQLite writes |
| modified | `plans/AUTOWFO_TODO.md` | Marked AWF-133 as done and appended session log entry |

**Files intentionally NOT touched**:
- `scripts/control_panel*.py` (not modified)
- `scripts/autowfo/engine_*.py` (not modified)
- `scripts/autowfo/data.py` (not modified)

## 2. Implementation Summary (Codex)

Implemented an integration test suite that exercises the Phase 21 execution path end-to-end using synthetic OHLCV and `tmp_path` storage only. The suite validates direction expansion/storage (`both`, `long`, `short`), direction-specific entry asymmetry in `compose()`, cross-timeframe alignment behavior under dual-direction combos, and persistence behavior when no trigger signals fire. All scenarios run through real `Experiment`, real `compose`, and real `ExperimentRunner` with SQLite verification, ensuring the integration contract between AWF-130 and AWF-131 is covered.

## 3. Deviations from Spec (Codex)

None.

## 4. Exit Criteria Checklist (Codex)

- [x] Both-direction experiment produces long AND short rows in SQLite
- [x] Long-only experiment produces only long rows
- [x] Short-only experiment produces only short rows
- [x] Cross-timeframe alignment works with both directions
- [x] Zero-signal combo stored correctly (`oos_n_trades=0`)
- [x] All tests pass: N passed, 0 failed

## 5. Test Results (Codex)

**Verification command run**:

```bash
pytest tests/test_autowfo_dual_direction.py -v
```

**Result**:

```text
6 passed, 0 failed, 0 errors
```

**New tests added**: 6 tests in `tests/test_autowfo_dual_direction.py`

**Specific test coverage for exit criteria**:

| Exit criterion | Test name | Result |
|----------------|-----------|--------|
| both-direction rows in SQLite | `test_both_directions_produce_rows` | pass |
| long-only produces only long rows | `test_long_only_experiment_stores_only_long` | pass |
| short-only produces only short rows | `test_short_only_experiment_stores_only_short` | pass |
| signal asymmetry (entry_long/entry_short mutual exclusivity) | `test_signal_asymmetry_entries_are_mutually_exclusive` | pass |
| cross-timeframe + dual direction alignment | `test_cross_timeframe_alignment_with_both_directions` | pass |
| empty signals still stored with `oos_n_trades=0` | `test_empty_signals_still_stored_with_zero_trades` | pass |

## 6. Cross-Phase Interface Exposure (Codex)

N/A - this AWF has no new cross-phase interface.

## 7. Known Issues / Risks (Codex)

None.

## 8. BLOCKER (if applicable) (Codex)

**Status**: NOT BLOCKED

---
# ARCHITECT REVIEW
> Everything below is filled by Architect only. Codex does not edit this section.
---

## R1. Architecture Alignment

- [x] Files match AWF spec (no unexpected additions/omissions)
- [x] Module contracts follow Architecture V2 §2.6
- [x] No unexpected cross-module imports
- [x] Cross-phase interface defined correctly (if applicable)

**Notes**:
Single test file `tests/test_autowfo_dual_direction.py` as specified. Tests import real `Experiment`, `compose`, `ExperimentRunner`, `ArtifactStore` — genuine integration tests, not mocked units. All 6 spec test scenarios covered: both-direction rows, long-only, short-only, signal asymmetry (mutual exclusivity), cross-timeframe+dual direction, zero-signal storage. `_make_ohlcv()` helper with `trend` and `spike_indices` parameters enables controlled signal triggering — good test design.

## R2. Code Quality

- [x] No hardcoded config values
- [x] No circular imports
- [x] Error handling only at boundaries
- [x] Scope limited to AWF no over-engineering

**Notes**:
N/A for production code — this AWF is test-only. Test helpers are well-structured: `_build_experiment()` parameterizes direction/timeframes/multiplier, `_run_experiment()` returns both `RunResult` and SQLite `conn` for direct verification. `spike_indices` parameter allows precise volume spike placement to control which bars trigger signals. All SQLite connections closed in `finally` blocks — proper resource management in tests.

## R3. Test Quality

- [x] All exit criteria have corresponding tests
- [x] Edge cases covered (None, NaN, empty)
- [x] Cross-phase interface has contract test
- [x] Test depth is reasonable

**Notes**:
6 integration tests exercise the full pipeline end-to-end:
1. `test_both_directions_produce_rows` — verifies both long+short rows in SQLite, n_combos=2
2. `test_long_only_experiment_stores_only_long` — direction constraint on grid+storage
3. `test_short_only_experiment_stores_only_short` — symmetric verification
4. `test_signal_asymmetry_entries_are_mutually_exclusive` — `entry_long & entry_short` never both True
5. `test_cross_timeframe_alignment_with_both_directions` — 1h trigger → 4h action, verifies alignment pattern `[False, True, True, True, False]` for both directions
6. `test_empty_signals_still_stored_with_zero_trades` — high multiplier (2.0) ensures no trigger fires on flat volume, `oos_n_trades=0` verified

The cross-timeframe test (scenario 5) is particularly valuable — it validates the alignment algorithm under real Experiment/compose/runner integration with both directions.

## R4. Review Result

**Result**: APPROVED

**Correction AWFs issued**: None

**Soft gate status**: N/A (no cross-phase interface)
