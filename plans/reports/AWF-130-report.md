# AWF-130 Implementation Report

## Header

| Field | Value |
|-------|-------|
| AWF ID | AWF-130 |
| Title | Signal Composer |
| Phase | 21 |
| Codex completion date | 2026-02-27 |
| Spec reference | `plans/AUTOWFO_PHASE21_SPEC.md#AWF-130` |
| Architect review date | 2026-02-28 |
| Review result | APPROVED |

## 1. Files Created / Modified (Codex)

| Status | File | Reason |
|--------|------|--------|
| created | `scripts/autowfo/signal_composer.py` | Implemented `SignalResult`, `compose()`, condition evaluation helper, and cross-timeframe trigger-to-action alignment |
| created | `tests/test_autowfo_signal_composer.py` | Added unit tests for same-timeframe, cross-timeframe, direction split, require_all AND/OR, and NaN->False behavior |
| modified | `plans/AUTOWFO_TODO.md` | Marked AWF-130 as done and appended session log entry |

**Files intentionally NOT touched**:
- `scripts/autowfo/engine_*.py` (not modified)
- `scripts/control_panel*.py` (not modified)
- `scripts/autowfo/data.py` (not modified)

## 2. Implementation Summary (Codex)

Implemented a dedicated signal composition module that consumes trigger/action OHLCV + combo params and returns a `SignalResult` with four bool series aligned to action timeframe. `_evaluate_conditions()` computes indicator series via plugin registry and applies operator dispatch from AWF-126, with per-side `require_all` handling (AND/OR across indicators) and strict bool normalization (`NaN -> False`). Added `_align_trigger_to_action()` using the specified rolling action-bar window rule `(t - T2_duration, t]`, with first action bar forced to `False` and empty/all-false trigger handling. `compose()` now handles long/short direction routing and keeps exit signals all-false for runner-managed SL/TP.

## 3. Deviations from Spec (Codex)

None.

## 4. Exit Criteria Checklist (Codex)

- [x] `compose()` returns `SignalResult` with 4 bool Series, all same length as `action_ohlcv.index`
- [x] Same-timeframe, same-asset case works (trigger_signal reindexed, no alignment needed)
- [x] Cross-timeframe case: trigger 1h, action 4h; trigger signals within T2 window propagate correctly
- [x] `require_all=True` ANDs conditions; `require_all=False` ORs them
- [x] Direction "long" -> `entry_short` all-False; "short" -> `entry_long` all-False
- [x] NaN indicator values -> False signals (not NaN, not error)
- [x] Exit signals are all-False (SL/TP delegated to runner)
- [x] All tests pass: N passed, 0 failed

## 5. Test Results (Codex)

**Verification command run**:

```bash
pytest tests/test_autowfo_signal_composer.py -v
python -c "from scripts.autowfo.signal_composer import compose, SignalResult; print('OK')"
```

**Result**:

```text
6 passed, 0 failed, 0 errors
OK
```

**New tests added**: 6 tests in `tests/test_autowfo_signal_composer.py`

**Specific test coverage for exit criteria**:

| Exit criterion | Test name | Result |
|----------------|-----------|--------|
| `SignalResult` contract + same-timeframe behavior | `test_compose_same_timeframe_long_direction` | pass |
| Direction split to short entries | `test_compose_short_direction_routes_entry_short` | pass |
| `require_all=False` OR behavior | `test_require_all_false_uses_or` | pass |
| `require_all=True` AND behavior | `test_require_all_true_uses_and` | pass |
| Cross-timeframe window alignment | `test_cross_timeframe_alignment_propagates_any_trigger` | pass |
| NaN input -> False (no NaN output) | `test_nan_values_produce_false_not_nan` | pass |

## 6. Cross-Phase Interface Exposure (Codex)

**Interface exposed**:

```python
def compose(
    trigger_ohlcv: pd.DataFrame,
    action_ohlcv: pd.DataFrame,
    experiment: "Experiment",
    combo_params: dict,
) -> SignalResult:
    ...
```

**Consuming phase**: Phase 21 AWF-131 (Experiment Runner), and later Phase 22+ pipeline integration.

**Contract test location**: `tests/test_autowfo_signal_composer.py::test_compose_same_timeframe_long_direction`

## 7. Known Issues / Risks (Codex)

For multi-indicator configs that reuse identical parameter names across indicators, combo key suffixing behavior from `expand_grid()` can make per-indicator parameter disambiguation ambiguous; current implementation follows side-prefixed params as provided and works for Phase 21 test scope.

## 8. BLOCKER (if applicable) (Codex)

**Status**: NOT BLOCKED

---
# ARCHITECT REVIEW
> Everything below is filled by Architect only. Codex does not edit this section.
---

## R1. Architecture Alignment

- [x] Files match AWF spec (no unexpected additions/omissions)
- [x] Module contracts follow Architecture V2 §7
- [x] No unexpected cross-module imports
- [x] Cross-phase interface defined correctly (if applicable)

**Notes**:
`signal_composer.py` implements `SignalResult` dataclass and `compose()` function exactly per spec. Imports from AWF-125 (`REGISTRY`) and AWF-126 (`apply`) — expected Phase 20 dependencies. No imports from `engine_*.py` or `control_panel*.py` — constraint satisfied. `_evaluate_conditions()` follows the spec algorithm: compute indicator → apply condition → AND/OR merge. `_align_trigger_to_action()` implements the `(t - T2_duration, t]` window rule with first-bar-False per spec §7.2. Cross-phase interface `compose()` signature matches spec exactly.

## R2. Code Quality

- [x] No hardcoded config values
- [x] No circular imports
- [x] Error handling only at boundaries
- [x] Scope limited to AWF no over-engineering

**Notes**:
Clean helper decomposition: `_extract_side_params()`, `_resolve_indicator_name()`, `_resolve_operator()` handle the combo_params key mapping. `_as_bool_series()` ensures NaN→False normalization throughout. Direction validation in `compose()` raises ValueError for invalid direction — correct boundary check. Exit signals all-False per spec (SL/TP delegated to runner). The `_align_trigger_to_action()` loop over action bars is O(n*m) but acceptable for Phase 21 scope; optimization can come later if needed. No over-engineering detected.

**Observation (non-blocking)**: `_align_trigger_to_action()` uses `for i in range(1, len(action_index))` with `.loc[]` slicing inside the loop. For large datasets (>10k bars), this could be slow. Noted for potential Phase 22+ optimization but NOT blocking for Phase 21.

## R3. Test Quality

- [x] All exit criteria have corresponding tests
- [x] Edge cases covered (None, NaN, empty)
- [x] Cross-phase interface has contract test
- [x] Test depth is reasonable

**Notes**:
6 tests cover: same-timeframe long (full SignalResult contract + dtype assertions), short direction routing, require_all=False OR, require_all=True AND, cross-timeframe 1h→4h alignment (window propagation), NaN→False (no NaN output). The `_indicator()` helper using `SimpleNamespace` is a clean mock pattern. `_build_experiment()` helper keeps tests DRY. Cross-timeframe test verifies `[False, True, True]` pattern matching trigger signals at bars 2 and 6 within 4h windows — correct.

## R4. Review Result

**Result**: APPROVED

**Correction AWFs issued**: None

**Soft gate status**:
- `compose()` interface verified — Phase 22+ may consume: YES
