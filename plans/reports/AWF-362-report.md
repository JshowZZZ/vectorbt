# AWF-362 Implementation Report

## Header

| Field | Value |
|-------|-------|
| AWF ID | AWF-362 |
| Title | Evidence warehouse read-only import for Phase 61-62 replay/drift evidence |
| Phase | 64 survivalism foundation |
| Codex completion date | 2026-04-26 |
| Spec reference | `plans/AUTOWFO_EVIDENCE_WAREHOUSE_V1.md#5-ingestion-priority` |
| Architect review date |  |
| Review result |  |

## 1. Files Created / Modified

| Status | File | Reason |
|--------|------|--------|
| modified | `autowfo/evidence_warehouse.py` | Add read-only Phase 61-62 replay/drift import into the Evidence Warehouse V1 tables |
| modified | `autowfo/commands/storage.py` | Add `storage evidence-warehouse --mode import-phase61-62` CLI wiring |
| modified | `tests/test_autowfo_evidence_warehouse.py` | Cover candidate/replay/gap row import, idempotency, source preservation, and missing drift warning behavior |
| modified | `tests/test_autowfo_cli.py` | Cover CLI import mode |
| modified | `plans/AUTOWFO_TODO.md` | Mark the bounded AWF-362 slice complete |
| created | `plans/reports/AWF-362-report.md` | Record scope, validation, and explicit non-goals |

**Files intentionally NOT touched**:
- `AGENTS.md` - explicitly restricted.
- `docs/` - AUTOWFO governance remains under `plans/`.
- Survival Gate writer modules - deferred until warehouse evidence records exist.
- Risk Engine modules - deferred until evidence and gate verdict records exist.
- Control panel files - cockpit work remains deferred.

## 2. Implementation Summary

AWF-362 adds the first bounded Evidence Warehouse V1 import path. The importer reads the frozen Phase 61-62 `awf331_rerun_summary.json` replay summary and, when present, the `execution_drift_report.json` drift report. It writes deterministic rows into:

- `strategy_candidates`
- `ft_replay_results`
- `execution_gap_events`

The import is source-read-only and idempotent. Re-running the same import deletes and replaces only rows owned by the Phase 61-62 import prefixes/source system, so it does not duplicate records. If the drift report is missing, the importer continues with candidate and replay rows and emits a warning instead of failing the whole import.

## 3. Deviations from Spec

None. This implements only the first read-only Phase 61-62 replay/drift import slice from the Evidence Warehouse V1 ingestion priority.

## 4. Exit Criteria Checklist

- [x] Phase 61-62 replay summary imports candidate rows.
- [x] Phase 61-62 replay summary imports Freqtrade replay result rows.
- [x] Phase 61-62 drift report imports row-level execution gap events when present.
- [x] Import can run repeatedly without duplicating rows.
- [x] Source artifacts are not mutated.
- [x] CLI exposes the bounded import mode.
- [x] Missing drift report produces a warning and keeps replay import usable.
- [x] No paper import was implemented.
- [x] No Survival Gate verdict writer was implemented.
- [x] No Risk Engine behavior was implemented.

## 5. Test Results

**Verification command run**:

```bash
python -m pytest tests/test_autowfo_evidence_warehouse.py tests/test_autowfo_cli.py -q -k "phase61_62_replay or evidence_warehouse"
```

**Result**:

```text
16 passed, 69 deselected in 11.31s
```

**Red phase before production implementation**:

```text
AttributeError: module 'autowfo.evidence_warehouse' has no attribute 'import_phase61_62_replay_evidence'
argparse.ArgumentError: invalid choice: 'import-phase61-62'
```

## 6. Cross-Phase Interface Exposure

**Interface exposed**:

```python
import_phase61_62_replay_evidence(
    artifacts_dir="artifacts",
    *,
    protocol_path=None,
    db_path=None,
    summary_path=None,
    drift_report_path=None,
) -> dict
```

**CLI exposed**:

```bash
python -m autowfo storage evidence-warehouse --mode import-phase61-62
```

**Consuming phase**: Later Phase 64 Survival Gate writer, lifecycle decision records, and Champion/Challenger comparison work.

## 7. Known Issues / Risks

- Imported warehouse columns remain `VARCHAR` because typed analytical schema design is intentionally deferred until importer semantics settle.
- Row-level drift is stored as portfolio-level `adapter_gap` events. Pair-direction drift can be imported in a later slice if a decision needs that granularity.
- Missing drift reports are non-blocking by design; replay rows still import and the warning makes the gap explicit.

## 8. BLOCKER

Status: NOT BLOCKED
