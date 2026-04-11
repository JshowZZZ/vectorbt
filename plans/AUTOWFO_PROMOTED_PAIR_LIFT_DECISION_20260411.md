# AUTOWFO Promoted Pair-Lift Validation Decision

Date: `2026-04-11`

## Scope
Close the promoted pair-lift validation phase.

The question was:
- is the newly lifted `drop SOL/BTC` branch strong enough to justify one more
  micro-cohort current-mode cycle, or
- is the gain too narrow to justify delaying the deferred hierarchical mode any longer?

## Protocol
Reference protocol:
- `plans/AUTOWFO_PROMOTED_PAIR_LIFT_VALIDATION_PROTOCOL.md`

Compared branches:
1. Promoted 9-symbol support-lift baseline
   - report:
     - `artifacts/reports/pilot_analysis_awf294_supportlift_baseline.json`
2. `drop SOL/BTC` support-lift branch
   - report:
     - `artifacts/reports/pilot_analysis_awf294_supportlift_drop_sol-btc.json`

Shared fixed conditions:
- timeframe: `2h`
- anchored window: `180d`
- fixed end: `2026-04-09T14:00:00Z`
- paired WFO:
  - `45/30/30`
  - `60/30/30`
- execution overlay:
  - `risk_mode = atr_multiple`
  - `tp_atr_multipliers = [1.5]`
  - `sl_atr_multipliers = [1.0]`
  - `max_holds = [4]`
- indicator neighborhood:
  - `obv_roc`
  - `keltner_pos`
  - `cmf`
  - `ad`
  - `chop`
  - `dpo`
- combo sizes:
  - `2`
  - `3`

## Baseline vs Pair-Lift Branch

| Branch | compared | stable-positive | gate-passed |
|---|---:|---:|---:|
| promoted 9-symbol baseline | `105` | `24` | `2` |
| drop `SOL/BTC` | `105` | `24` | `3` |

## What Improves
The `drop SOL/BTC` branch:
- preserves both promoted-baseline gate-passed rows
- adds one new gate-passed row
- keeps stable-positive density flat instead of paying for the gain with lower stability

### Preserved baseline rows
1. `obv_roc + keltner_pos + ad` / `trend_any` / `any`
2. `obv_roc + keltner_pos + ad` / `trend_high` / `high`

### Additional lifted row
3. `obv_roc + keltner_pos` / `trend_high` / `high`

## Interpretation
This is a real improvement, not just a cosmetic branch.

Why:
- the new branch adds one canonical gate-passed pair
- it does so without reducing stable-positive rows
- it keeps the promoted branch's existing winners intact

At the same time, the branch is clearly narrow:
- it depends on dropping `SOL/BTC`
- it still requires keeping `DOGE/BTC`
- it does not reopen broad family discovery

## Decision
Promote `drop SOL/BTC` as the next working micro-cohort branch for one final
current-mode refinement step.

### Why not open the hierarchical mode immediately
The current mode still produced one clean, bounded, evidence-backed improvement.
That is enough to justify one final micro-cohort cycle before opening the deferred mode.

### Why only one final cycle
The gain is now highly specific. The next branch must stay narrow and pair-centered.
If that micro-cohort branch does not compound evidence further, the deferred
hierarchical state/trigger mode should become the next default branch.

## Next Branch
Open a final current-mode micro-cohort refinement phase:
- working cohort:
  - promoted branch minus `SOL/BTC`
- keep `DOGE/BTC` inside the lane
- keep the anchored `2h / 180d` contract fixed
- narrow the family around the lifted pair:
  - `obv_roc`
  - `keltner_pos`
  - `ad`
  - `cmf`
  - `chop`

The next phase should answer only one question:
- does the lifted pair branch produce a denser local family in the 8-symbol
  micro-cohort, or has the current mode finally reached its practical limit?
