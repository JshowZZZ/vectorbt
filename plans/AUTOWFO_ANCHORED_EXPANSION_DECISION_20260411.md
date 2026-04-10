# AUTOWFO Anchored Expansion Decision 2026-04-11

## Scope
- Objective: validate that anchored research windows plus historical backfill work on real `2h` BTC-cross data, then test whether broader indicator and symbol coverage survives once the study window is truly fixed.
- Fixed research end: `2026-04-09T14:00:00Z`
- Common protocol:
  - `2h`
  - `180d`
  - paired WFO: `45/30/30` main and `60/30/30` sensitivity
  - `risk_mode=atr_multiple`
  - `pilot_trend_3`

## Runs
- `AWF-274` exact lane anchored rerun
  - main: `20260411_anchored_exact_main`
  - sensitivity: `20260411_anchored_exact_sens`
- `AWF-275` anchored 5-indicator / 4-symbol widening
  - main: `20260411_anchored_4sym5ind_main`
  - sensitivity: `20260411_anchored_4sym5ind_sens`
- `AWF-275` anchored 5-indicator / 5-symbol widening
  - main: `20260411_anchored_5sym5ind_main`
  - sensitivity: `20260411_anchored_5sym5ind_sens`

## Key Evidence
### AWF-274: anchored exact lane
- Realized shared overlap increased from the previous `~127d` baseline to a full `181d`.
- `pilot_analysis_awf274_anchored_exact_lane.json`
  - `compared_combo_rows = 90`
  - `stable_positive_rows = 30`
  - `gate_passed_rows = 0`
- `pilot_verdict_awf274_anchored_exact_lane.json`
  - verdict: `hold`
  - reason: `full_window_gate_stable_but_below_gate`

Primary failure mode:
- the lane remains directionally positive across both WFO settings
- but the full-window row no longer satisfies the strict gate because:
  - `min_combo_trades = 0.25 < 0.5`
  - one main-run symbol remains slightly negative on the worst symbol statistic

### AWF-275: anchored 5-indicator / 4-symbol widening
- `pilot_analysis_awf275_anchored_4sym_5ind.json`
  - `compared_combo_rows = 120`
  - `stable_positive_rows = 17`
  - `gate_passed_rows = 0`

Interpretation:
- broadening the indicator family does produce positive rows
- but the surviving rows either fail all-symbol-nonnegative support or fail the trade gate
- the strongest stable rows rotate toward `cmf + obv_roc` families, but they do so with negative worst-symbol returns

### AWF-275: anchored 5-indicator / 5-symbol widening
- `pilot_analysis_awf275_anchored_5sym_5ind.json`
  - `compared_combo_rows = 120`
  - `stable_positive_rows = 10`
  - `gate_passed_rows = 0`

Interpretation:
- widening symbols weakens the already fragile broadened family further
- the best stable rows still fail symbol support, and the original canonical `mfi + obv_roc + atr_ratio` lane weakens materially

## Decision
1. Anchored-window + historical-backfill is validated.
   - The system can now hold `end` fixed and truly widen `days` by config.
   - This closes the prior ambiguity where `180d` requests silently clipped to `~127d`.

2. Exact-lane promotion must be downgraded from `promote` to `hold` for the current full-window baseline.
   - The previous promotive conclusion came from a shorter realized overlap.
   - Under the full anchored `181d` window, the lane stays stable-positive but no longer clears the strict full-window gate.

3. Broader indicator and symbol expansion is not justified yet.
   - `4-symbol / 5-indicator` widening: `0` gate-passed
   - `5-symbol / 5-indicator` widening: `0` gate-passed
   - The safest conclusion is that full-window anchored evidence does not currently support widening either axis.

## Next Direction
- Keep the exact lane available as a frozen replay candidate, but treat it as `hold`, not `promote`.
- Do not widen indicators or symbols based on the current full-window anchored evidence.
- Future re-validation should use either:
  - a materially shifted anchored `end`
  - or a protocol-level change that specifically addresses the full-window trade-density and symbol-support failure modes
