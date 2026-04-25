# Phase 63: Parallel Exploitation + Exploration

## Decision Context
- Phase 60 (hierarchical state-trigger) is frozen; all sidecar candidates are `time-local`.
- Phase 61–62 (parity reset + drift foundation) is closed; Gate A + B passed.
- Paper trading infrastructure is operational (FT bridge, live signal producer, daily reconcile).
- The strongest frozen candidate is `obv_roc + keltner_pos` (trend_high/high, drop SOL/BTC, 8-symbol, canonical rank 1).

## Route C: Parallel Exploitation + Exploration

Phase 63 runs two independent workstreams that do not block each other.

## Operator Intent

The shortest path to a usable strategy is not another broad architecture rewrite. It is:

1. keep AUTOWFO as the strategy-search and signal-truth system
2. validate the frozen canonical lane through the existing Freqtrade dry-run path
3. run only bounded search expansions that answer a named hypothesis
4. promote or close branches from replay, parity, and paper evidence

Freqtrade is the second engine and execution adapter. It should backtest, dry-run, reconcile, and eventually execute AUTOWFO signals; it should not become the strategy-search source.

---

### Workstream A — Paper Trading Exploitation (AWF-348 ~ AWF-351)

Objective: validate the frozen canonical candidate in live market conditions via Freqtrade dry-run, accumulate ≥14 calendar days of reconciliation evidence.

| ID | Task | Gate |
|---|---|---|
| AWF-348 | Restart FT dry-run with latest bridge blocker fixes; confirm signal producer + FT are both healthy | PID alive, live_manifest.json fresh |
| AWF-349 | Accumulate ≥7 calendar days of daily reconciliation summaries | 7 daily JSONs written, no crash |
| AWF-350 | Accumulate ≥14 calendar days; build aggregate drift report | aggregate `open_match_ratio ≥ 0.95` across all days |
| AWF-351 | Paper trading verdict: classify as `parity-confirmed`, `drift-bounded`, or `parity-failed` | human decision memo |

Exit criteria:
- ≥14 daily reconciliation summaries collected
- aggregate drift report shows `open_match_ratio ≥ 0.95` or a documented explanation for lower parity
- human verdict memo written

---

### Workstream B — Strategy Search Expansion (AWF-352 ~ AWF-359)

Objective: explore the three highest-priority untested dimensions, each as a bounded pilot with hypothesis/metric/threshold per development principles.

#### B1: Non-Trend Regime Sweep (AWF-352/353)

Hypothesis: the existing `obv_roc + keltner_pos` family may yield gate-passed candidates in mean-reversion regimes (`rsi_revert_low`, `bb_revert_low`, `bb_breakout_high`) that have never been searched.

| ID | Task | Metric | Accept |
|---|---|---|---|
| AWF-352 | Paired anchored 2h/180d pilot on 8-symbol drop-SOL cohort; regime_preset covering `rsi_revert_low`, `bb_revert_low`, `bb_breakout_high`; top-10 indicator subset; combo_sizes [2,3] | gate-passed count, canonical count | ≥1 gate-passed row with avg_symbol_trades ≥ 1.0 |
| AWF-353 | Temporal replay on older anchor if AWF-352 produces gate-passed candidates | replay classification | at least `directional-only` |

Rollback: if zero gate-passed, close the non-trend branch and do not revisit.

#### B2: 4h Timeframe Sweep (AWF-354/355)

Hypothesis: a 4h timeframe may reveal lower-frequency strategies with different regime dynamics, potentially more robust than 2h time-local candidates.

| ID | Task | Metric | Accept |
|---|---|---|---|
| AWF-354 | Paired anchored 4h/180d pilot on 8-symbol drop-SOL cohort; same top-10 indicator subset; combo_sizes [2,3]; regime_preset pilot_trend_3 | gate-passed count, canonical count | ≥1 gate-passed row with avg_symbol_trades ≥ 1.0 |
| AWF-355 | Temporal replay on older anchor if AWF-354 produces gate-passed candidates | replay classification | at least `directional-only` |

Rollback: if zero gate-passed, close the 4h branch.

#### B3: Extended Window Validation (AWF-356/357)

Hypothesis: extending the data window from 180d to 360d for the strongest frozen candidates will either confirm cross-cycle robustness or reveal that the 180d finding is window-specific.

| ID | Task | Metric | Accept |
|---|---|---|---|
| AWF-356 | Paired anchored 2h/360d run on the exact frozen canonical lane (`obv_roc + keltner_pos`, trend_high/high, drop-SOL 8-symbol); compare metrics vs 180d baseline | combo OOS avg return, gate-pass status | gate-passed on 360d AND combo OOS return within 50% of 180d baseline |
| AWF-357 | If AWF-356 passes, run the `obv_roc + keltner_pos + ad` triple on 360d as well | same metrics | gate-passed on 360d |

Rollback: if 360d fails, the 180d finding is confirmed as window-specific; document and move on.

#### B4: Housekeeping (AWF-358/359)

| ID | Task |
|---|---|
| AWF-358 | Normalize hardcoded `E:\Project\...` paths in PS1 scripts and `.mcp.json` to environment variables |
| AWF-359 | Fix review items #3–#6 from the bridge audit (duplicate code block, missing KeyboardInterrupt, trades-table guard, inf handling) |

---

## Gate Structure

```
Phase 63 Entry ──┬── Workstream A (AWF-348~351)
                 │     └── Gate C: paper trading verdict
                 │
                 └── Workstream B (AWF-352~359)
                       ├── B1 Gate: non-trend regime verdict
                       ├── B2 Gate: 4h timeframe verdict
                       ├── B3 Gate: 360d window verdict
                       └── B4: housekeeping (no gate)

Phase 63 Exit ← both workstreams report verdicts
```

## Phase 64 Entry Conditions
- All workstream verdicts documented
- At least one of: paper trading parity-confirmed, or a new replay-confirmed candidate found
- If neither: re-evaluate strategy hypothesis from scratch (new indicator family, new asset class, or new timeframe regime)
