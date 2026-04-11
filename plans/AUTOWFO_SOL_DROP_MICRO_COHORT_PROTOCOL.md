# AUTOWFO SOL-Drop Micro-Cohort Protocol

## Objective
Run one final current-mode micro-cohort refinement around the validated `drop SOL/BTC`
pair-lift branch.

This phase is intentionally narrow. It is the last current-mode branch before the
deferred hierarchical state/trigger mode should open by default if evidence stops
compounding.

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
Use the promoted branch minus `SOL/BTC`:
- `LTC/BTC`
- `LINK/BTC`
- `AVAX/BTC`
- `ETH/BTC`
- `XRP/BTC`
- `ADA/BTC`
- `DOGE/BTC`
- `DOT/BTC`

## Breadth-Monitor Reference
Retain the promoted 9-symbol baseline as the comparison branch.

## Fixed Indicator Neighborhood
Center the final refinement on the lifted pair and its strongest nearby companions:
- `obv_roc`
- `keltner_pos`
- `ad`
- `cmf`
- `chop`

Combo sizes:
- `2`
- `3`
- `4`

## Decision Question
Does the `drop SOL/BTC` micro-cohort:
- preserve the validated lifted pair
- keep the promoted branch's core triple winners
- and produce a denser local family than the promoted 9-symbol baseline?

If not, the deferred hierarchical state/trigger mode should open next.

## Non-Goals
This phase does **not**:
- reopen broader family discovery
- retune exits
- change timeframe
- add staged exits or pyramiding
- implement the deferred hierarchical state/trigger mode yet
