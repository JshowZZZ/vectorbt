# AUTOWFO TP/SL Exit-Parameter Sensitivity Protocol

## Objective
Determine whether the Phase 54 symbol boundary conclusions (BNB/BTC dragger,
DOGE/BTC supporter, SOL/BTC secondary blocker) are symbol-intrinsic or
exit-parameter-specific.

The entire Phase 52–58 evidence chain used a single fixed exit overlay:
`tp_atr_multipliers=[1.5]`, `sl_atr_multipliers=[1.0]`. This test opens a
bounded TP/SL grid on the same indicator family and cohort to see whether
each symbol's role changes under different exit settings.

## Motivation
AWF-253/AWF-254 showed a broad TP/SL plateau (TP 1.0–2.25, SL 0.5–1.5), but
that was on the 4-symbol exact lane with a different indicator family
(`mfi + obv_roc + atr_ratio`). The 10-symbol breadth cohort
(`obv_roc + keltner_pos + ad`) has never been tested with varying TP/SL.

If BNB/BTC's dragger role is exit-parameter-specific rather than intrinsic,
the cohort boundary conclusions cannot be carried into the state/trigger mode
without re-evaluation.

## Fixed Conditions (do not change)
- timeframe: `2h`
- anchored window:
  - `days = 180`
  - `end = 2026-04-09T14:00:00Z`
- paired WFO:
  - main: `45/30/30`
  - sensitivity: `60/30/30`
- `risk_mode = atr_multiple`
- `max_holds = [4]`
- indicator neighborhood:
  - `obv_roc`
  - `keltner_pos`
  - `ad`
  - `cmf`
  - `dpo`
  - `chop`
- combo sizes: `2`, `3`
- `pilot_fixed_indicator_params = true`
- `pilot_single_trend_mom = true`
- symbols (full 10 BTC-cross majors):
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

## Variable Dimension (only free axis)
- `tp_atr_multipliers`: `[1.0, 1.5, 2.0]`
- `sl_atr_multipliers`: `[0.75, 1.0, 1.25]`

Total: 9 TP/SL combinations.

## Execution

### Step 1: Run 9 TP/SL pairs × paired WFO = 18 runs

For each (tp, sl) combination, run one main + sensitivity pair on the full
10-symbol cohort.

Run ID naming convention:
- `20260411_tpsl_tp{tp}_sl{sl}_main`
- `20260411_tpsl_tp{tp}_sl{sl}_sens`

(Use dash in place of decimal point, e.g. `tp1-5_sl1-0`)

### Step 2: pilot-analyze each pair

```bash
python -m autowfo pilot-analyze \
  --main-run <main_run_id> \
  --sensitivity-run <sens_run_id> \
  --out-json artifacts/reports/pilot_analysis_awf305_tpsl_tp{tp}_sl{sl}.json \
  --min-combo-trades 0.5 \
  --cwd .
```

### Step 3: Extract per-symbol worst-return data

The pilot-analyze JSON output's `symbol_support_main` / `symbol_support_sens`
contain only aggregated stats (min, mean, count), not per-symbol identity.

To get per-symbol detail, read each run's raw CSV directly:
`artifacts/runs/<run_id>/results/param_sweep_symbol_oos_summary.csv`

This CSV has columns including `symbol` and `oos_avg_total_return_pct` per
combo identity row. See `autowfo/engine_helpers.py` L253–L326 for the full
`oos_symbol_result_fields` schema.

For each TP/SL pair (both main and sensitivity run):
1. Read `param_sweep_symbol_oos_summary.csv`
2. For each stable-positive combo identity, extract every symbol's
   `oos_avg_total_return_pct`
3. Identify the worst symbol (min return) and record its value
4. Count how many times each symbol is worst across all stable-positive rows

### Step 4: Build summary JSON

Output: `artifacts/reports/pilot_grid_awf305_tpsl_sensitivity_summary.json`

Structure:
```json
{
  "schema": "awf305_tpsl_sensitivity_v1",
  "grid": [
    {
      "tp": 1.0,
      "sl": 0.75,
      "report": "pilot_analysis_awf305_tpsl_tp1-0_sl0-75.json",
      "compared_rows": 105,
      "stable_positive_rows": N,
      "gate_passed_rows": N,
      "worst_symbol_main_frequency": {
        "BNB/BTC": 15, "SOL/BTC": 8, "...": "..."
      },
      "worst_symbol_sens_frequency": {
        "BNB/BTC": 12, "...": "..."
      },
      "per_symbol_avg_return_main": {
        "BNB/BTC": 0.12, "SOL/BTC": 0.45, "...": "..."
      },
      "per_symbol_avg_return_sens": {
        "BNB/BTC": 0.08, "...": "..."
      }
    }
  ],
  "cross_grid_symbol_dragger_rank": {
    "BNB/BTC": { "worst_count_total": N, "avg_return_across_grid": X },
    "SOL/BTC": { "worst_count_total": N, "avg_return_across_grid": X },
    "...": "..."
  }
}
```

### Step 5: Write decision memo

Output: `plans/AUTOWFO_TPSL_SENSITIVITY_DECISION_<date>.md`

Required content:

1. **Per-symbol heatmap table**: 10 symbols × 9 TP/SL, each cell = count of
   times that symbol is worst among stable-positive rows

2. **Gate-passed variation table**: 9 TP/SL rows showing gate_passed and
   stable_positive counts

3. **Judgement** (apply these criteria):
   - Symbol is worst in ≥7/9 TP/SL combos → symbol-intrinsic dragger
   - Symbol is worst in ≤3/9 TP/SL combos → exit-parameter-specific, not
     intrinsic dragger
   - If supporter/dragger roles flip across TP/SL → record the flip boundary

4. **Impact on state/trigger mode entry**:
   - If dragger roles are stable → cohort boundary conclusions carry forward
   - If dragger roles are unstable → state/trigger mode must re-evaluate
     cohort boundary with the full 10-symbol set

## Validation Checks
- All 9 TP/SL reports should have the same `compared_combo_rows` (same
  indicator family and combo sizes)
- The tp=1.5 / sl=1.0 report should be comparable to Phase 53
  neighborhood baseline only on shared cohort/indicator protocol; combo-size
  coverage differs from Phase 53 because this TP/SL matrix is intentionally
  frozen to size `2..3`
- Summary JSON must be valid and parseable

## Non-Goals
- Do not change indicator combinations
- Do not do per-symbol individual TP/SL tuning (this is probing, not fitting)
- Do not open state/trigger mode
- Do not change combo sizes or WFO settings
