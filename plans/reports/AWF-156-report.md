# AWF-156 Implementation Report

## Header

| Field | Value |
|-------|-------|
| AWF ID | AWF-156 |
| Title | Nightly cron → scheduler 整合 |
| Phase | 29 |
| Codex completion date | 2026-03-01 |
| Spec reference | User task brief (Phase 29, AWF-156) |
| Architect review date |  |
| Review result |  |

## 1. Files Created / Modified (Codex)

| Status | File | Reason |
|--------|------|--------|
| modified | `autowfo/commands/cron.py` | Added scheduler-mode patrol branch: reads `artifacts/scheduler.json`, optional discovery tick, then queue-driven run-once execution with fallback to legacy engine patrol |
| modified | `tests/test_autowfo_cli.py` | Added cron scheduler-mode regression test verifying discovery tick and scheduler run_once each execute once |

**Files intentionally NOT touched**:
- `scripts/control_panel_experiments.py`
- `scripts/autowfo/scheduler.py`

## 2. Implementation Summary (Codex)

Extended cron command runtime to support scheduler-driven patrol when `artifacts/scheduler.json` exists. In scheduler mode, cron can run discovery tick first (when pool config exists) and then execute a single queued experiment run, while preserving existing engine patrol behavior when scheduler config is absent.

## 3. Deviations from Spec (Codex)

None.

## 4. Exit Criteria Checklist (Codex)

- [x] Cron reads scheduler mode from `artifacts/scheduler.json` and consumes `schedule_cron`
- [x] In scheduler mode, discovery tick executes before scheduler run-once when pool config exists
- [x] Queue processing uses scheduler run-once path instead of legacy batch patrol
- [x] Legacy engine patrol remains fallback when no scheduler config
- [x] Added test verifying tick + run_once each called once

## 5. Test Results (Codex)

**Verification command run**:

```bash
pytest tests/test_autowfo_cli.py -k "cron and (scheduler_mode_runs_discovery_then_run_once or cmd_cron_single_cycle or cmd_cron_multi_cycle_log or cmd_cron_notifications_and_state_update)" -q
```

**Result**:

```text
4 passed, 0 failed, 0 errors
```

**New tests added**: 1

**Specific test coverage for exit criteria**:

| Exit criterion | Test name | Result |
|----------------|-----------|--------|
| Scheduler mode discovery + run_once flow | `test_cmd_cron_scheduler_mode_runs_discovery_then_run_once` | pass |

## 6. Cross-Phase Interface Exposure (Codex)

N/A - this AWF has no cross-phase interface.

## 7. Known Issues / Risks (Codex)

None.

## 8. BLOCKER (if applicable) (Codex)

**Status**: NOT BLOCKED

---
# ARCHITECT REVIEW
> Everything below is filled by Architect only. Codex does not edit this section.
---

**Architect review date**: 2026-03-01
**Review result**: ✓ APPROVED

### R1 — Architecture Alignment
- [x] Cron reads `scheduler.json` for scheduler-mode detection
- [x] Discovery tick → run_once sequential execution in scheduler mode
- [x] Legacy engine patrol preserved as fallback when no scheduler config

### R2 — Code Quality
- [x] Clean branching: scheduler-mode vs legacy — no interleaving
- [x] No circular imports
- [x] No scope creep

### R3 — Test Quality
- [x] `test_cmd_cron_scheduler_mode_runs_discovery_then_run_once` verifies both calls
- [x] 4 cron-related tests pass (3 existing + 1 new)

### R4 — Report Quality
- [x] File list accurate
- [x] No deviations
- [x] Test count stated: 4 passed
