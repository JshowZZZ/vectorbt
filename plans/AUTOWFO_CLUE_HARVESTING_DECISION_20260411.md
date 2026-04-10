# AUTOWFO Baseline Clue-Harvesting Decision

Date: `2026-04-11`

## Scope
Close Phase 52 by judging whether the anchored breadth-first campaign produced enough
evidence to:
- keep refining the current single-layer combo-entry mode, or
- open the deferred hierarchical state/trigger mode.

## Fixed Protocol
- timeframe: `2h`
- anchored window: `180d`
- fixed end: `2026-04-09T14:00:00Z`
- paired WFO:
  - main: `45/30/30`
  - sensitivity: `60/30/30`
- symbols:
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
- execution overlay:
  - `risk_mode = atr_multiple`
  - `tp_atr_multipliers = [1.5]`
  - `sl_atr_multipliers = [1.0]`
  - `max_holds = [4]`
- indicator params frozen:
  - `pilot_fixed_indicator_params = true`
  - `pilot_single_trend_mom = true`

## Stage 1: Singles + Pairs
- Runs:
  - `20260411_clue_pairs_main`
  - `20260411_clue_pairs_sens`
- Reports:
  - `artifacts/reports/pilot_analysis_awf278_clue_pairs.json`
  - `artifacts/reports/indicator_clue_map_awf278_pairs.json`

### Result
- `975` compared rows
- `11` stable-positive rows
- `0` gate-passed rows

### Stage 1 clue interpretation
- Stable-positive rows are concentrated around `obv_roc`.
- Supporting family members appear in a narrow set:
  - `cmf`
  - `keltner_pos`
  - `dpo`
  - `ultosc`
  - `roc`
  - `rsi`
  - `ad`
  - `chop`
  - `mfi`
- Regime concentration already favors:
  - `trend_high / high`
  - then `trend_any / any`
- Failure mode is dominated by symbol support, not by trade-only failure:
  - all `11` stable rows still failed the overall gate through worst-symbol breakdown
  - only `3` also failed the paired trade floor

### Top-10 promotion
The Stage 2 promotion pool was selected from the Stage 1 clue map, with stable-positive
counts dominating the clue score and support/trade terms normalized to ratios so the
selection is not swamped by matrix-frequency constants.

Promoted indicators:
- `obv_roc`
- `cmf`
- `keltner_pos`
- `dpo`
- `ultosc`
- `chop`
- `roc`
- `rsi`
- `ad`
- `mfi`

## Stage 2: Evidence-Selected Triples
- Runs:
  - `20260411_clue_triples_main`
  - `20260411_clue_triples_sens`
- Report:
  - `artifacts/reports/pilot_analysis_awf278_clue_triples.json`

### Result
- `360` compared rows
- `44` stable-positive rows
- `1` gate-passed row

### Gate-passed family
- `indicator_list = obv_roc,keltner_pos,ad`
- `regime_name = trend_any`
- `vol_mode = any`
- `min_return = 0.6485%`
- `min_trades = 2.325`

This is the first breadth-first full-window family in the current mode that passes the
strict paired gate across the fixed 10-symbol BTC-cross cohort.

### Symbol-level support for the gate-passed row
The gate-passed row is not a one-symbol artifact.

Main run minimum symbol return:
- `BNB/BTC = +0.1174%`

Sensitivity run minimum symbol return:
- `BNB/BTC = +0.0019%`

Both runs remain:
- `10/10` non-negative
- `10/10` positive

### Dominant stable family clues
Full stable-positive frequency across the `44` triples:
- `obv_roc`: `31`
- `dpo`: `18`
- `keltner_pos`: `14`
- `cmf`: `13`
- `ultosc`: `12`
- `chop`: `10`
- `roc`: `10`
- `ad`: `9`
- `rsi`: `8`
- `mfi`: `7`

Stable rows are concentrated in:
- `trend_high / high`: `27`
- `trend_any / any`: `14`
- `trend_low / low`: `3`

### Dominant failure mode
Among the full `44` stable-positive rows:
- `43` fail symbol support
- `24` fail the paired trade gate
- `24` fail both
- `19` fail only symbol support
- `0` fail only trade density

Interpretation:
- the primary blocker is still worst-symbol support
- trade density is a secondary pressure, not the main failure mode

## Decision
Phase 52 closes with a `current-mode continue` verdict.

### What is supported
- The current single-layer combo-entry mode still contains real breadth-first signal
  structure under the anchored full-window protocol.
- `obv_roc` is the clearest center of gravity.
- A bounded local family exists around:
  - `obv_roc`
  - `keltner_pos`
  - `ad`
  - `cmf`
  - `dpo`
  - `chop` / `roc`

### What is not yet justified
- The deferred hierarchical state/trigger mode is still interesting, but it is not the
  next justified implementation branch.
- The breadth campaign produced enough signal in the current mode that abandoning it now
  would be premature.

## Next Branch
Open a bounded current-mode family-refinement phase under the same anchored protocol:
- fixed 10-symbol BTC-cross cohort
- fixed ATR exit
- same paired WFO
- narrow indicator neighborhood around the gate-passed family
- combo sizes `3..4`

The next phase should answer:
1. Is `obv_roc + keltner_pos + ad` an isolated winner, or part of a local family?
2. Which nearby indicator additions preserve all-symbol support?
3. Can the local family stay in the current mode, or does evidence flatten fast enough
   to justify opening the deferred state/trigger mode after all?
