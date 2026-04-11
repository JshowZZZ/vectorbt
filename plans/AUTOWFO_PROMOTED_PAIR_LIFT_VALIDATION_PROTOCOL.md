# AUTOWFO Promoted Pair-Lift Validation Protocol

## Objective
Validate the single strongest support-lift branch that emerged from the promoted-cohort
leave-one-out phase:
- `drop SOL/BTC`

This is a final small current-mode validation step. It exists only to decide whether
the newly lifted pair branch is strong enough to justify one more micro-cohort cycle,
or whether the deferred hierarchical state/trigger mode should finally open next.

## Fixed Conditions
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

## Compared Branches
Reference branch:
- promoted 9-symbol cohort

Validation branch:
- promoted cohort minus `SOL/BTC`

## Fixed Indicator Neighborhood
- `obv_roc`
- `keltner_pos`
- `cmf`
- `ad`
- `chop`
- `dpo`

Combo sizes:
- `2`
- `3`

## Decision Question
Does dropping `SOL/BTC`:
- preserve the promoted-cohort baseline winners,
- keep `DOGE/BTC` inside the lane,
- and justify promoting the lifted `obv_roc + keltner_pos` / `trend_high` / `high`
  pair branch as the next working micro-cohort?

Or is that lift too narrow to justify more current-mode branching?

## Non-Goals
This phase does **not**:
- reopen broader family discovery
- retune exits
- change timeframe
- add staged exits or pyramiding
- implement the deferred hierarchical state/trigger mode
