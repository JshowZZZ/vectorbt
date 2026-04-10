# AUTOWFO Baseline Clue-Harvesting Protocol

## Objective
Run one breadth-first evidence campaign in the current single-layer combo-entry mode
before introducing a new strategy mode.

This campaign is not trying to promote a final strategy. Its purpose is to extract
three kinds of clues under a fixed, comparable protocol:
- indicator-family clues
- symbol-cluster clues
- trade-density failure-mode clues

## Fixed Research Conditions
- timeframe: `2h`
- anchored window:
  - `days = 180`
  - `end = 2026-04-09T14:00:00Z`
- paired WFO:
  - main: `45/30/30`
  - sensitivity: `60/30/30`
- regime preset: `pilot_trend_3`
- indicator params:
  - `pilot_fixed_indicator_params = true`
  - `pilot_single_trend_mom = true`
- execution overlay:
  - `risk_mode = atr_multiple`
  - `tp_atr_multipliers = [1.5]`
  - `sl_atr_multipliers = [1.0]`
  - `max_holds = [4]`

## Symbol Cohort
Fixed 10-symbol BTC-cross major cohort:
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

The cohort deliberately mixes:
- the currently supported 4-symbol exact lane core
- liquid BTC-cross majors outside that exact lane

This allows the same run to reveal both:
- local cluster support
- boundary failure modes

## Indicator Universe
All 25 currently supported indicators:
- `volume_z`
- `obv_roc`
- `cmf`
- `mfi`
- `vroc`
- `ad`
- `rsi`
- `roc`
- `macd_hist`
- `stoch`
- `bb_width`
- `atr_ratio`
- `ma_trend`
- `cci`
- `willr`
- `adx`
- `trix`
- `dpo`
- `efi`
- `vwma_trend`
- `ultosc`
- `keltner_pos`
- `donchian_pos`
- `ppo`
- `chop`

## Campaign Structure
### Stage 1: Singles + Pairs
- combo sizes: `1` and `2`
- purpose:
  - measure stand-alone signal viability
  - measure pair interaction viability
  - build the first indicator clue map

### Stage 2: Evidence-Selected Triples
- combo size: `3`
- indicator pool: top 10 informative indicators selected from Stage 1
- purpose:
  - determine whether the most informative indicators combine into stronger families
  - avoid exploding the full `C(25,3)` search space before Stage 1 evidence exists

## Top-10 Indicator Selection Rule
Stage 2 promotion is based on Stage 1 evidence, not intuition alone.

Each indicator receives a clue score from the paired Stage 1 analysis using rows that
contain that indicator:
- gate-passed row count
- stable-positive row count
- normalized symbol-support ratio
- normalized trade-support ratio
- single-indicator stable/gate bonuses

The exact weighting may be adjusted slightly when Stage 1 data is in hand, but the intent is fixed.
In particular, if the breadth matrix makes raw support counts nearly constant across all
indicators, support/trade terms should be normalized so the selection remains clue-driven
rather than frequency-driven:
- prefer indicators that survive in both singles and pairs
- prefer indicators that preserve symbol support
- avoid promoting indicators that look strong only by average return while repeatedly breaking worst-symbol support

## Decision Questions This Campaign Must Answer
1. Which indicators have stand-alone signal value under the fixed full-window protocol?
2. Which pairs form repeatable local families?
3. Which symbols behave as cluster supporters versus draggers?
4. Are the dominant failures caused more by:
   - low trade density
   - worst-symbol breakdown
   - regime inconsistency
5. Does the current single-layer mode still deserve refinement, or is a new mode the next justified branch?

## Output Expectations
Stage 1 should produce:
- paired run artifacts
- pilot-analysis report
- indicator clue map / ranking for top-10 promotion

Stage 2 should produce:
- paired triples artifacts
- pilot-analysis report
- final clue-harvesting decision memo

## Explicit Non-Goals
This campaign does **not** try to:
- tune indicator parameters broadly
- expand exit logic beyond the fixed ATR baseline
- introduce staged take profit
- introduce pyramiding/add-on logic
- implement the future hierarchical state/trigger mode

Those questions are intentionally deferred until this baseline clue map is complete.
