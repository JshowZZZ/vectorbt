# AUTOWFO Search V2 Pilot Decision Memo

Date: 2026-04-08

## Scope

This memo records the execution result of the revised cross-symbol pilot described in
`plans/AUTOWFO_SEARCH_V2_PROPOSAL.md`.

Analyzed runs:

- `20260408_144415`: main pilot, requested `180d`, `2h`, `wf_train_days=45`, `wf_test_days=30`, `wf_step_days=30`, `wf_valid_days=0`
- `20260408_151900`: sensitivity pilot, same protocol except `wf_train_days=60`

Common pilot settings:

- 7-indicator shortlist: `mfi`, `cmf`, `obv_roc`, `macd_hist`, `trix`, `donchian_pos`, `atr_ratio`
- combo size `1..3`
- `pilot_trend_3` regime preset
- fixed default indicator params
- single trend-momentum setting
- `risk_mode=atr_multiple`
- `tp_atr_multipliers=[1.5]`
- `sl_atr_multipliers=[1.0]`
- `max_holds=[2,4]`
- 10 trade symbols: `ETH/BTC`, `BNB/BTC`, `ADA/BTC`, `XRP/BTC`, `SOL/BTC`, `DOGE/BTC`, `DOT/BTC`, `LINK/BTC`, `LTC/BTC`, `AVAX/BTC`

Each run evaluated `378` configurations.

## Realized Protocol

The requested pilot target was "180d, cleaner protocol, more statistical meaning".

What actually executed was narrower:

- effective shared data window in both runs was `2025-12-05 10:00:00` to `2026-04-08 14:00:00`
- realized overlap window was about `124` days, not the requested `180` days
- both runs produced only `2` OOS segments

This matters for interpretation:

- the pilot still gives useful evidence for a project decision
- the evidence is weaker than a true 180-day, multi-segment pilot would have been

There is also one important output limitation in the current legacy pilot path:

- `param_sweep_symbol_summary.csv` reports full-period per-symbol results
- it does not currently emit symbol-level OOS results

So the decision gate below uses:

- combo-level OOS metrics from `param_sweep_combo_summary.csv`
- symbol-level coverage and return shape from the full-period `param_sweep_symbol_summary.csv`

That is acceptable for a fast gate, but it is not the final form of the cohort evidence model.

## Main Pilot Findings

### Run `20260408_144415` (`45/30/30`)

High-level counts:

- `25 / 378` combos had `oos_avg_total_return_pct > 0`
- `4 / 378` combos had both `oos_avg_total_return_pct > 0` and positive mean full-period symbol return
- `1 / 378` combo had both `oos_avg_total_return_pct > 0` and positive median full-period symbol return
- `1 / 378` combo reached `positive_symbols >= 6` and `valid_symbols >= 6` under a loose trade floor of `>= 3`
- `0 / 378` combos reached that gate under a stricter trade floor of `>= 5`

Best boundary candidate:

- `indicator_list = mfi,cmf,obv_roc`
- `regime_name = trend_any`
- `max_hold = 4`
- `risk_mode = atr_multiple`
- `tp/sl = 1.5 / 1.0`

Observed metrics:

- `positive_symbols_3 = 6 / 10`
- `valid_symbols_3 = 9 / 10`
- `mean_symbol_return = +0.2008%`
- `median_symbol_return = +0.2755%`
- `worst_symbol_return = -0.6986%`
- `oos_avg_total_return_pct = +0.0848%`
- `oos_sharpe_like = +0.4844`

Positive symbols for this candidate were concentrated in:

- `LTC/BTC`, `XRP/BTC`, `DOT/BTC`, `ADA/BTC`, `DOGE/BTC`, `ETH/BTC`

Negative symbols were:

- `LINK/BTC`, `SOL/BTC`, `BNB/BTC`

Important weakness:

- this candidate did **not** survive a `>= 5` trades-per-symbol floor
- the OOS evidence came from only `2` segments

So this was not a clean "go" signal. It was a boundary candidate only.

## Sensitivity Findings

### Run `20260408_151900` (`60/30/30`)

High-level counts:

- `10 / 378` combos had `oos_avg_total_return_pct > 0`
- `1 / 378` combo had both `oos_avg_total_return_pct > 0` and positive mean full-period symbol return
- `0 / 378` combos had positive median full-period symbol return together with positive OOS average
- `0 / 378` combos reached `positive_symbols >= 6` and `valid_symbols >= 6` even under the loose trade floor of `>= 3`
- `0 / 378` combos reached even the softer `positive_symbols >= 5` and `valid_symbols >= 6` gate under trade floor `>= 5`

The boundary candidate from the main run was **not** stable:

- same combo signature: `mfi,cmf,obv_roc + trend_any + max_hold 4`
- full-period symbol profile stayed the same
- but `oos_avg_total_return_pct` flipped from `+0.0848%` to `-0.0451%`
- `oos_sharpe_like` flipped from `+0.4844` to `-1.0000`

That means the strongest candidate in the main pilot was not robust to a small WFO change.

## Decision

## Outcome: `NARROW-GO`

Interpretation:

- there is weak, non-zero evidence that a few cross-symbol structures may exist
- there is **not** enough stable evidence to justify full universal Search V2 now

Project-level implication:

- `NO-GO` for full wide Search V2 investment at this stage
- `NARROW-GO` for a focused follow-up track only

Why this is not a full `GO`:

- no candidate was stable across both WFO settings
- no candidate survived a stricter per-symbol trade floor while also keeping the `6/10` cohort gate
- realized overlap window was only about `124` days
- both runs had only `2` OOS segments
- symbol-level OOS cohort output is still missing from the legacy pilot artifacts

Why this is not a hard `NO-GO`:

- one combo did show a plausible cross-symbol pattern in the main run
- that pattern was coherent enough to justify a very small follow-up, but not a full campaign engine buildout

## Recommended Next Steps

### Immediate

1. Do **not** start full Search V2 implementation or full 25-indicator port.
2. Keep the current proposal priority order: protocol quality first, architecture later.

### Focused Follow-Up

1. Add symbol-level OOS cohort output to the pilot result model.
   - The next gate should be based on symbol-level OOS return / OOS trade count, not full-period symbol return.
2. Audit why the requested `180d` pilot realized only about `124` days of shared overlap.
   - If the data horizon can be extended materially, rerun the pilot under the intended longer window.
3. If another cheap research pass is funded, keep it narrow:
   - first focus on the boundary candidate family around `mfi + cmf + obv_roc`
   - compare against symbol clustering / subgroup discovery instead of assuming a universal signal

### Current Recommendation to Reviewers

If another reviewer must choose one label now, the correct label is:

> `NARROW-GO` for focused discovery, `NO-GO` for full Search V2 funding.

## Evidence Files

Main run:

- `artifacts/runs/20260408_144415/results/param_sweep_combo_summary.csv`
- `artifacts/runs/20260408_144415/results/param_sweep_symbol_summary.csv`
- `artifacts/runs/20260408_144415/results/param_sweep_top10_20260408_144415.csv`

Sensitivity run:

- `artifacts/runs/20260408_151900/results/param_sweep_combo_summary.csv`
- `artifacts/runs/20260408_151900/results/param_sweep_symbol_summary.csv`
- `artifacts/runs/20260408_151900/results/param_sweep_top10_20260408_151900.csv`

## Post-Decision Hardening

On 2026-04-08, the pilot path was extended to emit:

- `param_sweep_symbol_oos_summary.csv`
- run metadata `timeframe_diagnostics`

Verification run:

- `20260408_163100`

What this hardening confirmed:

- symbol-level OOS cohort output now exists for all `3780` combo-symbol rows
- the overlap-window collapse is traceable in metadata rather than inferred indirectly

Observed reason for the realized overlap shrink:

- several BTC-cross trade symbols start materially later than the requested `180d` window
- the effective shared start was forced by the latest-start symbols, especially:
  - `ADA/BTC`
  - `DOGE/BTC`
  - `DOT/BTC`
  - `LINK/BTC`
  - `LTC/BTC`
  - `AVAX/BTC`

So the pilot did not fail because the requested window logic was ignored.
It failed because the shared cohort data availability was narrower than the requested horizon.

This does not change the project decision:

> `NARROW-GO` for focused follow-up, `NO-GO` for full Search V2 funding.
