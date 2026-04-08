# AUTOWFO Rerun Campaign 2026-03-28

## Purpose
- Plan the next backtest/rerun campaign after Phases 45~47.
- Separate runs that need a full rerun from runs that only need `compare-ranking` / `rescore`.
- Use the control panel as the primary execution path so the campaign also validates the UI workflow.

## Current Facts
- Phase 47 is closed: ranking evidence parity landed.
- 2026-03-29 update:
  - trusted coverage is now complete for the currently recoverable local evidence set: `18/18` tested cells across `BNB/BTC`, `ETH/BTC`, `SOL/BTC`, `SOL/USDT`, `WBTC/BTC`, `XRP/BTC` and `1h/2h/4h`
  - Wave 3 ranking validation has been executed on `46` trusted runs
  - `absolute -> relative low_trade_mode` was accepted as a ranking-layer rollout and applied with `storage rescore`
- Local trusted shared views were rebuilt on 2026-03-28:
  - `artifacts/run_registry.json` and `artifacts/shared_views_manifest.json` now expose `8` trusted runs again
  - Wave 0 results are visible in the control panel Coverage / Results / Dashboard views
- Current template config in `artifacts/sweep_config.json` targets:
  - timeframe: `1h`
  - days: `60`
  - symbols:
    - `ETH/BTC`
    - `SOL/BTC`
    - `WBTC/BTC`
    - `BNB/BTC`
    - `JASMY/BTC`
    - `XRP/BTC`
    - `AMP/BTC`
    - `TCT/BTC`
    - `GTO/BTC`
    - `FTT/BTC`

## Rerun Classification

### Class A: Rescore-only
- Use when a run already exists as trusted evidence under `artifacts/runs/<run_id>/...`.
- Use if the change only affects ranking/reporting:
  - Phase 45 ranking rules
  - Phase 47 rescore parity / comparison tooling
- Action:
  - run `python -m autowfo storage compare-ranking ...`
  - if accepted, run `python -m autowfo storage rescore ...`
- No full search rerun needed.

### Class B: Must rerun
- Use when the pair/timeframe is missing from the trusted registry / coverage matrix.
- Use when historical evidence only exists in legacy root outputs or old baseline archive layout.
- Current local status:
  - because trusted shared views are empty, every pair that should be covered locally is effectively in this bucket.

### Class C: Decision-critical historical reruns
- These are the highest-value historical pairs to restore first because they were used as decision evidence in Phase 44/45 discussions:
  - `BNB/BTC 2h`
  - `SOL/BTC 2h`
  - `XRP/BTC 4h`
  - `SOL/USDT 2h` (only if you still care about the non-BTC quote validation track)
- These should be treated as targeted baseline reruns, not broad exploratory sweeps.

## Campaign Waves

### Wave 0: Control-panel smoke
- Goal: verify the panel execution loop end-to-end before larger batches.
- Jobs:
  - `ETH/BTC 1h 60d` via `baseline`
  - `BNB/BTC 1h 60d` via `run combo`
  - `SOL/BTC 1h 60d` via `baseline`
- Why:
  - exercises Coverage enqueue
  - exercises Batch start / queue state
  - exercises Results/Leaderboard refresh
  - gives at least one tested cell that can be re-tested from Coverage

### Wave 1: Coverage seed for current template
- Goal: seed trusted coverage for the current `artifacts/sweep_config.json`.
- Jobs:
  - remaining `1h 60d` cells from the 10-symbol template set
- Status on 2026-03-28:
  - launched from the control panel Coverage tab after fixing historical batch-name collisions
  - `BNB/BTC`, `ETH/BTC`, `SOL/BTC`, `WBTC/BTC`, `XRP/BTC` are now covered locally
  - remaining cells are `AMP/BTC`, `FTT/BTC`, `GTO/BTC`, `JASMY/BTC`, `TCT/BTC`
  - these five symbols were re-run successfully through Coverage/Batch after the seen-key override fix, but all five produced `No overlapping data after download`
  - `artifacts/cache_ccxt/binance_<pair>_{1h,4h}.csv` exists only as header-only files for these pairs, so they should be treated as exchange-data unavailable for the current Binance spot feed rather than pending operator retries
- Operational decision:
  - do not keep re-queueing these five `1h/60d` cells as active coverage debt
  - move the next active rerun wave to Wave 2 historical evidence rebuild
- Recommended workflow:
  - `baseline` for cells where you want full combo+refine evidence
  - `run combo` only if you are intentionally doing a lighter scan

### Control-panel queue safeguard
- Coverage-created batch jobs must stay unique across both the live queue and `artifacts/batch_state.json` history.
- If historical names are reused after `Clear Queue`, fresh jobs can be misclassified as already complete.
- This safeguard was fixed on 2026-03-28 and should be treated as part of Wave 1 validation:
  - clear queue
  - enqueue coverage gaps again
  - verify the Batch tab shows new jobs as `等待中` / `提交中` / `執行中`, not `完成`

### Wave 2: Historical evidence rebuild
- Goal: restore the decision-critical pairs that are not represented in current local shared views.
- Jobs:
  - `BNB/BTC 2h`
  - `SOL/BTC 2h`
  - `XRP/BTC 4h`
  - optional `SOL/USDT 2h`
- Recommended workflow:
  - use `baseline`
  - run these as a separate campaign after editing template config in the control panel
- Active status on 2026-03-28:
  - this is now the primary rerun track after Wave 1 separated control-panel bugs from exchange-data availability issues

### Wave 3: Ranking validation on trusted runs
- Goal: avoid unnecessary reruns after Waves 0~2 create trusted evidence.
- Action:
  - compare candidate ranking config with `storage compare-ranking`
  - only rerun if comparison shows the candidate requires fresh search evidence rather than a pure ranking-layer rescore
- 2026-03-29 outcome:
  - `legacy -> composite` confirmed the already-shipped composite ranking should be interpreted as a sample-sufficiency / risk-shaping upgrade, not a raw-return uplift.
  - `absolute -> relative` improved average OOS return and Sharpe-like broadly enough to justify a ranking-only rollout on trusted shared views.
  - No additional full rerun is required for this change; the accepted action is `storage rescore` plus control-panel verification.

## Control Panel Workflow

### Path A: Coverage-driven targeted rerun
1. Open `Config` tab.
2. Set the campaign template:
   - hand-edit `timeframes`
   - hand-edit `trade_symbols`
   - or apply the built-in Config preset that matches the current wave:
     - `Wave 0 Smoke 1h/60d`
     - `Wave 2 Core 2h/120d`
     - `Wave 2 XRP 4h/180d`
     - `Wave 2 SOL/USDT 2h/120d`
   - worker count / ranking config as needed
3. Save config so Coverage uses the same template.
4. Open `Coverage` tab.
5. Choose execution mode:
   - `完整流程（baseline）` for full evidence runs
   - `只廣搜（run combo）` only for lightweight scans
   - avoid `只精煉（run refine）` unless a pair already has fresh combo-stage evidence
6. Click an `Untested` cell to enqueue one job, or use `填補全部缺口` for the whole wave.
7. Open `Batch` tab and click `Start Batch`.
8. Watch queue progression and job completion.
9. Open `Results` tab to confirm new Top10 / Leaderboard data appeared.

### Config preset mapping
- `Wave 0 Smoke 1h/60d`
  - symbols: `ETH/BTC`, `BNB/BTC`, `SOL/BTC`
  - use Coverage cells individually: baseline for `ETH/BTC` and `SOL/BTC`, run combo for `BNB/BTC`
- `Wave 2 Core 2h/120d`
  - symbols: `BNB/BTC`, `SOL/BTC`
  - use `baseline`
- `Wave 2 XRP 4h/180d`
  - symbol: `XRP/BTC`
  - use `baseline`
- `Wave 2 SOL/USDT 2h/120d`
  - symbol: `SOL/USDT`
  - optional track, use `baseline`

### Path B: Coverage re-test
1. After one cell becomes `Tested`, go back to `Coverage`.
2. Click the tested cell.
3. Use `重新測試`.
4. This explicitly validates the AWF-232 tested-cell retest flow.

### Path C: Full-config retest from Results
1. Open `Results`.
2. Use `重測 Top 10？`.
3. This triggers `/start?refresh_data=1`.
4. Use it when you want to re-run the current saved config with data refresh, not when you want pair-by-pair coverage targeting.

## Recommended Operator Rules
- Prefer `baseline` for any run that may become decision evidence.
- Use `run combo` only for smoke tests or broad exploratory scans.
- Do not use `run refine` as the first run for an empty pair/timeframe.
- After each wave:
  - confirm the run appears in `Results`
  - confirm Coverage cell state changes from `Untested` to `Tested`
  - confirm Batch queue drains correctly
  - if trusted views now exist, use `storage compare-ranking` before scheduling more reruns

## Exit Criteria
- Wave 0:
  - Coverage enqueue works
  - Batch start works
  - Results refresh works
  - tested-cell retest works
- Wave 1:
  - current template matrix is materially populated with trusted runs
- Wave 2:
  - the historical decision-critical pairs exist locally as trusted evidence
- Wave 3:
  - ranking changes are evaluated via compare/rescore before any further rerun campaign
