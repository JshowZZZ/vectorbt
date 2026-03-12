# AWF-127 Implementation Report

## Header

| Field | Value |
|-------|-------|
| AWF ID | AWF-127 |
| Title | Experiment Definition Model |
| Phase | 20 |
| Codex completion date | 2026-02-27 |
| Spec reference | `plans/AUTOWFO_PHASE20_SPEC.md#AWF-127` |
| Architect review date | 2026-02-27 |
| Review result | APPROVED |

## 1. Files Created / Modified (Codex)

| Status | File | Reason |
|--------|------|--------|
| created | `scripts/autowfo/experiment.py` | Implemented `Experiment` class with load/save, validation, and deterministic grid expansion |
| created | `tests/test_autowfo_experiment.py` | Added unit tests for all required validation rules and expansion behavior |
| modified | `plans/AUTOWFO_TODO.md` | Marked AWF-127 `done` and added session log entry |

**Files intentionally NOT touched**:
- All pre-existing source files outside this AWF scope

## 2. Implementation Summary (Codex)

Added a new `Experiment` model that encapsulates config lifecycle (`from_dict`, `from_json`, `save`) and enforces spec-defined validation before use. Validation integrates with AWF-125/126 registries to verify indicator IDs and condition operators, and enforces all risk/WF/mode constraints from the AWF block. Implemented deterministic `expand_grid()` that products trigger/action/risk axes plus direction expansion (`both` -> long+short). Added default handling for empty `*_values` lists, including plugin default fallback via indicator `PARAMS`.

## 3. Deviations from Spec (Codex)

None.

## 4. Exit Criteria Checklist (Codex)

- [x] `Experiment.from_dict(valid_config)` succeeds without exception
- [x] `experiment.expand_grid()` returns correct count (product of all `*_values` lengths × 2 for direction="both")
- [x] Grid order is deterministic (run twice, same order)
- [x] All 9 validation rules raise `ValueError` with descriptive message
- [x] `direction="both"` produces long AND short entries
- [x] `experiment.save(path)` writes valid JSON that can be round-tripped with `from_json()`
- [x] All tests: N passed, 0 failed

## 5. Test Results (Codex)

**Verification command run**:

```bash
pytest tests/test_autowfo_experiment.py -v
```

**Result**:

```text
15 passed, 0 failed, 0 errors
```

**New tests added**: 15 tests in `tests/test_autowfo_experiment.py`

**Specific test coverage for exit criteria**:

| Exit criterion | Test name | Result |
|----------------|-----------|--------|
| Valid config loads | `test_from_dict_valid_config` | pass |
| Grid count + both-direction expansion | `test_expand_grid_returns_expected_count_and_direction_both` | pass |
| Deterministic order | `test_expand_grid_is_deterministic` | pass |
| Empty `*_values` default handling | `test_expand_grid_empty_values_uses_default` | pass |
| Validation rules 1~9 | `test_validation_rule_1_experiment_id` ... `test_validation_rule_9_mode_allowed_values` | pass |
| JSON round-trip | `test_save_and_from_json_roundtrip` | pass |

## 6. Cross-Phase Interface Exposure (Codex)

N/A — this AWF has no cross-phase interface.

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
- [x] Module contracts follow Architecture V2 §3
- [x] No unexpected cross-module imports
- [x] Cross-phase interface defined correctly (if applicable)

**Notes**:
Single file `scripts/autowfo/experiment.py` as specified. `Experiment` class implements `from_dict()`, `from_json()`, `save()`, `validate()`, `expand_grid()` — all per spec. Imports AWF-125 `REGISTRY` and AWF-126 `OPERATOR_REGISTRY` for validation rules 4 & 5 — these are expected cross-module references. `artifact_dir` property returns relative `pathlib.Path` per Architecture V2 §3 experiment model.

## R2. Code Quality

- [x] No hardcoded config values
- [x] No circular imports
- [x] Error handling only at boundaries
- [x] Scope limited to AWF no over-engineering

**Notes**:
Validation raises `ValueError` with descriptive messages at `from_dict()` boundary — correct pattern. `expand_grid()` uses `itertools.product` for deterministic Cartesian product. Empty `*_values` fallback to indicator plugin `PARAMS` default is a clean design. `_build_side_grid()`, `_expand_condition_values()`, `_build_risk_grid()` are well-scoped internal helpers. `ALLOWED_MODES` set is appropriate for validation rule 9. No over-engineering detected.

## R3. Test Quality

- [x] All exit criteria have corresponding tests
- [x] Edge cases covered (None, NaN, empty)
- [x] Cross-phase interface has contract test
- [x] Test depth is reasonable

**Notes**:
15 tests: valid config load, grid count with direction="both" (16 = 2×2×1×2×1×1×2), deterministic order, empty values default, all 9 validation rules individually tested, JSON roundtrip, artifact_dir path. Empty `*_values` default test covers important edge case. Each validation rule has its own focused test — excellent granularity. N/A for cross-phase contract test (no cross-phase interface exposed).

## R4. Review Result

**Result**: APPROVED

**Correction AWFs issued**: None

**Soft gate status**: N/A (no cross-phase interface)

