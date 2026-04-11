# AUTOWFO Promoted-Cohort Support-Lift Decision

Date: `2026-04-11`

## Scope
Close the promoted-cohort support-lift phase.

The question was:
- after the promoted 9-symbol branch proved stronger than the full 10-symbol baseline,
  do the strongest near-gate pair/triple rows still have room to improve through
  bounded symbol-support changes, or
- is the current mode already saturated enough that the deferred hierarchical mode
  should open next?

## Protocol
Reference protocol:
- `plans/AUTOWFO_PROMOTED_COHORT_SUPPORT_LIFT_PROTOCOL.md`

Shared fixed conditions:
- timeframe: `2h`
- anchored window:
  - `days = 180`
  - `end = 2026-04-09T14:00:00Z`
- paired WFO:
  - main: `45/30/30`
  - sensitivity: `60/30/30`
- execution overlay:
  - `risk_mode = atr_multiple`
  - `tp_atr_multipliers = [1.5]`
  - `sl_atr_multipliers = [1.0]`
  - `max_holds = [4]`
- fixed indicator neighborhood:
  - `obv_roc`
  - `keltner_pos`
  - `cmf`
  - `ad`
  - `chop`
  - `dpo`
- combo sizes:
  - `2`
  - `3`

Reference baseline:
- promoted 9-symbol branch under the same `2..3` matrix
  - runs:
    - `20260411_supportlift_baseline_main`
    - `20260411_supportlift_baseline_sens`
  - report:
    - `artifacts/reports/pilot_analysis_awf294_supportlift_baseline.json`

Leave-one-out matrix:
- 9 internal promoted-cohort variants
- per-drop reports:
  - `artifacts/reports/pilot_analysis_awf294_supportlift_drop_*.json`
- aggregate summary:
  - `artifacts/reports/pilot_analysis_awf294_supportlift_summary.json`

## Baseline
Promoted 9-symbol `2..3` baseline:
- `105` compared rows
- `24` stable-positive rows
- `2` gate-passed rows

Baseline gate-passed rows:
1. `obv_roc + keltner_pos + ad` / `trend_any` / `any`
2. `obv_roc + keltner_pos + ad` / `trend_high` / `high`

## Support-Lift Results
### 1. `SOL/BTC` is the clearest remaining blocker
Dropping `SOL/BTC` is the only promoted-cohort leave-one-out variant that improves
gate-passed rows:
- baseline promoted branch: `2`
- drop `SOL/BTC`: `3`

The additional gate-passed row is:
- `obv_roc + keltner_pos` / `trend_high` / `high`

This is the exact kind of near-gate pair lift the phase was designed to detect.

### 2. `DOGE/BTC` remains the strongest supporter
Dropping `DOGE/BTC` collapses the support-lift baseline:
- baseline promoted branch: `2` gate-passed
- drop `DOGE/BTC`: `0` gate-passed

So `DOGE/BTC` remains indispensable to the promoted branch.

### 3. Most other symbols are secondary
All other promoted-cohort removals:
- keep gate-passed rows unchanged at `2`, or
- reduce stable-positive density without adding any new gate-passed row

This means the support-lift signal is not diffuse. It concentrates strongly on:
- one blocker:
  - `SOL/BTC`
- one supporter:
  - `DOGE/BTC`

## Interpretation
The current mode is not flat yet.

Why:
- it still produces a new evidence shape under a strictly bounded next-step matrix
- that shape is not just more stable rows; it is one new gate-passed near-gate pair

But the gain is now narrower than before:
- it is no longer about broader family discovery
- it is now about whether a very specific blocker/supporter split justifies one more
  small current-mode branch

## Decision
Close Phase 57 with another `current-mode continue`, but only on a narrower branch.

### Supported conclusion
There is still one justified current-mode follow-up:
- validate the `drop SOL/BTC` pair-lift branch against the promoted 9-symbol baseline

### Unsupported conclusion
There is still no evidence-based reason to jump directly into the deferred hierarchical
mode before validating that one remaining narrow branch.

## Next Branch
Open a final small validation branch around the discovered support-lift:
- compare the promoted 9-symbol baseline against:
  - `drop SOL/BTC`
- keep the `2..3` pair/triple matrix fixed
- keep the same anchored contract and fixed exit overlay
- decide whether the `obv_roc + keltner_pos` / `trend_high` / `high` pair-lift branch:
  - deserves promotion as the next working micro-cohort, or
  - is too narrow to justify delaying the hierarchical mode any longer
