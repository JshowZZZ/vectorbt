# AUTOWFO Symbol-Support Boundary Protocol

## Objective
Follow the bounded family-refinement phase by mapping symbol supporters versus draggers
for the current-mode local family.

The question is no longer whether the family exists. It does.
The next question is:
- which symbol memberships preserve it, and
- which symbol memberships repeatedly break all-symbol support.

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

## Fixed Core Family
Primary family:
- `obv_roc`
- `keltner_pos`
- `ad`

Secondary local extension:
- `dpo`

## Source Cohort
Use the same 10-symbol BTC-cross major set as the source universe:
- `LTC/BTC`
- `LINK/BTC`
- `SOL/BTC`
- `AVAX/BTC`
- `ETH/BTC`
- `BNB/BTC`
- `XRP/BTC`
- `ADA/BTC`
- `DOGE/BTC`
- `DOT/BTC`

## Boundary-Mapping Principle
Vary symbol membership only in bounded, interpretable ways:
- start with the full 10-symbol cohort
- then test small, explainable sub-cohorts or leave-one-out variants
- do not reopen indicator breadth, timeframe breadth, or exit breadth in the same phase

## Decision Questions
1. Which symbols consistently preserve all-symbol support for the core family?
2. Which symbols repeatedly act as draggers in otherwise-stable rows?
3. Does the family remain broad-cohort viable, or is it better interpreted as a
   bounded BTC-cross cluster family?

## Non-Goals
This phase does **not**:
- introduce new indicators
- retune exits
- introduce staged exits or pyramiding
- implement the deferred hierarchical state/trigger mode
