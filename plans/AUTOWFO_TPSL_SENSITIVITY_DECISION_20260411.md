# AUTOWFO TP/SL Sensitivity Decision 2026-04-11

## Scope
- Cohort: full 10-symbol BTC-cross majors
- Indicator neighborhood: `obv_roc`, `keltner_pos`, `ad`, `cmf`, `dpo`, `chop`
- Combo sizes: `2..3`
- Window: anchored `2h / 180d`, `end=2026-04-09T14:00:00Z`
- WFO pair: main `45/30/30`, sensitivity `60/30/30`
- Exit grid: TP `[1.0, 1.5, 2.0]` × SL `[0.75, 1.0, 1.25]`

## Gate Variation
| TP | SL | Compared | Stable Positive | Gate Passed | Canonical |
|---|---:|---:|---:|---:|---:|
| 1.00 | 0.75 | 105 | 15 | 0 | 0 |
| 1.00 | 1.00 | 105 | 16 | 0 | 0 |
| 1.00 | 1.25 | 105 | 19 | 0 | 0 |
| 1.50 | 0.75 | 105 | 18 | 1 | 1 |
| 1.50 | 1.00 | 105 | 21 | 1 | 1 |
| 1.50 | 1.25 | 105 | 21 | 1 | 1 |
| 2.00 | 0.75 | 105 | 21 | 0 | 0 |
| 2.00 | 1.00 | 105 | 21 | 0 | 0 |
| 2.00 | 1.25 | 105 | 23 | 0 | 0 |

## Worst-Symbol Heatmap
| Symbol | tp1/sl0-75 | tp1/sl1 | tp1/sl1-25 | tp1-5/sl0-75 | tp1-5/sl1 | tp1-5/sl1-25 | tp2/sl0-75 | tp2/sl1 | tp2/sl1-25 |
|---|---|---|---|---|---|---|---|---|---|
| LTC/BTC | 4 | 5 | 5 | 2 | 4 | 3 | 3 | 4 | 5 |
| LINK/BTC | 0 | 0 | 2 | 1 | 1 | 3 | 1 | 1 | 5 |
| SOL/BTC | 4 | 4 | 7 | 4 | 4 | 6 | 4 | 4 | 7 |
| AVAX/BTC | 0 | 2 | 0 | 0 | 2 | 0 | 1 | 2 | 0 |
| ETH/BTC | 1 | 1 | 1 | 3 | 4 | 2 | 4 | 4 | 2 |
| BNB/BTC | 9 | 8 | 6 | 10 | 11 | 9 | 12 | 11 | 9 |
| XRP/BTC | 0 | 0 | 2 | 2 | 2 | 3 | 2 | 2 | 3 |
| ADA/BTC | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| DOGE/BTC | 0 | 0 | 1 | 0 | 0 | 1 | 0 | 0 | 1 |
| DOT/BTC | 0 | 0 | 0 | 0 | 0 | 1 | 1 | 0 | 0 |

## Cross-Grid Judgement
- `BNB/BTC`: strongest and clearest dragger. Worst-presence `9/9`, total worst-count `85`, and negative average return across the whole grid (`-0.1246%`). This result is stable enough to treat as symbol-intrinsic rather than fixed-exit noise.
- `SOL/BTC`: secondary recurring blocker. Worst-presence `9/9`, total worst-count `44`, with average return just below flat (`-0.0098%`). This still looks dragger-like, but materially weaker than `BNB/BTC`.
- `LTC/BTC`: recurring pressure point, not a primary dragger. Worst-presence `9/9`, total worst-count `35`, average return near flat (`-0.0095%`). Keep it in the “watch closely” tier rather than promote it to the same class as `BNB/BTC`.
- `ETH/BTC`, `LINK/BTC`, `XRP/BTC`: mixed contributors. They do appear as the worst symbol in multiple cells, but their cross-grid average returns remain positive, so the evidence does not support excluding them as intrinsic draggers.
- `AVAX/BTC`: boundary-sensitive / neutral. Worst-presence `4/9`, total worst-count `7`, average return `0.2098%`.
- `ADA/BTC`, `DOGE/BTC`, `DOT/BTC`: lowest dragger pressure and strongest supporter profile in this grid. Their worst-presence stays at `0/9`, `3/9`, and `2/9`, with clearly positive cross-grid average returns.

## Impact On State-Trigger Entry
- Carry the strongest current-mode boundary conclusion forward: `BNB/BTC` remains the only fully unambiguous symbol-intrinsic dragger under the bounded exit grid.
- Keep `SOL/BTC` as the main secondary blocker and `LTC/BTC` as a weaker recurring pressure point; both should stay observable in the first state-trigger experiments instead of being hard-excluded by default.
- Treat `ADA/BTC`, `DOGE/BTC`, and `DOT/BTC` as the lowest-pressure supporter set when constructing early state-trigger comparison cohorts.
- `AVAX/BTC`, `ETH/BTC`, `LINK/BTC`, and `XRP/BTC` remain cohort-membership variables rather than fixed “drop” or “keep” decisions.

## Files
- Summary JSON: `artifacts/reports/pilot_grid_awf305_tpsl_sensitivity_summary.json`
- `pilot_analysis_awf305_tpsl_tp1_sl0-75.json`: stable `15`, gate `0`
- `pilot_analysis_awf305_tpsl_tp1_sl1.json`: stable `16`, gate `0`
- `pilot_analysis_awf305_tpsl_tp1_sl1-25.json`: stable `19`, gate `0`
- `pilot_analysis_awf305_tpsl_tp1-5_sl0-75.json`: stable `18`, gate `1`
- `pilot_analysis_awf305_tpsl_tp1-5_sl1.json`: stable `21`, gate `1`
- `pilot_analysis_awf305_tpsl_tp1-5_sl1-25.json`: stable `21`, gate `1`
- `pilot_analysis_awf305_tpsl_tp2_sl0-75.json`: stable `21`, gate `0`
- `pilot_analysis_awf305_tpsl_tp2_sl1.json`: stable `21`, gate `0`
- `pilot_analysis_awf305_tpsl_tp2_sl1-25.json`: stable `23`, gate `0`
