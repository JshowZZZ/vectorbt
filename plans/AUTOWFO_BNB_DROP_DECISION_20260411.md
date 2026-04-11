# AUTOWFO BNB-Drop Cohort Validation Decision

Date: `2026-04-11`

## Scope
Close the small cohort-comparison phase that asks whether the `drop BNB/BTC` branch
should be promoted beyond diagnostic use.

## Protocol
Reference protocol:
- `plans/AUTOWFO_BNB_DROP_VALIDATION_PROTOCOL.md`

Compared branches:
1. Full 10-symbol family-neighborhood baseline
   - report:
     - `artifacts/reports/pilot_analysis_awf282_family_refine.json`
2. `drop BNB/BTC` leave-one-out branch
   - report:
     - `artifacts/reports/pilot_analysis_awf285_drop_bnb-btc.json`

Shared fixed conditions:
- timeframe: `2h`
- anchored window: `180d`
- fixed end: `2026-04-09T14:00:00Z`
- paired WFO:
  - `45/30/30`
  - `60/30/30`
- family neighborhood:
  - `obv_roc`
  - `keltner_pos`
  - `ad`
  - `cmf`
  - `dpo`
  - `chop`
- combo sizes:
  - `3`
  - `4`

## Baseline vs BNB-Dropped Branch

| Branch | compared | stable-positive | gate-passed |
|---|---:|---:|---:|
| full 10-symbol | `105` | `33` | `2` |
| drop `BNB/BTC` | `105` | `37` | `3` |

## Incremental Gain from Dropping `BNB/BTC`
The `drop BNB/BTC` branch:
- keeps both baseline gate-passed rows
- adds one new gate-passed row
- increases stable-positive rows by `4`

### Baseline gate-passed rows
1. `obv_roc + keltner_pos + ad` / `trend_any` / `any`
2. `obv_roc + keltner_pos + ad + dpo` / `trend_any` / `any`

### Additional gate-passed row after dropping `BNB/BTC`
3. `obv_roc + keltner_pos + ad` / `trend_high` / `high`

## Interpretation
This is not a cosmetic improvement.

Dropping `BNB/BTC`:
- does not collapse the baseline family
- preserves the original gate-passed current-mode lane
- unlocks an additional supported trend-high branch

So the branch is stronger than the baseline, not merely different.

## Decision
Promote the `drop BNB/BTC` branch as the preferred current-mode working cohort for the
next refinement cycle.

### Important qualification
The full 10-symbol cohort should not be discarded.

Use:
- `drop BNB/BTC` as the active refinement branch
- full 10-symbol cohort as the breadth-monitor baseline

This preserves two things at once:
- the strongest working branch for current-mode progress
- a wider baseline that can detect whether future refinement is merely exploiting the
  removal of a known dragger

## Next Branch
Open the next phase as a promoted-cohort refinement branch:
- fixed cohort:
  - all Phase 53 symbols except `BNB/BTC`
- same anchored protocol
- same execution overlay
- same current-mode family neighborhood as the starting point

The next phase should test whether the promoted 9-symbol branch:
1. develops a denser local family than the full 10-symbol baseline
2. preserves the breadth winner while expanding the `trend_high` branch
3. still justifies staying in the current mode before the deferred hierarchical mode is opened
