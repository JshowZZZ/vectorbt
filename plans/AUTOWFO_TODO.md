# AUTOWFO TODO

## Usage Rules
- This file is the execution backlog for AUTOWFO.
- Every implementation task must map to one TODO ID.
- Update status immediately after task completion.
- Allowed statuses: `todo`, `doing`, `blocked`, `done`.

## Priorities
- P-1: Prerequisite (must complete before P0)
- P0: Foundation and correctness ??protocol freeze
- P1: Core automation and ranking quality
- P2: Scale, usability, and continuous operation

## Existing Implementation Inventory
> Before planning, acknowledge what already exists in `scripts/run_btc_regime_sweep.py` (3000-line monolith):

| Capability | Current Location | Status | Gap |
|---|---|---|---|
| Walk-forward split | `_build_walk_forward_slices()` ~L1004 | Working (anchored mode) | No validation set; not true per-window re-optimization; hard-coded parameters |
| IS/OOS metrics | `_calc_pf_series()`, `_aggregate_oos_metrics()` | Working, 8 IS + 10 OOS fields | Missing Sharpe ratio, stability penalty, dispersion score |
| Indicator definitions | `INDICATOR_META` dict, 13 indicators | Working | No schema file, no validator, hard-coded |
| Regime logic | `REGIME_NAME_MAP`, 8 types | Working | Hard-coded, no external spec |
| Combo generation | `itertools.combinations`, C(13, 2..4) = 1079 | Working | No pruning beyond seen_keys dedup |
| Ranking | `sort by oos_avg_total_return_pct` | Working but simplistic | No Sharpe, no drawdown penalty, no consistency score |
| Two-stage search | `combo` ??`refine` mode | Working | Already implements AWF-008 concept |
| Artifacts | CSV + SQLite + HTML reports | Working | No config hash, no data fingerprint, all DB columns TEXT |
| Control panel | `control_panel.py` (2250 lines) | Working web UI :8787 | Tightly coupled to sweep script |

## Backlog
| ID | Priority | Status | Owner | Task | Deliverable | Exit Criteria |
|---|---|---|---|---|---|---|
| AWF-000 | P-1 | done | JshowZZZ + AI | Monolith decomposition ??extract `run_btc_regime_sweep.py` core logic into modules | `scripts/autowfo/split.py`, `metrics.py`, `strategy.py`, `artifacts.py`, `ranking.py`, `search.py`; main script becomes thin orchestrator | Each module importable + testable independently; sweep script still produces identical results |
| AWF-001 | P0 | todo | JshowZZZ + AI | Extract + freeze split protocol from `_build_walk_forward_slices()` | `plans/protocols/split_protocol.yaml` + `split.py` module + unit tests | Schema covers train/valid/test, horizons, overlap, anchored vs rolling modes |
| AWF-002 | P0 | todo | JshowZZZ + AI | Extract + freeze metric contract from `_calc_pf_series/_aggregate_*` | `plans/protocols/metric_contract.yaml` + `metrics.py` module + tests | All IS/OOS metric names and formulas frozen; includes Sharpe ratio formula |
| AWF-003 | P0 | todo | JshowZZZ + AI | Extract + freeze strategy spec schema from `INDICATOR_META/REGIME_NAME_MAP` | `plans/protocols/strategy_schema.json` + JSON Schema validator | Invalid specs fail fast; all 13 indicators + 8 regimes representable |
| AWF-004 | P0 | todo | JshowZZZ + AI | Extract + freeze artifact schema; add config hash + data fingerprint | `plans/protocols/artifact_contract.yaml` + artifact writer module | Every run emits config SHA256, data range hash, reproducible metadata |
| AWF-005 | P1 | blocked | JshowZZZ + AI | Refactor orchestration pipeline into modular AUTOWFO engine | `scripts/autowfo/engine.py` using frozen protocol modules | End-to-end run from spec to leaderboard using modular pipeline |
| AWF-002b | P1 | blocked | JshowZZZ + AI | Add Sharpe ratio + stability scoring to metric module | Extended `metrics.py`: per-segment Sharpe, cross-segment stddev, drawdown penalty weight | Stability metrics computable, compared side-by-side with old ranking |
| AWF-006 | P1 | blocked | JshowZZZ + AI | Implement stability-first ranking function using AWF-002b metrics | `ranking.py` module + before/after comparison artifacts | Top-N selection uses composite score (OOS return + Sharpe + consistency - drawdown penalty) |
| AWF-007 | P1 | blocked | JshowZZZ + AI | Add benchmark scenario for regression | Baseline config + expected outputs + golden test | Repeated runs are deterministic under fixed seed/data |
| AWF-008 | P1 | done | ??| Two-stage search (coarse ??focused) | Already in `run_btc_regime_sweep.py` (`combo` + `refine` modes) | Working; to be extracted into `search.py` during AWF-000 |
| AWF-001b | P1 | blocked | JshowZZZ + AI | Add true WFO mode (per-window re-optimization) alongside anchored mode | `split.py` extension + engine integration | Can run both anchored eval and true WFO; results comparable |
| AWF-009 | P2 | blocked | JshowZZZ + AI | Add run registry (history + diff between runs) | Experiment index + diff artifacts | Can compare current run vs prior run by config/data/metric changes |
| AWF-010 | P2 | blocked | JshowZZZ + AI | Add one-command execution entrypoint | CLI command wrapping full pipeline | `python -m autowfo run --config sweep.yaml` works end-to-end |
| AWF-011 | P2 | blocked | JshowZZZ + AI | Add regression tests for split and ranking invariants | Test suite additions | CI/local tests catch protocol regressions |
| AWF-012 | P2 | blocked | JshowZZZ + AI | Add operational playbook | Runbook doc | New run can be operated without notebook |

## Execution Phases

### Phase 1: Decompose (AWF-000)
> Goal: Break the monolith so individual protocols can be frozen and tested independently.
- Map every function in `run_btc_regime_sweep.py` to its target module.
- Extract with zero behavior change ??old script output must be identical.
- Add import bridge so `control_panel.py` continues to work.
- **Must complete before any Gate A work begins.**

### Phase 2: Protocol Freeze (AWF-001 ??AWF-004, then Gate A)
> Goal: Formalize what already works into versioned, testable specs.
- Each task = read existing hard-coded logic ??write explicit spec ??add schema validation ??add unit tests.
- Gate A checklist must all pass before moving to Phase 3.

### Phase 3: Ranking Upgrade (AWF-002b ??AWF-006 ??AWF-007, then Gate B)
> Goal: Replace simple sort-by-return with composite robustness scoring.
- AWF-002b: Add Sharpe + stability metrics to the metric module.
- AWF-006: New ranking function using composite score.
- AWF-007: Benchmark scenario to lock down deterministic results.
- Gate B checklist must pass before Phase 4.

### Phase 4: Advanced Modes (AWF-001b ??AWF-005, then Gate C)
> Goal: Add true WFO and refactor engine for modularity.
- AWF-001b: Per-window re-optimization mode.
- AWF-005: Full engine refactor using modular pipeline.
- Gate C reproducibility checks.

### Phase 5: Operationalize (AWF-009 ??AWF-012, then Gate D)
> Goal: Production-ready automation.
- Run registry, CLI, regression suite, runbook.
- Gate D regression green.

## Current Focus Window
- Active phase: **Phase 1 complete; Phase 2 deferred**
- Decision: Anti-over-engineering — protocol freeze (AWF-001~004) deferred until proven necessary
- Next action: Continue end-to-end baselines; run next window with non-empty OOS segments and re-evaluate ranking trigger
- Allowed implementation now: Bug fixes, end-to-end validation
- Blocked: AWF-001~004 deferred; AWF-005+ still blocked

## Session Log
| Date | Task IDs | Status Change | Decision | Next Action | Commit/Ref |
|---|---|---|---|---|---|
| 2026-02-06 | AWF-ALL | initialized | Backlog skeleton created | Start protocol freeze tasks AWF-001~004 | initial planning commit |
| 2026-02-06 | AWF-ALL | metadata_update | Added owner/date columns and structured logging format | Populate Est. Date during next planning sync | docs refinement |
| 2026-02-06 | AWF-000, AWF-008 | plan_revised | Architecture review found 3000-line monolith blocking protocol freeze; AWF-008 already done in code | Added AWF-000 (P-1), AWF-002b, AWF-001b; changed AWF-001~004 from "define" to "extract+freeze"; marked AWF-008 done; restructured into 5 execution phases | Start AWF-000 decomposition | ??|
| 2026-02-06 | AWF-000 | doing | Completed decomposition step 1 (constants extraction with compatibility re-export + characterization tests) | Continue AWF-000 step 2: extract data module | eb4e93a |
| 2026-02-07 | AWF-000 | doing | Completed decomposition step 2 (data module extraction with compatibility wrappers + characterization tests) | Continue AWF-000 step 3: extract split module | pending |
| 2026-02-07 | AWF-000 | doing | Completed decomposition step 3 (split module extraction with compatibility wrapper + characterization tests) | Continue AWF-000 step 4: extract metrics module | pending |
| 2026-02-07 | AWF-000 | doing | Completed decomposition step 4 (metrics module extraction with compatibility wrappers + characterization tests) | Continue AWF-000 step 5: extract artifacts module | pending |
| 2026-02-07 | AWF-000 | doing | Completed decomposition step 5 (artifacts module extraction with compatibility wrappers + characterization tests) | Continue AWF-000 step 6: extract strategy module | pending |
| 2026-02-07 | AWF-000 | doing | Completed decomposition step 6 (strategy module extraction with compatibility wrappers + characterization tests) | Continue AWF-000 step 7: extract search/ranking modules | pending |
| 2026-02-07 | AWF-000 | doing | Completed decomposition step 7 (search module extraction for combo key logic + characterization tests) | Continue AWF-000 step 8: extract ranking module | pending |
| 2026-02-07 | AWF-000 | doing | Completed decomposition step 8 (ranking module extraction with compatibility wrappers + characterization tests) | Continue AWF-000 step 9: extract report/render helpers | pending |
| 2026-02-07 | AWF-000 | doing | Completed decomposition step 9 (report module extraction with compatibility wrappers + characterization tests) | Continue AWF-000 step 10: extract portfolio execution module | pending |
| 2026-02-07 | AWF-000 | doing | Completed decomposition step 10 (portfolio module extraction with compatibility wrapper + characterization tests) | Re-evaluate AWF-000 exit criteria and remaining thin-orchestrator gaps | pending |
| 2026-02-07 | AWF-000 | doing | Completed decomposition step 11 (engine helper extraction for config/regime/count/filter logic + tests) | Continue AWF-000 step 12: migrate more main-flow orchestration into engine | pending |
| 2026-02-07 | AWF-000 | doing | Completed decomposition step 12 (engine extraction for progress/checkpoint gating + payload helpers + tests) | Continue AWF-000 step 13: migrate main loop blocks into engine runner | pending |
| 2026-02-07 | AWF-000 | doing | Completed decomposition step 13 (engine extraction for combo keyspace, existing-result normalization, seen-key build + tests) | Continue AWF-000 step 14: migrate timeframe evaluation runner blocks into engine | pending |
| 2026-02-07 | AWF-000 | doing | Completed decomposition step 14 (engine extraction for control file bootstrap/read helpers + tests) | Continue AWF-000 step 15: migrate timeframe eval loop scaffolding into engine | pending |
| 2026-02-07 | AWF-000 | doing | Completed decomposition step 15 (engine extraction for coarse-plan iterator and refine-target builder + tests) | Continue AWF-000 step 16: migrate eval_combo state construction helpers into engine | pending |
| 2026-02-07 | AWF-000 | doing | Completed decomposition step 16 (engine extraction for combo-key payload builder and regime-signal resolver + tests) | Continue AWF-000 step 17: extract row-assembly helpers and finalize thin orchestrator | pending |
| 2026-02-07 | AWF-000 | doing | Completed decomposition step 17 (engine extraction for symbol/combo row assembly helpers + tests) | Continue AWF-000 step 18: isolate eval runner orchestration into engine callable | pending |
| 2026-02-07 | AWF-000 | doing | Completed decomposition step 18 (engine extraction for effective-cost and trade-momentum filter helpers + tests) | Continue AWF-000 step 19: package eval loop into engine callable runner | pending |
| 2026-02-07 | AWF-000 | doing | Completed decomposition step 19 (engine callable runner for timeframe search orchestration + tests) | Continue AWF-000 step 20: extract final report/leaderboard finalize pipeline | pending |
| 2026-02-07 | AWF-000 | doing | Completed decomposition step 20 (engine extraction for finalize pipeline helpers: result-load/snapshot/filter/best-pick/leaderboard views + tests) | Continue AWF-000 step 21: validate bit-identical outputs for extracted orchestration | pending |
| 2026-02-07 | AWF-000 | doing | Completed decomposition step 21 (deterministic dual-run characterization test verifies artifact CSV outputs are bit-identical) | Continue AWF-000 step 22: perform exit-criteria audit and decide AWF-000 closure | pending |
| 2026-02-07 | AWF-000 | done | Completed decomposition step 22 exit audit: module importability check added, deterministic bit-identical artifact test in place, and phase focus moved to protocol freeze | Start AWF-001 split protocol extraction and schema freeze | pending |
| 2026-02-10 | AWF-000 | cleanup | Anti-over-engineering cleanup: (1) Added AUTOWFO Development Principles to AGENTS.md, (2) Added WF step_days >= test_days validation in split.py, (3) Removed 535 lines of thin wrappers from monolith (1724→1311 lines), main() now calls autowfo sub-modules directly, (4) Fixed report block duplicated regime signal reconstruction and cost calculation, (5) Deleted 3 pure wrapper-equivalence test files, updated remaining 8 test files to use sub-modules directly. 23 tests pass. | Continue end-to-end backtesting or address real bugs as they arise | pending |
| 2026-02-07 | AWF-008, AWF-002b, AWF-006 | e2e_baseline | Implemented `scripts/run_autowfo_baseline.py` and baseline helpers/tests; executed real-data two-pass sweep (`combo` then `refine`) with snapshot/comparison/trigger artifacts under `artifacts/runs/20260207_103734`; trigger result: `false` (only D2 true) so AWF-002b/AWF-006 not activated this round | Run next baseline window with non-empty OOS segments (adjust timeframe/data days or WF horizon), then re-check trigger | pending |
