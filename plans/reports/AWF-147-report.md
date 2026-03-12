# AWF-147 Implementation Report

## Header

| Field | Value |
|-------|-------|
| AWF ID | AWF-147 |
| Title | cli_legacy handler migration |
| Phase | 26 |
| Codex completion date | 2026-02-28 |
| Spec reference | User task brief (Phase 26, AWF-147) |
| Architect review date |  |
| Review result |  |

## 1. Files Created / Modified (Codex)

| Status | File | Reason |
|--------|------|--------|
| created | `autowfo/commands/core.py` | Preserved existing helper surface from legacy CLI while enabling handler extraction |
| modified | `autowfo/commands/run.py` | Added run/baseline command handler implementations |
| modified | `autowfo/commands/batch.py` | Added batch command handler implementation |
| modified | `autowfo/commands/gate.py` | Added Gate-C command handler implementation |
| modified | `autowfo/commands/cron.py` | Added cron command handler implementation |
| modified | `autowfo/commands/plan.py` | Added plan/discover/report/repro command handler implementations |
| modified | `autowfo/cli.py` | Replaced alias shim with parser+dispatch facade that routes to `autowfo/commands/*` |
| modified | `autowfo/cli_legacy.py` | Reduced to compatibility shim (<=100L) |

**Files intentionally NOT touched**:
- `scripts/control_panel.py`
- `scripts/autowfo/experiment.py`

## 2. Implementation Summary (Codex)

Moved CLI command handler implementations into the command modules (`run/batch/gate/cron/plan`) and rewired `autowfo/cli.py` to build parser/dispatch from those modules. Kept legacy helper behavior through `autowfo/commands/core.py` and patch-aware facade wrappers so existing monkeypatch-driven tests (especially `_run_workflow`, `_run_batch_job_single`, `_run_patrol_cycle`) remain behavior-compatible. Converted `cli_legacy.py` into a compatibility shim.

## 3. Deviations from Spec (Codex)

| Spec requirement | What was implemented instead | Justification |
|-----------------|------------------------------|---------------|
| `cli_legacy.py` handlers fully removed with no helper carryover | Handler bodies moved to `autowfo/commands/*`; shared helper functions retained in `autowfo/commands/core.py` for compatibility | Keeps external/private helper contracts stable while completing handler migration and reducing `cli_legacy.py` to shim |

## 4. Exit Criteria Checklist (Codex)

- [x] Handler logic migrated into `autowfo/commands/{run,batch,gate,cron,plan}.py`
- [x] `cli.py` dispatch routes through command modules
- [x] `cli_legacy.py` reduced to compatibility shim (<=100L)
- [x] `tests/test_autowfo_cli.py` all pass

## 5. Test Results (Codex)

**Verification command run**:

```bash
pytest tests/test_autowfo_cli.py -q
```

**Result**:

```text
40 passed, 0 failed, 0 errors
```

**New tests added**: 0

**Specific test coverage for exit criteria**:

| Exit criterion | Test name | Result |
|----------------|-----------|--------|
| run/baseline command behavior preserved | `test_cli_run_writes_runtime_config_and_invokes_sweep`, `test_cli_baseline_writes_runtime_config_and_invokes_baseline` | pass |
| batch handler behavior preserved | batch + parallel suite in `tests/test_autowfo_cli.py` | pass |
| cron/plan/gate dispatch preserved | cron/plan/gate tests in `tests/test_autowfo_cli.py` | pass |

## 6. Cross-Phase Interface Exposure (Codex)

N/A - this AWF has no cross-phase interface.

## 7. Known Issues / Risks (Codex)

`autowfo/commands/core.py` remains large because helper compatibility was preserved; a later pass can further split helper clusters if needed.

## 8. BLOCKER (if applicable) (Codex)

**Status**: NOT BLOCKED

---
# ARCHITECT REVIEW
> Everything below is filled by Architect only. Codex does not edit this section.
---

**Architect review date**: 2026-02-28
**Review result**: ✓ APPROVED (with note)

### R1 — Architecture Alignment
- [x] `cli_legacy.py` reduced to 8L shim — meets ≤100L target
- [x] `cli.py` is 210L dispatch facade — meets ≤300L target
- [x] 5 command modules created with handler implementations
- [x] 40 CLI tests pass — full regression
- [ ] **Note**: `autowfo/commands/core.py` (2116L) is a shared helper monolith carried from legacy. Exceeds 700L target significantly. Non-blocking for this AWF but should be decomposed in future housekeeping.

### R2 — Code Quality
- [x] No circular imports
- [x] Monkeypatch-driven test compatibility preserved via `core.py` helper surface
- [x] No scope creep

### R3 — Test Quality
- [x] 40 tests pass — all CLI behaviors verified
- [x] No new tests needed

### R4 — Report Quality
- [x] File list accurate
- [x] Deviation documented: core.py helper retention
- [x] Test count stated: 40 passed
