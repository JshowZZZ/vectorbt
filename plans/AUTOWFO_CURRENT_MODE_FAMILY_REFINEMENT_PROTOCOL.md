# AUTOWFO Current-Mode Family Refinement Protocol

## Objective
Follow Phase 52 with one bounded current-mode refinement pass before opening the
deferred hierarchical state/trigger mode.

The question is narrow:
- is `obv_roc + keltner_pos + ad` an isolated breadth winner, or
- does it sit inside a real local family that still survives strict symbol support on
  the anchored 10-symbol cohort?

## Fixed Research Conditions
- timeframe: `2h`
- anchored window:
  - `days = 180`
  - `end = 2026-04-09T14:00:00Z`
- paired WFO:
  - main: `45/30/30`
  - sensitivity: `60/30/30`
- regime preset: `pilot_trend_3`
- indicator params:
  - `pilot_fixed_indicator_params = true`
  - `pilot_single_trend_mom = true`
- execution overlay:
  - `risk_mode = atr_multiple`
  - `tp_atr_multipliers = [1.5]`
  - `sl_atr_multipliers = [1.0]`
  - `max_holds = [4]`

## Symbol Cohort
Same fixed 10-symbol BTC-cross major cohort as Phase 52:
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

## Indicator Neighborhood
Bounded local family around the Phase 52 breadth winner:
- `obv_roc`
- `keltner_pos`
- `ad`
- `cmf`
- `dpo`
- `chop`

Rationale:
- gate-passed breadth family:
  - `obv_roc + keltner_pos + ad`
- strongest nearby stable companions from Phase 52:
  - `cmf`
  - `dpo`
  - `chop`

## Campaign Structure
- combo sizes: `3` and `4`
- no widened exit grid
- no new symbols
- no new timeframes

## Decision Questions
1. Does the gate-passed breadth winner remain alive when surrounded by nearby family members?
2. Which indicator additions preserve all-symbol support?
3. Is `trend_any` still the best carrier, or does `trend_high` become dominant in the bounded neighborhood?
4. Does the current mode still have a real local family, or does evidence flatten fast enough to justify opening the deferred hierarchical mode?

## Non-Goals
This phase does **not**:
- reopen the 25-indicator breadth campaign
- add staged exits
- add pyramiding
- implement the deferred hierarchical state/trigger mode
