# AUTOWFO SOL-Drop Micro-Cohort Decision

Date: `2026-04-11`

## Scope
Close the final current-mode micro-cohort refinement phase.

The question was:
- does the validated `drop SOL/BTC` branch still compound evidence enough to justify
  yet another current-mode cycle, or
- has the current single-layer combo-entry mode now reached its practical limit?

## Protocol
Reference protocol:
- `plans/AUTOWFO_SOL_DROP_MICRO_COHORT_PROTOCOL.md`

Compared branches:
1. Promoted 9-symbol baseline
   - runs:
     - `20260411_microcohort_promoted9_main`
     - `20260411_microcohort_promoted9_sens`
   - report:
     - `artifacts/reports/pilot_analysis_awf300_microcohort_promoted9.json`
2. `drop SOL/BTC` 8-symbol micro-cohort
   - runs:
     - `20260411_microcohort_dropsol_main`
     - `20260411_microcohort_dropsol_sens`
   - report:
     - `artifacts/reports/pilot_analysis_awf300_microcohort_dropsol.json`

Shared fixed conditions:
- timeframe: `2h`
- anchored window: `180d`
- fixed end: `2026-04-09T14:00:00Z`
- paired WFO:
  - `45/30/30`
  - `60/30/30`
- execution overlay:
  - `risk_mode = atr_multiple`
  - `tp_atr_multipliers = [1.5]`
  - `sl_atr_multipliers = [1.0]`
  - `max_holds = [4]`
- indicator neighborhood:
  - `obv_roc`
  - `keltner_pos`
  - `ad`
  - `cmf`
  - `chop`
- combo sizes:
  - `2`
  - `3`
  - `4`

## Baseline vs Micro-Cohort

| Branch | compared | stable-positive | gate-passed |
|---|---:|---:|---:|
| promoted 9-symbol | `75` | `27` | `2` |
| drop `SOL/BTC` micro-cohort | `75` | `25` | `3` |

## What Changed
The `drop SOL/BTC` micro-cohort:
- preserves both promoted-baseline winners
- adds one new canonical gate-passed pair
- but loses `2` stable-positive rows overall

### Promoted-baseline winners
1. `obv_roc + keltner_pos + ad` / `trend_any` / `any`
2. `obv_roc + keltner_pos + ad` / `trend_high` / `high`

### Additional micro-cohort winner
3. `obv_roc + keltner_pos` / `trend_high` / `high`

## Interpretation
This is the clearest signal so far that the current mode has reached diminishing returns.

Why:
- a further narrowing step still adds one useful canonical row
- but it no longer improves the broader stable-positive surface
- the gain now depends on both:
  - a narrower cohort
  - a narrower family center

So the current mode still yields information, but only by compressing scope further.
That is usually the point where a new strategy model should open instead of continuing to
shrink the old one.

## Decision
Close the current-mode branch here.

### Keep as frozen reference
Retain the `drop SOL/BTC` micro-cohort as the strongest frozen current-mode reference
branch discovered so far.

### Do not continue shrinking current mode
Do not open another narrower current-mode search branch after this one.

## Next Branch
Open the deferred hierarchical state/trigger mode as the next active development branch.

The new mode should be seeded directly from the current-mode evidence:
- long-horizon state candidates:
  - `obv_roc + keltner_pos`
  - `obv_roc + keltner_pos + ad`
- short-horizon trigger candidates:
  - `ad`
  - `cmf`
  - `chop`

The purpose of the new mode is no longer speculative.
It now has a clear evidence-backed starting point:
- the current mode has already isolated the state-like pair and the strongest nearby
  trigger companions.
