# AWF-152 Implementation Report

## Header

| Field | Value |
|-------|-------|
| AWF ID | AWF-152 |
| Title | Error code 結構化補全 |
| Phase | 27 |
| Codex completion date | 2026-02-28 |
| Spec reference | User task brief (Phase 27, AWF-152) |
| Architect review date |  |
| Review result |  |

## 1. Files Created / Modified (Codex)

| Status | File | Reason |
|--------|------|--------|
| modified | `scripts/control_panel_experiments.py` | Added structured 400 payloads (`ok/error_code/message`) for `/discovery/tick` invalid pool and `/experiments/queue` validation failures |
| modified | `tests/test_control_panel_experiments.py` | Added HTTP tests validating structured error responses and `error_code` fields |

**Files intentionally NOT touched**:
- `scripts/control_panel.py` (success path format unchanged)
- `scripts/control_panel/static/js/api.js`

## 2. Implementation Summary (Codex)

Standardized error payloads for targeted failure paths without changing successful response schemas. `/discovery/tick` invalid input now returns `error_code=invalid_pool_config`, and `/experiments/queue` validation failure returns `error_code=invalid_experiment_config`, both with `ok=false` and human-readable `message`.

## 3. Deviations from Spec (Codex)

None.

## 4. Exit Criteria Checklist (Codex)

- [x] `/discovery/tick` invalid pool returns 400 structured `error_code`
- [x] `/experiments/queue` validation failures return structured `error_code`
- [x] Success response formats unchanged
- [x] Regression tests added and passing

## 5. Test Results (Codex)

**Verification command run**:

```bash
pytest tests/test_control_panel_experiments.py -q
```

**Result**:

```text
13 passed, 0 failed, 0 errors
```

**New tests added**: 2

**Specific test coverage for exit criteria**:

| Exit criterion | Test name | Result |
|----------------|-----------|--------|
| discovery invalid pool structured error | `test_post_discovery_tick_invalid_pool_returns_structured_error` | pass |
| queue invalid payload structured error | `test_post_experiments_queue_invalid_payload_returns_structured_error` | pass |

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

**Architect review date**: 2026-02-28
**Review result**: ✓ APPROVED

### R1 — Architecture Alignment
- [x] `/discovery/tick` 400 now returns `{ok, error_code, message}` — structured
- [x] `/experiments/queue` validation failure returns structured `error_code`
- [x] Success response formats unchanged — no breaking changes

### R2 — Code Quality
- [x] Error codes are machine-readable constants (`invalid_pool_config`, `invalid_experiment_config`)
- [x] Human-readable message preserved alongside code
- [x] No scope creep

### R3 — Test Quality
- [x] 2 new tests validate error_code presence in 400 responses
- [x] 13 total experiments tests pass

### R4 — Report Quality
- [x] File list accurate
- [x] No deviations
- [x] Test count stated: 13 passed
