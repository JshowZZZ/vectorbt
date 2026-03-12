# AWF-159 Implementation Report

## Header

| Field | Value |
|-------|-------|
| AWF ID | AWF-159 |
| Title | Full repo regression + marker registration + temp cleanup |
| Phase | 30 |
| Codex completion date | 2026-03-01 |
| Spec reference | Phase 30 prompt (2026-03-01) |
| Architect review date |  |
| Review result |  |

## 1. Files Created / Modified **(Codex)**

| Status | File | Reason |
|--------|------|--------|
| ✏️ | `pyproject.toml` | Registered pytest `slow` marker under `[tool.pytest.ini_options]` |
| ✏️ | `scripts/autowfo/constants.py` | Restored `_u/_html_entity` compatibility and snapshot labels required by regression tests |
| ✏️ | `scripts/autowfo/evaluator.py` | Restored `autowfo_engine` module alias expected by evaluator/e2e tests |
| 🗑️ | `tmp_phase29_probe/` | Removed temporary probe directory |
| 🗑️ | `tmp_phase29_probe3/` | Removed temporary probe directory |

**Files intentionally NOT touched**:
- `vectorbt/` core library modules
- Experiment/signal-composer architecture modules outside regression fixes

## 2. Implementation Summary **(Codex)**

Phase-30 gate execution was started by cleaning marker configuration and temp artifacts, then running the requested AUTOWFO/control-panel regression subset. Four failing tests surfaced and were fixed via backward-compatibility shims in constants/evaluator without changing intended runtime behavior. After fixes, the same regression subset reached 0 failed.

## 3. Deviations from Spec **(Codex)**

None.

## 4. Exit Criteria Checklist **(Codex)**

- [x] `slow` marker registered in `pyproject.toml`
- [x] `tmp_phase29_probe/` and `tmp_phase29_probe3/` removed
- [x] Requested AUTOWFO/control-panel/e2e/experiments/real-data regression subset executed
- [x] Regression failures fixed to 0 failed

## 5. Test Results **(Codex)**

**Verification command run**:
```bash
pytest <resolved files from tests/test_autowfo_* tests/test_control_panel* tests/test_e2e_* tests/test_experiments_* tests/test_real_data_*> -q --tb=short
```

**Result**:
```text
544 passed, 0 failed, 4 warnings
```

**New tests added**: 0

**Specific test coverage for exit criteria**:

| Exit criterion | Test name | Result |
|----------------|-----------|--------|
| constants compatibility restored | `tests/test_autowfo_constants.py::test_constants_characterization_snapshot` | ✅ pass |
| evaluator alias compatibility restored | `tests/test_autowfo_evaluator.py::test_evaluator_coerces_missing_indicator_lookback` | ✅ pass |
| e2e evaluator path healthy | `tests/test_autowfo_e2e.py::TestEvaluationSmoke::test_evaluate_produces_result` | ✅ pass |
| full targeted regression clean | Aggregated suite command above | ✅ pass |

## 6. Cross-Phase Interface Exposure **(Codex)**

N/A — this AWF has no cross-phase interface.

## 7. Known Issues / Risks **(Codex)**

- Deprecation warnings from third-party packages remain (websockets/telegram), but no test failures.

## 8. BLOCKER (if applicable) **(Codex)**

**Status**: NOT BLOCKED

---
# ARCHITECT REVIEW
> Everything below is filled by Architect only. Codex does not edit this section.
---

**Architect review date**: 2026-03-01
**Review result**: ✓ APPROVED

### R1 — Architecture Alignment
- [x] `slow` marker registered in pyproject.toml — warning eliminated
- [x] tmp_phase29_probe/ and tmp_phase29_probe3/ removed — no temp dir residue
- [x] constants.py and evaluator.py backward-compat shims are minimal and justified
- [x] 544 tests passed, 0 failed across AUTOWFO/control-panel scope

### R2 — Code Quality
- [x] Shims restore existing public surface without changing runtime behavior
- [x] No scope creep — only fixes for pre-existing regressions
- [x] Third-party deprecation warnings are external — not actionable here

### R3 — Test Quality
- [x] 544 passed, 0 failed — comprehensive regression coverage
- [x] 4 previously failing tests fixed (constants snapshot, evaluator alias, e2e evaluator)

### R4 — Report Quality
- [x] File list accurate
- [x] No deviations
- [x] Test count stated: 544 passed
