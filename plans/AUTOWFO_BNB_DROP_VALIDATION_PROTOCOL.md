# AUTOWFO BNB-Drop Validation Protocol

## Objective
Validate whether the `BNB/BTC`-dropped branch should become the preferred current-mode
working cohort, or remain only a diagnostic branch.

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

## Fixed Family Neighborhood
- `obv_roc`
- `keltner_pos`
- `ad`
- `cmf`
- `dpo`
- `chop`

Combo sizes:
- `3`
- `4`

## Cohort Comparison
Reference cohort:
- full 10-symbol BTC-cross major set

Validation cohort:
- same cohort minus `BNB/BTC`

## Decision Question
Does dropping `BNB/BTC`:
- produce a materially better working current-mode lane that deserves promotion as the
  default refinement cohort, or
- merely expose a helpful diagnostic branch while the full 10-symbol cohort remains the
  correct primary baseline?

## Non-Goals
This phase does **not**:
- reopen indicator breadth
- retune exits
- add new regimes or timeframes
- implement the deferred hierarchical state/trigger mode
