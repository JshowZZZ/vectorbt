# AUTOWFO TODO

## Usage Rules
- This file tracks only active-phase execution items.
- Completed historical items are archived in `plans/AUTOWFO_TODO_ARCHIVE.md`.
- Allowed statuses: `todo`, `doing`, `blocked`, `done`.
- Policy is authoritative in `plans/AUTOWFO_DEVELOPMENT_PRINCIPLES.md`; plans and TODO entries must not override it.
- Survivalism work must cite the framework, evidence warehouse, gate policy, lifecycle, or frozen protocols before implementation.

## Active Phase
- Phase 63: Parallel Exploitation + Exploration (Route C).
- Workstream A: paper trading exploitation via FT dry-run.
- Workstream B: strategy search expansion (non-trend regimes, 4h timeframe, 360d window).
- Previous phases: 60 frozen, 61–62 closed.
- Active plan: `plans/AUTOWFO_PHASE63_PLAN.md`.

## Gate State
- Phase 61–62 Gate A + Gate B: passed.
- Phase 63 entry: approved 2026-04-18.
- Next gate: Phase 63 workstream verdicts (paper trading + search expansion).

## Active Operator Focus
- Fast path: keep using AUTOWFO for strategy/indicator discovery and the existing Freqtrade bridge for backtest, dry-run paper trading, reconcile, and drift checks.
- Do not add new broad search dimensions unless they map to the active Phase 63 workstreams below.
- Do not let Freqtrade own strategy logic; it consumes AUTOWFO signal artifacts and reports execution evidence back.
- Next implementation direction, once explicitly started by the user: Evidence Warehouse V1 before Risk Engine V1.

## Required Context For New Survivalism Work
- North star: `plans/AUTOWFO_SURVIVALISM_FRAMEWORK.md`
- Decision record: `plans/AUTOWFO_DECISION_LOG.md`
- First implementation spec: `plans/AUTOWFO_EVIDENCE_WAREHOUSE_V1.md`
- Gate policy: `plans/AUTOWFO_SURVIVAL_GATE_POLICY.md`
- Strategy lifecycle: `plans/AUTOWFO_STRATEGY_LIFECYCLE.md`
- Frozen protocols:
  - `plans/protocols/evidence_warehouse_v1.json`
  - `plans/protocols/survival_gate_policy_v1.json`

Suggested first new implementation item after user start:

| ID | Status | Task | Hypothesis | Metric | Accept threshold | Rollback |
|---|---|---|---|---|---|---|
| AWF-360 | todo | Evidence warehouse protocol validator and candidate identity helper | stable identity enables old/new candidate comparison | JSON protocol validation + repeated ID equality | protocol validates and same candidate definition yields same candidate_id | keep planning-only; do not import legacy data |

## Active Items

### Workstream A — Paper Trading Exploitation

| ID | Status | Task | Metric | Accept threshold | Rollback |
|---|---|---|---|---|---|
| AWF-348 | todo | Restart FT dry-run with blocker fixes; confirm signal producer + FT healthy | PID alive, live_manifest.json fresh | both processes running, manifest < 30 min old | debug startup if either process fails |
| AWF-349 | todo | Accumulate ≥7 days of daily reconciliation summaries | daily JSON count | 7 daily summaries, no crash | investigate and fix if reconciler crashes |
| AWF-350 | todo | Accumulate ≥14 days; build aggregate drift report | aggregate open_match_ratio | ≥ 0.95 across all days | document drift explanation if below threshold |
| AWF-351 | todo | Paper trading verdict memo | human classification | parity-confirmed / drift-bounded / parity-failed | close workstream with verdict |

### Workstream B — Strategy Search Expansion

| ID | Status | Task | Hypothesis | Metric | Accept threshold | Rollback |
|---|---|---|---|---|---|---|
| AWF-352 | todo | Non-trend regime paired pilot (rsi_revert, bb_revert, bb_breakout) | existing family yields gate-passed candidates in mean-reversion regimes | gate-passed count with avg_symbol_trades ≥ 1.0 | ≥ 1 gate-passed row | close non-trend branch |
| AWF-353 | todo | Non-trend temporal replay (if AWF-352 passes) | non-trend candidates survive older anchor | replay classification | at least directional-only | classify as time-local |
| AWF-354 | todo | 4h timeframe paired pilot on drop-SOL 8-symbol cohort | 4h reveals lower-frequency strategies | gate-passed count with avg_symbol_trades ≥ 1.0 | ≥ 1 gate-passed row | close 4h branch |
| AWF-355 | todo | 4h temporal replay (if AWF-354 passes) | 4h candidates survive older anchor | replay classification | at least directional-only | classify as time-local |
| AWF-356 | todo | 360d extended window validation for frozen canonical lane | cross-cycle robustness vs 180d | gate-pass status + OOS return vs 180d | gate-passed AND return within 50% of 180d | document as window-specific |
| AWF-357 | todo | 360d run for obv_roc+keltner_pos+ad triple (if AWF-356 passes) | triple also survives 360d | gate-pass status | gate-passed on 360d | close extended-window triple branch |
| AWF-358 | todo | Normalize hardcoded paths in PS1 scripts and .mcp.json to env vars | — | — | paths use env vars | — |
| AWF-359 | todo | Fix bridge audit items #3–#6 (duplicate code, KeyboardInterrupt, trades-table guard, inf) | — | — | all 4 items resolved, tests pass | — |
