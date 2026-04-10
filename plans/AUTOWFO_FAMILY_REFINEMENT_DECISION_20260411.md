# AUTOWFO Current-Mode Family Refinement Decision

Date: `2026-04-11`

## Scope
Close the bounded follow-up phase that came after the breadth-first clue-harvesting
campaign.

The question was narrow:
- is the Phase 52 breadth winner `obv_roc + keltner_pos + ad` an isolated point, or
- does it live inside a real local family under the same anchored 10-symbol protocol?

## Protocol
Reference protocol:
- `plans/AUTOWFO_CURRENT_MODE_FAMILY_REFINEMENT_PROTOCOL.md`

Fixed conditions:
- timeframe: `2h`
- anchored window: `180d`
- fixed end: `2026-04-09T14:00:00Z`
- paired WFO:
  - main: `45/30/30`
  - sensitivity: `60/30/30`
- symbols: same 10 BTC-cross majors as Phase 52
- execution overlay:
  - `risk_mode = atr_multiple`
  - `tp_stop = 1.5`
  - `sl_stop = 1.0`
  - `max_hold = 4`
- indicator neighborhood:
  - `obv_roc`
  - `keltner_pos`
  - `ad`
  - `cmf`
  - `dpo`
  - `chop`
- combo sizes:
  - `3`
  - `4`

## Runs
- main: `20260411_family_refine_main`
- sensitivity: `20260411_family_refine_sens`
- paired report:
  - `artifacts/reports/pilot_analysis_awf282_family_refine.json`

## Result
- `105` compared rows
- `33` stable-positive rows
- `2` gate-passed rows

This is materially denser than the breadth triples stage:
- Phase 52 Stage 2:
  - `360` compared
  - `44` stable-positive
  - `1` gate-passed
- Phase 53 bounded family:
  - `105` compared
  - `33` stable-positive
  - `2` gate-passed

Interpretation:
- the breadth winner is not isolated
- the bounded neighborhood does contain a real local family

## Gate-Passed Rows
1. Core family
   - `obv_roc + keltner_pos + ad`
   - `trend_any / any`
   - `min_return = 0.6485%`
   - `min_trades = 2.325`

2. Local superset
   - `obv_roc + keltner_pos + ad + dpo`
   - `trend_any / any`
   - `min_return = 0.4707%`
   - `min_trades = 0.75`

The second row is not random noise. It suggests the core family has at least one
nearby supported expansion path.

## Symbol-Level Support on the Core Family
The core gate-passed row remains positive across the full 10-symbol cohort in both WFOs.

Weakest symbol in main:
- `BNB/BTC = +0.1174%`

Weakest symbol in sensitivity:
- `BNB/BTC = +0.0019%`

This remains a broad-cohort family, not a narrow exact-lane replay artifact.

## Stable Family Structure
Stable-positive frequency across the full `33` stable rows:
- `obv_roc`: `29`
- `cmf`: `21`
- `keltner_pos`: `20`
- `ad`: `17`
- `chop`: `17`
- `dpo`: `13`

This confirms the local family center is:
- `obv_roc`
- `keltner_pos`
- `ad`

and the nearest follow-up family members are:
- `cmf`
- `chop`
- `dpo`

## Regime Clue
Stable rows are no longer concentrated almost entirely in `trend_high`:
- `trend_high`: `13`
- `trend_any`: `11`
- `trend_low`: `9`

Interpretation:
- once the indicator neighborhood is bounded around the breadth winner, the family is
  no longer just a `trend_high` artifact
- the dominant supported gate rows still sit in `trend_any / any`

## Failure Mode
Among the `33` stable-positive rows:
- `26` fail symbol support
- `14` fail the paired trade gate
- `9` fail both
- `17` fail symbol support without also failing trade
- `0` fail trade density alone

Interpretation:
- worst-symbol support is still the primary blocker
- trade density still matters, but it is not creating independent false negatives

## Decision
Close this phase with another `current-mode continue` verdict.

### Supported conclusion
- The current single-layer combo-entry mode still deserves refinement.
- A real local family now exists around the Phase 52 breadth winner.
- Opening the deferred hierarchical state/trigger mode immediately is still not the
  best next branch.

### Next branch
The next justified branch is not another indicator-neighborhood expansion.
The dominant blocker is still symbol support, so the next phase should map:
- which symbols repeatedly preserve the local family
- which symbols repeatedly drag near-miss rows below zero

## Recommended Next Phase
Open a symbol-support boundary phase under the same anchored protocol:
- keep the current core family fixed
- keep the fixed ATR exit
- keep the 10-symbol BTC-cross cohort as the source set
- vary only the symbol membership in a bounded, interpretable way

That next phase should answer:
1. Which symbols are repeatable supporters of the `obv_roc + keltner_pos + ad` family?
2. Which symbols consistently drag otherwise-stable rows below the gate?
3. Does the current mode still generalize across bounded BTC-cross clusters, or is the
   apparent breadth actually a fragile coalition?
