# AUTOWFO Promoted-Cohort Support-Lift Protocol

## Objective
Follow the promoted-cohort refinement phase by testing whether the remaining weakness in
the current mode is concentrated in one or two symbols inside the promoted 9-symbol
cohort.

The question is no longer whether the promoted cohort is better than the full
10-symbol baseline. It is.
The next question is:
- can the strongest near-gate current-mode rows be lifted through bounded symbol-support
  changes, or
- are they already close enough to saturation that the deferred hierarchical mode should
  open next?

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

## Working Cohort
Use the promoted 9-symbol branch:
- `LTC/BTC`
- `LINK/BTC`
- `SOL/BTC`
- `AVAX/BTC`
- `ETH/BTC`
- `XRP/BTC`
- `ADA/BTC`
- `DOGE/BTC`
- `DOT/BTC`

## Fixed Candidate Neighborhood
Keep the refinement tightly focused on the indicators that dominate the promoted-cohort
stable rows:
- `obv_roc`
- `keltner_pos`
- `cmf`
- `ad`
- `chop`
- `dpo`

Combo sizes:
- `2`
- `3`

This keeps the phase centered on the strongest near-gate pair/triple rows rather than
reopening broader family discovery.

## Target Rows
The phase is designed to study support lift around these promoted-cohort clues:
- `obv_roc + keltner_pos` / `trend_high` / `high`
- `obv_roc + keltner_pos` / `trend_any` / `any`
- `obv_roc + cmf` / `trend_any` / `any`
- `obv_roc + cmf + chop` / `trend_any` / `any`
- `obv_roc + ad + chop` / `trend_high` / `high`

## Support-Lift Matrix
- use the promoted 9-symbol cohort as the source branch
- run bounded leave-one-out variants inside that cohort
- drop exactly one symbol at a time
- do not change any other dimension

This produces an interpretable answer:
- if a near-gate pair/triple crosses into gate-passed only when one symbol is removed,
  that symbol is a likely blocker for the promoted branch
- if no leave-one-out variant lifts the near-gate rows, the current mode is likely close
  to saturation on this branch

## Decision Question
Does the promoted cohort still have room for one more symbol-support-focused current-mode
cycle, or is the remaining evidence too saturated to justify delaying the deferred
hierarchical state/trigger mode any longer?

## Non-Goals
This phase does **not**:
- reopen 25-indicator breadth
- change timeframe
- retune exits
- add staged exits or pyramiding
- implement the deferred hierarchical state/trigger mode
