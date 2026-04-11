# AUTOWFO State-Trigger HTF Repair Pilot Decision

Date: `2026-04-12`
Ticket: `AWF-311`
Depends on: `AWF-304` (bounded fail), `AWF-309` (bounded pass)

## Scope

Repair the single near-pass hierarchical row from `AWF-304`:

- state: `obv_roc + keltner_pos`
- trigger: `ad`
- regime: `trend_any` / `any`

That row failed the symbol-support gate because `DOT/BTC` was the sole negative
symbol in both main (`-1.45%`) and sensitivity (`-2.43%`).

The repair strategy was to overlay daily HTF trend confirmation from the `AWF-309`
bounded pass (`1d:10`, `1d:20`) onto the narrowed state-trigger search, so the
combined pilot tests 3 filter variants × 3 regime cells = 9 combos per run.

## Fixed Conditions

- timeframe: `2h`
- anchored window:
  - `days = 180`
  - `end = 2026-04-09T14:00:00Z`
- paired WFO:
  - main: `45/30/30`
  - sensitivity: `60/30/30`
- working cohort (8-symbol `drop SOL/BTC`):
  - `LTC/BTC`, `LINK/BTC`, `AVAX/BTC`, `ETH/BTC`
  - `XRP/BTC`, `ADA/BTC`, `DOGE/BTC`, `DOT/BTC`
- state candidates: `["obv_roc", "keltner_pos"]` only
- trigger candidates: `["ad"]` only
- overlap allowed
- exit rule: `state_reversal`
- HTF overlay variants:
  - baseline (no HTF)
  - `htf_trend:1d:10`
  - `htf_trend:1d:20`
- fixed execution overlay:
  - `risk_mode = atr_multiple`
  - `tp_atr_multipliers = [1.5]`
  - `sl_atr_multipliers = [1.0]`
  - `max_holds = [4]`

## Final Runs

- main: `20260411_171358`
- sensitivity: `20260411_171537`

Frozen configs:
- `plans/protocols/awf311_state_trigger_htf_repair_main.json`
- `plans/protocols/awf311_state_trigger_htf_repair_sensitivity.json`

Corrected paired report:
- `artifacts/reports/pilot_analysis_awf311_state_trigger_htf_repair.json`

## Topline Results

| Metric | AWF-311 repair | AWF-304 first pilot | Frozen baseline |
|---|---:|---:|---:|
| compared | `9` | `18` | `75` |
| stable-positive | `3` | `5` | `25` |
| gate-passed | `1` | `0` | `3` |

**The repair pilot produced the first gate-passed hierarchical state-trigger row.**

## Gate-Passed Row Detail

| Field | Value |
|---|---|
| state | `obv_roc + keltner_pos` |
| trigger | `ad` |
| HTF filter | `htf_trend:1d:20` |
| regime | `trend_any` / `any` |
| main avg OOS return | `16.91%` |
| sensitivity avg OOS return | `19.57%` |
| main avg OOS trades | `1.84` |
| sensitivity avg OOS trades | `1.59` |
| main min symbol return | `+4.93%` (DOT/BTC) |
| sensitivity min symbol return | `+3.97%` (DOT/BTC) |
| symbol support | `8/8` positive in both runs |

### Per-Symbol Return (htf_trend:1d:20, trend_any/any)

| Symbol | Main return | Sens return |
|---|---:|---:|
| DOT/BTC | `+4.93%` | `+3.97%` |
| LINK/BTC | `+11.78%` | `+14.98%` |
| ADA/BTC | `+12.39%` | `+15.75%` |
| XRP/BTC | `+14.57%` | `+12.64%` |
| AVAX/BTC | `+17.42%` | `+19.15%` |
| LTC/BTC | `+22.92%` | `+31.67%` |
| DOGE/BTC | `+23.52%` | `+26.73%` |
| ETH/BTC | `+27.77%` | `+31.69%` |

### Before vs After: DOT/BTC Repair

| Metric | AWF-304 (no HTF) | AWF-311 (1d:20) | Delta |
|---|---:|---:|---:|
| Main DOT/BTC return | `-1.45%` | `+4.93%` | `+6.38pp` |
| Sens DOT/BTC return | `-2.43%` | `+3.97%` | `+6.40pp` |
| Main nonneg symbols | `7/8` | `8/8` | `+1` |
| Sens nonneg symbols | `7/8` | `8/8` | `+1` |

## Filter Variant Comparison

| Variant | Stable-positive | Gate-passed | Blocker |
|---|---:|---:|---|
| baseline (no HTF) | `1` | `0` | DOT/BTC negative |
| `htf_trend:1d:10` | `1` | `0` | XRP/BTC negative (-3.86%/-3.92%) |
| `htf_trend:1d:20` | `1` | `1` | none — all symbols positive |

Key finding: `1d:10` fixes DOT/BTC but breaks XRP/BTC. Only `1d:20` achieves full
cohort coverage. The longer daily window is more stable across the symbol set.

## Interpretation

### 1. The repair succeeded — first hierarchical gate pass

The `htf_trend:1d:20` variant produces the first gate-passed state-trigger row.
This is the strongest evidence yet that the hierarchical mode can work, though it
requires daily HTF confirmation to achieve full symbol support.

### 2. The daily HTF filter acts as a DOT/BTC regime gate

Without HTF confirmation, DOT/BTC enters unfavorable state-trigger positions and
produces marginal losses. The 20-day daily trend filter removes enough of those
entries to push DOT/BTC positive while preserving profitable entries for all other
symbols.

### 3. Trade density is reduced but still sufficient

The HTF overlay reduces average trades from `2.44–2.69` (no filter) to `1.59–1.84`
(`1d:20`). This is a material reduction but still passes the trade gate. The
trade-density cost is the price of broader symbol support.

### 4. The gate-passed row is structurally coherent

The winning configuration is the exact alignment predicted by the accumulated evidence
chain:

- state layer: `obv_roc + keltner_pos` (strongest current-mode family core)
- trigger layer: `ad` (strongest nearby companion)
- HTF filter: daily 20-period trend confirmation (AWF-309 promoted branch)
- regime: `trend_any` / `any` (broadest regime coverage)

This is not a random discovery — it is a narrow, evidence-directed repair.

### 5. The repair row does not yet match the frozen baseline volume

The frozen current-mode `drop SOL/BTC` reference has `3` gate-passed rows; this
repair pilot has `1`. The hierarchical mode is not yet as dense as the single-layer
mode, but it now has its first concrete positive evidence.

## Decision

Classification: `bounded pass`

Decision:
- close `AWF-311` as a successful repair pilot
- promote `state=obv_roc+keltner_pos / trigger=ad / htf_trend:1d:20` as the first
  validated hierarchical gate-passed configuration
- keep the frozen current-mode `drop SOL/BTC` branch as the stronger reference until
  the hierarchical mode accumulates more gate-passed density
- keep Phase 60 open as a now-validated research track with concrete positive evidence

## Consequences For Phase 60

The hierarchical state-trigger mode now has a gate-passed result for the first time.

Next natural steps (not yet committed):
- expand the trigger candidate set beyond `ad` to see if other triggers also pass
  with `htf_trend:1d:20` overlay
- test whether the 3-indicator state variant (`obv_roc + keltner_pos + ad`) also
  benefits from the HTF repair
- evaluate temporal robustness of the repaired row on the older-anchor window
  (AWF-310 style replay)
