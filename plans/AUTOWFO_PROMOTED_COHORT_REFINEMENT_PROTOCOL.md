# AUTOWFO Promoted-Cohort Current-Mode Refinement Protocol

## Objective
Take the promoted `drop BNB/BTC` branch and use it as the next working cohort for
one more bounded current-mode refinement cycle.

The goal is not to reopen breadth discovery. The goal is to test whether the promoted
cohort continues to densify the current-mode family enough to justify staying on this
branch, while keeping the original full 10-symbol cohort alive as a breadth-monitor
comparison branch.

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
Use the 9-symbol promoted branch:
- `LTC/BTC`
- `LINK/BTC`
- `SOL/BTC`
- `AVAX/BTC`
- `ETH/BTC`
- `XRP/BTC`
- `ADA/BTC`
- `DOGE/BTC`
- `DOT/BTC`

Excluded:
- `BNB/BTC`

## Breadth-Monitor Baseline
Retain the original 10-symbol cohort as a comparison baseline under the **same**
refinement matrix.

The promoted cohort is the working branch.
The full 10-symbol cohort remains the breadth-monitor branch.

## Fixed Family Neighborhood
Keep the currently supported family neighborhood fixed:
- `obv_roc`
- `keltner_pos`
- `ad`
- `cmf`
- `dpo`
- `chop`

This phase does not add new indicators.

## Refinement Matrix
The bounded refinement step is:
- keep the six-indicator neighborhood fixed
- widen combo sizes from the prior `3..4` family-refinement pass to `2..5`
- run the same matrix on both:
  - the promoted 9-symbol working cohort
  - the full 10-symbol breadth-monitor baseline

Combo sizes:
- `2`
- `3`
- `4`
- `5`

This keeps the phase narrow:
- no new indicators
- no new exit grid
- no timeframe change
- no new strategy mode

But it still gives a real answer to the current question:
- does the stronger cohort merely preserve the old family, or
- does it actually reveal a denser local family under the same anchored contract?

## Decision Question
Does the promoted 9-symbol cohort:
- continue to increase current-mode evidence density,
- preserve the breadth winner,
- and expand the supported `trend_high` branch enough to justify one more current-mode cycle?

Compared against the same `2..5` matrix on the full 10-symbol breadth-monitor branch,
does the promoted cohort:
- improve stable-positive density,
- improve gate-passed density,
- and preserve the core `obv_roc + keltner_pos + ad` family?

## Non-Goals
This phase does **not**:
- reopen 25-indicator breadth
- retune exits
- change timeframe
- implement the deferred hierarchical state/trigger mode
