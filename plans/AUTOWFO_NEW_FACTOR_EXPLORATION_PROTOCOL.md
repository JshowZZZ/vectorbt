# AUTOWFO New Factor Exploration Protocol

Date: `2026-04-11`

## Motivation

After completing the full Phase 52–59 current-mode evidence chain, three persistent
observations remain unexplained by the existing 25-indicator library:

1. `BNB/BTC` is the sole symbol-intrinsic dragger across every TP/SL cell
   (9/9 worst-presence, cross-grid avg = `-0.1246%`) despite the same `OBV_ROC +
   Keltner_Pos + AD` family being profitable for all other symbols.

2. The existing indicator set is derived exclusively from price and on-chain volume.
   No factor captures perpetual-market-specific structure (funding, open interest).

3. The current evaluation is locked to a single timeframe level (`2h`). No
   cross-timeframe hierarchy has been tested.

These gaps motivate three bounded new-factor exploration tracks. Each is treated as a
standalone sidecar experiment so it does not displace the active Phase 60
hierarchical state-trigger work.

## Scope

This protocol covers three new factor tracks:

- **Track A**: Funding Rate as a signal indicator
- **Track B**: Open Interest as a signal indicator
- **Track C**: Cross-Timeframe (HTF) confirmation filter

Each track is executed independently. Results are recorded in the standard
pilot-analysis contract and archived to `artifacts/reports/`.

These tracks are explicitly **sidecar evidence**:
- they do not block `AWF-303` or `AWF-304`
- they do not reopen broad discovery
- they only affect the Phase 60 candidate pool if they produce evidence better than the
  frozen current-mode references

The motivation question for every track is the same:

> Does the new factor reduce BNB/BTC's dragger presence or improve overall
> gate-passed density without degrading the existing gate-passed rows?

## Fixed Shared Conditions

All three tracks share:

- timeframe: `2h` (native resolution; HTF filter for Track C is derived)
- anchored window:
  - `days = 180`
  - `end = 2026-04-09T14:00:00Z`
- paired WFO:
  - main: `45/30/30`
  - sensitivity: `60/30/30`
- `risk_mode = atr_multiple`
- `tp_stop = 1.5`, `sl_stop = 1.0`, `max_hold = 4`
- base indicator neighborhood:
  - `obv_roc`
  - `keltner_pos`
  - `ad`
  - `cmf`
  - `chop`
- symbols: full 10-symbol BTC-cross majors (including `BNB/BTC` and `SOL/BTC`)
- combo sizes: `2`, `3`
- `pilot_fixed_indicator_params = true`
- `pilot_single_trend_mom = true`
- structural baseline:
  - `artifacts/reports/pilot_analysis_awf291_baseline10_refine.json`
  - `compared = 168`, `stable = 45`, `gate = 2`
- exit-robustness sidecar reference:
  - `plans/AUTOWFO_TPSL_SENSITIVITY_DECISION_20260411.md`
  - `BNB/BTC` cross-grid avg = `-0.1246%`
  - `BNB/BTC` worst-presence = `9/9`

---

## Track A: Funding Rate as Signal Indicator

### Background

`funding_rate_daily` is currently used only as a friction cost parameter (fixed at
`0.0003` / day). It has never been tested as a trading signal.

Perpetual funding rates carry information that price/volume candles do not:
- Positive and rising rate → long-side crowding → elevated reversal risk
- Extreme positive rate → Launchpool / event-driven positioning in `BNB` → historically
  coincides with BNB's worst entry quality in the current system

### Hypothesis

Adding a funding-rate gate as an entry condition should:
- block entries during crowded-long periods (high positive rate)
- preserve entries during neutral-rate periods where OBV + Keltner signals are reliable
- reduce `BNB/BTC`'s dragger frequency without requiring hard asset exclusion

### Data Requirements

This track must not start until a separate data-availability note confirms:
- which of the 10 BTC-cross symbols have a matching Binance perpetual instrument
- whether the signal uses same-instrument history or an asset-level perpetual proxy
- how missing instruments are handled (`drop symbol` vs `proxy mapping`)

- Binance perpetual funding-rate history (8-hour settlement intervals)
- Symbols: same 10 BTC-cross majors
- Window: same 180-day lookback
- Resampling: forward-fill 8h rate onto 2h bars (4 bars per funding period)

**Look-ahead risk**: funding rate is only known at the settlement tick.
The forward-fill must use the rate from the **previous** settlement, not the current one.
This must be validated in the data pipeline before any run.

### Indicator Definition

```
funding_rate_gate:
  long_allowed = (funding_rate_8h <= threshold_long)
  short_allowed = (funding_rate_8h >= threshold_short)
```

Proposed parameter variants:
- `threshold_long`: `[0.01%, 0.02%]`  (block entries when rate exceeds this per 8h)
- `threshold_short`: `[-0.01%, -0.02%]`  (block short entries when rate too negative)

### Indicator Key

`funding_gate` (proposed new key in `strategy.py`)

### Search Shape

Add `funding_gate` as an optional additional filter slotted into the existing combo
search. It is not a standalone combo member — it is tested as an **overlay gate** that
can be active or inactive.

Two branches per regime:
- without `funding_gate` (existing baseline behavior)
- with `funding_gate` (new overlay)

Expect approximately `2x` run volume vs the baseline.

### Success Criteria

- at least one new gate-passed row is unlocked in the full 10-symbol cohort, OR
- `funding_gate` appears as a stable co-member in `≥ 3` stable-positive rows, OR
- the best `funding_gate` row improves `BNB/BTC`'s min-symbol return versus the
  structural baseline without degrading the lowest-pressure supporters
  (`ADA/BTC`, `DOGE/BTC`, `DOT/BTC`)

If none of the above, reject `funding_gate` as a current-mode indicator.

### Expected Artifacts

Run IDs:
- `20260411_newf_funding_main`
- `20260411_newf_funding_sens`

Report:
- `artifacts/reports/pilot_analysis_awf307_funding_gate.json`

---

## Track B: Open Interest as Signal Indicator

### Background

Open Interest (OI) measures the total number of outstanding perpetual contracts.
A rapid OI increase with rising price confirms trend conviction (new money entering).
A rapid OI decrease (de-leveraging) often precedes volatility spikes or reversals.

This is structurally similar to `OBV` (volume accumulation confirms direction) but
targets the derivatives market rather than the spot market.

### Hypothesis

An OI-rate-of-change indicator (`oi_roc`) should:
- serve as a complementary trend-confirmation layer alongside `OBV_ROC`
- identify periods when BNB's price move is driven by real accumulation vs.
  leverage flushing (where OBV and OI diverge, the signal is unreliable)

### Data Requirements

This track must not start until the same perpetual-instrument mapping note required by
Track A is frozen. If BTC-quote perpetual instruments do not exist for part of the
cohort, the protocol must explicitly state whether OI is read from an asset-level proxy.

- Binance open interest history (available at 5-minute granularity, resample to 2h)
- Symbols: same 10 BTC-cross majors
- Window: same 180-day lookback

### Indicator Definition

```
oi_roc:
  oi_roc_value = (OI_current - OI_N_bars_ago) / OI_N_bars_ago
  long_signal = (oi_roc_value > 0)
  short_signal = (oi_roc_value < 0)
```

Proposed parameter variants:
- `oi_roc_lookback`: `[12, 24]`  (lookback in 2h bars = 24h or 48h)

### Indicator Key

`oi_roc` (proposed new key in `strategy.py`)

### Search Shape

Add `oi_roc` as a standard combo member alongside the existing 25 indicators.
Test in the bounded family neighborhood:
- pairs: `oi_roc` + each existing member
- triples: `oi_roc` + two existing members

Expected row count must be recomputed from the frozen bounded neighborhood before
execution. Do not rely on rough `~324` row estimates when scheduling the batch.

Limit to the bounded neighborhood (`obv_roc`, `keltner_pos`, `ad`, `cmf`, `chop`)
plus `oi_roc` itself for the first test. Do not open the full 25-indicator space.

### Success Criteria

- `oi_roc` appears as a stable co-member in `≥ 3` stable-positive rows, OR
- at least one `oi_roc`-containing row is gate-passed, OR
- replacing `obv_roc` with `oi_roc` in the canonical family yields a comparable
  stable-positive count with better `BNB/BTC` minimum symbol return

If none met, treat `oi_roc` as a non-contributor in the current mode.

### Expected Artifacts

Run IDs:
- `20260411_newf_oi_main`
- `20260411_newf_oi_sens`

Report:
- `artifacts/reports/pilot_analysis_awf308_oi_roc.json`

---

## Track C: Cross-Timeframe (HTF) Confirmation Filter

### Background

The entire evidence chain uses a single evaluation level (`2h`). A higher-timeframe
(HTF) trend filter imposes a directional prior before the 2h signal is allowed to fire.

This is zero additional data cost: the 2h OHLCV data already contains the information
needed to construct `8h` or `daily` candles by resampling.

### Hypothesis

A daily-trend gate (e.g., `close > EMA_20_daily`) should:
- block long entries on 2h when the daily trend is already in distribution
- preserve entries where multi-timeframe alignment is present
- reduce `BNB/BTC` false entries driven by intra-day momentum without daily backing

### Indicator Definition

```
htf_trend_gate:
  daily_close = resample(2h OHLCV → daily)
  daily_ema_20 = EMA(daily_close, 20)
  long_allowed = (daily_close[-1] > daily_ema_20[-1])
  short_allowed = (daily_close[-1] < daily_ema_20[-1])
```

Proposed parameter variants:
- `htf_window`: `[10, 20]`  (daily EMA period)
- `htf_timeframe`: `[8h, daily]`  (resample level)

**Look-ahead risk**: the daily bar must be computed using bars up to and including
the current 2h bar's parent daily bar — but only the portion of the daily bar that
has already closed. This means using the **previous** completed daily bar's close.

### Indicator Key

`htf_trend` (proposed new key in `strategy.py`)

### Search Shape

Add `htf_trend` as an overlay gate. Test in two branches
per regime:
- without `htf_trend`
- with `htf_trend`

This is a filter, not a standalone combo member, analogous to the existing
`trend_any / trend_high / trend_low` regime preset.

### Implementation Note

This can be prototyped without modifying `strategy.py` by treating the daily EMA
crossover condition as an additional column in the preprocessed bar context.
The first prototype should compute the resampled series in `data.py` or
`engine_runtime.py` before being wired into `strategy.py` properly.

### Success Criteria

- `htf_trend` filter increases stable-positive rows by `≥ 10%` vs the unfiltered
  baseline under the same indicator neighborhood, OR
- `BNB/BTC`'s minimum-symbol return improves from below `+0.05%` to above `+0.10%`
  for the best gate-passed combo, OR
- at least one new `trend_high` gate-passed row is unlocked that was previously
  blocked by `BNB/BTC` minimum-symbol failure

### Expected Artifacts

Run IDs:
- `20260411_newf_htf_main`
- `20260411_newf_htf_sens`

Report:
- `artifacts/reports/pilot_analysis_awf309_htf_trend.json`

---

## Execution Order

These tracks are sidecar experiments relative to Phase 60. They should not block
`AWF-303` (implementation) or `AWF-304` (first hierarchical pilot).

Suggested order based on implementation cost:

| Priority | Track | Reason |
|---|---|---|
| 1st | Track C (HTF) | Zero new data; resampling only; lowest implementation risk |
| 2nd | Track A (Funding Rate) | Only after perpetual-instrument mapping is frozen |
| 3rd | Track B (Open Interest) | Same mapping dependency as Track A, plus heavier data path |

All three can be run in parallel once data pipelines are ready.

## Interpretation Guide

For each track, after the paired pilot-analysis is complete:

1. Check whether the best row improves `BNB/BTC`'s min-symbol return or removes
   `BNB/BTC` from the practical blocker role under the same fixed exit cell.

2. Check if any new gate-passed row appears that was not in the Phase 53–59 baseline.

3. If a new factor helps `BNB/BTC` but degrades `ADA/BTC` / `DOGE/BTC` / `DOT/BTC`,
   it is too aggressive a filter — do not promote.

4. Carry only confirmed stable contributors into the Phase 60 state-trigger mode.
   If none pass the success criteria, proceed to Phase 60 with the existing
   six-indicator family only.

## Relation to Phase 60

If any new factor passes its success criteria, it becomes a candidate for the
state or trigger layer of the Phase 60 hierarchical mode:

- `funding_gate` → natural State candidate (long-horizon market regime)
- `oi_roc` → natural Trigger candidate (short-horizon entry confirmation)
- `htf_trend` → natural State candidate (structural trend alignment)

If none pass, Phase 60 proceeds with the frozen seed candidates as-is.
