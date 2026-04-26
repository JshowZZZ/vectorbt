# AWF-360 Implementation Report

## Header

| Field | Value |
|-------|-------|
| AWF ID | AWF-360 |
| Title | Evidence warehouse protocol validator and candidate identity helper |
| Phase | 64 survivalism foundation |
| Codex completion date | 2026-04-25 |
| Spec reference | `plans/AUTOWFO_TODO.md#suggested-first-new-implementation-item-after-user-start` |
| Architect review date |  |
| Review result |  |

## 1. Files Created / Modified

| Status | File | Reason |
|--------|------|--------|
| created | `autowfo/evidence_warehouse.py` | Add the Evidence Warehouse V1 protocol loader/validator and deterministic candidate identity helper |
| created | `tests/test_autowfo_evidence_warehouse.py` | Add focused protocol validation and candidate identity stability coverage |
| modified | `plans/protocols/evidence_warehouse_v1.json` | Fix internal protocol consistency by requiring `data_profile_id` on `backtest_runs` because the identity contract requires it there |
| modified | `plans/AUTOWFO_EVIDENCE_WAREHOUSE_V1.md` | Keep the spec table aligned with the frozen protocol fix |
| modified | `plans/AUTOWFO_TODO.md` | Mark AWF-360 done and record validation evidence |
| created | `plans/reports/AWF-360-report.md` | Record AWF-360 scope, validation, and constraints followed |

**Files intentionally NOT touched**:
- `AGENTS.md` - explicitly restricted by operator instruction and repo workflow.
- `docs/` - AUTOWFO governance remains under `plans/`.
- Risk Engine modules - out of scope until Evidence Warehouse records exist.
- Control panel files - cockpit work is deferred until evidence contracts exist.

## 2. Implementation Summary

AWF-360 adds `autowfo.evidence_warehouse` as the first small implementation surface for the survivalism workstream. The module validates the frozen Evidence Warehouse V1 protocol, including required identity keys, logical table contracts, gate verdict fields, allowed verdicts, allowed execution gap types, and implementation invariants. It also adds a deterministic `candidate_id` helper built from the documented candidate definition fields. During validation, the first test run found that `data_profile_id` was listed as required for `backtest_runs` in the identity contract but missing from the `backtest_runs.required_fields` table contract; the protocol and spec were updated to make the frozen contract self-consistent.

## 3. Deviations from Spec

None. The only spec change was a consistency correction required for the protocol to validate against its own identity contract.

## 4. Exit Criteria Checklist

- [x] Evidence Warehouse V1 JSON protocol validates.
- [x] Same candidate definition yields the same `candidate_id`.
- [x] Candidate identity changes when a definition field changes.
- [x] Missing candidate identity fields are rejected.
- [x] No legacy artifact import was implemented.
- [x] No Risk Engine behavior was implemented.

## 5. Test Results

**Verification command run**:

```bash
python -m pytest tests/test_autowfo_evidence_warehouse.py -q
python -m pytest tests/test_autowfo_evidence_warehouse.py tests/test_autowfo_split_protocol.py tests/test_awf345_execution_drift_protocol.py -q
python -m pytest tests/test_autowfo_storage_ops.py -q
python -m pytest tests/test_autowfo_evidence_warehouse.py tests/test_autowfo_split_protocol.py tests/test_awf345_execution_drift_protocol.py tests/test_autowfo_storage_ops.py -q
python -m compileall autowfo
```

**Result**:

```text
7 passed in 0.08s
12 passed in 13.54s
10 passed in 1.51s
22 passed in 8.46s
compileall completed
```

**Red phase before production implementation**:

```text
ImportError: cannot import name 'evidence_warehouse' from 'autowfo'
```

**New tests added**: 7 tests in `tests/test_autowfo_evidence_warehouse.py`

| Exit criterion | Test name | Result |
|----------------|-----------|--------|
| Protocol validates | `test_default_evidence_warehouse_protocol_loads_required_contract` | pass |
| Missing identity key rejected | `test_validate_evidence_warehouse_protocol_rejects_missing_identity_key` | pass |
| Gate verdict requires policy identity | `test_validate_evidence_warehouse_protocol_rejects_gate_verdict_without_policy_id` | pass |
| Reordered nested definitions produce stable ID | `test_build_candidate_id_is_stable_for_equivalent_nested_definitions` | pass |
| Changed definition changes ID | `test_build_candidate_id_changes_when_candidate_definition_changes` | pass |
| Missing candidate field rejected | `test_build_candidate_id_rejects_missing_required_definition_field` | pass |
| Identity payload is stable JSON | `test_candidate_identity_payload_is_json_stable` | pass |

## 6. Cross-Phase Interface Exposure

**Interface exposed**:

```python
load_evidence_warehouse_protocol(path: str | None = None) -> dict
validate_evidence_warehouse_protocol(payload: object, source: str = "<in-memory>") -> None
build_candidate_identity_payload(candidate_definition: Mapping[str, Any]) -> dict
build_candidate_id(candidate_definition: Mapping[str, Any]) -> str
```

**Consuming phase**: Phase 64 Evidence Warehouse V1 import, Survival Gate verdict writer, and Champion/Challenger comparison work.

**Contract test location**: `tests/test_autowfo_evidence_warehouse.py`

## 7. Known Issues / Risks

- This slice intentionally does not create DuckDB tables or import legacy artifacts.
- `candidate_id` currently preserves list order, so semantically unordered fields such as market universe must be passed in canonical order by the caller or normalized in a later import-specific helper.
- The protocol validator now catches protocol/table identity mismatches; future protocol edits may require corresponding spec updates before tests pass.

## 8. BLOCKER

Status: NOT BLOCKED
