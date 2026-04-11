# AUTOWFO Promoted-Cohort Current-Mode Refinement Decision

Date: `2026-04-11`

## Scope
Close the promoted-cohort current-mode refinement phase.

The question was:
- does the promoted `drop BNB/BTC` cohort still compound current-mode evidence under
  one more bounded refinement step, and
- is the gain large enough to keep the current single-layer combo-entry mode open
  before the deferred hierarchical state/trigger mode is revisited?

## Protocol
Reference protocol:
- `plans/AUTOWFO_PROMOTED_COHORT_REFINEMENT_PROTOCOL.md`

Shared fixed conditions:
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
- fixed family neighborhood:
  - `obv_roc`
  - `keltner_pos`
  - `ad`
  - `cmf`
  - `dpo`
  - `chop`
- bounded refinement matrix:
  - combo sizes `2..5`

Compared branches:
1. Promoted 9-symbol working cohort
   - runs:
     - `20260411_promoted9_refine_main`
     - `20260411_promoted9_refine_sens`
   - report:
     - `artifacts/reports/pilot_analysis_awf291_promoted9_refine.json`
2. Full 10-symbol breadth-monitor baseline
   - runs:
     - `20260411_baseline10_refine_main`
     - `20260411_baseline10_refine_sens`
   - report:
     - `artifacts/reports/pilot_analysis_awf291_baseline10_refine.json`

## Headline Result

| Branch | compared | stable-positive | gate-passed |
|---|---:|---:|---:|
| promoted 9-symbol | `168` | `49` | `3` |
| full 10-symbol | `168` | `45` | `2` |

The promoted cohort still dominates the breadth-monitor baseline.

## Main Findings
### 1. The promoted cohort preserves its Phase 55 edge
The promoted 9-symbol branch keeps the same three canonical gate-passed rows it already
revealed when `BNB/BTC` was removed:
1. `obv_roc + keltner_pos + ad` / `trend_any` / `any`
2. `obv_roc + keltner_pos + ad + dpo` / `trend_any` / `any`
3. `obv_roc + keltner_pos + ad` / `trend_high` / `high`

The full 10-symbol branch still supports only the first two rows.

### 2. The extra refinement step increases density, but not canonical breadth
Compared with the earlier `3..4` promoted-cohort pass:
- stable-positive rows improved from `37` to `49`
- gate-passed rows stayed at `3`

Compared with the earlier `3..4` full 10-symbol pass:
- stable-positive rows improved from `33` to `45`
- gate-passed rows stayed at `2`

Interpretation:
- widening to `2..5` is useful as a clue-harvesting refinement
- but it does **not** create a new canonical gate-passed family

### 3. The remaining bottleneck is still symbol support, not trade density
Within the promoted 9-symbol branch:
- `25` stable rows fail on symbol support only
- `7` fail on trade gate only
- `14` fail on both

That means symbol support participates in the failure of `39` out of `46` nongate
stable rows.

The full 10-symbol branch shows the same pattern:
- `23` symbol-only failures
- `7` trade-only failures
- `13` both

So the promoted cohort helps, but the current mode is still constrained mainly by
which symbols can jointly carry the family.

### 4. The most informative new rows are near-gate pairs, not new canonical winners
The promoted-cohort `2..5` refinement surfaced several strong, trade-supported rows
that remain below the overall gate because of symbol support:
- `obv_roc + keltner_pos` / `trend_high` / `high`
- `obv_roc + keltner_pos` / `trend_any` / `any`
- `obv_roc + cmf` / `trend_any` / `any`
- `obv_roc + cmf + chop` / `trend_any` / `any`

This is the clearest clue added by Phase 56:
- the current mode is still yielding useful structure
- but that structure now points to support-lift questions, not broader family discovery

## Decision
Close Phase 56 with another `current-mode continue` verdict.

### Why not open the hierarchical mode yet
The promoted cohort still strictly dominates the breadth-monitor baseline.
The current mode is therefore not flat enough to abandon.

### Why not stay on the same refinement axis
The `2..5` pass improved stable density but did not create a new canonical winner.
The next justified question is no longer:
- "is there a broader family?"

It is now:
- "which remaining symbols block the strongest near-gate rows from crossing the support gate?"

## Next Branch
Open a small promoted-cohort support-lift phase:
- keep the promoted 9-symbol cohort as the working branch
- keep the same anchored `2h / 180d` contract
- keep the same fixed exit overlay
- focus only on the strongest near-gate pair/triple rows around:
  - `obv_roc + keltner_pos`
  - `obv_roc + cmf`
  - `obv_roc + cmf + chop`
  - `obv_roc + ad + chop`

The next phase should answer one concrete question:
- can a further bounded symbol-support lift turn those trade-supported near-gate rows
  into additional gate-passed current-mode evidence, or is the promoted cohort now
  close enough to saturation that the deferred hierarchical mode should finally open?
