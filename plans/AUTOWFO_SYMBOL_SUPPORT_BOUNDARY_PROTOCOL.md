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

## Fixed Family Neighborhood
Use the same bounded neighborhood that closed Phase 53:
- `obv_roc`
- `keltner_pos`
- `ad`
- `cmf`
- `dpo`
- `chop`

Combo sizes remain:
- `3`
- `4`

This keeps the local-family question alive while varying only symbol membership.

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

## Boundary-Mapping Matrix
Reference baseline:
- reuse the Phase 53 full 10-symbol paired family-neighborhood result
  - `20260411_family_refine_main`
  - `20260411_family_refine_sens`

New execution matrix:
- run the same family-neighborhood protocol on 10 bounded leave-one-out variants
- each variant removes exactly one symbol from the 10-symbol source cohort
- no other dimension changes

This produces interpretable answers:
- if dropping one symbol materially increases gate-passed rows, that symbol is a likely dragger
- if dropping one symbol weakens or removes the existing gate-passed rows, that symbol is a likely supporter

## Decision Questions
1. Which symbols consistently preserve all-symbol support for the local family neighborhood?
2. Which symbols repeatedly act as draggers in otherwise-stable rows?
3. Does the family remain broad-cohort viable, or is it better interpreted as a
   bounded BTC-cross cluster family?

## Non-Goals
This phase does **not**:
- introduce new indicators
- retune exits
- introduce staged exits or pyramiding
- implement the deferred hierarchical state/trigger mode
