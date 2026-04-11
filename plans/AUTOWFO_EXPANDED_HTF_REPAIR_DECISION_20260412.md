# AUTOWFO Expanded State-Trigger HTF Repair Decision

Date: `2026-04-12`
Ticket: `AWF-312`
Depends on: `AWF-311` (bounded pass), `AWF-304` (bounded fail)

## Scope

Test whether the AWF-311 gate pass (`state=obv_roc+keltner_pos`, `trigger=ad`,
`htf_trend:1d:20`) generalizes to:
- all 3 trigger candidates: `ad`, `cmf`, `chop`
- both state sets: `obv_roc+keltner_pos`, `obv_roc+keltner_pos+ad`

Using the proven `htf_trend:1d:20` overlay plus baseline (no HTF) for comparison.

## Fixed Conditions

Same as `AWF-311` except:
- state candidates restored to both:
  - `["obv_roc", "keltner_pos"]`
  - `["obv_roc", "keltner_pos", "ad"]`
- trigger candidates restored to all:
  - `["ad"]`, `["cmf"]`, `["chop"]`
- HTF overlay: only `1d:20` (rejected `1d:10` per AWF-311 evidence)
- combo count: 2 state × 3 trigger × 2 filter (none + 1d:20) × 3 regime = 36 per run

## Final Runs

- main: `20260411_172613`
- sensitivity: `20260411_172748`

Frozen configs:
- `plans/protocols/awf312_expanded_htf_repair_main.json`
- `plans/protocols/awf312_expanded_htf_repair_sensitivity.json`

Paired report:
- `artifacts/reports/pilot_analysis_awf312_expanded_htf_repair.json`

## Topline Results

| Metric | AWF-312 expanded | AWF-311 repair | AWF-304 first | Frozen baseline |
|---|---:|---:|---:|---:|
| compared | `36` | `9` | `18` | `75` |
| stable-positive | `10` | `3` | `5` | `25` |
| gate-passed | `4` | `1` | `0` | `3` |
| canonical gate-passed | `3` | `1` | `0` | `3` |

**The expanded pilot matches the frozen current-mode baseline in canonical gate density.**

## Gate-Passed Rows

### 1. (Canonical) state=obv_roc+keltner_pos+ad / trigger=ad / htf_trend:1d:20 / trend_any/any

| Metric | Main | Sensitivity |
|---|---:|---:|
| avg OOS return | `16.91%` | `19.57%` |
| avg OOS trades | `1.84` | `1.59` |
| min symbol return | `+4.93%` | `+3.97%` |
| symbol support | `8/8` | `8/8` |

Identical to the AWF-311 canonical winner (the 3-indicator state variant
`obv_roc+keltner_pos+ad` adds `ad` to both state and trigger roles; because of
shared overlap, the realized signal is the same as the 2-indicator variant).

### 2. (Redundant of #1) state=obv_roc+keltner_pos / trigger=ad / htf_trend:1d:20 / trend_any/any

Same min return, trades, and symbol support as #1 — the 2-indicator state variant
is evidence-equivalent to the 3-indicator one.

### 3. (Canonical) state=obv_roc+keltner_pos / trigger=cmf / htf_trend:1d:20 / trend_low/low

| Metric | Main | Sensitivity |
|---|---:|---:|
| avg OOS return | `3.65%` | `3.65%` |
| avg OOS trades | `0.16` | `0.16` |
| symbol support | `8/8` nonneg | `8/8` nonneg |

**Warning: avg trades = 0.16**. This row technically passes the gate because the
few trades it takes are nonnegative, but it is practically insufficient — less than
1 trade per 8 OOS segments across the cohort. This is a gate artifact, not a viable
production signal.

### 4. (Canonical) state=obv_roc+keltner_pos+ad / trigger=chop / htf_trend:1d:20 / trend_high/high

| Metric | Main | Sensitivity |
|---|---:|---:|
| avg OOS return | `0.59%` | `0.59%` |
| avg OOS trades | `0.03` | `0.03` |
| symbol support | `8/8` nonneg | `8/8` nonneg |

**Warning: avg trades = 0.03**. Same issue as #3 but even more extreme. The entry
condition is too restrictive — the combined state-trigger-HTF filter almost never
fires.

## Interpretation

### 1. The `ad` trigger gate pass is confirmed and reproducible

Rows #1 and #2 reproduce the AWF-311 result exactly. Both state variants produce
the same practical signal (because `ad` is shared between state and trigger). The
`htf_trend:1d:20` overlay remains the critical repair ingredient. This is the only
row with meaningful trade density.

### 2. The `cmf` and `chop` triggers technically pass but are not viable

Both new canonical rows (#3 and #4) have avg OOS trades well below `1.0`. They pass
the strictest interpretation of the gate (nonnegative symbols, nonnegative return)
but do so by barely trading at all. A future trade-density floor (e.g., min 1.0
avg OOS trades) would reject them.

### 3. The `1d:20` overlay generalizes as a symbol-support repair

All 4 gate-passed rows use `htf_trend:1d:20`. Zero baseline rows (no HTF) pass the
gate. This confirms that the daily 20-period trend filter is the mechanism that
repairs `DOT/BTC` symbol support across all trigger variants — not just `ad`.

### 4. The hierarchical mode now matches current-mode canonical density

With 3 canonical gate-passed rows (1 practically viable), the hierarchical mode
formally equals the frozen current-mode baseline's 3 canonical gate-passed rows.
However, the practical comparison is more conservative:

| Mode | Canonical gate-passed | Practically viable (trades ≥ 1.0) |
|---|---:|---:|
| Hierarchical (AWF-312) | `3` | `1` |
| Current-mode baseline | `3` | `3` |

So the hierarchical mode has caught up on paper but not yet in practical density.

## Decision

Classification: `confirming pass`

Decision:
- close `AWF-312` as a confirming expansion of AWF-311
- retain `state=obv_roc+keltner_pos / trigger=ad / htf_trend:1d:20 / trend_any/any`
  as the only practically viable hierarchical gate-passed configuration
- discard `cmf` and `chop` trigger rows as gate artifacts (insufficient trade density)
- keep Phase 60 open; the hierarchical mode has concrete evidence but still needs
  density expansion before it can replace the frozen current-mode reference

## Consequences For Phase 60

The validated hierarchical production candidate is now narrow and specific:
- state: `obv_roc + keltner_pos`
- trigger: `ad`
- HTF filter: `htf_trend:1d:20`
- regime: `trend_any` / `any`
- exit: `state_reversal`

Next natural steps:
- temporal robustness replay of the validated configuration on the older anchor
  window (AWF-310 style)
- consider whether other trigger indicators beyond the current 5-indicator
  neighborhood might add viable density
- consider a stricter trade-density floor in the gate criteria to avoid future
  near-zero-trade artifacts
