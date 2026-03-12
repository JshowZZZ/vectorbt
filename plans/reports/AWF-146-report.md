# AWF-146 Implementation Report

## Header

| Field | Value |
|-------|-------|
| AWF ID | AWF-146 |
| Title | control_panel_legacy handler migration |
| Phase | 26 |
| Codex completion date | 2026-02-28 |
| Spec reference | User task brief (Phase 26, AWF-146) |
| Architect review date |  |
| Review result |  |

## 1. Files Created / Modified (Codex)

| Status | File | Reason |
|--------|------|--------|
| modified | `scripts/control_panel.py` | Ensured facade routing and compatibility exports remained stable after migration |
| modified | `scripts/control_panel_batch.py` | Added protected `_bind_cp_globals` guard to prevent route handler overwrite |
| modified | `scripts/control_panel_coverage.py` | Added protected `_bind_cp_globals` guard to prevent route handler overwrite |
| modified | `scripts/control_panel_results.py` | Added protected `_bind_cp_globals` guard to preserve read-route dispatch |
| modified | `scripts/control_panel_signals.py` | Added protected `_bind_cp_globals` guard and fixed feedback-adjusted export endpoint payload handling |
| modified | `scripts/control_panel_signals_feedback.py` | Added protected `_bind_cp_globals` guard for stable cross-module binding |
| modified | `scripts/control_panel_dashboard.py` | Added protected `_bind_cp_globals` guard so dashboard routes do not self-overwrite |
| modified | `scripts/control_panel_dashboard_routes.py` | Added protected `_bind_cp_globals` guard for deterministic route handling |

**Files intentionally NOT touched**:
- `scripts/control_panel_experiments.py`
- `scripts/autowfo/experiment.py`

## 2. Implementation Summary (Codex)

Completed the deep AWF-146 stabilization on top of the prior split by fixing a critical binding regression: `_bind_cp_globals` had been overwriting `try_handle_get/post`, causing intermittent 404s after first request. Added protected-name guards across migrated control-panel modules so handlers remain stable while still supporting deferred `_cp()` state sharing. Restored compatibility expected by existing tests (`cp.subprocess` monkeypatch surface) and corrected `/signals/export-feedback-adjusted-config` response construction.

## 3. Deviations from Spec (Codex)

None.

## 4. Exit Criteria Checklist (Codex)

- [x] `control_panel_legacy.py` reduced to compatibility shim (<=100L)
- [x] `control_panel.py` remains routing facade and dispatches to responsibility modules
- [x] Handler behavior and response format preserved (no endpoint contract change)
- [x] AWF-146 validation tests all pass

## 5. Test Results (Codex)

**Verification command run**:

```bash
pytest tests/test_control_panel.py tests/test_control_panel_experiments.py tests/test_experiments_ui_integration.py -q
```

**Result**:

```text
80 passed, 0 failed, 0 errors
```

**New tests added**: 0

**Specific test coverage for exit criteria**:

| Exit criterion | Test name | Result |
|----------------|-----------|--------|
| batch/coverage/signals/dashboard routes preserved | `tests/test_control_panel.py` integration suite | pass |
| experiments routes unaffected | `tests/test_control_panel_experiments.py` | pass |
| UI integration backend flow preserved | `tests/test_experiments_ui_integration.py` | pass |

## 6. Cross-Phase Interface Exposure (Codex)

N/A - this AWF has no cross-phase interface.

## 7. Known Issues / Risks (Codex)

`control_panel_signals.py` is 737 lines (within allowed ±50 buffer over 700 target) but still structurally dense; future follow-up split may improve maintainability.

## 8. BLOCKER (if applicable) (Codex)

**Status**: NOT BLOCKED

---
# ARCHITECT REVIEW
> Everything below is filled by Architect only. Codex does not edit this section.
---

**Architect review date**: 2026-02-28
**Review result**: ✓ APPROVED (with note)

### R1 — Architecture Alignment
- [x] `control_panel_legacy.py` reduced to 12L shim — meets ≤100L target
- [x] 10 responsibility modules now hold real handler logic (292-764L each)
- [x] `_bind_cp_globals` guard prevents handler overwrite regression
- [x] 35+ endpoint behaviors preserved (80 tests green)
- [ ] **Note**: `control_panel_signals.py` (764L) and `control_panel_signals_feedback.py` (713L) slightly exceed 700L target. Non-blocking; can be addressed in future housekeeping.

### R2 — Code Quality
- [x] No circular imports
- [x] Deferred `_cp()` pattern preserved for cross-module state sharing
- [x] No API contract changes

### R3 — Test Quality
- [x] 80 tests pass across control_panel + experiments + integration
- [x] No new tests needed — behavior unchanged

### R4 — Report Quality
- [x] File list accurate
- [x] No deviations from spec
- [x] Test count stated: 80 passed
