# AWF-167 Implementation Report

## Header

| Field | Value |
|-------|-------|
| AWF ID | AWF-167 |
| Title | Discovery history UI + indicator coverage analytics |
| Phase | 32 |
| Codex completion date | 2026-03-01 |
| Spec reference | Phase 32 prompt (2026-03-01), AWF-167 |
| Architect review date |  |
| Review result |  |

## 1. Files Created / Modified **(Codex)**

| Status | File | Reason |
|--------|------|--------|
| ?? | `scripts/autowfo/analytics.py` | Added `query_indicator_coverage_map()` to compute pair coverage and sharpe aggregates from persisted combo results |
| ?? | `scripts/control_panel_experiments.py` | Added GET `/analytics/coverage-map.json` handler returning coverage payload |
| ?? | `scripts/control_panel.py` | Wired coverage-map route into control panel dispatcher |
| ?? | `scripts/control_panel/static/js/discovery.js` | Added recent tick history panel (last 5 ticks) based on `/discovery/tick` responses |
| ?? | `scripts/control_panel/static/js/analytics.js` | Added coverage-map panel and integrated `/analytics/coverage-map.json` data fetch with existing analytics tab |
| ?? | `tests/test_autowfo_analytics.py` | Added unit test for coverage-map query schema and semantics |
| ?? | `tests/test_control_panel_experiments.py` | Added endpoint tests for coverage-map payload and empty fallback |
| ?? | `scripts/autowfo/experiment_runner.py` | Added explicit `trigger_indicators`/`action_indicators` in `indicator_params` to ensure analytics coverage and leaderboard extraction from real run rows |

**Files intentionally NOT touched**:
- `scripts/autowfo/signal_composer.py`
- `scripts/autowfo/experiment.py`

## 2. Implementation Summary **(Codex)**

Implemented analytics coverage-map query over cross-run combo results and exposed it through a new control-panel endpoint consumed by the Analytics tab. Discovery tab now keeps an in-UI recent tick history for operator visibility. To keep real-run analytics parseable, runner output now persists normalized trigger/action indicator lists inside `indicator_params`, ensuring coverage and leaderboard consistency on generated data.

## 3. Deviations from Spec **(Codex)**

None.

## 4. Exit Criteria Checklist **(Codex)**

- [x] Discovery UI shows recent tick history (generated/enqueued/skipped + timestamp)
- [x] Added backend `GET /analytics/coverage-map.json` in `control_panel_experiments.py`
- [x] Analytics layer provides indicator-pair coverage map query with tested flag and avg sharpe
- [x] Analytics UI displays coverage map panel sourced from existing analytics endpoints
- [x] Added analytics unit test for coverage-map format and behavior
- [x] Added control-panel endpoint tests including empty-store fallback

## 5. Test Results **(Codex)**

**Verification commands run**:
```bash
node --check scripts/control_panel/static/js/discovery.js
node --check scripts/control_panel/static/js/analytics.js
pytest tests/test_autowfo_analytics.py -v
pytest tests/test_control_panel_experiments.py -v
```

**Result**:
```text
node checks passed
18 passed, 0 failed
```

**New tests added**: 1 test in `tests/test_autowfo_analytics.py`

**Specific test coverage for exit criteria**:

| Exit criterion | Test name | Result |
|----------------|-----------|--------|
| coverage map query returns expected schema | `test_query_indicator_coverage_map` | ? pass |
| coverage-map endpoint returns payload shape | `test_get_analytics_endpoints_payload_shape` | ? pass |
| coverage-map endpoint empty fallback | `test_get_analytics_endpoints_empty_on_store_failure` | ? pass |

## 6. Cross-Phase Interface Exposure **(Codex)**

N/A �X this AWF has no cross-phase interface.

## 7. Known Issues / Risks **(Codex)**

- Coverage map currently emits upper-triangle pair combinations (`A,B` where `A<=B`); any future heatmap expecting full matrix must mirror entries client-side.

## 8. BLOCKER (if applicable) **(Codex)**

**Status**: NOT BLOCKED

---
# ARCHITECT REVIEW
> Everything below is filled by Architect only. Codex does not edit this section.
---

**Architect review date**: 2026-03-01
**Review result**: ✓ APPROVED

### R1 — Architecture Alignment
- [x] `query_indicator_coverage_map()` added to analytics.py — upper-triangle pair coverage
- [x] `GET /analytics/coverage-map.json` endpoint wired in control_panel_experiments.py
- [x] Discovery UI tick history (last 5) — client-side accumulation from POST responses
- [x] Analytics tab coverage map panel integrated
- [x] Runner persists `trigger_indicators`/`action_indicators` for analytics parsability

### R2 — Code Quality
- [x] Coverage map is additive query — no existing analytics behavior changed
- [x] Runner change is minimal (explicit indicator_params) — backward-compatible
- [x] Upper-triangle limitation documented — client-side mirror if needed

### R3 — Test Quality
- [x] Coverage map query schema test added
- [x] Endpoint payload shape + empty fallback tests added
- [x] 18 tests pass across analytics + experiments

### R4 — Report Quality
- [x] File list accurate
- [x] No deviations
- [x] Test count stated: 18 passed
