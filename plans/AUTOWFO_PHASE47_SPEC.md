# AUTOWFO Phase 47 Spec

## Phase 47: Ranking Evidence Parity

### Goal
Make non-rerun ranking evaluation trustworthy and operator-usable by aligning `storage rescore`
with the engine's real Top10 selection path and by adding a first-class comparison workflow for
candidate ranking configs across trusted runs.

### Scope Rules
- Do not change the search grid, indicator universe, or walk-forward engine behavior.
- Do not re-run search during comparison; Phase 47 is storage/reporting only.
- Keep trusted-run formats backward-compatible: existing `combo_summary`, `top10`, `leaderboard`,
  and shared-view files must remain readable by current tooling and UI.
- Reuse run-local Phase 44 evidence (`artifacts/runs/{run_id}/...`) as the only source of truth.

### Root Cause Summary
- `autowfo storage rescore` currently re-sorts the full `param_sweep_combo_summary.csv` directly.
  That bypasses the engine's finalize-time selection path:
  - `timeframes` / current-run slice selection
  - quality filters (`min_avg_daily_trades_target`, `min_oos_trades_target`)
  - fallback activity filter behavior
- Because of this, re-scored Top10/leaderboard outputs can diverge from what the engine would
  have written for the same run config.
- Operators also lack a first-class way to compare a candidate ranking config against trusted
  runs before deciding to `rescore` or re-run.

### Validation Baseline
- `python -m pytest tests/test_autowfo_storage_ops.py tests/test_autowfo_cli.py tests/test_autowfo_baseline.py -q`

---

## AWF-233: Rescore parity with finalize-time selection

### Objective
Ensure `storage rescore` uses the same candidate-row selection path as the engine's final Top10
generation so that non-rerun rescoring is evidence-preserving.

### Required changes
- Load each trusted run's run-local runtime config (`runtime/sweep_config.json`) when available.
- Apply the same pre-ranking selection steps used by finalize:
  - timeframe/day selection
  - quality filters
  - fallback activity filter
- Rebuild Top10 from the filtered current-run candidate set, then apply combo dedup and `head(top_n)`.
- Refresh per-run leaderboard rows from the rescored best row while preserving operator-facing
  context fields such as `plot_symbol` / `report_file`.

### Exit criteria
- A trusted run with multiple timeframe/day rows only rescoreds the active timeframe/day subset.
- A trusted run with strict quality thresholds preserves the same fallback behavior as engine finalize.
- Rebuilt shared views continue to succeed after rescoring.

---

## AWF-234: Trusted-run ranking comparison command

### Objective
Add a no-rerun comparison command so operators can quantify ranking changes before mutating shared views.

### Required changes
- Add `autowfo storage compare-ranking`.
- Inputs:
  - trusted run roots from `artifacts/runs/*`
  - optional baseline ranking override
  - candidate ranking override (partial override merged onto the run's original ranking config)
- Outputs:
  - machine-readable JSON report
  - human-readable HTML report
- Default comparison basis:
  - baseline config = trusted run runtime/metadata ranking config
  - candidate config = baseline config merged with candidate override

### Exit criteria
- Operators can compare a candidate ranking config against all trusted runs without re-running search.
- Output includes per-run diagnostics and aggregate deltas for Top10 quality/diversity metrics.

---

## AWF-235: Aggregate decision summary

### Objective
Summarize whether a candidate ranking config is materially better, worse, or mixed across trusted runs.

### Required changes
- Aggregate per-run deltas for:
  - average OOS return
  - average OOS Sharpe-like
  - average OOS drawdown
  - average OOS minimum trades
  - unique combo signatures in Top10
- Count improved / worsened / unchanged runs per metric.
- Record skipped runs and reasons.

### Exit criteria
- Report consumers can answer "Is this config worth rescore/rerun?" from the aggregate summary alone.

---

## AWF-236: Regression closure and planning sync

### Objective
Close the implementation loop with targeted regression and planning updates.

### Required changes
- Add regression tests for:
  - rescore parity on multi-timeframe / filtered candidate sets
  - compare-ranking command outputs
  - CLI parser wiring
- Update planning docs after implementation status is known.

### Exit criteria
- Targeted regression green.
- `plans/AUTOWFO_TODO.md` and `plans/AUTOWFO_MASTER_PLAN.md` reflect actual implementation status.
