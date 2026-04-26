# AWF-361 Implementation Report

## Header

| Field | Value |
|-------|-------|
| AWF ID | AWF-361 |
| Title | Evidence warehouse DuckDB skeleton and CLI build/validate entry |
| Phase | 64 survivalism foundation |
| Codex completion date | 2026-04-26 |
| Spec reference | `plans/AUTOWFO_EVIDENCE_WAREHOUSE_V1.md#7-implementation-boundaries` |
| Architect review date |  |
| Review result |  |

## 1. Files Created / Modified

| Status | File | Reason |
|--------|------|--------|
| modified | `autowfo/evidence_warehouse.py` | Add empty DuckDB warehouse build/validate helpers from the frozen Evidence Warehouse V1 protocol |
| modified | `autowfo/commands/storage.py` | Add `storage evidence-warehouse --mode build|validate` CLI wiring |
| modified | `autowfo/cli.py` | Add the CLI command handler shim |
| modified | `tests/test_autowfo_evidence_warehouse.py` | Cover table skeleton creation, idempotent rebuild, source-artifact preservation, and missing-table validation |
| modified | `tests/test_autowfo_cli.py` | Cover CLI build and validate return-code behavior |
| modified | `plans/AUTOWFO_TODO.md` | Mark the bounded AWF-361 slice complete |
| created | `plans/reports/AWF-361-report.md` | Record scope, validation, and explicit non-goals |

**Files intentionally NOT touched**:
- `AGENTS.md` - explicitly restricted.
- `docs/` - AUTOWFO governance remains under `plans/`.
- Risk Engine modules - deferred until warehouse evidence records exist.
- Control panel files - cockpit work remains deferred.

## 2. Implementation Summary

AWF-361 creates the first empty Evidence Warehouse V1 DuckDB skeleton from `plans/protocols/evidence_warehouse_v1.json`. The builder creates one empty table per protocol table contract, using required protocol fields as string columns, plus an `evidence_warehouse_metadata` table carrying schema and protocol identity. The validator checks that the DB exists, required tables exist, required columns exist, and metadata matches the frozen protocol. The CLI entry is intentionally small: `python -m autowfo storage evidence-warehouse --mode build|validate`.

No source artifacts are imported or rewritten. The tests explicitly confirm that a source artifact under `artifacts/freqtrade_bridge/` remains byte-identical after repeated warehouse builds.

## 3. Deviations from Spec

None. This implements only the V1 skeleton and CLI build/validate boundary from the spec; imports, gate verdicts, lifecycle records, and risk enforcement are left out.

## 4. Exit Criteria Checklist

- [x] Empty DuckDB warehouse skeleton is generated from the frozen protocol.
- [x] Rebuild is idempotent on the same inputs.
- [x] Source artifacts are not mutated.
- [x] CLI can build the warehouse skeleton.
- [x] CLI validate mode returns non-zero when the warehouse DB is missing.
- [x] No legacy artifact import was implemented.
- [x] No Risk Engine behavior was implemented.

## 5. Test Results

**Verification command run**:

```bash
python -m pytest tests/test_autowfo_evidence_warehouse.py tests/test_autowfo_cli.py -q -k "evidence_warehouse"
```

**Result**:

```text
12 passed, 69 deselected in 10.43s
```

**Red phase before production implementation**:

```text
AttributeError: module 'autowfo.evidence_warehouse' has no attribute 'build_evidence_warehouse'
argparse.ArgumentError: invalid choice: 'evidence-warehouse'
```

**New tests added**: 5 tests across `tests/test_autowfo_evidence_warehouse.py` and `tests/test_autowfo_cli.py`.

| Exit criterion | Test name | Result |
|----------------|-----------|--------|
| Build empty protocol tables | `test_build_evidence_warehouse_creates_empty_protocol_tables` | pass |
| Idempotent and source read-only | `test_build_evidence_warehouse_is_idempotent_and_preserves_source_artifacts` | pass |
| Missing table validation | `test_validate_evidence_warehouse_detects_missing_table` | pass |
| CLI build path | `test_cli_storage_evidence_warehouse_builds_duckdb_skeleton` | pass |
| CLI validate missing DB path | `test_cli_storage_evidence_warehouse_validate_fails_for_missing_db` | pass |

## 6. Cross-Phase Interface Exposure

**Interface exposed**:

```python
build_evidence_warehouse(artifacts_dir="artifacts", *, protocol_path=None, db_path=None) -> dict
validate_evidence_warehouse(artifacts_dir="artifacts", *, protocol_path=None, db_path=None) -> dict
```

**CLI exposed**:

```bash
python -m autowfo storage evidence-warehouse --mode build
python -m autowfo storage evidence-warehouse --mode validate
```

**Consuming phase**: Later Phase 64 read-only import and Survival Gate writer work.

## 7. Known Issues / Risks

- All protocol columns are created as `VARCHAR` in this skeleton. Typed analytical columns should be added only when import semantics are defined.
- The skeleton contains zero imported rows by design.
- The default CLI protocol path is relative to `--cwd`, matching existing storage command conventions; tests pass an explicit protocol path when using a temporary cwd.

## 8. BLOCKER

Status: NOT BLOCKED
