# AUTOWFO Historical Anchored Replay Protocol

Date: `2026-04-11`

## Objective

Run one historical anchored replay on the frozen current-mode full 10-symbol baseline,
using the same `180d` window size but ending one year earlier than the current
full-window anchor.

This is a temporal sidecar evidence task. It exists to answer:

- does the bounded current-mode family still survive on a materially earlier market
  window?
- are the current blocker/supporter roles already visible one year earlier?
- does the current `2h / 180d` evidence look regime-specific, or does it replay on an
  earlier 180-day slice with the same protocol?

## Why This Comes Before New External Data Factors

This replay:
- uses the already-validated anchored-window contract
- uses existing OHLCV data infrastructure only
- requires no new Binance funding/OI pipeline
- gives immediate temporal robustness evidence for both current-mode and future
  state-trigger candidate selection

## Fixed Conditions

- timeframe: `2h`
- anchored window:
  - `days = 180`
  - `end = 2025-04-09T14:00:00Z`
- paired WFO:
  - main: `45/30/30`
  - sensitivity: `60/30/30`
- execution overlay:
  - `risk_mode = atr_multiple`
  - `tp_atr_multipliers = [1.5]`
  - `sl_atr_multipliers = [1.0]`
  - `max_holds = [4]`
- regime preset: `pilot_trend_3`
- indicator params:
  - `pilot_fixed_indicator_params = true`
  - `pilot_single_trend_mom = true`

## Symbol Cohort

Use the same full 10-symbol BTC-cross major cohort as the frozen full-window baseline:

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

Use the same bounded current-mode family neighborhood as the frozen full 10-symbol
baseline:

- `obv_roc`
- `keltner_pos`
- `ad`
- `cmf`
- `dpo`
- `chop`

Combo sizes:
- `3`
- `4`

## Comparison Baseline

Compare against the existing full-window anchored bounded-family baseline:

- `artifacts/reports/pilot_analysis_awf282_family_refine.json`

This gives a clean temporal comparison:
- same indicators
- same symbols
- same exit
- same WFO pair
- same bounded `3..4` family neighborhood
- different anchored time slice only

## Decision Questions

1. Does any gate-passed row survive on the historical 180-day slice?
2. Is `BNB/BTC` already the dominant dragger one year earlier?
3. Are the current supporter symbols (`ADA/BTC`, `DOGE/BTC`, `DOT/BTC`) already the
   lowest-pressure set on the older window?
4. Does the older slice reinforce the case for opening the hierarchical state-trigger
   mode, or does it suggest the current family is too time-local?

## Success / Interpretation

Interpret the replay in three tiers:

- `replay-confirmed`
  - at least one gate-passed row survives, and
  - blocker/supporter roles remain directionally similar

- `directional-only`
  - no gate-passed row survives, but stable-positive density remains meaningful or
    symbol-role ordering remains similar

- `time-local`
  - gate-passed rows disappear and symbol-role structure changes materially

This sidecar does not reopen current-mode narrowing by itself.
It only updates the temporal evidence base used by:
- `AWF-304` first hierarchical pilot comparison
- `AWF-307` to `AWF-309` sidecar interpretation

## Expected Artifacts

Run IDs:
- `20260411_awf310_hist180_main`
- `20260411_awf310_hist180_sens`

Reports:
- `artifacts/reports/pilot_analysis_awf310_hist180.json`
- `plans/AUTOWFO_HISTORICAL_ANCHORED_REPLAY_DECISION_20260411.md`
