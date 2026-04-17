# AUTOWFO Parity Gate V1

> Status: frozen from `AWF-339`
> Date: 2026-04-18
> Source artifact: `artifacts/freqtrade_bridge/awf331_rerun_summary.json`
> Policy source: `plans/AUTOWFO_DEVELOPMENT_PRINCIPLES.md` §6

## Purpose

Freeze the first aggregate parity gate from the corrected adapter contract rerun.
This gate is for future corrected-contract reruns on the same frozen row scope as
`AWF-338` / `AWF-339`.

This file is not the same thing as `parity_report.json` row verdicts:

- `trade_comparison.verdict` remains a strict row-level exact-parity check
- this gate is an aggregate acceptance layer derived from the rerun distribution
- a rerun may therefore keep row verdicts at `review` while still passing Gate V1

## Sample Basis

- Frozen source: `artifacts/freqtrade_bridge/awf331_rerun_summary.json`
- Unique deduplicated rows: `10`
- Statistical branch used: `n >= 10`
- Quantile method: linear interpolation, matching the implementation used in
  `scripts/run_awf339_rerun.py`

The frozen `AWF-339` sample produced:

- `p10(open_match_ratio) = 0.9890696190996902`
- `p10(exact_match_ratio) = 0.5826530612244898`
- `p90(abs(trade_count_delta_pct)) = 0.009517951521778744`

Where:

- `trade_count_delta_pct = abs(trade_count_delta) / autowfo_trade_count`

## Gate Definition

For future reruns on the same frozen row scope, Gate V1 is:

| Metric | Evaluation statistic | Threshold | Direction |
|---|---|---|---|
| Open match quality | `p10(open_match_ratio)` | `>= 0.9890696190996902` | higher is better |
| Exact match quality | `p10(exact_match_ratio)` | `>= 0.5826530612244898` | higher is better |
| Trade-count drift | `p90(abs(trade_count_delta_pct))` | `<= 0.009517951521778744` | lower is better |

These are aggregate thresholds. They are not per-row minimums.

## Hard Block Conditions

Do not apply Gate V1 and mark the rerun blocked if any of the following is true:

1. `row_scope_validation.row_count_matches_expectation` is not `true`
2. the rerun does not preserve the frozen `10`-row deduplicated scope
3. any row has `open_match_ratio < 0.5`
4. `branch_conditions.awf339a_required` is `true`
5. sample size falls to `n <= 3`

If `3 < n < 10`, do not reuse this file as-is. Reopen the gate derivation and
follow `plans/AUTOWFO_DEVELOPMENT_PRINCIPLES.md` §6 with the second-worst rule.

## AWF-339 Baseline Reading

The frozen baseline that generated this gate had:

- row-scope validation `10 / 10` with canonical overlap on stable rank `2`
- `open_match_ratio min = 0.963276836158192`
- `exact_match_ratio min = 0.46938775510204084`
- `10 / 10` rows improved open-match and exact-match ratios versus the pre-fix
  `AWF-331` summary
- `AWF-339a` not triggered

The low exact-match minimum does not invalidate Gate V1 by itself. The policy
uses near-tail distribution statistics, not minima, for `n >= 10`.

## Verdict Policy

For a future rerun on the same scope:

- `pass`: all three aggregate thresholds pass and no hard block condition fires
- `review`: no hard block condition fires, but one or more aggregate thresholds miss
- `blocked`: any hard block condition fires

`review` means adapter/drift analysis is required before accepting new evidence.
`blocked` means do not continue into threshold, drift, or production-facing work.
