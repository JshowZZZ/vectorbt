# AUTOWFO Exact-Lane Range Decision 2026-04-10

## Purpose

Document the first post-promotion scope/range-testing results for the frozen exact lane:

- symbols: `LTC/BTC`, `LINK/BTC`, `SOL/BTC`, `AVAX/BTC`
- timeframe baseline: `2h`
- family: `mfi + obv_roc + atr_ratio`
- regime: `trend_high`
- risk mode: `ATR multiple`
- plateau under test:
  - `tp_stop in [1.0, 2.25]`
  - `sl_stop in [0.5, 1.5]`
  - `max_hold = 4`

## Runs

### AWF-261: Operator-generated exact-lane scope test

- Main: `20260410_100403`
- Sensitivity: `20260410_100537`
- Analysis: `artifacts/reports/pilot_analysis_awf261_exact_lane_scope_test.json`

Outcome:

- `compared_combo_rows = 30`
- `stable_positive_rows = 30`
- `gate_passed_rows = 30`
- realized shared overlap: `127d`

Interpretation:

- The new operator workflow reproduces the frozen exact lane cleanly.
- Under the canonical `45/30/30` vs `60/30/30` pair, every tested TP/SL point in the plateau passes the current gate.
- This closes the question of whether the exact lane only works in ad hoc replay scripts.

### AWF-262: `2h / 120d` temporal range test

- Main: `20260410_101315`
- Sensitivity: `20260410_101628`
- Strict analysis: `artifacts/reports/pilot_analysis_awf262_exact_lane_range120.json`
- Relaxed analysis: `artifacts/reports/pilot_analysis_awf262_exact_lane_range120_relaxed.json`

Strict outcome (`min_combo_trades = 0.5`):

- `compared_combo_rows = 30`
- `stable_positive_rows = 24`
- `gate_passed_rows = 0`
- realized shared overlap: `121d`

Relaxed outcome (`min_combo_trades = 0.375`):

- `gate_passed_rows = 24`

Interpretation:

- The lane does not collapse under a shorter shared window.
- The dominant failure mode is trade density, not return structure:
  - top stable rows remain symbol-supported
  - the paired trade floor fails on the sensitivity side
- Therefore `120d` should be read as "sample-limited but structurally alive", not as a protocol invalidation.

### AWF-263: `1h / 180d` density follow-up

- Main: `20260410_102301`
- Sensitivity: `20260410_102302`
- Analysis: `artifacts/reports/pilot_analysis_awf263_exact_lane_density_1h.json`

Outcome:

- `compared_combo_rows = 30`
- `stable_positive_rows = 0`
- `gate_passed_rows = 0`
- realized shared overlap: `181d`

Interpretation:

- Increasing bar density to `1h` does not rescue the lane.
- The failure is stronger than the `120d` case:
  - full overlap is available
  - trade density is higher
  - but no stable-positive rows survive the paired contract
- Current evidence still supports a `2h` lane-specific interpretation.

## Decision

### Conclusion

Current decision: `NARROW-GO` for continued `2h` exact-lane work, `NO-GO` for broad timeframe expansion.

### Why

1. The operator-generated `2h` scope test is fully reproducible and strong.
2. The first temporal range contraction (`120d`) weakens only because of trade-floor pressure, not because the symbol-supported edge disappears.
3. The first density expansion (`1h`) fails completely despite full overlap and more bars.

### Operational reading

The lane should currently be treated as:

- robust enough to keep as a frozen `2h` candidate
- not robust enough to justify wider timeframe expansion
- sensitive to sample sufficiency under shorter shared windows

## Recommended next step

1. Do not widen into generic multi-timeframe range campaigns.
2. Keep the lane fixed at `2h`.
3. Focus the next analysis on trade-floor policy and sample sufficiency:
   - whether the current `0.5` paired trade gate is too strict for short-window exact-lane validation
   - whether the lane should require a longer shared window before any broader promotion
4. If another expansion is attempted, it should stay inside the `2h` lane and target evidence policy, not raw bar density.
