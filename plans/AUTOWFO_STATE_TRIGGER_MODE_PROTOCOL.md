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

Working interpretation:
1. state determines whether the system is allowed to hold a long position
2. trigger determines when to enter while state is active
3. state reversal exits the position

## Compatibility Rules
- keep the existing combo-entry mode intact
- add a new strategy mode, do not mutate existing behavior
- preserve the same artifact and analysis contracts where possible
- continue using anchored `2h / 180d` paired WFO for the first pilot

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
- no staged exits yet
- no pyramiding yet
- no full parameter grid yet

## Initial Search Shape
- one state family at a time
- one trigger at a time
- no multi-trigger stacking in the first pilot
- no add-on logic in the first pilot

The first pilot question is simple:
- does a state/trigger split outperform the frozen current-mode micro-cohort baseline
  on the same anchored contract?

## Non-Goals
This phase does **not**:
- reopen broad 25-indicator discovery
- retune exits beyond state reversal
- add pyramiding immediately
- retire the existing combo-entry mode
