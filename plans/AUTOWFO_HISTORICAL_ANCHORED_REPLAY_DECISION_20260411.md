# AUTOWFO Historical Anchored Replay Decision

Date: `2026-04-11`

## Objective

Re-run the frozen full 10-symbol bounded-family current-mode baseline on a one-year-
earlier anchored `180d` window and classify whether the earlier slice confirms,
partially supports, or invalidates the modern bounded-family evidence.

Protocol reference:
- `plans/AUTOWFO_HISTORICAL_ANCHORED_REPLAY_PROTOCOL.md`

Comparison baseline:
- `artifacts/reports/pilot_analysis_awf282_family_refine.json`

Historical replay artifacts:
- main: `20260411_awf310_hist180_main`
- sensitivity: `20260411_awf310_hist180_sens`
- paired report: `artifacts/reports/pilot_analysis_awf310_hist180.json`

## Window Realization

The older anchored replay realized the full requested shared window:

- requested anchor end: `2025-04-09T14:00:00Z`
- realized shared start: `2024-10-11 14:00:00`
- realized shared end: `2025-04-09 14:00:00`
- realized shared days: `181`
- requested symbol count: `10`
- available trade symbol count: `10`

This confirms the anchored-window/backfill contract works on materially older `2h`
BTC-cross data, not only on the recent `2025-10` to `2026-04` slice.

## Headline Result

Classification: `directional-only`

Summary:
- compared rows: `105`
- stable-positive rows: `21`
- gate-passed rows: `0`
- canonical gate-passed rows: `0`

Interpretation:
- the bounded family still produces cross-WFO directional structure on the earlier
  slice
- but the modern gate-passed family shape does not replay cleanly one year earlier

## Comparison to the Full-Window Bounded-Family Baseline

Modern bounded-family baseline (`AWF-282`):
- `105` compared
- `33` stable-positive
- `2` gate-passed

Historical replay (`AWF-310`):
- `105` compared
- `21` stable-positive
- `0` gate-passed

This is a clear downgrade, but not a total collapse. The older slice retains
meaningful stable-positive density while losing strict symbol-support completeness.

## Family Survival

The current canonical bounded-family winners do **not** survive on the older slice:

- `obv_roc + keltner_pos + ad`
- `obv_roc + keltner_pos + ad + dpo`

Neither appears in the historical stable-positive set.

The strongest earlier slice rows shift toward:
- `ad + cmf + dpo` / `trend_high` / `high`
- `obv_roc + cmf + dpo` / `trend_high` / `high`
- `ad + cmf + chop` / `trend_low` / `low`

This suggests the earlier window still rewards bounded multi-indicator confirmation,
but not the exact modern `obv_roc + keltner_pos + ad` expression.

## Symbol-Role Change

Across all historical replay rows, the dominant blocker is no longer `BNB/BTC`.

Worst-symbol frequency across the replay grid:
- `SOL/BTC`: `36`
- `AVAX/BTC`: `19`
- `ADA/BTC`: `16`
- `BNB/BTC`: `10`
- `LTC/BTC`: `9`

Worst-symbol frequency restricted to stable-positive rows:
- `SOL/BTC`: `8`
- `BNB/BTC`: `4`
- `XRP/BTC`: `3`
- `DOT/BTC`: `2`
- `LTC/BTC`: `2`

Interpretation:
- `BNB/BTC` remains a pressure point, but it is not the primary historical blocker
- `SOL/BTC` is the dominant blocker on the earlier slice
- symbol-role ordering is therefore only partially stable through time

## Decision

Do **not** reopen current-mode narrowing from this result alone.

Use this replay as temporal evidence only:
- it weakens the claim that the modern bounded family is fully time-invariant
- it supports opening the hierarchical state-trigger mode, because the earlier slice
  still contains directional structure but not the same gate-passed family form
- it also argues that future sidecar factors should be judged on whether they improve
  temporal robustness, not just current-window gate status

## Follow-On Implications

1. `AWF-303` / `AWF-304` remain the mainline.
   The state-trigger mode should be judged against both:
   - the modern frozen bounded-family/current-mode reference
   - this older `directional-only` slice

2. `AWF-309` becomes more valuable.
   Cross-timeframe confirmation is now more attractive because the older slice retains
   directional structure but loses strict symbol-support closure.

3. `AWF-307` / `AWF-308` should stay behind data-availability gating.
   There is no need to rush external-data factors before the lower-risk temporal and
   HTF evidence paths are exhausted.
