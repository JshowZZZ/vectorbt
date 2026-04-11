# AUTOWFO State-Trigger Mode Protocol

## Objective
Open the deferred hierarchical state/trigger mode as the next active strategy model.

This mode must coexist with the existing single-layer combo-entry mode.
It is additive, not a replacement.

## Why Now
The current single-layer combo-entry mode has been carried through:
- breadth discovery
- family refinement
- symbol-boundary mapping
- cohort promotion
- support-lift mapping
- final micro-cohort refinement

It still yields useful evidence, but only through increasingly narrow branches.
That is the signal to open the next model family.

## Minimal Mode Definition
The first version should express:
- long-horizon state filter
- short-horizon trigger
- state-driven exit
- no add-on logic yet

Working interpretation:
1. state determines whether the system is allowed to hold a long position
2. trigger determines when to enter while state is active
3. state reversal exits the position

## Compatibility Rules
- keep the existing combo-entry mode intact
- add a new strategy mode, do not mutate existing behavior
- preserve the same artifact and analysis contracts where possible
- continue using anchored `2h / 180d` paired WFO for the first pilot
- land the new mode behind an explicit config surface, not as implicit special-case logic

## Frozen Comparison Baseline
The first hierarchical pilot must be compared against the strongest frozen current-mode
reference branch from Phase 59:

- protocol reference:
  - `plans/AUTOWFO_SOL_DROP_MICRO_COHORT_PROTOCOL.md`
- decision reference:
  - `plans/AUTOWFO_SOL_DROP_MICRO_COHORT_DECISION_20260411.md`

Working cohort for the first hierarchical pilot:
- `LTC/BTC`
- `LINK/BTC`
- `AVAX/BTC`
- `ETH/BTC`
- `XRP/BTC`
- `ADA/BTC`
- `DOGE/BTC`
- `DOT/BTC`

## Seed Candidates from Current-Mode Evidence
### State candidates
- `obv_roc + keltner_pos`
- `obv_roc + keltner_pos + ad`

### Trigger candidates
- `ad`
- `cmf`
- `chop`

These are not final winners.
They are the smallest evidence-backed starting pool.

## First-Pilot Constraints
- timeframe: `2h`
- anchored window:
  - `days = 180`
  - `end = 2026-04-09T14:00:00Z`
- paired WFO:
  - main: `45/30/30`
  - sensitivity: `60/30/30`
- exit rule:
  - state reversal
- working cohort:
  - `drop SOL/BTC` frozen micro-cohort
- no staged exits yet
- no pyramiding yet
- no full parameter grid yet
- fixed indicator params only
- same three-regime trend-only preset:
  - `trend_any`
  - `trend_high`
  - `trend_low`

## Initial Search Shape
- one state family at a time
- one trigger family at a time
- no multi-trigger stacking in the first pilot
- no add-on logic in the first pilot
- explicit first pilot matrix:
  - state sets:
    - `["obv_roc", "keltner_pos"]`
    - `["obv_roc", "keltner_pos", "ad"]`
  - trigger sets:
    - `["ad"]`
    - `["cmf"]`
    - `["chop"]`
- allow overlapping roles in the first pilot:
  - `ad` may appear as both a state companion and a trigger candidate

Expected paired search width before regime/WFO duplication:
- `2` state sets
- `3` trigger sets
- `3` regimes
- total raw role combinations per run: `18`

The first pilot question is simple:
- does a state/trigger split outperform the frozen current-mode micro-cohort baseline
  on the same anchored contract?

## Frozen Config Contract
The new mode should be introduced through explicit config keys so it remains additive and
replayable:

- `strategy_mode = state_trigger_entry`
- `state_indicator_sets = [["obv_roc", "keltner_pos"], ["obv_roc", "keltner_pos", "ad"]]`
- `trigger_indicator_sets = [["ad"], ["cmf"], ["chop"]]`
- `allow_shared_indicator_roles = true`
- `state_exit_policy = state_reversal`

The existing current mode remains:
- `strategy_mode = combo_entry`

## Expected First Implementation Scope
The first implementation should stop at the smallest researchable version:
- support long-horizon state plus short-horizon trigger
- support state-reversal exit
- preserve the current result schema as much as practical
- add explicit role metadata to results where needed

The first implementation should **not** yet include:
- pyramiding
- staged take profit
- separate trigger-timeframe support
- broader indicator discovery
- TP/SL grid interaction

## First-Pilot Decision Outputs
`AWF-304` should be able to answer these specific questions:
- does the best hierarchical row beat the frozen current-mode `drop SOL/BTC` baseline
  on strict paired gate status?
- if not, does it at least improve stable-positive density or worst-symbol support?
- does any trigger candidate consistently outperform the current-mode nearest companion
  role for the same state family?

## Non-Goals
This phase does **not**:
- reopen broad 25-indicator discovery
- retune exits beyond state reversal
- add pyramiding immediately
- retire the existing combo-entry mode
