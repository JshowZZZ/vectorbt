# AWF-364 Phase 63 State Reconciliation Report

## Header

| Field | Value |
|-------|-------|
| AWF ID | AWF-364 |
| Title | Phase 63 artifact-truth reconciliation before Survival Gate work |
| Phase | 64 survivalism foundation |
| Codex completion date | 2026-04-28 |
| Spec reference | `plans/AUTOWFO_PHASE63_PLAN.md`, `plans/AUTOWFO_TODO.md` |

## Artifact Truth

Phase 63 paper evidence is incomplete.

Observed paper summaries under `artifacts/paper_dryrun/`:

- `daily_summary_20260413.json`
- `daily_summary_20260418.json`
- `daily_summary_20260420.json`
- `daily_summary_20260426.json`

This is `4` daily summaries, below the Phase 63 `AWF-349` threshold of `7` daily
summaries and below the `AWF-350` threshold of `14` daily summaries.

Current `artifacts/live_signal_store/live_manifest.json` was created at
`2026-04-18T17:56:42+00:00` and points to:

- selection: `top_stable_positive`
- rank: `10`
- source bundle:
  `artifacts/freqtrade_bridge/20260411_microcohort_dropsol_main_stable_r10/signal_manifest.json`

This does not match the Phase 63 paper objective, which calls for validating the
frozen canonical lane. The canonical reference remains rank `1` /
`canonical_gate_passed` for `obv_roc + keltner_pos`.

AWF-352 artifacts exist:

- `artifacts/phase63/awf352_nontrend_main.json`
- `artifacts/phase63/awf352_nontrend_sens.json`
- `artifacts/runs/20260418_081050/`
- `artifacts/phase63/latest_top10_20260418_081050_by_winrate.csv`

The top visible rows in the latest AWF-352 CSV are non-trend rows with negative
OOS return. This report does not promote that into a branch verdict; it only
records that AWF-352 has artifact evidence and still needs a formal bounded
pilot analysis/verdict before AWF-353.

## Implementation Outcome

AWF-364 does not produce a paper verdict. It records that:

- existing Phase 63 paper evidence is `incomplete_evidence`
- current live manifest freshness and candidate selection must be refreshed
  before paper verdict work
- existing paper summaries may be imported as evidence, but not treated as
  passing evidence

## Follow-Up

Continue with:

- AWF-348 refresh against the canonical rank 1 lane
- AWF-349 and AWF-350 evidence accumulation
- AWF-365 Evidence Warehouse paper import for existing and future summaries
- AWF-366 Survival Gate writer only after evidence records exist
