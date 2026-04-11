# AUTOWFO Symbol-Support Boundary Decision

Date: `2026-04-11`

## Scope
Close the symbol-support boundary phase that followed the bounded current-mode family
refinement.

The question was:
- which symbols act as draggers versus supporters for the current-mode local family, and
- does the family still look broad-cohort viable after bounded leave-one-out testing?

## Protocol
Reference protocol:
- `plans/AUTOWFO_SYMBOL_SUPPORT_BOUNDARY_PROTOCOL.md`

Reference baseline:
- `20260411_family_refine_main`
- `20260411_family_refine_sens`
- baseline paired report:
  - `artifacts/reports/pilot_analysis_awf282_family_refine.json`

Leave-one-out matrix:
- same fixed family neighborhood:
  - `obv_roc`
  - `keltner_pos`
  - `ad`
  - `cmf`
  - `dpo`
  - `chop`
- same combo sizes:
  - `3`
  - `4`
- same fixed ATR exit
- same anchored `2h / 180d`
- each variant drops exactly one symbol from the 10-symbol BTC-cross cohort

Aggregate summary:
- `artifacts/reports/pilot_analysis_awf285_symbol_boundary_summary.json`

## Baseline
Full 10-symbol family-neighborhood baseline from Phase 53:
- `105` compared rows
- `33` stable-positive rows
- `2` gate-passed rows

Baseline gate-passed rows:
1. `obv_roc + keltner_pos + ad` / `trend_any` / `any`
2. `obv_roc + keltner_pos + ad + dpo` / `trend_any` / `any`

## Leave-One-Out Results
Delta versus the baseline:

| Dropped symbol | gate rows | stable rows | Interpretation |
|---|---:|---:|---|
| `BNB/BTC` | `3` (`+1`) | `37` (`+4`) | strongest dragger |
| `ETH/BTC` | `2` (`0`) | `33` (`0`) | neutral |
| `LINK/BTC` | `2` (`0`) | `32` (`-1`) | mild supporter |
| `XRP/BTC` | `2` (`0`) | `32` (`-1`) | mild supporter |
| `DOT/BTC` | `2` (`0`) | `32` (`-1`) | mild supporter |
| `SOL/BTC` | `2` (`0`) | `31` (`-2`) | supporter |
| `AVAX/BTC` | `2` (`0`) | `29` (`-4`) | stronger supporter |
| `ADA/BTC` | `2` (`0`) | `29` (`-4`) | stronger supporter |
| `LTC/BTC` | `1` (`-1`) | `33` (`0`) | supporter with direct gate impact |
| `DOGE/BTC` | `0` (`-2`) | `25` (`-8`) | strongest supporter |

## Main Findings
### 1. `BNB/BTC` is the clearest dragger
Dropping `BNB/BTC` is the only leave-one-out variant that improves both:
- gate-passed rows
- stable-positive rows

It also unlocks one additional gate-passed row:
- `obv_roc + keltner_pos + ad` / `trend_high` / `high`

This is the strongest evidence in the phase.

### 2. `DOGE/BTC` is the clearest supporter
Dropping `DOGE/BTC` removes all gate-passed rows and cuts stable-positive rows from `33`
to `25`.

This is not a neutral symbol.

### 3. The current mode still looks broad-cohort viable
Even with bounded leave-one-out stress:
- the baseline full 10-symbol cohort still passes
- most removals preserve the two baseline gate-passed rows

Interpretation:
- the family is not only a narrow cluster artifact
- the current mode remains broad-cohort viable
- but that viability is uneven across symbols

### 4. The family has one obvious weak edge and one obvious strong edge
At the current anchored protocol:
- weak edge:
  - `BNB/BTC`
- strong edge:
  - `DOGE/BTC`

Everything else is secondary relative to those two.

## Decision
Close Phase 54 with a `current-mode continue` verdict again.

### What is now supported
- The bounded family is real.
- The family is still broad enough to survive the full 10-symbol cohort.
- Symbol membership matters, but not enough to invalidate the current mode.

### What is not supported
- There is still no evidence-based need to open the deferred hierarchical state/trigger
  mode next.

## Next Branch
The next justified branch is a constrained cohort validation phase centered on the
identified dragger:
- keep the current family neighborhood fixed
- compare the baseline 10-symbol cohort against the `drop BNB/BTC` 9-symbol cohort
- determine whether the `BNB/BTC`-dropped branch is:
  - a better working cohort for current-mode refinement, or
  - only a diagnostic branch that should not replace the broad baseline

That next phase should stay small and answer only one question:
- should `BNB/BTC` remain inside the active broad-cohort current-mode lane?
