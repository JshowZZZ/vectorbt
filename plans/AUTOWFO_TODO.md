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
| AWF-360 | done | Evidence warehouse protocol validator and candidate identity helper | stable identity enables old/new candidate comparison | JSON protocol validation + repeated ID equality | protocol validates and same candidate definition yields same candidate_id | keep planning-only; do not import legacy data |
| AWF-361 | done | Evidence warehouse DuckDB skeleton and CLI build/validate entry | empty warehouse schema enables safe later imports | DuckDB table skeleton + CLI validate/build | protocol tables and required columns exist; validate fails cleanly when DB is missing | remove CLI entry and generated warehouse DB only |
| AWF-362 | done | Evidence warehouse read-only import for Phase 61-62 replay/drift evidence | frozen replay/drift artifacts can seed warehouse evidence without mutating sources | imported candidate/replay/gap row counts + source artifact hashes | Phase 61-62 summary imports candidates and replay rows; drift report imports gap rows when present; repeated import stays idempotent | delete imported warehouse rows and remove CLI import mode only |
| AWF-363 | done | Repair Evidence Warehouse candidate identity source ownership | same strategy should share AUTOWFO candidate identity across replay/paper imports | candidate source_system + repeated ID equality | strategy_candidates use `autowfo`; import ownership stays in run/trade/gap IDs | revert identity helper changes only |
| AWF-364 | done | Phase 63 state reconciliation report | artifact truth prevents premature paper verdict | paper summary count + manifest selection/freshness | report records 4 daily summaries and stale stable-rank manifest; no verdict | remove report only |
| AWF-365 | done | Evidence Warehouse read-only import for Phase 63 paper reconcile evidence | dry-run summaries can seed paper/gap evidence without mutating sources | imported candidate/paper/gap row counts + warnings | paper trades import idempotently by Freqtrade trade ID; cross-day opened/closed summaries merge into one row; partial paper_dir imports preserve other batches; DB facts enrich open/close/profit/fee fields; zero-trade/stale/missing fee signals are explicit | remove import mode only |
| AWF-366 | done | Survival Gate policy loader and immutable verdict writer | versioned gate rows need policy/candidate/artifact identity before decisions | gate policy/verdict row writes | missing policy_id, unknown verdicts, and missing policy/candidate references are rejected; verdicts are append-only | remove writer APIs only |
| AWF-367 | done | Phase 63 paper survival aggregate report | paper verdicts must be blocked until enough evidence exists | evidence day count + verdict_allowed + blocking_reasons | <7 daily summaries, missing/stale manifest freshness, or quality blockers yield `incomplete_evidence` and no verdict allowance | remove report builder only |
| AWF-368 | done | Champion/Challenger lifecycle baseline for paper evidence | canonical lane and fresh branches need comparable roles | candidate_role in paper report | canonical rank 1 is Champion; other paper rows are Challenger/Mixed | remove role classification only |

AWF-360 completion note: implemented `autowfo.evidence_warehouse` as the minimal Evidence Warehouse V1 protocol loader/validator plus deterministic candidate identity helper. Validation: `python -m pytest tests/test_autowfo_evidence_warehouse.py -q` (`7 passed`). Scope stayed planning-only: no legacy import, no Risk Engine, no control-panel changes.

AWF-361 completion note: implemented the empty Evidence Warehouse V1 DuckDB skeleton and `autowfo storage evidence-warehouse --mode build|validate` CLI. Validation: `python -m pytest tests/test_autowfo_evidence_warehouse.py tests/test_autowfo_cli.py -q -k "evidence_warehouse"` (`12 passed, 69 deselected`). Scope stayed bounded: no legacy import, no Survival Gate writer, no Risk Engine, no control-panel changes.

AWF-362 completion note: implemented read-only Phase 61-62 replay/drift import through `autowfo.evidence_warehouse.import_phase61_62_replay_evidence` and `autowfo storage evidence-warehouse --mode import-phase61-62`. The importer seeds `strategy_candidates`, `ft_replay_results`, and row-level `execution_gap_events` from `awf331_rerun_summary.json` plus `execution_drift_report.json`, preserves source artifacts, and remains idempotent on repeated runs. Validation: `python -m pytest tests/test_autowfo_evidence_warehouse.py tests/test_autowfo_cli.py -q -k "phase61_62_replay or evidence_warehouse"` (`16 passed, 69 deselected`). Scope stayed bounded: no paper import, no Survival Gate verdict writer, no Risk Engine, no control-panel changes.

AWF-363-AWF-368 completion note: extended Evidence Warehouse V1 without adding Risk Engine, live activation, or control-panel changes. Candidate identity now uses canonical `source_system=autowfo` and cleans up legacy AWF-362 source ownership rows on re-import; Phase 63 paper summaries can be imported incrementally through `autowfo.evidence_warehouse.import_phase63_paper_reconcile_evidence` and `autowfo storage evidence-warehouse --mode import-phase63-paper`; paper trade facts are enriched from read-only Freqtrade SQLite rows when available and cross-day opened/closed summaries merge into a single fact row; paper survival evidence can be summarized through `build_phase63_paper_survival_report` with explicit `blocking_reasons`, including missing/stale manifest freshness evidence; Survival Gate policies/verdicts can be written through `write_gate_policy` and `write_gate_verdict` with existing policy/candidate references required. `plans/reports/AWF-364-report.md` records current artifact truth: 4 paper summaries, stale stable-rank live manifest, and no Phase 63 paper verdict. `plans/reports/AWF-363-368-report.md` records the data-integrity fix pass.

AWF-348 completion note: restored Phase 63 paper runtime to the frozen canonical rank 1 lane on 2026-04-28. The managed live signal producer and Freqtrade dry-run were observed running, `artifacts/live_signal_store/live_manifest.json` was refreshed to `selection=canonical_gate_passed`, `rank=1`, and `last_bar_utc=2026-04-28T14:00:00`, and `artifacts/paper_dryrun/daily_summary_20260428.json` was written. The day was zero-trade and classified as `strategy_no_signal_today` because manifest lane/freshness, signal rows, pair mapping, process health, and the dry-run SQLite `trades` table were all healthy while the current signal window had no enter/exit rows. Evidence Warehouse paper import succeeded without stale-manifest warnings. `plans/reports/AWF-348-report.md` records the recovery details.

AWF-349a automation note: added `python -m autowfo bridge-paper-evidence-day` as the one-click Phase 63 daily paper evidence collector. The command checks canonical lane/freshness, performs one-shot live-signal refresh when needed, runs dry-run reconcile, imports Phase 63 paper evidence into the Evidence Warehouse, writes `artifacts/paper_dryrun/health/phase63_paper_health_YYYYMMDD.json`, emits zero-trade classification plus zero-signal explainability, and filters aggregate paper survival reports to the expected canonical lane. It also exposes valid evidence day counting through `build_phase63_paper_survival_report`. AWF-349 remains in progress because the post-recovery canonical lane has only one filtered day (`2026-04-28`) and it is still zero-trade. `plans/reports/AWF-349a-report.md` records the automation slice.

## Active Items

### Workstream A — Paper Trading Exploitation

| ID | Status | Task | Metric | Accept threshold | Rollback |
|---|---|---|---|---|---|
| AWF-348 | done | Restart FT dry-run with blocker fixes; confirm signal producer + FT healthy | PID alive, live_manifest.json fresh | both processes running, manifest < 30 min old; zero-trade reason classified | debug startup if either process fails |
| AWF-349 | doing | Accumulate ≥7 days of daily reconciliation summaries | valid evidence day count + daily health JSON | ≥7 canonical rank 1 valid evidence days after 2026-04-28; no collector crash | investigate and fix collector/reconciler if health report is missing or invalid |
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
