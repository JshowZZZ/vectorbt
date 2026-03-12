# AWF-129 Implementation Report

## Header

| Field | Value |
|-------|-------|
| AWF ID | AWF-129 |
| Title | Experiment CRUD API |
| Phase | 20 |
| Codex completion date | 2026-02-27 |
| Spec reference | `plans/AUTOWFO_PHASE20_SPEC.md#AWF-129` |
| Architect review date | 2026-02-27 |
| Review result | APPROVED |

## 1. Files Created / Modified (Codex)

| Status | File | Reason |
|--------|------|--------|
| created | `scripts/control_panel_experiments.py` | Implemented experiment CRUD and queue handlers using deferred `_cp()` accessor pattern |
| modified | `scripts/control_panel.py` | Wired five experiment endpoints into `Handler` (`GET`, `POST`, `DELETE`) |
| created | `tests/test_control_panel_experiments.py` | Added endpoint regression tests for list/create/get/delete/run paths |
| modified | `plans/AUTOWFO_TODO.md` | Marked AWF-129 `done` and appended session log entry |

**Files intentionally NOT touched**:
- Existing AUTOWFO engine files (`engine_*.py`)
- Existing strategy files (`strategy.py`, `strategy_schema.py`)

## 2. Implementation Summary (Codex)

Added a new `control_panel_experiments` module that encapsulates experiment endpoint behavior and uses deferred access to `scripts.control_panel` shared state/helpers (`_cp()` pattern). Implemented handlers for listing experiments by scanning `artifacts/experiments/*/config.json`, creating validated experiments through `Experiment.from_dict`, reading one config, guarded deletion with 409 when run directories exist, and run-queue insertion via existing batch enqueue mechanism. Updated `control_panel.py` to route new GET/POST/DELETE paths to these handlers. Added HTTP integration tests covering empty/non-empty listings, create validation errors, config fetch 404, delete conflict behavior, and queue insertion.

## 3. Deviations from Spec (Codex)

| Spec requirement | What was implemented instead | Justification |
|-----------------|------------------------------|---------------|
| `POST /experiments/{id}/run` adds to `artifacts/batch_state.json` queue | Uses existing `_batch_enqueue` mechanism, which persists queue in `artifacts/batch_queue.json` and keeps `batch_state.json` as runtime history | Matches current control panel queue architecture and satisfies "reuse existing batch queue mechanism" without introducing a parallel queue format |

## 4. Exit Criteria Checklist (Codex)

- [x] `GET /experiments.json` returns correct list shape (test with 0 and 2 experiments)
- [x] `POST /experiments/create` with valid config creates `config.json` on disk
- [x] `POST /experiments/create` with invalid config returns HTTP 400 with `error` field
- [x] `GET /experiments/{id}/config.json` returns config for existing experiment; 404 for missing
- [x] `DELETE /experiments/{id}` succeeds when no runs exist; returns 409 when runs exist
- [x] `POST /experiments/{id}/run` adds entry to batch queue
- [x] All tests: N passed, 0 failed

## 5. Test Results (Codex)

**Verification command run**:

```bash
pytest tests/test_control_panel_experiments.py -v
```

**Result**:

```text
5 passed, 0 failed, 0 errors
```

**New tests added**: 5 tests in `tests/test_control_panel_experiments.py`

**Specific test coverage for exit criteria**:

| Exit criterion | Test name | Result |
|----------------|-----------|--------|
| experiments list shape (0 and 2) | `test_get_experiments_list_shape_with_zero_and_two_experiments` | pass |
| create valid + invalid | `test_post_experiments_create_valid_and_invalid` | pass |
| get config existing/missing | `test_get_experiment_config_existing_and_missing` | pass |
| delete success + 409 with runs | `test_delete_experiment_success_and_conflict_on_runs` | pass |
| run endpoint queue insertion | `test_post_experiment_run_adds_job_to_batch_queue` | pass |

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
- [x] Module contracts follow Architecture V2 §9
- [x] No unexpected cross-module imports
- [x] Cross-phase interface defined correctly (if applicable)

**Notes**:
`scripts/control_panel_experiments.py` implements 5 handlers as specified. `scripts/control_panel.py` wired with 5 new route entries — minimal diff. Uses `_cp()` deferred accessor pattern per spec to avoid circular imports. Imports `Experiment` from AWF-127 for validation on create — expected dependency. Deviation: `batch_queue.json` via `_batch_enqueue` instead of direct `batch_state.json` write — acceptable, matches existing control panel architecture and is justified in report §3.

## R2. Code Quality

- [x] No hardcoded config values
- [x] No circular imports
- [x] Error handling only at boundaries
- [x] Scope limited to AWF no over-engineering

**Notes**:
`_cp()` deferred accessor cleanly avoids circular import between `control_panel.py` and `control_panel_experiments.py`. HTTP status codes (200, 400, 404, 409) used correctly at API boundaries. `Experiment.from_dict()` validation reused from AWF-127 — no duplication. Delete guard (409 when runs exist) is a good safety boundary. `_handle_experiments_list()` scans `config.json` + `run_meta.json` for summary data — straightforward and correct.

## R3. Test Quality

- [x] All exit criteria have corresponding tests
- [x] Edge cases covered (None, NaN, empty)
- [x] Cross-phase interface has contract test
- [x] Test depth is reasonable

**Notes**:
5 HTTP integration tests using `ThreadingHTTPServer` + `http.client.HTTPConnection` — good end-to-end coverage. Tests cover: empty list (0 experiments), populated list (2 experiments with run metadata), create valid + invalid (400), config get existing + missing (404), delete clean + with runs (409), run queue insertion. `_setup_env` monkeypatches all path constants — clean isolation. `_serve_handler_connection` context manager ensures server cleanup. N/A for cross-phase contract test.

## R4. Review Result

**Result**: APPROVED

**Correction AWFs issued**: None

**Soft gate status**: N/A (no cross-phase interface)

