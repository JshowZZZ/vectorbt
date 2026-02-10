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
| AWF-003 | P0 | done | JshowZZZ + AI | Extract + freeze strategy spec schema from `INDICATOR_META/REGIME_NAME_MAP` | `plans/protocols/strategy_schema.json` + JSON Schema validator | Invalid specs fail fast; all 13 indicators + 8 regimes representable; adding a new indicator only requires config change |
| AWF-002 | P0 | done | JshowZZZ + AI | Extract + freeze metric contract from `_calc_pf_series/_aggregate_*` | `plans/protocols/metric_contract.yaml` + `metrics.py` module + tests | All IS/OOS metric names and formulas frozen; cross-run comparability guaranteed |
| AWF-004 | P0 | done | JshowZZZ + AI | Extract + freeze artifact schema; add config hash + data fingerprint | `plans/protocols/artifact_contract.yaml` + artifact writer module | Every run emits config SHA256, data range hash, reproducible metadata |
| AWF-001 | P0 | done | JshowZZZ + AI | Extract + freeze split protocol from `_build_walk_forward_slices()` | `plans/protocols/split_protocol.yaml` + `split.py` module + unit tests | Schema covers train/valid/test, horizons, overlap, anchored vs rolling modes |
| AWF-005 | P1 | blocked | JshowZZZ + AI | Refactor orchestration pipeline into modular AUTOWFO engine | `scripts/autowfo/engine.py` using frozen protocol modules | End-to-end run from spec to leaderboard using modular pipeline |
| AWF-002b | P1 | blocked | JshowZZZ + AI | Add Sharpe ratio + stability scoring to metric module | Extended `metrics.py`: per-segment Sharpe, cross-segment stddev, drawdown penalty weight | Stability metrics computable, compared side-by-side with old ranking |
| AWF-006 | P1 | blocked | JshowZZZ + AI | Implement stability-first ranking function using AWF-002b metrics | `ranking.py` module + before/after comparison artifacts | Top-N selection uses composite score (OOS return + Sharpe + consistency - drawdown penalty) |
| AWF-007 | P1 | blocked | JshowZZZ + AI | Add benchmark scenario for regression | Baseline config + expected outputs + golden test | Repeated runs are deterministic under fixed seed/data |
| AWF-008 | P1 | done | ??| Two-stage search (coarse ??focused) | Already in `run_btc_regime_sweep.py` (`combo` + `refine` modes) | Working; to be extracted into `search.py` during AWF-000 |
| AWF-001b | P1 | blocked | JshowZZZ + AI | Add true WFO mode (per-window re-optimization) alongside anchored mode | `split.py` extension + engine integration | Can run both anchored eval and true WFO; results comparable |
| AWF-013 | P1 | done | JshowZZZ + AI | Multi-process parallelization for combo evaluation | `eval_combo` extracted to pure function + `ProcessPoolExecutor` with centralized IO | 3-worker parallel run produces bit-identical results to single-thread; ×2.5 speedup measured |
| AWF-009 | P1 | done | JshowZZZ + AI | Add run registry (history + diff between runs) | Experiment index + coverage map across symbols/timeframes | Can see which symbol/timeframe combinations have been tested and which remain |
| AWF-010 | P1 | done | JshowZZZ + AI | Add one-command execution entrypoint | CLI command wrapping full pipeline | `python -m autowfo run --config experiment.yaml` works end-to-end |
| AWF-014 | P1 | done | JshowZZZ + AI | Batch runner — sequential multi-config execution with preflight checks | `autowfo batch --plan batch_plan.json` CLI subcommand + batch orchestrator | 3-config batch completes unattended; registry accumulates; crash-restart skips completed jobs via seen_keys |
| AWF-015 | P1 | done | JshowZZZ + AI | Coverage planner — auto-generate batch plan from untested pairs | `autowfo plan` CLI subcommand reading `run_registry.json` coverage gaps | Planner output feeds directly into `autowfo batch`; `--max-jobs N` limits scope |
| AWF-016 | P1 | blocked | JshowZZZ + AI | Cross-run dashboard — aggregate analysis across accumulated runs | `autowfo report` CLI subcommand producing `artifacts/cross_run_report.html` | Coverage matrix + combo stability + global leaderboard from ≥3 runs |
| AWF-017a | P1 | done | JshowZZZ + AI | Control panel architecture refactor — front/back separation, Tab navigation, CSS upgrade | `scripts/control_panel/` with `static/` assets, modular JS, Tab-based layout | Panel serves from file-based static assets; new tab addable without touching Python |
| AWF-017b | P1 | done | JshowZZZ + AI | Batch queue UI — queue table, progress display, cancel buttons | Batch panel in control panel with enqueue/start/cancel/clear actions | Queue table live-refreshes; can enqueue config and start batch from browser |
| AWF-017c | P1 | blocked | JshowZZZ + AI | Coverage map UI — timeframe×symbol matrix, one-click scheduling | Coverage tab with color-coded grid and click-to-enqueue interaction | Matrix shows tested/untested/queued; click adds to batch queue |
| AWF-017d | P1 | blocked | JshowZZZ + AI | Cross-run dashboard UI + run history — timeline, global leaderboard | Dashboard tab with run history table, combo stability chart, aggregated KPIs | Registry data browsable; ≥3 runs produce stability trend visualization |
| AWF-011 | P1 | done | JshowZZZ + AI | Add regression tests for split and ranking invariants | Test suite additions | CI/local tests catch protocol regressions |
| AWF-012 | P1 | done | JshowZZZ + AI | Add operational playbook | Runbook doc | New run can be operated without notebook |

## Execution Phases

### Phase 1: Decompose (AWF-000) ✅
> Goal: Break the monolith so individual protocols can be frozen and tested independently.
- Extracted 10 modules from 3000-line monolith into `scripts/autowfo/`.
- Zero behavior change verified via bit-identical artifact tests.
- Status: **Complete**.

### Phase 2: Foundation — Protocol Freeze (AWF-003 → AWF-002 → AWF-004 → AWF-001) ✅
> Goal: Make the system trustworthy and extensible for repeated use as a strategy-exploration platform.
- Strategy schema, metric contract, artifact contract, split protocol all frozen with JSON/YAML specs + validation.
- Status: **Complete**. Gate A passed at commit `524f837`.

### Phase 3: Scale & Experiment Management (AWF-013, AWF-009, AWF-010) ✅
> Goal: Run faster, track what's been tested, lower operational cost.
- Multi-process parallelization (×2.66 speedup), run registry, CLI entrypoint.
- Status: **Complete**.

### Phase 4: Quality Guardrails (AWF-011, AWF-012) ✅
> Goal: Production-ready testing and operational documentation.
- Regression test suite (87 tests, 18 files), operational runbook.
- Status: **Complete**. Gate D passed at commit `a147972`.

---

### Phase 5: Control Panel Architecture Refactor (AWF-017a)
> Goal: Restructure the 2250-line single-file control panel into a maintainable, extensible architecture.
- Separate Python API backend from HTML/JS/CSS frontend assets.
- Introduce Tab-based navigation (控制台 / 結果 / 覆蓋 / 儀表板 / 歷史).
- Adopt lightweight CSS framework for consistent button/card/form styling.
- Modular JS files per tab (batch.js, coverage.js, dashboard.js).
- **Must complete before Phase 6-8 UI work begins.**

### Phase 6: Batch Execution (AWF-014 + AWF-017b)
> Goal: Enable unattended multi-config execution with browser-based control.
- AWF-014: Batch runner backend — `autowfo batch --plan batch_plan.json`, preflight checks, crash-safe resume via `seen_keys`.
- AWF-017b: Batch queue UI — enqueue/start/cancel buttons, queue table with per-job status/progress, live refresh.
- Deliverable: Queue 3 configs from browser → batch runs unattended → registry accumulates.

### Phase 7: Coverage Intelligence (AWF-015 + AWF-017c)
> Goal: Auto-detect untested timeframe×symbol pairs and schedule them.
- AWF-015: Coverage planner backend — `autowfo plan` reads `run_registry.json` gaps, generates batch plan, `--max-jobs N` limits scope.
- AWF-017c: Coverage map UI — color-coded matrix (🟢tested / 🟡queued / ⬜untested), click-to-enqueue, coverage % progress bar.
- Deliverable: Planner output feeds directly into batch queue; visual coverage gap identification.

### Phase 8: Cross-Run Insight (AWF-016 + AWF-017d)
> Goal: Aggregate analysis across accumulated runs for combo stability and trend detection.
- AWF-016: Cross-run dashboard backend — `autowfo report` producing `cross_run_report.html`, combo appearance frequency, stability scoring.
- AWF-017d: Dashboard UI — run history DataTable, combo stability timeline chart, global leaderboard, aggregated KPIs.
- Deliverable: ≥3 runs produce meaningful stability trend visualization from browser.

### Phase 9: Ranking Upgrade — Evidence-Driven (AWF-002b → AWF-006 → AWF-007, then Gate B)
> Goal: Replace simple sort-by-return with composite robustness scoring.
> Trigger: only activated when baseline runs show D1 or D2 pass (ranking quality is the bottleneck).
> Current evidence: 11 baseline windows all show D3-only; AWF-002b/AWF-006 remain deferred.
- AWF-002b: Add Sharpe + stability metrics to the metric module.
- AWF-006: New ranking function using composite score.
- AWF-007: Benchmark scenario to lock down deterministic results.
- Gate B checklist must pass before Phase 10.

### Phase 10: Advanced Modes (AWF-001b → AWF-005, then Gate C)
> Goal: Add true WFO and refactor engine for modularity.
- AWF-001b: Per-window re-optimization mode.
- AWF-005: Full engine refactor using modular pipeline.
- Gate C reproducibility checks.

## Current Focus Window
- Active phase: **Phase 7 — Coverage Intelligence**
- Decision: AWF-015 planner backend 已完成，下一步聚焦 AWF-017c coverage map UI（click-to-enqueue）
- Execution order: AWF-017c → (AWF-016 + AWF-017d)
- Next action: Implement coverage matrix UI with tested/untested states and one-click enqueue to batch queue
- AWF-002b/AWF-006: deferred until baseline runs show D1 or D2 pass (11 windows all D3-only)
- Gate A status: passed at commit `524f837`
- Gate D status: passed at commit `a147972`

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
| 2026-02-07 | AWF-008, AWF-002b, AWF-006 | e2e_baseline_window2 | Executed second real-data two-pass sweep with non-empty OOS segments under `artifacts/runs/20260207_161041`; `trigger_decision.json` shows D1/D2/D3 all false, so AWF-002b/AWF-006 remain deferred. Also fixed runtime config loader to accept UTF-8 BOM to prevent accidental fallback to default config. | Run third baseline on a different market window (timeframe/days) and compare trigger stability across windows before changing ranking logic | pending |
| 2026-02-07 | AWF-008, AWF-002b, AWF-006 | e2e_baseline_window3 | Executed third two-pass sweep under `artifacts/runs/20260207_172457` (temporary config: `1h/300d`, `combo_segment_size=20`, `top_n_refine=20`, then restored baseline config). Trigger stayed `false` with D1/D2/D3 all false and OOS segments=2, but refine pass processed `0/0` additional combos (comparison deltas all 0), so this run is not sufficient to judge refine-stage ranking uplift. | Run next baseline with settings that force non-zero refine candidate execution, then re-check trigger on that evidence | pending |
| 2026-02-07 | AWF-008 | baseline_guard | Added baseline run guardrail: pass snapshots now include `run_total/run_done/run_skipped/run_stage` from `run_status.json`, and refine `run_total=0` emits a warning in stdout + manifest. | Use this signal to reject non-informative refine runs when evaluating AWF-002b/AWF-006 trigger evidence | pending |
| 2026-02-08 | AWF-008 | refine_candidate_fix | Fixed refine candidate starvation on low-frequency windows: refine path now reuses activity fallback logic, and `min_avg_daily_trades_target` / `min_oos_trades_target` are configurable from `sweep_config.json` (defaults unchanged). | Run baseline with lowered activity floor to verify refine executes non-zero candidates and compare trigger outcome | pending |
| 2026-02-08 | AWF-008, AWF-002b, AWF-006 | e2e_baseline_window4 | Executed baseline under `artifacts/runs/20260208_034213` (temporary config: `1h/300d`, `combo_segment_size=20`, `top_n_refine=20`, `min_avg_daily_trades_target=0.1`, restored afterward). Refine executed `486/486` (non-zero), comparison became informative, and trigger stayed `false` (D1=false, D2=false, D3=true). | Add one more non-zero-refine window to confirm trigger stability before enabling AWF-002b/AWF-006 | pending |
| 2026-02-08 | AWF-008, AWF-002b, AWF-006 | e2e_baseline_window5 | Executed baseline under `artifacts/runs/20260208_055709` (temporary config: `4h/365d`, `combo_segment_size=10`, `top_n_refine=20`, `min_avg_daily_trades_target=0.1`, restored afterward). Refine executed `1107/1107` (non-zero), comparison remained informative (`delta_avg_oos_return_pct=+0.2482`), and trigger stayed `false` with D3-only (`D1=false`, `D2=false`, `D3=true`). | Run one more non-zero-refine window with stricter activity floor to test whether persistent D3 is data-regime noise or ranking-quality signal before AWF-002b/AWF-006 decision | pending |
| 2026-02-08 | AWF-008, AWF-002b, AWF-006 | e2e_baseline_window6 | Executed strict-floor baseline under `artifacts/runs/20260208_081420` (temporary config: `4h/365d`, `combo_segment_size=10`, `top_n_refine=20`, `min_avg_daily_trades_target=1.0`, restored afterward). Refine still executed `5508/5508` (non-zero), comparison remained informative (`delta_avg_oos_return_pct=+0.0512`), and trigger remained `false` with persistent D3-only (`D1=false`, `D2=false`, `D3=true`). | Keep AWF-002b/AWF-006 deferred; run one targeted different market window (or symbols mix) to confirm whether D3 persistence is structural before any ranking-logic change | pending |
| 2026-02-08 | AWF-ALL | plan_revised | Shifted to platform mindset: AUTOWFO is a reusable strategy-exploration tool, not a one-off script. Correctness and extensibility prioritized over speed. | Reactivated Phase 2 (Protocol Freeze) as next focus: AWF-003 → AWF-002 → AWF-004 → AWF-001. Added AWF-013 (parallelization) to backlog. Promoted AWF-009/010 to P1. Updated AGENTS.md principles. AWF-002b/006 remain evidence-gated. | Start AWF-003 | pending |
| 2026-02-08 | AWF-003 | done | Completed strategy schema freeze: added `plans/protocols/strategy_schema.json`, added `scripts/autowfo/strategy_schema.py` validator/loader, and switched constants to schema-backed metadata maps with fail-fast validation on invalid specs. Added schema tests including invalid-spec rejection and module fail-fast behavior. | Move to AWF-002 metric-contract extraction and freeze | pending |
| 2026-02-08 | AWF-002 | done | Completed metric contract freeze: added `plans/protocols/metric_contract.yaml` and `scripts/autowfo/metric_contract.py`, wired `metrics.py` to load/validate frozen metric sections, and added fail-fast + contract coverage tests. Also fixed empty-OOS output consistency by always emitting `oos_avg_daily_trades`. | Move to AWF-004 artifact contract extraction and reproducibility metadata freeze | pending |
| 2026-02-08 | AWF-004 | done | Completed artifact contract freeze: added `plans/protocols/artifact_contract.yaml` and `scripts/autowfo/artifact_contract.py`, wired `artifacts.py` to enforce required run-metadata fields, and added deterministic config/data hash helpers. Sweep now emits `config_sha256` + `data_fingerprint` into combo/symbol/leaderboard outputs and writes `run_metadata.json` plus run-scoped metadata snapshot. | Move to AWF-001 split protocol extraction and freeze | pending |
| 2026-02-08 | AWF-001 | done | Completed split protocol freeze: added `plans/protocols/split_protocol.yaml` and `scripts/autowfo/split_protocol.py`, wired `split.py` to load/validate supported mode and positive horizon constraints, and added fail-fast/contract tests. Existing walk-forward slice outputs remain behavior-compatible for default anchored mode. | Run Gate A checklist and record protocol freeze commit hash | pending |
| 2026-02-08 | AWF-ALL | gate_a_passed | Gate A checklist satisfied after finishing AWF-003/AWF-002/AWF-004/AWF-001 and validation suite. | Protocol frozen at commit `524f837`; phase focus moves to Phase 3 with AWF-013 as next task. | 524f837 |
| 2026-02-08 | AWF-013 | doing | Implemented parallel combo evaluation core: extracted pure evaluator (`scripts/autowfo/evaluator.py`), added `ProcessPoolExecutor` runner (`scripts/autowfo/parallel.py`), and enabled `max_workers` config path for combo mode with centralized IO/checkpointing in main process. Added deterministic equivalence test for 3-worker vs single-thread outputs. | Run targeted performance benchmark on representative window to confirm/quantify speedup versus single-thread and finalize AWF-013 exit criteria | pending |
| 2026-02-08 | AWF-013 | done | Added benchmark harness `scripts/run_autowfo_parallel_benchmark.py`, tuned worker IPC payload/chunking, and re-ran benchmark matrix. Latest heavy-profile evidence: `artifacts/benchmarks/awf013_parallel_benchmark_20260209_000935.json` with `speedup=2.6641` and `bit_identical=true` (3-worker vs single-thread). | Move to AWF-009 run registry implementation | pending |
| 2026-02-09 | AWF-009 | done | Implemented run registry module `scripts/autowfo/registry.py` and integrated it into sweep finalize flow. Each run now updates `artifacts/run_registry.json` with run index and coverage map including `tested_pairs` and `untested_pairs` across timeframe×symbol space. Baseline archiving now copies `run_registry.json`. | Move to AWF-010 one-command execution entrypoint | pending |
| 2026-02-09 | AWF-010 | done | Implemented one-command AUTOWFO entrypoint package (`autowfo`) with `run`/`baseline` subcommands, config loader (JSON/YAML + UTF-8 BOM), runtime `artifacts/sweep_config.json` materialization, and subprocess orchestration into existing sweep/baseline modules. Added CLI tests and verified command help paths. | Run next non-zero-refine baseline window and re-check AWF-002b/AWF-006 trigger conditions | pending |
| 2026-02-09 | AWF-008, AWF-002b, AWF-006 | e2e_baseline_window7 | Executed baseline using `python -m autowfo baseline --config artifacts/sweep_config_window7.json` (temporary config: `2h/240d`, `combo_segment_size=20`, `top_n_refine=20`, `min_avg_daily_trades_target=0.1`). Refine executed `729/729` (non-zero), comparison stayed informative (`delta_avg_oos_return_pct=+0.0978`, `delta_avg_oos_segments=+0.70`), and trigger remained `false` with D3-only (`D1=false`, `D2=false`, `D3=true`). Output archived at `artifacts/runs/20260209_110250`. | Keep AWF-002b/AWF-006 deferred; run next targeted symbol-mix window to verify whether D3 persistence is structural before ranking-logic changes | pending |
| 2026-02-09 | AWF-008, AWF-002b, AWF-006 | e2e_baseline_window8_symbols | Executed targeted symbol-mix baseline using `python -m autowfo baseline --config artifacts/sweep_config_window8_symbols.json` (temporary config: `2h/240d`, `ETH/USDT+BNB/USDT+SOL/USDT`, `combo_segment_size=20`, `top_n_refine=20`, `min_avg_daily_trades_target=0.1`). Refine executed `2268/2268` (non-zero), comparison remained informative (`delta_avg_oos_return_pct=+0.7033`, `delta_avg_oos_min_total_trades=+6.20`), and trigger still remained `false` with D3-only (`D1=false`, `D2=false`, `D3=true`). Output archived at `artifacts/runs/20260209_124307`. | Keep AWF-002b/AWF-006 deferred; run next higher-frequency window to test whether D3 persistence is timeframe/split-granularity driven | pending |
| 2026-02-09 | AWF-008 | e2e_baseline_window9_hf_fail | First high-frequency run (`artifacts/sweep_config_window9_hf.json`) failed during refine with `KeyError: 32` in `strategy._apply_indicator_combo` (`volume_zscore_by_lb` missing expanded lookback). Partial artifacts archived at `artifacts/runs/20260209_140004` (combo complete, refine aborted). | Add evaluator-side lookback coercion + regression test, then rerun same window | pending |
| 2026-02-09 | AWF-008 | bugfix_refine_lookback_coercion | Fixed refine lookback overflow by coercing indicator params in evaluator before applying combo logic; added regression test `tests/test_autowfo_evaluator.py` validating `volume_lookback 32 -> 28` nearest-key fallback. | Re-run failed high-frequency baseline window to validate end-to-end stability | cf56d0a |
| 2026-02-09 | AWF-008, AWF-002b, AWF-006 | e2e_baseline_window9_hf_rerun | Re-ran `python -m autowfo baseline --config artifacts/sweep_config_window9_hf.json` after bugfix. Both passes succeeded with non-zero workloads (`combo=9600`, `refine=5481`), comparison remained informative (`delta_avg_oos_return_pct=+1.5771`, `delta_avg_oos_segments=+0.5`), and trigger still remained `false` with D3-only (`D1=false`, `D2=false`, `D3=true`). Output archived at `artifacts/runs/20260209_145335`. | Keep AWF-002b/AWF-006 deferred; run one longer-horizon high-frequency window to determine whether D3 persistence is horizon-driven | pending |
| 2026-02-09 | AWF-008, AWF-002b, AWF-006 | e2e_baseline_window10_hf_long | Executed longer-horizon high-frequency baseline using `python -m autowfo baseline --config artifacts/sweep_config_window10_hf_long.json` (temporary config: `1h/300d`, USDT symbol mix). Both passes remained non-zero (`combo=9600`, `refine=5508`), comparison stayed informative (`delta_avg_oos_return_pct=+0.2722`, `delta_avg_oos_min_total_trades=+1.97`), and trigger still remained `false` with persistent D3-only (`D1=false`, `D2=false`, `D3=true`). Output archived at `artifacts/runs/20260209_160500`. | Treat D3 persistence as non-trigger evidence (D1/D2 unchanged); keep AWF-002b/AWF-006 deferred and move next effort to AWF-011 regression guardrails | pending |
| 2026-02-09 | AWF-011 | done | Added split/ranking regression invariants: split default-vs-explicit mode equivalence, slice-count horizon formula, monotonic boundary checks, non-int horizon rejection, ranking fallback score selection when preferred metric missing/NaN, ranking sort without hold-hour tie-break field, and Top-N fallback ordering checks. | Move to AWF-012 operational playbook while keeping AWF-002b/AWF-006 evidence-gated | pending |
| 2026-02-09 | AWF-012 | done | Added notebook-free operational playbook `plans/AUTOWFO_RUNBOOK.md` covering preflight checks, CLI run patterns (`python -m autowfo run` / `baseline`), artifact map, trigger interpretation, failure handling, and post-run checklist. | Execute Gate D checklist and keep AWF-002b/AWF-006 deferred until D1/D2 trigger conditions are met | pending |
| 2026-02-10 | AWF-ALL | gate_d_passed | Completed Gate D sign-off: regression suite green and runbook available; no unresolved critical drift issues identified in latest session log review. | Continue evidence-window collection and keep AWF-002b/AWF-006 trigger-gated on D1/D2 thresholds | a147972 |
| 2026-02-10 | AWF-008, AWF-002b, AWF-006 | e2e_baseline_window11_quick | Executed quick baseline using `python -m autowfo baseline --config artifacts/sweep_config_window11_quick.json` (`4h/180d`, `ETH/USDT+SOL/USDT`, `combo_segment_size=8`, `top_n_refine=12`). Both passes were non-zero (`combo=3840`, `refine=702`), comparison remained informative (`delta_avg_oos_return_pct=+1.2267`, `delta_avg_oos_drawdown_pct=-0.0734`, `delta_avg_oos_min_total_trades=+0.85`), and trigger remained `false` with D3-only (`D1=false`, `D2=false`, `D3=true`). Output archived at `artifacts/runs/20260210_013015`. | Keep AWF-002b/AWF-006 deferred and continue cross-window evidence collection focused on D1/D2 emergence | pending |
| 2026-02-10 | AWF-014, AWF-015, AWF-016 | plan_revised | Added Automation Loop phase (Phase 3.5): AWF-014 batch runner, AWF-015 coverage planner, AWF-016 cross-run dashboard. Focus shifted from passive evidence collection to building automation infrastructure for unattended batch execution and systematic coverage expansion. | Start AWF-014 batch runner implementation | pending |
| 2026-02-10 | AWF-017a/b/c/d | plan_restructured | Full TODO restructure: (1) Consolidated 6+3.5 phases into clean 10-phase sequence, (2) Phases 1-4 marked complete with gate refs, (3) Added AWF-017a/b/c/d for control panel enhancement (architecture refactor + batch UI + coverage map UI + dashboard UI), (4) Phase 5 = panel refactor (prerequisite for all new UI), Phase 6-8 = backend+frontend paired delivery, Phase 9-10 = evidence-gated ranking/WFO, (5) Updated focus window to Phase 5. | Start AWF-017a — front/back separation, Tab navigation, CSS upgrade | 8eb4e90 |
| 2026-02-10 | AWF-017a | done | Implemented control panel architecture refactor: added file-based static frontend assets under `scripts/control_panel/static/` (`index.html`, `css/app.css`, modular JS `app.js` + `tabs.js`/`batch.js`/`coverage.js`/`dashboard.js`), switched backend `/` and `/static/*` to serve static files, and introduced Tab-based navigation scaffolding (`控制台/結果/覆蓋/儀表板/歷史`) without changing existing API endpoints. | Move to AWF-014 backend batch runner and AWF-017b queue UI implementation | pending |
| 2026-02-10 | AWF-014 | done | Implemented `autowfo batch` backend in `autowfo/cli.py`: plan parsing, preflight checks (config/cwd/disk), crash-safe resume via `artifacts/batch_state.json` seen-keys, and `--continue-on-error` flow. Added CLI tests for run/skip/preflight/error-continue paths (`tests/test_autowfo_cli.py`). | Start AWF-017b batch queue UI and API wiring on top of stable batch backend | pending |
| 2026-02-10 | AWF-017b | done | Implemented control-panel batch queue flow: backend APIs (`/batch/queue.json`, `/batch/enqueue`, `/batch/start`, `/batch/cancel`, `/batch/clear`, `/batch/remove`) wired to `autowfo batch` + `artifacts/batch_state.json`; frontend batch tab now provides enqueue/start/cancel/clear, live queue table, and log tail refresh. Added queue backend tests in `tests/test_control_panel.py`. | Move to AWF-015 planner backend and AWF-017c coverage map scheduling UI | pending |
| 2026-02-10 | AWF-015 | done | Implemented coverage planner backend in `autowfo plan`: reads `run_registry.json` untested pairs, generates per-gap config files, and writes executable batch plan (`--max-jobs`, `--workflow`, `--mode`, `--workers`) for direct `autowfo batch` consumption. Added CLI tests for plan generation and empty-gap behavior. | Move to AWF-017c coverage map UI with click-to-enqueue integration | pending |
