# AUTOWFO Master Plan

## Objective
Build a long-term, reproducible, and automation-first **platform** for systematically
exploring the strategy-indicator space using time stacking (walk-forward style),
not one-off best-parameter picks. Users will repeatedly run it with different
indicators, symbols, and time windows to discover robust combinations.

## North Star
- Primary outcome: improve out-of-sample robustness, not in-sample peak performance.
- Definition of success: strategy selection process that is reproducible, explainable, and resistant to time-regime drift.

## Scope
- In scope:
  - Time-stacked evaluation (range/rolling/expanding splits).
  - Automated parameter and indicator-combination search.
  - In-sample selection and out-of-sample validation.
  - Stability-first ranking across splits and symbols.
  - Reproducible experiment outputs (artifacts and metadata).
- Out of scope (initially):
  - Live trading execution infrastructure.
  - Exchange-specific order routing.
  - Full AutoML/Bayesian orchestration across external clusters.

## Architectural Direction
- **Platform mindset**: AUTOWFO is a reusable strategy-exploration tool; correctness first, extensibility second, speed third.
- Keep vectorbt core simulation and indicator engines as compute primitives.
- Add orchestration layer on top (AUTOWFO) rather than forcing major core refactors.
- Treat each run as an experiment with fixed seed, dataset snapshot, config, and metrics.
- ~~Decompose monolith first~~: **completed** (AWF-000, commit `c059646`). Runtime modules now live in `autowfo/`.

## Current Implementation Reality
> Updated 2026-03-14. Runtime modules converge under `autowfo/`; packaged control panel lives in `autowfo/control_panel/`; mutable experiment, scheduler, paper, and analytics stores carry explicit schema-version contracts plus operator-facing validation/migration/rebuild tooling. New operational risk discovered on 2026-03-14: root-level `artifacts/` run outputs can lose single-run provenance when reused as a shared workspace, so evidence-integrity reset is now the active focus. Gates A+D remain passed.

| Component | Status | Quality | Key Gap |
|---|---|---|---|
| Walk-forward eval | Modular (`split.py` + protocol) | True-WFO enabled (`anchored` + `rolling`) + 3-way split | `valid_days=0` default (backward-compatible); validation segment ready for use |
| IS/OOS metrics (8+15) | Modular (`metrics.py` + contract) | Upgraded | Sharpe-like/stability/low-trade penalty metrics added (AWF-002b complete) |
| Indicator framework (25) | Schema-backed (`strategy_schema.py`) | Expanded | 13->25 indicators; C(25,2..4) = 15,250 combos |
| Regime logic (8 types) | Schema-backed | Frozen | Adding regimes is config-only |
| Combo search (15,250+) | Modular (`search.py` + `pruning.py`) | Intelligent pruning | PruningTracker: per-indicator score tracking, adaptive threshold, warm-start, budget cap, batch dispatch |
| Two-stage search | combo/refine modes | Working | AWF-008 done |
| Ranking | Modular (`ranking.py`) | Upgraded | Composite score default + legacy mode preserved + config-driven weights; paired comparison report pipeline ready (AWF-006/007 complete) |
| Artifacts (CSV/DB/HTML) | Reproducible (`artifacts.py` + contract) | Frozen | Config hash + data fingerprint included |
| Parallel evaluation | 3-worker (`parallel.py`) | x2.66 speedup | Bit-identical verified |
| Run registry | (`registry.py`) | Working | Coverage map across timeframe/symbol |
| CLI entrypoint | `python -m autowfo` | Working | `run` + `baseline` + `batch` + `plan` + `report` subcommands |
| Regression tests | 87 tests / 18 files | Green | Split + ranking invariants covered |
| Operational runbook | `AUTOWFO_RUNBOOK.md` | Complete | Preflight/run/post-run checklist |
| Web control panel | Static tabs + batch + coverage + dashboard/history | Complete (Phase 8) | Next gap is ranking-quality upgrades (AWF-002b/006) now immediate |

## Milestones

### Phase 1: Decompose (AWF-000) [Done]
- Extracted 10 modules from 3000-line monolith into the AUTOWFO runtime package (now `autowfo/`).
- Bit-identical artifact output verified.
- Linked TODO: `AWF-000`.

### Phase 2: Protocol Freeze (AWF-003/002/004/001) [Done]
- Strategy schema, metric contract, artifact contract, split protocol frozen with JSON/YAML specs.
- Gate A passed at commit `524f837`.
- Linked TODO: `AWF-003`, `AWF-002`, `AWF-004`, `AWF-001`.

### Phase 3: Scale & Experiment Management (AWF-013/009/010) [Done]
- Multi-process parallelization (x2.66 speedup, bit-identical).
- Run registry with timeframe/symbol coverage map.
- CLI entrypoint (`python -m autowfo run|baseline|batch|plan|report|repro|gate-c`).
- Linked TODO: `AWF-013`, `AWF-009`, `AWF-010`.

### Phase 4: Quality Guardrails (AWF-011/012) [Done]
- Regression test suite (87 tests, 18 files).
- Operational runbook (`plans/AUTOWFO_RUNBOOK.md`).
- Gate D passed at commit `a147972`.
- Linked TODO: `AWF-011`, `AWF-012`.

---

### Phase 5: Control Panel Architecture Refactor (AWF-017a) [Done]
- Restructure 2250-line single-file control panel into maintainable architecture.
- Front/back separation: Python API backend + `static/` HTML/JS/CSS assets.
- Tab-based navigation (Overview / Config / Results / Batch / Coverage / Dashboard).
- Lightweight CSS framework for consistent styling.
- Prerequisite for all Phase 6-8 UI work.
- Linked TODO: `AWF-017a`.

### Phase 6: Batch Execution (AWF-014 + AWF-017b) [Done]
- Batch runner backend: `autowfo batch --plan batch_plan.json`, preflight checks, crash-safe resume.
- Batch queue UI: enqueue/start/cancel buttons, per-job status/progress, live refresh.
- Exit criteria: queue 3 configs from browser -> batch runs unattended -> registry accumulates.
- Linked TODO: `AWF-014`, `AWF-017b`.

### Phase 7: Coverage Intelligence (AWF-015 + AWF-017c) [Done]
- Coverage planner backend: `autowfo plan` reads registry gaps, generates batch plan.
- Coverage map UI: color-coded timeframe/symbol matrix, click-to-enqueue.
- Exit criteria: planner output feeds directly into batch queue; visual gap identification.
- Linked TODO: `AWF-015`, `AWF-017c`.

### Phase 8: Cross-Run Insight (AWF-016 + AWF-017d) [Done]
- Cross-run dashboard backend: `autowfo report` producing aggregate analysis.
- Dashboard UI: run history table, combo stability timeline, global leaderboard.
- Exit criteria: >=3 runs produce meaningful stability trend visualization from browser.
- Linked TODO: `AWF-016`, `AWF-017d`.

### Phase 9: Ranking Upgrade Immediate (AWF-002b/006/007)
- Sharpe + stability scoring, composite ranking function, legacy vs composite paired comparison.
- Governance change: D1/D2/D3 repurposed as health-monitoring indicators, no longer activation gates.
- Rationale: 13 baseline windows persistently D3-only proves single-metric ranking pushes low-trade combos
  to top; this is itself the strongest evidence that ranking upgrade is needed.
- AWF-002b: Added `oos_sharpe_like`, `oos_return_std`, `oos_positive_segment_ratio` plus low-trade penalty fields to metrics + contract.
- AWF-006: Composite score = return + stability + risk-adjust drawdown penalty low-sample penalty.
  Legacy mode preserved for A/B comparison, default switched to composite, weights configurable in `sweep_config.json`.
- AWF-007: Same-window paired comparison (legacy vs composite) implemented in baseline workflow with fixed-format JSON/HTML report;
  includes 3-axis diagnostic: strategy quality / sample sufficiency / combo scarcity.
- Gate B checklist must pass before Phase 10.
- Linked TODO: `AWF-002b`, `AWF-006`, `AWF-007`.

### Phase 10: Advanced Modes (AWF-001b/005) [Done]
- True WFO mode (per-window re-optimization).
- Full engine refactor using modular pipeline (391-line thin orchestrator + 4590-line engine).
- Gate C reproducibility checks passed at commit `cfe3c8a`.
- Linked TODO: `AWF-001b`, `AWF-005`.

---

### Phase 11: Engine Health + Operational Maturity (AWF-018/019/020)
- Engine secondary decomposition: split 4590-line `engine.py` into ~5 responsibility-scoped sub-modules (~1200 lines each).
- Coverage gap fill: expand tested pairs from 5 to 9 (1h/2h/4h x ETH/BNB/SOL) using existing plan/batch toolchain.
- Baseline strategy benchmarks: add buy-and-hold + random-entry reference rows to cross-run leaderboard.
- Rationale: engine bloat is the #1 tech-debt risk; coverage is too thin for meaningful cross-run analysis; leaderboard lacks alpha baseline.
- Exit criteria: engine sub-modules are split by responsibility with bit-identical output; coverage 9/9; leaderboard includes BH/random benchmarks.
- Linked TODO: `AWF-018`, `AWF-019`, `AWF-020`.

### Phase 12: Strategy Universe Expansion + Smart Search (AWF-021/022/023/024)
- Validation set 3-way split: train/validation/test protocol to eliminate hyperparameter overfitting.
- Indicator universe expansion: 13->25 indicators (done: CCI, Williams %R, ADX, TRIX, DPO, EFI, VWMA, UltOsc, Keltner, Donchian, PPO, Choppiness).
- Combo intelligent pruning: early-stopping + warm-start from prior top-N to handle C(25,2..4) 15,000+ combos.
- Cross-timeframe parallel execution: batch-level parallelism via `--parallel-jobs N` in `autowfo batch` (ThreadPoolExecutor + subprocess).
- Prerequisite: AWF-018 engine decomposition complete before modifying search/indicator modules.
- Exit criteria: search space >15,000 combos; pruning materially reduces wall-time; 3-way split validated.
- Linked TODO: `AWF-021`, `AWF-022`, `AWF-023`, `AWF-024`.

### Phase 13: Decision Intelligence + Continuous Operation (AWF-025/026/027/028)
- Combo stability trend analysis: time-series per-combo visualization across run windows.
- Regime-aware ranking: conditional scoring by market regime with per-regime leaderboard views.
- Automated patrol cycle: `autowfo cron` for daily plan/batch/report with messaging alerts.
- Experiment notebook export: auto-generate reproducible `.ipynb` per run.
- Exit criteria: dashboard shows actionable trends; daily cycle runs unattended; each run is self-documenting.
- Linked TODO: `AWF-025`, `AWF-026`, `AWF-027`, `AWF-028`.

### Phase 14: Production Hardening + End-to-End Verification (AWF-030/031/032) COMPLETE
- Gate E closure: verify engine decomposition bit-identical artifacts + changelog commit. 
- End-to-end smoke test: lightweight synthetic pipeline integration test covering full engine path. (11 tests, 4 seams)
- Cron patrol validation: full patrol cycle state tracking and report output verification. (5 tests)
- Exit criteria: Gate E signed off; e2e smoke test automated; patrol cycle validated. **All met.**
- Linked TODO: `AWF-030`, `AWF-031`, `AWF-032`.

### Phase 15: UI Redesign Trading-Terminal Style (AWF-033/034/035/036/037/038) [Complete]
- Complete control panel UI rewrite with dark-themed trading terminal aesthetics.
- Tech stack: Vue 3 (ESM CDN, no build step) + Tailwind CSS (Play CDN) + Chart.js.
- 6 tabs: Overview, Config, Results, Batch, Coverage, Analytics.
- Zero backend changes: all 35 API endpoints unchanged; pure static file replacement.
- Old UI preserved in `autowfo/control_panel/static_legacy/` for fallback.
- Prerequisite: Phase 14 complete (all gates passed, 347 tests green).
- **Progress (2026-02-19):**
  - AWF-033 Vue 3 + Tailwind CDN + dark theme + CSS variables + i18n + store + api + components complete
  - AWF-034 6-tab navigation + top nav bar + logo + theme toggle
  - AWF-035 Overview KPI + Config dropdown/chips + Results filters/charts/Top10 dedup/freshness/retest
  - AWF-036 Batch Queue enqueue/start/cancel/clear + status badges + log panel
  - AWF-037 Coverage heatmap + Dashboard KPI/leaderboard/combo stability/regime/timeline
  - AWF-038 done toast | skeleton | modal | tab-transition | error-boundary - Exit criteria: all original features work in new UI; dark/light theme toggle; responsive layout; professional UX.
- Linked TODO: `AWF-033`, `AWF-034`, `AWF-035`, `AWF-036`, `AWF-037`, `AWF-038`.

### Phase 16: Continuous Loop Upgrades (AWF-039~AWF-105) ??DONE
> Goal: Evolve the control panel into a closed-loop strategy-operations platform.
- AWF-039~042: OHLCV freshness automation, cron notifications, top-config export, Monte Carlo analytics.
- AWF-043~051: Paper-feedback loop (summary / diagnostics / recommendations / adjusted-batch enqueue) + i18n consolidation.
- AWF-052~063: Dashboard reliability hardening ??fallback contracts, schema versioning, request correlation, incident timeline, ops filters/export.
- AWF-064~105: Cross-run payload normalization, error-code taxonomy, request_id correlation, error-event persistence + query/retention/pagination, ops controls, config walk-forward guardrail.
- Status: **Complete**. All 66 AWFs done; archived in `plans/AUTOWFO_TODO_ARCHIVE.md`.

### Phase 17: Re-run Correctness + Top10 Accuracy (AWF-106/107/108) ??DONE
> Goal: Fix two structural correctness bugs uncovered by production observation ??seen_keys are always fully invalidated on re-run (causing full re-evaluation every time), and the Results Top10 display shows only the latest run rather than the historical best.
- **AWF-106 (P1): `stripped_seen_keys` architectural fix.** ??
  Root cause: `combo_key` includes `data_start` and `data_end` fields (part of the 57-field `combo_key_fields` list in `engine_helpers.py::_build_sweep_schema_fields`). `_load_or_update_symbol()` appends fresh OHLCV candles on every run ??`data_end` advances ??all 15,250 seen_keys built from the previous CSV use the old `data_end` ??none match new combo_keys ??0 skips ??full re-evaluation.
  Fix: `_build_seen_keys()` returns both `full_seen_keys` (with `data_start`/`data_end`, for artifact tracking) and `stripped_seen_keys` (without data-range fields, for skip decisions). Engine search skip check uses `stripped_seen_keys`. CSV output format is unchanged.
- **AWF-107 (P1): Top10 dual-path display.** ??
  Root cause: `_get_results_payload()` uses `_latest_top10_path()` (mtime-based glob ??latest `param_sweep_top10_*.csv`) as its primary source; `_pick_top10(combo["rows"])` from the full 45k-row `combo_summary.csv` (which contains the true historical best) only runs as fallback when the latest file is empty.
  Fix: promote `_pick_top10(combo["rows"])` from full combo_summary.csv to primary `top10` key; expose the latest-run file as a separate `top10_latest_run` key. `results.js` adds a toggle button: ?甇瑕?雿喋s?甈∠??? New test `test_get_results_payload_top10_dual_path` validates payload contract.
- **AWF-108 (P2): Performance micro-optimisations.** ??
  (a) Progress emit throttle ??emit only every 200 consecutive skips (via `_skip_emit_count` counter in `_run_parallel_combo_search_for_timeframe`) to reduce WebSocket/print overhead.
  (b) `_build_seen_keys` vectorization ??replaced `iterrows()` with `to_dict(orient='records')` for 5-10x speedup on large DataFrames.
  (c) `checkpoint_every_n` and `progress_every_n` added to `DEFAULT_CONFIG` and wired through `run_btc_regime_sweep.py` ??`_build_run_lifecycle_callbacks()` for runtime-configurable tuning.
- Prerequisite: Phase 16 complete (AWF-105 done). ??
- Exit criteria: second run with same config skips all previously evaluated combos; Results Top10 defaults to all-time best combo; performance micro-opts verified with regression tests. ??**147 tests passing.**
- Linked TODO: `AWF-106`, `AWF-107`, `AWF-108`.

### Phase 18: Technical Debt Reduction (AWF-109嚚WF-117)
> Goal: Fix two confirmed correctness bugs and reduce structural debt before UX work begins.
- **Two confirmed bugs (fix first):**
  - AWF-109: `control_panel.DEFAULT_CONFIG` diverged from `engine_helpers.DEFAULT_CONFIG` by 8 keys (`ranking`, `wf_valid_days`, `wf_mode`, `min_avg_daily_trades_target`, `min_oos_trades_target`, `max_workers`, `progress_every_n`, `checkpoint_every_n`). UI generates incomplete configs silently.
  - AWF-110: Control panel Run button calls `run_btc_regime_sweep.py` directly, bypassing `python -m autowfo` ??all AWF-105/106/107/108 CLI guards (walk-forward validation, stripped_seen_keys, Top10 dual-path, progress throttle) are inactive for single runs.
- AWF-111/112: Cross-platform PYTHON path cleanup; constants.py UTF-8 normalization.
- AWF-113: control_panel.py secondary decomposition (5715L ??8 responsibility-scoped modules ??00L each, `ProcessManager` class replaces 6 global locks/variables). Same pattern as AWF-018 engine decomposition.
- AWF-114: cli.py secondary decomposition (2072L ??5 command modules ??00L).
- AWF-115/116: engine.py stops re-exporting private symbols; sys.path manipulation eliminated.
- AWF-117: Document archive ??AWF-000嚚?63 moved to `plans/AUTOWFO_TODO_ARCHIVE.md`.
- Prerequisite: Phase 17 complete. ??
- Exit criteria: AWF-109/110 bugs fixed; control_panel.py decomposed; all 1291 tests green.
- Linked TODO: `AWF-109`, `AWF-110`, `AWF-111`, `AWF-112`, `AWF-113`, `AWF-114`, `AWF-115`, `AWF-116`, `AWF-117`.

### Phase 19: UX / Operational Flow Redesign (AWF-118嚚WF-124)
> Goal: Redesign control panel from technical-module layout to user-workflow layout.
> Core insight: current 6-tab layout mirrors system internals. User mental model is: **Config ??Run ??Results ??Fill Gaps ??Repeat**. Each step currently requires a different tab with no guided flow between them.
- AWF-118: Config instant validation ??`wf_step_days < wf_test_days` visible before save.
- AWF-119: Quick Test panel relocation ??pytest runner moved out of Overview into Config (collapsed).
- AWF-120: Overview as Operations Hub ??smart next-action guidance card + last-run KPI summary after each run.
- AWF-121: Unified execution entry point ??single Start button with mode selector (combo/refine/fill-gaps/patrol); removes three-button ambiguity.
- AWF-122: Coverage one-click gap fill ??plan + enqueue + start via single `/coverage/fill-all-gaps` endpoint.
- AWF-123: Results "Refine This Combo" shortcut ??top combo ??refine config in 2 clicks.
- AWF-124: Dashboard auto-update on run complete ??async report regeneration; no manual Generate Report.
- Prerequisite: Phase 18 AWF-109/110 complete (correct execution paths before UX redesign).
- Exit criteria: full backtest loop (Config ??Run ??Results ??Coverage ??Dashboard) completable without leaving Overview for routine operations; all 1291 tests green.
- Linked TODO: `AWF-118`, `AWF-119`, `AWF-120`, `AWF-121`, `AWF-122`, `AWF-123`, `AWF-124`.

### Phase 20: Cross-Asset Foundation ??Plugin System & Experiment Model
> Goal: Replace monolithic strategy schema with extensible indicator plugin system and introduce the Experiment as the fundamental testable unit.
> Architecture spec: `plans/AUTOWFO_ARCHITECTURE_V2.md` (approved 2026-02-27).
- AWF-125: Indicator plugin system (`scripts/autowfo/indicators/` auto-discovery directory, 5 built-in indicators: RSI, MACD, BB, EMA, Volume). Each plugin implements `INDICATOR_ID`, `PARAMS`, `CONDITION_OPERATORS`, and `compute(ohlcv_df, params) -> Series`.
- AWF-126: Condition operator library (`scripts/autowfo/conditions/` with 4 modules: threshold, crossover, band, momentum ??8 operators total).
- AWF-127: Experiment definition model (`scripts/autowfo/experiment.py`): JSON schema for trigger/action/risk/wf layers, validation, parameter grid expansion via `itertools.product()`.
- AWF-128: New artifact directory structure (`artifacts/experiments/{exp_id}/runs/{timestamp}/results.db + run_meta.json`); existing combo_summary.csv artifacts remain untouched.
- AWF-129: Experiment CRUD API + control panel backend (`control_panel_experiments.py`): create, list, load, delete experiments; queue single experiment run.
- Prerequisite: Phase 19 complete. AWF-113~116 (decomposition debt) deferred to parallel housekeeping.
- Exit criteria: Can define an experiment via JSON, load it, expand parameter grid, validate trigger+action config, and write to experiment artifact directory. Unit tests covering indicator compute, condition operators, experiment validation, and grid expansion all green.

### Phase 21: Signal Composer ??Cross-Asset / Cross-Timeframe Execution
> Goal: Multi-asset, multi-timeframe signal generation integrated with vectorbt.
- AWF-130: `signal_composer.py`: cross-timeframe alignment algorithm (for each T2 candle close, scan preceding T2-window for any T1 signal). Handles both normal (T1 ??T2) and inverted (T1 > T2) cases.
- AWF-131: `experiment_runner.py`: wraps existing WFO engine for experiment-based execution. Accepts experiment config, fetches OHLCV for trigger/action assets, generates signals via signal_composer, passes to vectorbt `Portfolio.from_signals()`.
- AWF-132: Multi-asset data layer: extend `data.py` with multi-asset + multi-timeframe Parquet caching (`artifacts/ohlcv/binance_{ASSET}-{QUOTE}_{TF}.parquet`).
- AWF-133: Both-direction signal generation: experiments produce long + short entries independently; results tagged by direction; analytics compares direction win rates.
- Prerequisite: Phase 20 complete.
- Exit criteria: Full experiment run (trigger BTC 1h RSI ??action ETH 4h BB, both directions) produces verified signals and WFO results stored in SQLite per-run DB.

### Phase 22: Analytics Layer ??DuckDB Cross-Run Intelligence
> Goal: Two-layer storage with cross-experiment OLAP analytics.
- AWF-134: Per-run SQLite output from `experiment_runner.py` (WAL mode, `combo_results` table per spec in Architecture V2 禮4.3).
- AWF-135: `analytics.py`: DuckDB store (`artifacts/analytics.duckdb`), ingest from SQLite after each run, maintain indicator_effectiveness and all_time_best views.
- AWF-136: Post-run analytics hook in `engine_finalize.py`: call `analytics.update_from_run(experiment_id, run_id)` after run completes (non-blocking, async thread).
- AWF-137: Control panel analytics endpoints (`control_panel_analytics.py`): indicator leaderboard, asset pair matrix, condition win rates, time stability scores, search coverage map.
- Prerequisite: Phase 21 complete.
- Exit criteria: After 2+ experiment runs, DuckDB analytics queries return consistent aggregated results. Indicator leaderboard visible in control panel Analytics tab.

### Phase 23: Mode B Discovery + Scheduler
> Goal: Automated pool-based indicator exploration and experiment queue scheduling.
- AWF-138: Mode B pool expansion: C(N, 2..4) indicator combo generation from user-provided pool; integrates with `pruning.py` to manage search space.
- AWF-139: `scheduler.py`: experiment queue management, priority ordering (user-defined > discovery), nightly batch support (configurable schedule via `artifacts/scheduler.json`).
- AWF-140: Queue-driven execution: control panel Experiments tab can submit experiment to queue; scheduler runs unattended; Overview shows queue depth and next scheduled run.
- AWF-141: Discovery loop: scheduler auto-generates Mode B mini-experiments from indicator pool config, adds to queue, accumulates results into analytics.
- Prerequisite: Phase 22 complete.
- Exit criteria: Pool config runs end-to-end without user intervention; experiments queue and execute in priority order; analytics accumulates across all runs.

### Phase 24: Control Panel Experiments & Analytics UI
> Goal: Full control panel redesign with Experiments tab and Analytics tab.
- AWF-142: Experiments tab UI: list all experiments with status, last run, best OOS Sharpe; create form for Mode A (hypothesis) and Mode B (pool); experiment detail view with run history and best combos.
- AWF-143: Analytics tab UI: indicator leaderboard table, asset pair heatmap (trigger ? action), condition parameter distribution, time stability chart.
- AWF-144: Overview redesign: experiment-aware next-action suggestions ("3 experiments queued", "RSI appears in 80% of top combos"), queue depth KPI.
- AWF-145: End-to-end integration validation: create experiment ??queue ??run ??analytics updated ??results visible ??all from control panel UI without CLI.
- Prerequisite: Phase 23 complete.
- Exit criteria: Full discovery loop (define experiment ??run ??analyze ??discover new insights) completable entirely through control panel UI. All existing tests green.

### Phase 20 (Delivery Snapshot)
- Status: Complete
- Summary: Indicator plugin/condition library + experiment model + experiment artifacts + CRUD baseline landed.
- Linked AWFs: `AWF-125`, `AWF-126`, `AWF-127`, `AWF-128`, `AWF-129`.

### Phase 21 (Delivery Snapshot)
- Status: Complete
- Summary: Cross-asset data layer and signal composition integrated into experiment runner with dual-direction coverage.
- Linked AWFs: `AWF-130`, `AWF-131`, `AWF-132`, `AWF-133`.

### Phase 22 (Delivery Snapshot)
- Status: Complete
- Summary: Results consumption loop closed (SQLite read APIs) and DuckDB analytics foundation + endpoints established.
- Linked AWFs: `AWF-134`, `AWF-135`, `AWF-136`, `AWF-137`.

### Phase 23 (Delivery Snapshot)
- Status: Complete
- Summary: Mode-B pool discovery, scheduler queue, queue-driven execution, and idempotent discovery loop delivered.
- Linked AWFs: `AWF-138`, `AWF-139`, `AWF-140`, `AWF-141`.

### Phase 24 (Delivery Snapshot)
- Status: Complete
- Summary: Experiments/queue/discovery control-panel flows became operable via browser-facing UI integration.
- Linked AWFs: `AWF-142`, `AWF-143`, `AWF-144`, `AWF-145`.

### Phase 25 (Delivery Snapshot)
- Status: Complete
- Summary: Structural debt closure for control panel/CLI facades, engine export hygiene, and package-path cleanup.
- Linked AWFs: `AWF-113`, `AWF-114`, `AWF-115`, `AWF-116`.

### Phase 26 (Delivery Snapshot)
- Status: Complete
- Summary: Legacy monolith decomposition completed across control-panel/CLI/engine namespace consumers.
- Linked AWFs: `AWF-146`, `AWF-147`, `AWF-148`.

### Phase 27 (Delivery Snapshot)
- Status: Complete
- Summary: End-to-end lifecycle validation plus scheduler stop, discovery cold-start guard, and structured error codes.
- Linked AWFs: `AWF-149`, `AWF-150`, `AWF-151`, `AWF-152`.

### Phase 28 (Delivery Snapshot)
- Status: Complete
- Summary: E2E analytics readback gap fixed and Analytics tab UI delivered on existing analytics endpoints.
- Linked AWFs: `AWF-153`, `AWF-154`.

### Phase 29 (Delivery Snapshot)
- Status: Complete
- Summary: Real-data smoke validation, cron-scheduler integration, command-core split, and overview experiment awareness completed.
- Linked AWFs: `AWF-155`, `AWF-156`, `AWF-157`, `AWF-158`.

### Phase 30 (Delivery Snapshot)
- Status: Complete
- Summary: Full AUTOWFO/control-panel regression closure, signals module slimming, and documentation freeze baseline completed.
- Linked AWFs: `AWF-159`, `AWF-160`, `AWF-161`.

### Phase 31 (Delivery Snapshot)
- Status: Complete
- Summary: Cross-asset live validation, multi-round discovery burn-in, and manual discovery-loop acceptance tooling completed.
- Linked AWFs: `AWF-162`, `AWF-163`, `AWF-164`.

### Phase 32 (Delivery Snapshot)
- Status: Complete
- Summary: Discovery-to-experiment auto-mapping, full-auto scheduler patrol integration, and discovery/coverage observability surfaces delivered.
- Linked AWFs: `AWF-165`, `AWF-166`, `AWF-167`.

### Phase 33 (Delivery Snapshot)
- Status: Complete
- Summary: Patrol stability hardening, patrol-history and growth observability, and final regression/documentation closure delivered.
- Linked AWFs: `AWF-168`, `AWF-169`, `AWF-170`.

### Phase 34 (Delivery Snapshot)
- Status: Complete
- Summary: Patrol log rotation/timeout guardrails, real-data patrol dry-run validation tooling, CLI version/deprecation polish, and final operational regression closure.
- Linked AWFs: `AWF-171`, `AWF-172`, `AWF-173`.

---

### UI-1: Control Panel UX Overhaul (AWF-190~AWF-192)
> Goal: Modernize control panel navigation, component consistency, and visual polish without changing backend APIs.
> Motivation: 10-tab horizontal navigation overflows on narrow viewports; inconsistent styling/i18n across tabs; no loading states or user feedback on mutations.
- AWF-190: Sidebar navigation + responsive layout rebuild (horizontal tabs → collapsible icon sidebar, mobile breakpoints).
- AWF-191: Shared component library + i18n completion (KpiCard/StatusBadge/EmptyState/SearchInput/Pagination components; i18n 100% coverage audit).
- AWF-192: Page-level visual polish + micro-interactions (skeleton loading, toast feedback, Chart.js theme-aware colors, empty-state illustrations).
- Prerequisite: Steady State (Phase 39) — no backend changes required.
- Exit criteria: All 10 tabs render correctly with sidebar; shared components used consistently; i18n coverage ≥95%; loading/empty/error states present on all data-fetching views; all existing tests green.
- Linked TODO: `AWF-190`, `AWF-191`, `AWF-192`.

### Phase 40: Namespace and Packaging Convergence (AWF-193~AWF-198) [Done]
- Goal: converge AUTOWFO runtime and control panel into a single installable `autowfo.*` package surface.
- Runtime namespace: product imports now use `autowfo.*`; `scripts.autowfo.*` is no longer a supported package path.
- Control panel packaging: HTTP server and static assets now live under `autowfo/control_panel/` and start via `python -m autowfo.control_panel`.
- Packaging contract: distribution package discovery now includes only `vectorbt*` and `autowfo*`; control panel static assets ship as package data.
- Validation: import-surface cleanup, CLI/control-panel smoke checks, editable install, build smoke, and targeted regression suites completed before closure.
- Linked TODO: `AWF-193`, `AWF-194`, `AWF-195`, `AWF-196`, `AWF-197`, `AWF-198`.

### Phase 41: Service Boundary and Operations Hardening (AWF-199~AWF-204) [Done]
- Goal: make the packaged control panel operate as a configurable service runtime instead of a `cwd`-bound single-process script surface.
- Runtime contract: path derivation, process state, data-refresh state, and scheduler state now converge behind a shared control-panel runtime container.
- Startup contract: `python -m autowfo.control_panel` now accepts `--host`, `--port`, `--root`, `--artifacts-dir`, and data-refresh options, with environment-variable fallbacks for unattended operation.
- Compatibility boundary: routed modules keep existing HTTP routes and payloads, while mutable alias surfaces synchronize back into the shared runtime.
- Validation: focused control-panel regression, runtime reconfiguration coverage, CLI startup override coverage, and full repository regression completed before closure.
- Linked TODO: `AWF-199`, `AWF-200`, `AWF-201`, `AWF-202`, `AWF-203`, `AWF-204`.

### Phase 42: Storage Contract Hardening and Migration Readiness (AWF-205~AWF-210) [Done]
- Goal: put explicit schema-version contracts around AUTOWFO's mutable state files and experiment artifacts so upgrades remain backward-compatible and diagnosable.
- Artifact contract: `run_meta.json` now persists `schema_version`, while legacy unversioned run metadata remains readable via normalization on read.
- Mutable-state contract: scheduler queue, paper positions, and signal-scheduler state now write versioned payloads and still accept legacy on-disk shapes during load.
- Analytics contract: DuckDB analytics store now maintains an `analytics_metadata` table with a persisted schema version for future migration/rebuild decisions.
- Validation: focused storage suites, experiment/control-panel consumer suites, and full repository regression completed before closure.
- Linked TODO: `AWF-205`, `AWF-206`, `AWF-207`, `AWF-208`, `AWF-209`, `AWF-210`.

### Phase 43: Storage Operations and Migration Tooling (AWF-211~AWF-216) [Done]
- Goal: turn Phase 42 storage contracts into operator-usable tooling for validation, normalization, analytics rebuild, and lightweight UI observability.
- Validation tooling: `python -m autowfo doctor` and `python -m autowfo storage validate` now inspect run metadata, scheduler queue, paper positions, signal-scheduler state, and analytics metadata without mutating files.
- Migration tooling: `python -m autowfo storage migrate [--dry-run]` now rewrites legacy-readable payloads through canonical readers/writers into the current versioned shapes.
- Rebuild tooling: `python -m autowfo storage rebuild-analytics` now recreates `analytics.duckdb` from experiment run stores and reports imported runs/combos plus schema version.
- Control-panel observability: packaged overview now surfaces storage-health summary and exposes `/ops/storage-health.json` for machine-readable inspection.
- Validation: focused storage/CLI/control-panel suites, consumer suites, JS syntax smoke, CLI doctor smoke, and full repository regression completed before closure.
- Linked TODO: `AWF-211`, `AWF-212`, `AWF-213`, `AWF-214`, `AWF-215`, `AWF-216`.

### Phase 44: Evidence Reset and Run Isolation (AWF-217~AWF-224) [Done]
- Goal: reset AUTOWFO's evidence model so runs are isolated by construction, shared summaries become derived views, and legacy root-level outputs with broken provenance are removed instead of left behind as technical debt.
- Root cause: `autowfo run` currently uses `cwd/artifacts/` as a shared mutable workspace for runtime config, checkpoints, result CSV/DB files, and registry/leaderboard updates; run-scoped snapshots can therefore reflect shared-state contamination rather than single-run truth.
- Evidence policy:
  - `trusted` = run-local outputs produced under the isolated model
  - `legacy` = historical root-level outputs retained only until purge/reset completes
  - `invalid` = outputs whose provenance cannot be safely used by product code or analysis
- Direction:
  - isolate runtime config, status, results, reports, and metadata under `artifacts/runs/{run_id}/`
  - rebuild shared registry/leaderboard/analytics from trusted runs only (backward-compatible formats)
  - add purge tooling for root-level legacy artifacts with dry-run support
  - re-run only the decision-relevant campaigns after the new model is in place
- Implementation refinement (2026-03-13 architect review):
  - AWF-218 split into 218a/b/c to reduce blast radius: RunWorkspace abstraction → dual-write migration with bit-identical verification → root assumption removal.
  - AWF-219 adds backward-compatibility constraint: rebuilt shared views must preserve file formats and API response shapes for gradual UI migration.
  - Dual-write smoke test in AWF-218b serves as safety gate before purge (AWF-220) proceeds.
- Outcome (2026-03-14):
  - `autowfo run` now writes runtime config, status, results, metadata, reports, registry, and leaderboard under `artifacts/runs/{run_id}/...`.
  - Root legacy evidence was quarantined into `artifacts_legacy_deleted/`, and shared compatibility views are now rebuilt from trusted run-local roots only.
  - Decision-relevant trusted reruns completed for `BNB/BTC 2h seg8`, `SOL/BTC 2h seg16`, `SOL/USDT 2h seg16`, and `XRP/BTC 4h 180d`.
- Exit criteria: root-level legacy run outputs no longer act as primary evidence; control panel and analytics read trusted sources only; important recent campaigns have trusted reruns.
- Linked TODO: `AWF-217`, `AWF-218a`, `AWF-218b`, `AWF-218c`, `AWF-219`, `AWF-220`, `AWF-221`, `AWF-222`, `AWF-223`, `AWF-224`.

## Steady State
- Status: Restored after Phase 44 closure. UI-1, namespace/package convergence, control-panel runtime hardening, storage-contract hardening, storage-ops tooling, and evidence integrity reset are complete.
- Scope closure: Phase 20~39 capabilities delivered end-to-end (experiment lifecycle, discovery/scheduler, analytics/UI, paper feedback loop, notifications, report export, and operational guardrails).
- Runtime posture: unattended operation supported with anomaly notifications, bounded schedulers, explicit control-panel root/artifacts startup contract, versioned mutable-state/artifact payloads, and first-class storage validation/migration/rebuild commands.
- Environment baseline: `pandas>=2.0,<3.0` (validated on 2.3.3), `numpy>=1.23,<2.4` (validated on 2.3.5), `numba>=0.60,<0.64` (validated on 0.63.1).
- Maintenance mode: prioritize dependency drift management and warning cleanup.

## Stage Gates (Do Not Skip)
- Gate 0: Monolith decomposed before protocol freeze (Phase 1). **Passed.**
- Gate A: Protocol freeze before scale/automation work (Phase 2). **Passed at `524f837`.**
- Gate D: Regression suite green before automation expansion (Phase 4). **Passed at `a147972`.**
- Gate B: Ranking rule freeze before advanced modes (Phase 9). **Passed at `cfe3c8a`.**
- Gate C: Reproducibility checks before broadening strategy universe (Phase 10). **Passed at `cfe3c8a`.**
- Gate E: Engine decomposition verified before strategy universe expansion (Phase 11/12 boundary). **Passed at `e43fe33`.**

## Gate Checklists
Gate A (Protocol Freeze) owner: Maintainer + AI agent pair sign-off
- [x] Split schema config/YAML finalized and committed.
- [x] Metric contract doc finalized and committed.
- [x] Schema validation tests pass locally.
- [x] `plans/AUTOWFO_TODO.md` focus window updated.
- [x] `Change Log` entry added with `Protocol frozen at commit <hash>`.

Gate B (Ranking Freeze) owner: Maintainer + AI agent pair sign-off
- [x] Ranking formula spec finalized (including penalties).
- [x] Before/after ranking comparison artifacts stored (`artifacts/runs/20260211_125631/ranking_mode_comparison.json` + `.html`).
- [x] Selection-rule regression tests pass (`pytest tests -k "autowfo or control_panel or run_btc_regime_sweep" -q` -> `186 passed`, `846 deselected`).
- [x] `Change Log` entry added with `Ranking frozen at commit cfe3c8a`.

Gate C (Reproducibility Check) owner: Maintainer + AI agent pair sign-off
- [x] Fixed seed and dataset snapshot identifiers recorded.
- [x] Repeated runs produce stable top-N within defined tolerance.
- [x] Experiment artifact schema validation passes.
- [x] `Change Log` entry added with `Reproducibility verified at commit cfe3c8a`.

Gate D (Regression Green) owner: Maintainer + AI agent pair sign-off
- [x] Regression suite green (split and ranking invariants).
- [x] No unresolved critical drift issues in latest session log.
- [x] Runbook updated for any operator-impacting change.
- [x] `Change Log` entry added with `Regression gate passed at commit <hash>`.

Gate E (Engine Decomposition) owner: Maintainer + AI agent pair sign-off
- [x] `engine.py` split into 5 sub-modules, each 600 lines (largest: `engine_search.py` at 1589L).
- [x] Bit-identical artifact output verified: 21 identity/completeness/isolation/line-count/signature tests in `tests/test_autowfo_gate_e.py` confirm re-export layer is `is`-identical to sub-module originals.
- [x] All existing tests pass (186/186); 3 monkeypatch targets updated for sub-module patching (re-export compatibility intact).
- [x] `Change Log` entry added with `Engine decomposition verified at commit e43fe33`.

## Anti-Drift Rules
- No feature implementation unless linked to a TODO item.
- No metric changes without changelog entry in this file.
- No selection-rule changes without before/after comparison artifacts.
- Prefer additive modules over invasive rewrites.

## Risks and Mitigations
- Overfitting to in-sample:
  - Mitigation: OOS-first score and split consistency constraints.
  - Mitigation (Phase 12): Add validation set 3-way split to eliminate hyperparameter overfitting.
- Combinatorial explosion:
  - Mitigation: staged search, pruning, and caching.
  - Mitigation (Phase 12): Intelligent pruning with early-stopping and warm-start.
- Non-reproducible results:
  - Mitigation: strict seed handling, dataset snapshot IDs, and config hashing.
- Direction drift:
  - Mitigation: mandatory TODO linkage and stage gates.
- Engine monolith re-emergence:
  - Mitigation (Phase 11): Secondary decomposition of `engine.py` into responsibility-scoped sub-modules.
- Limited strategy universe:
  - Mitigation (Phase 12): Config-only indicator expansion + smart pruning.

## Reporting Standard
Each experiment should record:
- config hash
- data range and symbols
- split protocol
- search space size
- top-N candidates
- IS vs OOS metrics
- runtime and memory summary

## Change Log
- 2026-03-13: Phase 44 architect review — AWF-218 split into 218a/b/c (RunWorkspace abstraction → dual-write migration → root assumption removal) to reduce blast radius on engine write paths; AWF-219 gains backward-compatibility constraint on rebuilt shared views; dual-write smoke test in 218b serves as safety gate before purge. Post-Phase-44 strategy: rerun decision-relevant campaigns → evaluate ranking with new evidence → then consider production.
- 2026-03-05: UI-1 phase completed (AWF-190~192): sidebar navigation verified, 107 action-button migrations, KpiCard component, skeleton loading on 4 main views, Chart.js MutationObserver theme adaptation, CSS cleanup. All 14 JS files syntax-check pass; 1427 tests green. System returns to Steady State.
- 2026-03-04: UI-1 phase opened (AWF-190~192): control panel UX overhaul — sidebar navigation, shared component library + i18n completion, page-level visual polish. Frontend-only; no backend API changes.
- 2026-03-02: AWF-189 (Maintenance): warning cleanup + pandas 2.x downgrade verification. Warning count 513→30 (target <50 met). `-W error::DeprecationWarning` gate passes.
- 2026-03-01: Phase 39 completed (AWF-186~188): pandas 2.x environment finalized and fully regressed (`pytest tests -q --tb=short` green), analytics research HTML export (`autowfo export-report` + `/analytics/report.html`) delivered, and Steady State maintenance mode declared.
- 2026-02-06: Initial long-term AUTOWFO master plan created.
- 2026-02-06: Added milestone-to-TODO mapping and quantified gate checklists with sign-off ownership.
- 2026-02-06: Architecture review documented existing implementation inventory; added Milestone 0 (monolith decomposition); updated Milestones 1/4/5 to reflect extract-from-existing approach; added Gate 0; added AWF-000, AWF-002b, AWF-001b; marked AWF-008 as done.
- 2026-02-07: Gate 0 passed AWF-000 decomposition exit criteria verified (module importability coverage + deterministic bit-identical artifact characterization at commit `c059646`).
- 2026-02-07: Real-data two-pass baseline executed via `scripts/run_autowfo_baseline.py` (combo then refine) with archived outputs in `artifacts/runs/20260207_103734`; quantitative trigger decision recorded as `false` (D2-only), so AWF-002b/AWF-006 deferred pending a next window with non-empty OOS segments.
- 2026-02-07: Second real-data two-pass baseline executed with non-empty OOS segments at `artifacts/runs/20260207_161041`; quantitative trigger decision remained `false` (D1/D2/D3 all false), so AWF-002b/AWF-006 continue to be deferred. Runtime config parsing was hardened to accept UTF-8 BOM and avoid unintended fallback to defaults.
- 2026-02-07: Third baseline window executed at `artifacts/runs/20260207_172457` (`1h/300d` temporary window, baseline config restored afterward); trigger remained `false` with D1/D2/D3 all false. Refine stage ran with `0/0` additional combos, so next evidence cycle must ensure non-zero refine candidate execution before using comparison deltas for ranking decisions.
- 2026-02-07: Baseline runner now records pass-level workload (`run_total/run_done/run_skipped/run_stage`) from `run_status.json` and emits a warning when refine processes zero candidates, preventing non-informative combo-vs-refine comparisons from being misread as strong evidence.
- 2026-02-08: Refine candidate selection now reuses activity fallback behavior to avoid zero-candidate collapse on low-frequency windows; quality filter thresholds (`min_avg_daily_trades_target`, `min_oos_trades_target`) are now configurable via `sweep_config.json` with unchanged defaults.
- 2026-02-08: Fourth baseline window executed at `artifacts/runs/20260208_034213` with non-zero refine execution (`486/486`); trigger decision remained `false` (D3-only), so AWF-002b/AWF-006 stay deferred pending additional multi-window evidence.
- 2026-02-08: Fifth baseline window executed at `artifacts/runs/20260208_055709` (`4h/365d`, segmented combo window) with non-zero refine execution (`1107/1107`); trigger again remained `false` with D3-only while combo-vs-refine comparison stayed informative (positive OOS return delta), so AWF-002b/AWF-006 remains deferred pending one more stricter-floor evidence pass.
- 2026-02-08: Sixth baseline window executed at `artifacts/runs/20260208_081420` using stricter activity floor (`min_avg_daily_trades_target=1.0`); refine remained non-zero (`5508/5508`) and trigger still stayed `false` with D3-only. This suggests current non-trigger outcome is stable across multiple non-zero-refine windows, so AWF-002b/AWF-006 continues to be deferred pending targeted cross-window confirmation.
- 2026-02-08: **Platform mindset shift** reframed AUTOWFO as a reusable strategy-exploration platform (correctness > extensibility > speed). Reordered phases: Protocol Freeze (Phase 2) reactivated as immediate focus with AWF-003 first; added AWF-013 (parallelization) to Milestone 5; promoted AWF-009/010 to P1; AWF-002b/006 remain evidence-gated. Updated AGENTS.md, AUTOWFO_TODO.md, and this file.
- 2026-02-08: AWF-003 implemented: strategy metadata moved from hard-coded maps into `plans/protocols/strategy_schema.json` with loader/validator in `scripts/autowfo/strategy_schema.py`; constants now fail fast on invalid schema and runtime maps are schema-backed (`INDICATOR_META`, `REGIME_NAME_MAP`, `REGIME_TYPE_MAP`).
- 2026-02-08: AWF-002 implemented: metric definitions are now frozen in `plans/protocols/metric_contract.yaml` and validated by `scripts/autowfo/metric_contract.py`; `scripts/autowfo/metrics.py` enforces metric key consistency against the contract and keeps empty-OOS outputs schema-complete (including `oos_avg_daily_trades`) to preserve cross-run comparability.
- 2026-02-08: AWF-004 implemented: artifact schema/metadata rules moved into `plans/protocols/artifact_contract.yaml` with loader/validator in `scripts/autowfo/artifact_contract.py`; run artifacts now include reproducibility metadata (`config_sha256`, `data_fingerprint`) in combo/symbol/leaderboard outputs and emit `run_metadata.json` plus `run_metadata_<run_id>.json`.
- 2026-02-08: AWF-001 implemented: split protocol moved into `plans/protocols/split_protocol.yaml` with loader/validator in `scripts/autowfo/split_protocol.py`; `scripts/autowfo/split.py` now validates protocol-backed mode/constraint assumptions (default `anchored`, positive horizons, non-overlapping OOS via `step_days >= test_days`) while preserving current walk-forward slice outputs.
- 2026-02-08: Protocol frozen at commit `524f837` (Gate A passed): strategy schema, metric contract, artifact contract, and split protocol are all externalized and validated; TODO focus moves from Phase 2 to Phase 3 (AWF-013).
- 2026-02-08: AWF-013 in progress: combo evaluation logic extracted into pure module (`scripts/autowfo/evaluator.py`) and multi-process path added via `ProcessPoolExecutor` (`scripts/autowfo/parallel.py`) behind `max_workers` config. Main process keeps centralized checkpoint/IO writes, and 3-worker deterministic equivalence is validated by `tests/test_autowfo_parallel.py`.
- 2026-02-08: AWF-013 benchmark harness added (`scripts/run_autowfo_parallel_benchmark.py`) with archived outputs under `artifacts/benchmarks/`. Current environment shows bit-identical outputs for 1-worker vs 3-worker runs but speedup remains below target (`~0.89x` to `~1.40x`), indicating remaining IPC/serialization overhead and/or hardware-core constraints before AWF-013 can be closed.
- 2026-02-08: AWF-013 throughput tuning applied: worker payload was compacted (metrics-first result contract) and parent-side row materialization centralized to reduce cross-process serialization overhead. New benchmark samples under `artifacts/benchmarks/` reached best observed `~2.45x` speedup (still bit-identical) on heavier synthetic workloads, which is close but still below the `2.5x` exit threshold in the current environment.
- 2026-02-09: AWF-013 exit criteria satisfied and marked done. After additional chunked dispatch/IPC tuning, benchmark artifact `artifacts/benchmarks/awf013_parallel_benchmark_20260209_000935.json` records `bit_identical=true` with `speedup=2.6641` for 3-worker vs single-thread run on heavy profile.
- 2026-02-09: AWF-009 implemented and marked done: added `scripts/autowfo/registry.py` plus sweep integration to maintain `artifacts/run_registry.json` as experiment index + coverage map (`tested_pairs` and `untested_pairs`) across timeframe/symbol combinations.
- 2026-02-09: AWF-010 implemented and marked done: added one-command entrypoint package `autowfo` (`python -m autowfo`) with `run` and `baseline` workflows, JSON/YAML config loading, runtime config materialization to `artifacts/sweep_config.json`, and subprocess orchestration into existing AUTOWFO scripts. Verified via CLI tests and command help checks.
- 2026-02-09: Additional evidence window executed through new one-command path (`python -m autowfo baseline --config artifacts/sweep_config_window7.json`) and archived at `artifacts/runs/20260209_110250`. Both passes were non-zero (`combo=9600`, `refine=729`) with informative comparison deltas (`delta_avg_oos_return_pct=+0.0978`), but trigger remained `false` with persistent D3-only (`D1=false`, `D2=false`, `D3=true`), so AWF-002b/AWF-006 remain deferred.
- 2026-02-09: Targeted symbol-mix evidence window executed (`python -m autowfo baseline --config artifacts/sweep_config_window8_symbols.json`) and archived at `artifacts/runs/20260209_124307`. With `ETH/USDT+BNB/USDT+SOL/USDT` and non-zero refine workload (`2268/2268`), trigger still remained `false` with D3-only (`D1=false`, `D2=false`, `D3=true`), indicating the non-trigger state persists across at least two symbol universes and keeping AWF-002b/AWF-006 deferred.
- 2026-02-09: High-frequency evidence run initially failed during refine (run `artifacts/runs/20260209_140004`) due to `KeyError: 32` from lookback expansion exceeding precomputed indicator maps. Fix applied at commit `cf56d0a`: evaluator now coerces refine indicator lookbacks to nearest available precomputed keys before combo application, with regression coverage in `tests/test_autowfo_evaluator.py`.
- 2026-02-09: After the lookback-coercion fix, high-frequency rerun (`python -m autowfo baseline --config artifacts/sweep_config_window9_hf.json`) completed successfully and was archived at `artifacts/runs/20260209_145335` (`combo=9600`, `refine=5481`). Trigger remained `false` with D3-only (`D1=false`, `D2=false`, `D3=true`) while comparison deltas were informative (`delta_avg_oos_return_pct=+1.5771`), so AWF-002b/AWF-006 continue to be deferred.
- 2026-02-09: Longer-horizon high-frequency evidence window (`python -m autowfo baseline --config artifacts/sweep_config_window10_hf_long.json`) archived at `artifacts/runs/20260209_160500` also remained non-trigger (`D1=false`, `D2=false`, `D3=true`) despite non-zero refine workload (`5508/5508`) and positive refine uplift (`delta_avg_oos_return_pct=+0.2722`). This reinforces that ranking-upgrade trigger conditions are still unmet; AWF-002b/AWF-006 stay deferred.
- 2026-02-09: AWF-011 implemented: added regression-invariant tests for split and ranking modules (`tests/test_autowfo_split.py`, `tests/test_autowfo_ranking.py`) covering split mode equivalence, horizon-based slice count, monotonic boundaries, non-int horizon rejection, ranking fallback score-column selection (missing/all-NaN preferred metric), tie-break resilience when hold-hour field is absent, and Top-N fallback ordering behavior.
- 2026-02-09: AWF-012 implemented: added notebook-free operational playbook `plans/AUTOWFO_RUNBOOK.md` (preflight checks, `python -m autowfo run/baseline` command patterns, artifact map, trigger interpretation, failure handling, and post-run checklist). Verified AUTOWFO regression subset remains green (`33 passed`) after runbook integration.
- 2026-02-10: Regression gate passed at commit `a147972` (Gate D): regression checks green, runbook available, and latest session-log review shows no unresolved critical drift issues.
- 2026-02-10: Additional evidence window executed (`python -m autowfo baseline --config artifacts/sweep_config_window11_quick.json`) and archived at `artifacts/runs/20260210_013015` with non-zero workloads (`combo=3840`, `refine=702`), positive refine uplift (`delta_avg_oos_return_pct=+1.2267`), and non-trigger result (`D1=false`, `D2=false`, `D3=true`), so AWF-002b/AWF-006 remain deferred.
- 2026-02-10: Operational hardening after runtime incident: disk-space exhaustion (`OSError: [Errno 28] No space left on device`) was handled by artifact cleanup and runbook update to require pre-run disk headroom checks plus recovery steps.
- 2026-02-10: Added AWF-017a/b/c/d (control panel enhancement) to backlog architecture refactor, batch queue UI, coverage map UI, cross-run dashboard UI. Restructured TODO from 6+3.5 phases into clean 10-phase roadmap: Phases 1-4 completed, Phase 5 (panel refactor) as current focus, Phases 6-8 pair backend+frontend per feature, Phases 9-10 remain evidence-gated. Updated milestones and stage gates in this file to match.
- 2026-02-10: AWF-017a implemented: control panel frontend moved to file-based static assets under scripts/control_panel/static (index.html, css/app.css, modular JS app.js plus tabs.js/batch.js/coverage.js/dashboard.js), backend retains existing API contracts while serving /static/*, and tab navigation scaffolding is now decoupled from Python source edits.
- 2026-02-10: AWF-014 implemented: added `python -m autowfo batch --plan <file>` backend with structured plan parsing, preflight checks (config/cwd/disk), crash-safe resume state (`artifacts/batch_state.json`, seen-key dedup), and `--continue-on-error` behavior. Added CLI regression coverage for success, resume-skip, missing-config preflight, and partial-failure continuation paths.
- 2026-02-10: AWF-017b implemented: control panel now exposes batch queue APIs (`/batch/queue.json`, `/batch/enqueue`, `/batch/start`, `/batch/cancel`, `/batch/clear`, `/batch/remove`) and frontend batch tab actions (enqueue/start/cancel/clear + live queue/log refresh) wired to `autowfo batch` and `artifacts/batch_state.json`. Added queue lifecycle tests in `tests/test_control_panel.py`.
- 2026-02-10: AWF-015 implemented: added `python -m autowfo plan` coverage planner to generate executable batch plans from `run_registry.json` `untested_pairs`, including per-gap config generation and controls for `--max-jobs`, `--workflow`, `--mode`, and `--workers`. Added CLI tests for both populated and empty-gap planning paths.
- 2026-02-10: AWF-017c implemented: control panel coverage tab now renders timeframe/symbol matrix from `/coverage/matrix.json` with tested/queued/untested states and supports one-click scheduling through `/coverage/enqueue` (per-pair config generation + batch queue insertion). Added regression tests for coverage matrix classification and enqueue behavior.
- 2026-02-11: AWF-016 and AWF-017d implemented and marked done. Added `scripts/autowfo/cross_run.py`, CLI subcommand `python -m autowfo report`, dashboard report endpoints (`/dashboard/cross_run.json`, `/dashboard/report`, `/dashboard/report/generate`), and live dashboard/history UI rendering for summary KPI, global leaderboard, combo stability, and run timeline. Focused regression suite covering aggregation, CLI, and control-panel hooks passed (`22 passed`).
- 2026-02-11: Additional evidence window executed (`python -m autowfo baseline --config artifacts/sweep_config_window12_symbols.json`) and archived at `artifacts/runs/20260211_103459` (`4h/180d`, `ETH/USDT+BNB/USDT`). Both passes were non-zero (`combo=3840`, `refine=1161`) and comparison remained informative (`delta_avg_oos_return_pct=+0.3130`, `delta_avg_oos_drawdown_pct=-0.2822`), while trigger remained `false` with D3-only (`D1=false`, `D2=false`, `D3=true`), so AWF-002b/AWF-006 continue to stay deferred.
- 2026-02-11: Additional timeframe-variant evidence window executed (`python -m autowfo baseline --config artifacts/sweep_config_window13_2h.json`) and archived at `artifacts/runs/20260211_105818` (`2h/180d`, `ETH/USDT+BNB/USDT`). Both passes were non-zero (`combo=3840`, `refine=2403`) and comparison remained informative (`delta_avg_oos_return_pct=+1.1668`, `delta_avg_oos_drawdown_pct=-0.7468`), while trigger remained `false` with D3-only (`D1=false`, `D2=false`, `D3=true`), so AWF-002b/AWF-006 remain deferred.
- 2026-02-11: **Governance change** D1/D2/D3 repurposed from activation gates to health-monitoring indicators. 13 baseline windows all persistently D3-only (low-trade combos in top-10) constitutes sufficient evidence that single-metric ranking is the bottleneck. AWF-002b/AWF-006/AWF-007 unblocked for immediate implementation. Phase 9 title changed from "Evidence-Gated" to "Immediate". Gate B proceeds without D1/D2 trigger prerequisite. Updated AGENTS.md, AUTOWFO_TODO.md, and this file.
- 2026-02-11: AWF-002b and AWF-006 implemented. Added new OOS robustness metrics (`oos_return_std`, `oos_positive_segment_ratio`, `oos_sharpe_like`, `oos_low_trade_segment_ratio`, `oos_low_trade_penalty`) to `metrics.py` and `plans/protocols/metric_contract.yaml`, expanded combo artifact/report columns and labels, and replaced ranking logic with dual-mode (`legacy`/`composite`) `scripts/autowfo/ranking.py` where composite is default and weights are configurable via `sweep_config.json`. Integrated composite ranking into refine candidate selection, final top10 pick, and leaderboard best-run view. Focused regression suite passed (`52 passed` across ranking/metrics/engine/sweep tests).
- 2026-02-11: AWF-007 implemented. Baseline workflow now emits same-window ranking-mode paired comparison artifacts: `ranking_mode_comparison.json` (fixed schema for machine parsing) and `ranking_mode_comparison.html` (human-readable table report) under `artifacts/runs/<run_label>/`. Report includes legacy/composite paired rows, overlap and delta summary, and 3-axis diagnostics (`strategy_quality`, `sample_sufficiency`, `combo_scarcity`). Added baseline helper/tests; expanded AUTOWFO-targeted regression run passed (`120 passed`, `846 deselected`).
- 2026-02-11: Gate B evidence run executed with `python -m autowfo baseline --config artifacts/sweep_config_window11_quick.json`, archived at `artifacts/runs/20260211_125631`. Paired report artifacts (`ranking_mode_comparison.json` + `.html`) are present, with informative same-window deltas (`overlap_rows=0`, `delta_avg_oos_return_pct=-1.8896`, `delta_avg_oos_sharpe_like=+1.1136`, `delta_avg_oos_min_total_trades=+3.8`). Trigger ratios remain monitoring-only (`D1=false`, `D2=false`, `D3=true`), and Gate B checklist is now 3/4 complete pending ranking-freeze commit hash recording.
- 2026-02-11: AWF-001b moved to doing with foundational plumbing. Split protocol now supports `anchored` + `rolling`; `scripts/autowfo/split.py` added window-level API (`_build_walk_forward_windows`) while preserving existing slice API compatibility; runtime now accepts `wf_mode` and carries it through combo keying, combo/symbol artifacts, leaderboard rows, run metadata, and report metadata. Focused/regression subset remains green (`123 passed`, `846 deselected` for AUTOWFO-related tests).
- 2026-02-11: AWF-001b completed. In `wf_mode=rolling`, evaluator now performs per-window train-time policy selection (`filtered` vs `unfiltered`) and applies the selected policy to the corresponding test window, while `anchored` mode remains unchanged. Added regression test coverage in `tests/test_autowfo_evaluator.py`; AUTOWFO-focused suite is green (`124 passed`, `846 deselected`).
- 2026-02-11: AWF-005 started (modular refactor step 1). Runtime settings resolution previously embedded in `run_btc_regime_sweep.py` is now centralized in `scripts/autowfo/engine.py::_resolve_runtime_settings`, and sweep entrypoint consumes the normalized settings payload. Added regression tests for defaults/normalization and split-mode callback wiring (`tests/test_autowfo_engine.py`). AUTOWFO-focused suite remains green (`126 passed`, `846 deselected`).
- 2026-02-11: AWF-005 modular refactor step 2 completed. Extracted timeframe runtime bootstrap into `scripts/autowfo/engine.py::_prepare_timeframe_runtime` (context prep, data fingerprinting, WF windows/slices, runtime-eval payload) and moved finalize payload assembly into engine via `_build_leaderboard_row_payload` and `_build_run_metadata_payload`. Rewired `scripts/run_btc_regime_sweep.py` to use these helpers and removed duplicated inline orchestration blocks. Validation remains green (`42 passed` targeted sweep/engine tests, `129 passed`, `846 deselected` AUTOWFO subset).
- 2026-02-11: AWF-005 modular refactor step 3 completed. Extracted report output orchestration into engine helpers: `_build_report_file_paths` (deterministic report filenames/paths), `_build_report_html` (full report template assembly), and `_write_report_files` (dual output write). Sweep entrypoint now delegates report path/template/write blocks to `scripts/autowfo/engine.py`. Added regression coverage for report helpers in `tests/test_autowfo_engine.py`; validation remains green (`45 passed` targeted sweep/engine tests, `132 passed`, `846 deselected` AUTOWFO subset).
- 2026-02-11: AWF-005 modular refactor step 4 completed. Extracted best-run replay orchestration into `scripts/autowfo/engine.py::_prepare_best_replay_payload` (regime resolution, indicator coercion/apply, cost alignment, replay portfolio execution, summary frame), plus best-report frame assembly (`_build_best_report_frames`) and leaderboard table rendering helpers (`_leaderboard_report_columns`, `_build_leaderboard_report_html`). Sweep entrypoint now consumes engine helpers for these finalize responsibilities and removes additional inline logic. Validation remains green (`48 passed` targeted sweep/engine tests, `135 passed`, `846 deselected` AUTOWFO subset).
- 2026-02-11: AWF-005 modular refactor step 5 completed. Extracted report column schema helpers (`_top_report_columns`, `_summary_report_columns`) and unified report table HTML assembly (`_build_report_table_html_sections`) into `scripts/autowfo/engine.py`; sweep entrypoint now delegates report-params/OOS/top10/summary table rendering through engine helper and removes inline column/wiring blocks. Added regression coverage for schema and default/custom rendering path; validation remains green (`50 passed` targeted sweep/engine tests, `137 passed`, `846 deselected` AUTOWFO subset).
- 2026-02-11: AWF-005 modular refactor step 6 completed. Extracted best-context fallback orchestration (`_prepare_best_timeframe_context`) and final artifact emit summary flow (`_persist_run_metadata_and_registry`, `_build_completion_output_map`) into `scripts/autowfo/engine.py`; sweep entrypoint now delegates best-report fallback handling, metadata/registry persistence, and completion output listing to engine helpers. Added regression coverage for success/error context paths, metadata+registry call wiring, and output order guarantees. Validation remains green (`53 passed` targeted sweep/engine tests, `140 passed`, `846 deselected` AUTOWFO subset).
- 2026-02-12: AWF-005 modular refactor step 7 completed. Extracted finalize orchestration wrapper `scripts/autowfo/engine.py::_run_finalize_pipeline` so sweep finalize now delegates combo/per-symbol result loading, activity-filter fallback, top10 selection, best-context preparation, replay/report generation, leaderboard assembly, metadata+registry persistence, and completion output mapping through one engine helper call. Fixed `vol_zs` forwarding regression in replay payload wiring during extraction and added regression tests for empty-combo warning path, best-context error warning path, and `vol_zs` pass-through contract. Validation remains green (`56 passed` targeted sweep/engine tests, `143 passed`, `846 deselected` AUTOWFO subset).
- 2026-02-12: AWF-005 modular refactor step 8 completed. Extracted remaining timeframe execution lifecycle helpers into engine: `_run_parallel_combo_search_for_timeframe` (parallel combo plan orchestration with dedupe/progress/checkpoint callback wiring) and `_checkpoint_pending_rows` (checkpoint gating + CSV/DB flush + buffer clear/state updates). `scripts/run_btc_regime_sweep.py` now delegates these branches to engine helpers, reducing local orchestration surface while preserving behavior and deterministic outputs. Added regression tests for parallel done/skipped accounting and checkpoint flush/skip semantics. Validation remains green (`59 passed` targeted sweep/engine tests, `146 passed`, `846 deselected` AUTOWFO subset).
- 2026-02-12: AWF-005 modular refactor step 9 completed. Extracted timeframe loop helper blocks into engine: `_prepare_timeframe_runtime_or_skip` (runtime try/skip + combo-total adjustment + progress/warn emit), `_build_combo_task_payload` (combo key/task payload assembly), and `_append_eval_result_rows` (symbol/combo row assembly from evaluator outputs). `scripts/run_btc_regime_sweep.py` now uses thin adapters instead of large inline closures for these sections, further reducing orchestration bulk while preserving behavior. Added regression tests for skip-path handling, combo-task payload contract, and eval-result row append behavior. Validation remains green (`62 passed` targeted sweep/engine tests, `149 passed`, `846 deselected` AUTOWFO subset).
- 2026-02-12: AWF-005 modular refactor step 10 completed. Extracted `eval_combo` state-machine orchestration into `scripts/autowfo/engine.py::_run_combo_eval_step` covering pause gating, dedupe skip, task evaluation, row append callback, progress emission, checkpoint trigger, and counter tick callback. `scripts/run_btc_regime_sweep.py` `eval_combo` closure is now a thin delegator, further shrinking local control flow while preserving behavior and progress ordering. Added regression tests for skip/evaluate paths and counter callback accounting. Validation remains green (`64 passed` targeted sweep/engine tests, `151 passed`, `846 deselected` AUTOWFO subset).
- 2026-02-12: AWF-005 modular refactor step 11 completed. Extracted per-timeframe runner orchestration into `scripts/autowfo/engine.py::_run_timeframe_search_loop`, centralizing timeframe iteration, runtime-attempt invocation, total-combo state synchronization, no-WF warning path, and range/fingerprint accumulation. `scripts/run_btc_regime_sweep.py` now supplies thin callbacks for runtime-attempt and timeframe-body dispatch, reducing main-function orchestration depth while preserving deterministic outputs. Added regression test for loop state/warning semantics. Validation remains green (`65 passed` targeted sweep/engine tests, `152 passed`, `846 deselected` AUTOWFO subset).
- 2026-02-12: AWF-005 modular refactor step 12 completed. Extracted timeframe-ready branch orchestration into `scripts/autowfo/engine.py::_run_timeframe_ready_search`, consolidating dispatch between parallel combo and search/refine paths plus callback wiring for combo-task payload build, row append, eval step execution, and refine-plan propagation. `scripts/run_btc_regime_sweep.py` `_run_timeframe_body` is now a thin delegator with only local total-combo update callback. Added regression tests for parallel/refine branch routing and refine-plan callback propagation. Validation remains green (`67 passed` targeted sweep/engine tests, `154 passed`, `846 deselected` AUTOWFO subset).
- 2026-02-13: AWF-005 modular refactor step 13 completed. Extracted runtime-prepare kwargs assembly and finalize pre-state plumbing into `scripts/autowfo/engine.py` via `_build_prepare_timeframe_runtime_kwargs` and `_run_finalize_after_timeframe_loop`; `scripts/run_btc_regime_sweep.py` now delegates these blocks and no longer manually stitches timeframe range/fingerprint state into finalize calls. Added regression tests for prepare-kwargs mapping and finalize loop-output injection/force-checkpoint semantics. Validation remains green (`69 passed` targeted sweep/engine tests, `156 passed`, `846 deselected` AUTOWFO subset).
- 2026-02-13: AWF-005 modular refactor step 14 completed. Extracted remaining timeframe-ready/finalize callback+kwargs wiring into `scripts/autowfo/engine.py` via `_build_timeframe_ready_search_kwargs`, `_run_timeframe_ready_search_with_refine_tracking`, and `_build_finalize_pipeline_kwargs`; `scripts/run_btc_regime_sweep.py` now delegates these wiring layers and removes local refine callback closure plus large inline finalize kwargs assembly. Added regression tests for sort/top-score callback wiring, refine total/progress propagation, and finalize kwargs contract mapping. Validation remains green (`72 passed` targeted sweep/engine tests, `159 passed`, `846 deselected` AUTOWFO subset).
- 2026-02-13: AWF-005 modular refactor step 15 completed. Extracted progress/control/checkpoint lifecycle into `scripts/autowfo/engine.py::_build_run_lifecycle_callbacks`, centralizing stateful progress emit, pause-loop wait behavior, checkpoint flush/state updates, and done/total counter callbacks. `scripts/run_btc_regime_sweep.py` now consumes engine-provided lifecycle callbacks and removes local lifecycle closures/locals for these responsibilities. Added regression tests for lifecycle progress/counter behavior, pause-loop emit/sleep behavior, and checkpoint-state propagation contract. Validation remains green (`75 passed` targeted sweep/engine tests, `162 passed`, `846 deselected` AUTOWFO subset).
- 2026-02-13: AWF-005 modular refactor step 16 completed. Introduced structured context objects for prepare/timeframe-ready/finalize wiring in `scripts/autowfo/engine.py` (`_build_prepare_timeframe_runtime_context`, `_build_timeframe_ready_search_context`, `_build_finalize_pipeline_context`) and corresponding adapter builders (`*_from_context`) so kwargs expansion is centralized at engine boundary. `scripts/run_btc_regime_sweep.py` now builds/reuses these contexts and replaces repeated large kwargs fan-out callsites with compact context-based calls. Added regression tests for context builder/adapter mapping across prepare/timeframe-ready/finalize paths. Validation remains green (`78 passed` targeted sweep/engine tests, `165 passed`, `846 deselected` AUTOWFO subset).
- 2026-02-13: AWF-005 modular refactor step 17 completed. Consolidated remaining timeframe main-loop orchestration into higher-level engine runners: `scripts/autowfo/engine.py::_build_timeframe_execution_callbacks` (prepare/body callback assembly) and `_run_timeframe_search_and_finalize` (loop + finalize orchestration wrapper). `scripts/run_btc_regime_sweep.py` now delegates these orchestration layers and removes local per-timeframe closures plus direct loop/finalize stitching. Added regression tests for callback wiring contract and looplize handoff behavior. Validation remains green (`80 passed` targeted sweep/engine tests, `167 passed`, `846 deselected` AUTOWFO subset).
- 2026-02-13: AWF-005 modular refactor step 18 completed. Added finalize-result completion handler `scripts/autowfo/engine.py::_handle_finalize_result` (warn path + completion progress emit + ordered output print) and pipeline wrapper `scripts/autowfo/engine.py::_run_timeframe_pipeline` to combine callback-build and loop/finalize execution into one engine call. `scripts/run_btc_regime_sweep.py` now delegates to these helpers and removes remaining local finalize output wiring. Added regression tests for warn/completion paths and wrapper wiring contract. Validation remains green (`83 passed` targeted sweep/engine tests, `170 passed`, `846 deselected` AUTOWFO subset).
- 2026-02-13: AWF-005 modular refactor step 19 completed. Added shared runtime context builder `scripts/autowfo/engine.py::_build_shared_pipeline_runtime_context` and shared adapters (`_build_prepare_timeframe_runtime_context_from_shared`, `_build_timeframe_ready_search_context_from_shared`, `_build_finalize_pipeline_context_from_shared`) so prepare/ready/finalize context assembly reuses one canonical runtime bundle. Also moved sweep-local helper logic into engine (`_safe_int`, `_safe_float`, `_has_all_config_fields`) and rewired `scripts/run_btc_regime_sweep.py` to consume engine-level helpers. Added regression coverage for shared adapters and helper behavior. Validation remains green (`88 passed` targeted sweep/engine tests, `175 passed`, `846 deselected` AUTOWFO subset).
- 2026-02-13: AWF-005 modular refactor step 20 completed. Added sweep adapter builder `scripts/autowfo/engine.py::_build_sweep_adapter_functions` and removed sweep-local wrapper helpers (`_combo_key_from_dict`, `_indicator_combo_label`, `_format_indicator_list`, `_df_to_html`) from `scripts/run_btc_regime_sweep.py`. Entry point now wires adapter callables once and reuses them across seen-key filtering, timeframe-ready search context, and finalize report rendering. Updated report-equivalence tests to validate adapter behavior directly; validation remains green (`91 passed` targeted sweep/engine/report tests, `176 passed`, `846 deselected` AUTOWFO subset).
- 2026-02-13: AWF-005 modular refactor step 21 completed. Added schema-field helper `scripts/autowfo/engine.py::_build_sweep_schema_fields` to centralize `COMBO_KEY_FIELDS`, `COMBO_RESULT_FIELDS`, `SYMBOL_RESULT_FIELDS`, and `STRICT_CONFIG_FIELDS` contracts, and rewired `scripts/run_btc_regime_sweep.py` to consume generated schema maps instead of inline constant blocks. Added schema contract regression test coverage and verified behavior-preserving output contracts. Validation remains green (`92 passed` targeted sweep/engine/report tests, `177 passed`, `846 deselected` AUTOWFO subset).
- 2026-02-13: Gate C preflight implementation completed. Artifact contract now requires `combo_seed` in `run_metadata`, and engine finalize metadata pipeline propagates seed into persisted run metadata (`scripts/autowfo/engine.py`). Added reproducibility utility module `scripts/autowfo/reproducibility.py` with `compare_top_n_stability` for identity-overlap + metric-tolerance checks across repeated runs. Added regression coverage for contract enforcement, seed propagation, and reproducibility comparison behavior. Validation remains green (`99 passed` targeted tests, `180 passed`, `846 deselected` AUTOWFO subset).
- 2026-02-13: Gate C execution tooling and run evidence completed. Added artifact-schema validator `scripts/autowfo/reproducibility.py::validate_run_artifact_schema` and new CLI workflow `python -m autowfo gate-c` (dual-run orchestration + schema validation + top-N stability comparison) with `workflow=run` output-dir handling fix. Executed real dual-run check using fixed seed/config (`artifacts/sweep_config_window11_quick.json`) and generated `artifacts/reproducibility/gate_c_window11_quick.json` (`schema_valid=true`, `stable=true`, `gate_c_passed=true`; run IDs `20260213_133808`/`20260213_134556`). Validation remains green (`18 passed` targeted CLI/repro tests, `186 passed`, `846 deselected` AUTOWFO subset).
- 2026-02-13: Ranking frozen at commit `cfe3c8a` (Gate B passed). Ranking formula/spec, paired comparison artifacts, and AUTOWFO regression baseline are now locked for Phase 10+ work.
- 2026-02-13: Reproducibility verified at commit `cfe3c8a` (Gate C passed). Dual-run fixed-seed validation and artifact-schema checks are both green and recorded in `artifacts/reproducibility/gate_c_window11_quick.json`.
- 2026-02-13: Phase 11/12/13 planning added. Phase 11 (AWF-018/019/020): engine secondary decomposition + coverage gap fill + baseline benchmarks. Phase 12 (AWF-021/022/023/024): strategy universe expansion + 3-way split + intelligent pruning + cross-timeframe parallelism. Phase 13 (AWF-025/026/027/028): combo stability trends + regime-aware ranking + automated patrol cycle + notebook export. Gate E added between Phase 11 and 12. Active focus moved to Phase 11.
- 2026-02-13: AWF-018 engine secondary decomposition completed. Split 4850-line `engine.py` into 5 sub-modules: `engine_helpers.py` (896L), `engine_runtime.py` (732L), `engine_report.py` (570L), `engine_search.py` (1589L), `engine_finalize.py` (1125L). Thin `engine.py` re-export layer (121L) maintains backward compatibility. Dependency graph verified cycle-free: helpers/runtime are leaves; reporttime; finalizepers+report; searchpers+runtime+finalize. 3 test monkeypatch targets updated to patch on correct sub-module. Validation: 186 passed, 0 failed. Gate E checklist items 1 and 3 checked.
- 2026-02-14: AWF-019 coverage gap-fill tooling completed. Enhanced `autowfo plan` with `--target-timeframes`/`--target-symbols`/`--timeframe-days` to detect gaps for never-run dimensions. Added `_compute_coverage_gaps` (cartesian-product minus tested) and enhanced `registry._build_coverage_map` with optional `target_timeframes`/`target_symbols`. Generated `artifacts/batch_plan_gap_fill.json` with 4 gap jobs: 1h-BNB(90d), 1h-ETH(90d), 1h-SOL(90d), 2h-SOL(120d). 8 new tests added (2 registry + 6 CLI). Validation: 194 passed, 0 failed. Actual batch execution pending user action.
- 2026-02-14: AWF-020 baseline strategy benchmarks completed. Created `scripts/autowfo/benchmark.py` with `compute_bh_return_pct` (buy-and-hold) and `compute_random_entry_return_pct` (random-entry) pure functions. Injected benchmark computation into `engine_finalize._run_finalize_pipeline` after `best_ctx` load (defensive None handling for missing `trade_close`). Propagated `bh_return_pct` and `random_entry_return_pct` through `_build_leaderboard_row_payload` `registry._build_run_entry` `cross_run.build_cross_run_payload`. Cross-run leaderboard now includes 3 new columns (`bh_return_pct`, `random_entry_return_pct`, `alpha_vs_bh`) and 3 new summary KPIs (`avg_bh_return_pct`, `avg_random_return_pct`, `avg_alpha_vs_bh`). HTML report updated with benchmark KPI cards. Backward compatible with old registry entries (missing fields None). 16 new tests (10 benchmark + 4 cross_run + 2 registry). Validation: 140+ passed, 0 failed. Phase 11 complete.
- 2026-02-14: AWF-024 3-way train/validation/test split protocol completed. Expanded `split_protocol.yaml` window_tuple from 4 to 6 elements (`train_start, train_end, valid_start, valid_end, test_start, test_end`). `split.py::_build_walk_forward_windows` now accepts `valid_days=0` (default, backward-compatible) and produces 6-tuples; when `valid_days>0`, validation segment is inserted between train and test with no overlap. `evaluator.py` unpacks 6-tuples with validation-first filter policy selection (falls back to train in rolling mode when degenerate). `wf_valid_days` wired through entire pipeline: `engine_helpers.py` (default config + 4 field lists), `engine_runtime.py` (6 functions), `engine_search.py` (15 changes across 8 functions), `engine_report.py` (4 changes), `engine_finalize.py` (16 changes across 7 functions), `constants.py` (labels), `run_btc_regime_sweep.py` (extraction + passthrough). Added 12 new split tests covering zero/positive valid_days, overlap, modes, count formula, 6-tuple format, and error cases. Fixed existing tests across 6 test files. Validation: 142 passed, 0 failed (80 engine + 23 split + 4 protocol + 2 evaluator + 3 report + 11 control_panel + 9 sweep). Phase 12 AWF-024 complete; next AWF-021.
- 2026-02-14: AWF-021 indicator universe expansion completed. Expanded from 13 to 25 indicators by adding 12 new: CCI (momentum), Williams %R (momentum), ADX (volatility), TRIX (momentum), DPO (momentum), EFI (volume), VWMA Trend (volume), Ultimate Oscillator (momentum), Keltner Channel Position (volatility), Donchian Channel Position (volatility), PPO (momentum), Choppiness Index (volatility). Changes span 10 files: `strategy_schema.json` (12 entries), `constants.py` (22 param fields + 24 labels), `data.py` (14 params + 12 precompute blocks + 12 return keys), `strategy.py` (4 functions: coerce/coarse/refine/apply), `run_btc_regime_sweep.py` (14 lookback definitions + shared context), `engine_runtime.py` (signature + forwarding), `engine_search.py` (4 context builders), `engine_finalize.py` (7 functions). Updated 5 test files with new params and expected counts. C(25,2..4) = 15,250 combos >> 5,000 exit criteria met. Validation: 218 passed, 0 failed across 22 test files. Phase 12 AWF-021 complete; next AWF-022.
- 2026-02-14: AWF-022 combo intelligent pruning completed. Created `scripts/autowfo/pruning.py` with `PruningTracker` class (per-indicator score tracking, adaptive threshold via median-of-top-N ? prune_ratio, warm-start from existing results, budget cap) and `_split_into_batches` utility. Wired into serial search (`_run_combo_eval_step`: budget_exhausted + should_prune before eval, record_result + update_threshold after eval) and parallel search (`_run_parallel_combo_search_for_timeframe`: pruning-aware task collection + batch-based dispatch with inter-batch threshold updates). PruningTracker created in `_run_timeframe_ready_search` from `pruning_config` with optional warm_start + summary logging. Threaded `pruning_config` through 3 context builders and `engine_helpers._resolve_runtime_settings`. Activated via `sweep_config.json` `"pruning": {"enabled": true, "warmup_count": 500, "prune_ratio": 0.3, "batch_size": 2000}`. 35 new tests in `tests/test_autowfo_pruning.py`. Validation: 242 passed, 0 failed across 23 test files. Phase 12 AWF-022 complete; next AWF-023.
- 2026-02-14: AWF-023 cross-timeframe parallel execution completed. Implemented batch-level parallelism in `autowfo batch`: (1) extracted `_run_batch_job_single` reusable, thread-safe per-job function with `threading.Lock` for state mutations (seen_keys check, history append, state write). (2) Created `_run_batch_jobs_parallel` `ThreadPoolExecutor(max_workers=N)` dispatching all jobs concurrently with `as_completed` collection; each job is an independent subprocess via `subprocess.run` (GIL released); supports fail-fast and continue-on-error modes. (3) Modified `_cmd_batch` to branch: `parallel_jobs > 1` parallel path, else sequential (reusing `_run_batch_job_single`). (4) Added `--parallel-jobs N` CLI argument (default=1). 8 new tests in `tests/test_autowfo_cli.py` (5 integration + 3 unit). Validation: 246 passed, 0 failed. Phase 12 complete (AWF-024/021/022/023 all done).
- 2026-02-14: AWF-025 combo stability trend analysis completed. Added 5 trend helper functions to `cross_run.py`: `_linear_slope` (OLS for evenly-spaced series), `_trend_label` (improving/declining/flat classifier with configurable threshold), `_svg_sparkline` (inline SVG polyline with green/red coloring based on slope), `_compute_trend_metrics` (returns trend_direction/slope/return_std/consistency_pct/sparkline). Rewrote `_build_combo_stability` with chronological sort and `trend_points` list per combo. HTML report now shows trend arrow emoji, consistency_%, return_std, and embedded SVG sparkline columns in "Combo Stability Trends" section. Fixed `_write_csv` test helper to use `csv.DictWriter` (was breaking on indicator_list containing commas). 15 new tests. Validation: 261 passed, 0 failed.
- 2026-02-14: AWF-026 regime-aware ranking completed. `ranking.py`: added `regime_weights` to `DEFAULT_RANKING_CONFIG`, `_apply_regime_weight` (per-regime composite_score multiplier), `_top_by_score_per_regime` (groupby regime ranking), `_regime_summary` (per-regime count/avg-return/avg-score); fixed `_resolve_ranking_config` to merge `regime_weights` from input config. `cross_run.py`: added `_parse_regime_from_combo_key`, `_build_per_regime_leaderboard` (groups combo_stability by regime, sorted by avg return descending), `_build_regime_summary` (per-regime count/avg-return/avg-drawdown); payload now includes `per_regime_leaderboard` and `regime_summary`; HTML report has new "Regime Summary" table and "Per-Regime Leaderboard" sections with per-regime sub-tables. 16 new tests (10 ranking + 6 cross_run). Validation: 267 passed, 0 failed. Phase 13 AWF-025/026 complete; next AWF-027.
- 2026-02-14: AWF-027 automated patrol cycle completed. `cli.py`: (1) `_run_patrol_cycle` orchestrates plan/batch/report with error recovery and `continue_on_error` support; sequential batch path uses correct `_run_batch_job_single` keyword-only API (idx/total/job/state/state_path/lock) with caller-level failure handling; parallel path uses `_run_batch_jobs_parallel` with `failed_jobs` return tracking. (2) `_cmd_cron` configurable `--interval` seconds and `--max-cycles` loop with per-cycle OK/partial/fail status logging. (3) `cron` subparser 15+ arguments covering registry/template-config/plan-out/batch-state/report paths + workflow/mode/workers/top-n/parallel-jobs/interval/max-cycles/target-timeframes/target-symbols/timeframe-days. 5 new tests (patrol no-gaps/with-gaps/plan-error, cron single-cycle, parser defaults). Validation: 280 passed, 0 failed. Next AWF-028.
- 2026-02-14: AWF-028 experiment notebook export completed.
- 2026-02-14: Engine decomposition verified at commit `e43fe33` (Gate E passed). 21 verification tests in `tests/test_autowfo_gate_e.py` confirm: (1) all 60+ re-exported callables are `is`-identical to sub-module originals, (2) no missing/extra callables, (3) `DEFAULT_CONFIG` constant identity, (4) sub-modules importable independently (no circular deps), (5) all sub-modules 800 lines, (6) critical signatures (`_run_finalize_pipeline` keyword-only, `_build_completion_output_map` dict contract) stable. AWF-030 complete. Created `scripts/autowfo/notebook.py` with `build_experiment_notebook`: generates 10-cell `.ipynb` (2 markdown + 8 code) including run metadata table, imports, metadata JSON loader, top-10/combo-summary/symbol-summary CSV loaders, leaderboard row display, OOS return/drawdown/composite-score analysis, combo summary statistics with regime distribution, and user notes placeholder. Wired into `engine_finalize._run_finalize_pipeline` after `_persist_run_metadata_and_registry` with non-critical try/except; `completion_outputs` includes `experiment_notebook` path when successful. 30 new tests across helper functions, integration, and finalize wiring. Validation: 310 passed, 0 failed. Phase 13 complete (AWF-025/026/027/028 all done).
- 2026-02-22: Root cause analysis completed for two production-observed re-run issues. (1) `data_end` in `combo_key` invalidates all seen_keys on every run: `_load_or_update_symbol()` always appends new OHLCV candles ??`data_end` advances ??all prior seen_keys have old `data_end` ??0 skips ??full 8,395+ combo re-evaluation. (2) `_get_results_payload()` reads `_latest_top10_path()` (mtime-based) as primary source for Top10, so the historical best from `combo_summary.csv` is never shown unless the latest run file is empty. AWF-106 (stripped_seen_keys) + AWF-107 (dual Top10 display) + AWF-108 (perf micro-opts) planned and **fully implemented** as Phase 17. Key changes: `engine_helpers.py` ??`_strip_data_range_from_combo_key()` + `_build_seen_keys()` dict return + `to_dict(orient='records')` vectorization + `checkpoint_every_n`/`progress_every_n` in `DEFAULT_CONFIG`; `engine_search.py` ??stripped-key skip checks + 200-skip emit throttle; `run_btc_regime_sweep.py` ??`["stripped"]` unpack + configurable lifecycle params; `control_panel.py` ??`_get_results_payload()` dual-path (`top10` all-time + `top10_latest_run`); `results.js` ??`top10Mode` toggle; `i18n.js` ??mode labels. 147 tests passing.
- 2026-02-19: Phase 15 UI redesign progress corrected. AWF-033~037 all fully implemented (TODO statuses were lagging behind reality). AWF-038 UX polish partially done (toast  button animations partial; loading skeleton  confirmation modal  tab transitions  error boundary . Runtime bug fixes applied: (1) `control_panel.py::_start_run()` subprocess PYTHONPATH missing added `env=_env` with `PYTHONPATH=ROOT`; (2) `strategy.py::_coerce_lb()` NaN lookback `None` dict key `KeyError: None` now falls back to first `data_map` key; (3) Top10 cross-run duplicate combos `_pick_top10` fingerprint dedup (backend) + `_rowFingerprint` (frontend); (4) Added freshness bar (green d / amber d / red >7d) + retest button in Results tab. 11/11 control_panel tests pass; 4/4 strategy schema tests pass. Phase 16 backlog (AWF-039~042) added for continuous operation closure.
- 2026-02-19: AWF-038 completed. Implemented remaining UX polish for new control panel: first-load skeletons across Overview/Config/Results/Batch/Coverage/Dashboard tabs, global confirmation modal (wired to high-impact actions such as batch start/cancel/clear/remove, top-10 retest, and log clears), smooth tab transition via Vue transition classes, and tab-level error boundary fallback. Frontend static modules pass `node --check`; backend regression `pytest tests/test_control_panel.py -q` remains green (11/11).
- 2026-02-19: AWF-040 completed. Added cron notification integration in `autowfo/cli.py`: webhook + Telegram dispatch (`--notify-webhook`, `--notify-telegram-token`, `--notify-telegram-chat-id`), Top-N rank-change summary (`NEW` / `UP` / `DOWN` / `SAME`) with persisted snapshot (`artifacts/cron_notify_state.json`), and freshness alert from `artifacts/data_refresh_state.json` when `data_end` is older than 7 days (`--freshness-alert-days`). Added 3 AWF-040 tests and validated with `pytest tests/test_autowfo_cli.py -q` (40 passed).
- 2026-02-19: AWF-041 completed. Added strategy deployment bridge in `scripts/control_panel.py`: `POST /signals/export-top-config` (exports Top combo to `artifacts/live_signal_configs/*.json`), `POST /signals/paper-feedback` (append validated feedback to `artifacts/paper_feedback.ndjson`), and read endpoints `GET /signals/paper-feedback-spec.json` + `GET /signals/paper-feedback.json`. Updated `scripts/control_panel/static/js/results.js` with `Export Top1 Live Config` and feedback spec download actions. Added 4 AWF-041 tests and validated with `pytest tests/test_control_panel.py -q` (18 passed).
- 2026-02-19: AWF-042 completed. Added Monte Carlo advanced analysis closure: `scripts/autowfo/benchmark.py` now provides `compute_monte_carlo_return_stats` (bootstrap mean-return sampling with deterministic seed, P05/P50/P95, CVaR5, positive-probability). `scripts/control_panel.py` adds `GET /results/advanced.json` plus additive helpers for return/drawdown/trade distribution summaries and Monte Carlo payload assembly. `scripts/control_panel/static/js/results.js` adds an "Advanced Analytics (Monte Carlo)" panel (trials/sample-size/seed controls, run action, JSON download, KPI cards). Added AWF-042 tests and validated with `pytest tests/test_autowfo_benchmark.py tests/test_control_panel.py -q` (34 passed).
- 2026-02-19: AWF-043 completed. Closed the paper-feedback operator loop in Results: `scripts/control_panel.py` adds `_paper_feedback_summary` and `GET /signals/paper-feedback-summary.json`; `scripts/control_panel/static/js/results.js` adds a "Paper Feedback Loop" panel with feedback submit form, summary KPI cards (total/latest/mean pnl/win-rate), recent-feedback table, and manual refresh against `/signals/paper-feedback*` APIs. Added tests `test_paper_feedback_summary_metrics` and `test_paper_feedback_summary_empty`; validated with `pytest tests/test_control_panel.py -q` (22 passed).
- 2026-02-19: AWF-044 completed. Added feedback diagnostics layer for operator decisions: `scripts/control_panel.py` now provides `_paper_feedback_diagnostics` and `GET /signals/paper-feedback-diagnostics.json`, aggregating paper feedback by signal-config / action / symbol-timeframe with count, avg/median pnl, win-rate, and top/worst ranking slices. `scripts/control_panel/static/js/results.js` extends Paper Feedback Loop with "Top Signal Configs" and "Action Diagnostics" tables. Added regression test `test_paper_feedback_diagnostics_groups_and_ranking`; validated with `pytest tests/test_control_panel.py -q` (23 passed).
- 2026-02-19: AWF-045 completed. Added feedback-driven recommendation and export workflow: `scripts/control_panel.py` now provides `_paper_feedback_recommendations`, `GET /signals/paper-feedback-recommendations.json`, and `POST /signals/export-feedback-adjusted-config` backed by `_export_feedback_adjusted_signal_config` / `_apply_feedback_adjustment_to_signal_config` (auto/defensive/balanced/offensive profiles with risk multipliers for `tp_stop`/`sl_stop`/`max_hold`). `scripts/control_panel/static/js/results.js` adds recommendation profile/min-samples controls, recommendation table, and "Export Adjusted Config" action in Paper Feedback Loop. Added tests `test_paper_feedback_recommendations_profiles` and `test_export_feedback_adjusted_signal_config_with_recommendation`; validated with `pytest tests/test_control_panel.py -q` (25 passed).
- 2026-02-19: AWF-046 completed. Added feedback recommendation writeback and batch scheduling bridge: `scripts/control_panel.py` now provides `_build_feedback_adjusted_sweep_config`, `_enqueue_feedback_adjusted_batch`, and `POST /signals/enqueue-feedback-adjusted-batch` to generate `artifacts/planned_configs/feedback_*.json` and enqueue run jobs from Results. `scripts/control_panel/static/js/results.js` adds `Enqueue Adjusted Batch` action in Paper Feedback Loop. `scripts/run_btc_regime_sweep.py` adds `_resolve_risk_grid_from_config` so `tp_stops` / `sl_stops` / `max_holds` can be overridden by sweep config. Added tests `test_build_feedback_adjusted_sweep_config_from_signal_payload`, `test_enqueue_feedback_adjusted_batch_creates_config_and_queue_job`, and `test_resolve_risk_grid_from_config_overrides_and_fallback`.
- 2026-02-19: AWF-047 completed. Closed feedback-enqueue observability + risk guardrails + endpoint regression: `scripts/control_panel.py` now clamps `tp_stop/sl_stop/max_hold` in `_build_feedback_adjusted_sweep_config` using `FEEDBACK_SWEEP_RISK_LIMITS`, persists `risk_guardrails` warnings into config payload, and returns warnings through `_enqueue_feedback_adjusted_batch` + `POST /signals/enqueue-feedback-adjusted-batch`. `scripts/control_panel/static/js/results.js` shows enqueue plan metadata (`job/config/warnings`) and provides one-click jump to Batch tab. `scripts/run_btc_regime_sweep.py` now enforces both min/max bounds in `_resolve_risk_grid_from_config` (`tp/sl<=0.2`, `max_hold<=240`). Added tests `test_build_feedback_adjusted_sweep_config_applies_risk_guardrails`, `test_enqueue_feedback_adjusted_batch_returns_guardrail_warnings`, `test_enqueue_feedback_adjusted_batch_endpoint_returns_warnings`, and expanded `test_resolve_risk_grid_from_config_overrides_and_fallback`; validated with `pytest tests/test_control_panel.py -q` (30 passed) and `pytest tests/test_run_btc_regime_sweep.py -q` (10 passed).
- 2026-02-19: AWF-048 completed. Improved feedback-enqueue warning readability and endpoint smoke validation: `scripts/control_panel/static/js/i18n.js` adds feedback enqueue labels; `scripts/control_panel/static/js/results.js` now renders guardrail warnings as human-readable text (field label + inputamped + allowed range), displays `signal_config_path` in enqueue plan card, and localizes enqueue card labels/buttons. Added integration test `tests/test_control_panel.py::test_enqueue_feedback_adjusted_batch_endpoint_smoke_integration` using real `ThreadingHTTPServer` + HTTP POST against `/signals/enqueue-feedback-adjusted-batch` without mocking the core enqueue flow. Validation: `node --check scripts/control_panel/static/js/results.js` and `pytest tests/test_control_panel.py -q` (31 passed).
- 2026-02-19: AWF-049 completed. Consolidated Results feedback/advanced copy to i18n keys and added export endpoint smoke integration: `scripts/control_panel/static/js/i18n.js` now includes advanced/feedback UI labels and action/toast strings; `scripts/control_panel/static/js/results.js` switches feedback/advanced panel labels and feedback-related confirm/toast text to `tr(...)` lookups with fallback, while preserving existing behavior. Added integration test `tests/test_control_panel.py::test_export_feedback_adjusted_config_endpoint_smoke_integration` using real `ThreadingHTTPServer` + HTTP POST against `/signals/export-feedback-adjusted-config` (no core-flow mock), asserting response payload and exported config contents. Validation: `node --check scripts/control_panel/static/js/i18n.js`, `node --check scripts/control_panel/static/js/results.js`, and `pytest tests/test_control_panel.py -q` (32 passed).
- 2026-02-19: AWF-050 completed. Consolidated i18n coverage for shared shell/components/dashboard surfaces: `scripts/control_panel/static/js/app.js` now localizes tab labels, report link, and theme toggle title via i18n keys (with fallback) and eagerly exposes `window._AUTOWFO_L`; `scripts/control_panel/static/js/components.js` localizes Confirm modal defaults, ErrorBoundary messages/toast prefix, StatusBadge labels, and DataTable search/empty/pagination text via i18n keys; `scripts/control_panel/static/js/dashboard.js` localizes panel titles, action buttons, table headers, KPI labels, and dashboard toasts. Added corresponding i18n keys in `scripts/control_panel/static/js/i18n.js`. Validation: `node --check scripts/control_panel/static/js/i18n.js scripts/control_panel/static/js/app.js scripts/control_panel/static/js/components.js scripts/control_panel/static/js/dashboard.js` and `pytest tests/test_control_panel.py -q` (32 passed).
- 2026-02-20: AWF-051/AWF-052 completed. Consolidated remaining tab copy i18n for `scripts/control_panel/static/js/overview.js`, `scripts/control_panel/static/js/config.js`, `scripts/control_panel/static/js/batch.js`, and `scripts/control_panel/static/js/coverage.js` using `L[key] || fallback`; added control-panel endpoint smoke integration for `/coverage/matrix.json`, `/coverage/enqueue`, `/batch/enqueue`, `/batch/queue.json`, and `/batch/remove` in `tests/test_control_panel.py`. Validation: `node --check scripts/control_panel/static/js/i18n.js scripts/control_panel/static/js/overview.js scripts/control_panel/static/js/config.js scripts/control_panel/static/js/batch.js scripts/control_panel/static/js/coverage.js` and `pytest tests/test_control_panel.py -q`.
- 2026-02-20: AWF-053/AWF-054 completed. Added dashboard endpoint smoke integration for `/dashboard/cross_run.json`, `/dashboard/report/generate`, `/dashboard/report` in `tests/test_control_panel.py`; finalized store-layer confirm default i18n consolidation in `scripts/control_panel/static/js/store.js` (`title/message/confirm/cancel` defaults now i18n-backed with fallback). Validation: `pytest tests/test_control_panel.py -q` (37 passed).
- 2026-02-20: AWF-055/AWF-056 completed. Hardened dashboard failure handling by returning structured 500 JSON for `/dashboard/cross_run.json` payload errors and expanded regression coverage in `tests/test_control_panel.py` for payload failure (500), report missing artifact (404), report generation failures (500), `global_leaderboard` payload contract, and summary consistency across `/dashboard/report/generate`, `artifacts/cross_run_report.json`, and `/dashboard/cross_run.json` (including invalid JSON body fallback). Validation: `pytest tests/test_control_panel.py -q` (43 passed).
- 2026-02-20: AWF-057/AWF-058/AWF-059 completed. Refactored dashboard integration tests in `tests/test_control_panel.py` with shared server/client harness (`_serve_handler_connection`), reusable cross-run payload schema assertions (`_assert_dashboard_cross_run_payload_schema`), and reusable report HTML structure assertions (`_assert_dashboard_report_html_structure`), then migrated dashboard smoke/failure/consistency tests to shared helpers. Validation: `pytest tests/test_control_panel.py -q` (43 passed).
- 2026-02-20: AWF-060/AWF-061/AWF-062 completed. Expanded shared endpoint smoke harness usage to signals/coverage/batch integration tests in `tests/test_control_panel.py`; introduced explicit cross-run payload schema version (`autowfo.cross_run_payload/v1`) in `scripts/autowfo/cross_run.py`; enforced schema-version contract in dashboard/report consistency tests for generated artifact payloads. Validation: `pytest tests/test_control_panel.py -q` (43 passed) and `pytest tests/test_autowfo_cross_run.py -q` (27 passed).
- 2026-02-20: AWF-063/AWF-064/AWF-065 completed. Added resilient dashboard `/dashboard/cross_run.json` cached-payload fallback to `artifacts/cross_run_report.json` when live aggregation fails; introduced `normalize_cross_run_payload` + `load_cross_run_payload` in `scripts/autowfo/cross_run.py` for legacy/incomplete payload compatibility; and added regression coverage for fallback success/failure + legacy normalization in `tests/test_control_panel.py` and `tests/test_autowfo_cross_run.py`. Validation: `pytest tests/test_control_panel.py -q` (45 passed) and `pytest tests/test_autowfo_cross_run.py -q` (29 passed).
- 2026-02-20: AWF-066/AWF-067/AWF-068 completed. Added report-serving resilience on control panel: `GET /dashboard/report` now falls back to cached payload rendering when generation fails; `POST /dashboard/report/generate` now returns cache-backed success with persisted fallback HTML and `cache_fallback` metadata; and live `/dashboard/cross_run.json` path now normalizes payload via `normalize_cross_run_payload` for consistent contract behavior. Added regression tests in `tests/test_control_panel.py` and `tests/test_autowfo_cross_run.py` including `top_n` bound checks. Validation: `pytest tests/test_control_panel.py -q` (47 passed) and `pytest tests/test_autowfo_cross_run.py -q` (30 passed).
- 2026-02-20: AWF-069/AWF-070/AWF-071 completed. Hardened schema migration and fallback observability: `scripts/autowfo/cross_run.py::normalize_cross_run_payload` now always emits v1 schema while preserving legacy `source_schema_version`; `scripts/control_panel.py` now centralizes cache fallback metadata via `_cross_run_cache_fallback_meta`; and regression tests now assert schema migration and fallback metadata fields on dashboard cross-run/report paths. Validation: `pytest tests/test_control_panel.py -q` (47 passed) and `pytest tests/test_autowfo_cross_run.py -q` (31 passed).
- 2026-02-20: AWF-072/AWF-073/AWF-074 completed. Added dashboard `top_n` guardrail consistency: introduced `_normalize_top_n` in `scripts/control_panel.py` with default/min/max bounds and wired it through cross-run payload build, cached payload load, report generation, and report-generate endpoint parsing; added `tests/test_control_panel.py::test_normalize_top_n_bounds_and_defaults` regression. Validation: `pytest tests/test_control_panel.py -q` (48 passed) and `pytest tests/test_autowfo_cross_run.py -q` (31 passed).
- 2026-02-20: AWF-075/AWF-076/AWF-077 completed. Added strict payload contract enforcement and fallback hardening: introduced `validate_cross_run_payload` in `scripts/autowfo/cross_run.py` and applied validation across dashboard live/cached/report paths in `scripts/control_panel.py`; expanded regressions in `tests/test_autowfo_cross_run.py` and `tests/test_control_panel.py` for validator pass/fail and contract-invalid live payload fallback flows. Validation: `pytest tests/test_control_panel.py -q` (50 passed) and `pytest tests/test_autowfo_cross_run.py -q` (33 passed).
- 2026-02-20: AWF-078/AWF-079/AWF-080 completed. Added machine-readable validation error taxonomy and endpoint propagation: `scripts/autowfo/cross_run.py` now raises `CrossRunPayloadValidationError` with stable codes (`invalid_json`, `missing_summary_keys`, etc.); `scripts/control_panel.py` now propagates `error_code` in 500 responses and `reason_code` in cache-fallback metadata; regressions expanded in `tests/test_autowfo_cross_run.py` and `tests/test_control_panel.py` for code-level assertions. Validation: `pytest tests/test_control_panel.py -q` (50 passed) and `pytest tests/test_autowfo_cross_run.py -q` (33 passed).
- 2026-02-21: AWF-081/AWF-082/AWF-083 completed. Added endpoint-level payload-source and dual-failure observability: `scripts/control_panel.py` now tags cross-run/report-generate responses with `payload_source` (`live`/`cache_fallback`), enriches cache fallback metadata with structured `live_error`, and emits `cache_error`/`cache_error_code` when both live and cache paths fail; `scripts/autowfo/cross_run.py::load_cross_run_payload` now emits typed `payload_file_missing` instead of generic missing-file errors. Regressions expanded in `tests/test_control_panel.py` and `tests/test_autowfo_cross_run.py` for source-tagging and dual-failure code assertions. Validation: `pytest tests/test_control_panel.py -q` (50 passed) and `pytest tests/test_autowfo_cross_run.py -q` (34 passed).
- 2026-02-21: AWF-084/AWF-085/AWF-086 completed. Delivered dashboard observability UX closure: `scripts/control_panel/static/js/dashboard.js` now shows payload source telemetry (live vs cache fallback), fallback reason/source/time metadata, and structured diagnostics panel for `live_error`/`cache_error`; also fixed dashboard data binding to canonical payload keys (`global_leaderboard`, `run_history`) with compatibility fallbacks. `scripts/control_panel/static/js/api.js` now throws structured API errors carrying `status`, `error_code`, `cache_error_code`, and nested diagnostics, consumed by dashboard toasts/panels; `scripts/control_panel/static/js/i18n.js` extended with telemetry/diagnostics keys; `tests/test_control_panel.py` expanded to assert `live_error/cache_error` type-level contract fields. Validation: `node --check scripts/control_panel/static/js/api.js`; `node --check scripts/control_panel/static/js/dashboard.js`; `node --check scripts/control_panel/static/js/i18n.js`; `pytest tests/test_control_panel.py -q` (50 passed); `pytest tests/test_autowfo_cross_run.py -q` (34 passed).
- 2026-02-21: AWF-087/AWF-088/AWF-089 completed. Standardized dashboard failure envelopes and refreshed operator controls: `scripts/control_panel.py` now emits dashboard 500 payloads through `_dashboard_error_payload` with stable `endpoint` and `error_utc` fields, while cache fallback metadata includes endpoint aliasing; `scripts/control_panel/static/js/dashboard.js` now adds auto-refresh toggle + polling interval controls and prefers backend `endpoint/error_utc` in diagnostics; `scripts/control_panel/static/js/api.js` now preserves `endpoint/error_utc` in structured API errors. Regressions in `tests/test_control_panel.py` now assert `endpoint/error_utc` and fallback endpoint metadata contract fields. Validation: `node --check scripts/control_panel/static/js/api.js`; `node --check scripts/control_panel/static/js/dashboard.js`; `node --check scripts/control_panel/static/js/i18n.js`; `pytest tests/test_control_panel.py -q` (50 passed); `pytest tests/test_autowfo_cross_run.py -q` (34 passed).
- 2026-02-21: AWF-090/AWF-091/AWF-092 completed. Added request-scoped correlation and diagnostics exportability for dashboard operations: `scripts/control_panel.py` now generates and propagates `request_id` for `/dashboard/cross_run.json` and `/dashboard/report/generate` across live/fallback/error responses (including fallback metadata), `scripts/control_panel/static/js/api.js` now preserves `request_id` in structured API errors, and `scripts/control_panel/static/js/dashboard.js` now surfaces request ID in telemetry/diagnostics with one-click JSON copy for incident sharing. Regressions in `tests/test_control_panel.py` now assert request_id shape and cross-field correlation (`cache_fallback.request_id == request_id`) across success/fallback/error paths. Validation: `node --check scripts/control_panel/static/js/api.js`; `node --check scripts/control_panel/static/js/dashboard.js`; `node --check scripts/control_panel/static/js/i18n.js`; `pytest tests/test_control_panel.py -q` (50 passed); `pytest tests/test_autowfo_cross_run.py -q` (34 passed).
- 2026-02-14: Phase 14 Production Hardening complete. AWF-030 (Gate E closure, 21 tests), AWF-031 (e2e smoke test, 11 tests across 4 integration seams: Data->Context, Context->Windows, Evaluation, Finalize->Artifacts), AWF-032 (cron patrol validation, 5 tests: state timestamps, target filtering, multi-cycle log, max_jobs cap, batch failure recovery). All exit criteria met: Gate E signed off, e2e smoke test automated, patrol cycle validated.

- 2026-02-24: Project status synchronization + upload batch completed. Consolidated large pending changes across AUTOWFO engine split (`engine_search.py` / `engine_finalize.py` / `engine_report.py`), control-panel modular frontend (`api.js`, `i18n.js`, `components.js`, tab modules), and protocol/docs updates (`split_protocol.yaml`, `strategy_schema.json`, `AUTOWFO_TODO.md`, `AGENTSMD_INTEGRATION.md`). Validation run for this upload batch: `pytest tests/test_autowfo_cli.py tests/test_autowfo_cross_run.py tests/test_control_panel.py tests/test_autowfo_e2e.py tests/test_autowfo_gate_e.py -q` -> `172 passed`.
- 2026-02-25: Design audit completed. Phase 18 (Technical Debt) and Phase 19 (UX Redesign) defined with AWF-109嚚WF-124. Two confirmed correctness bugs identified via code inspection: (1) `control_panel.DEFAULT_CONFIG` missing 8 keys vs `engine_helpers.DEFAULT_CONFIG` ??UI generates incomplete configs silently (AWF-109). (2) Control panel Run button calls `run_btc_regime_sweep.py` directly, bypassing `python -m autowfo` ??all AWF-105/106/107/108 CLI guards inactive for single runs (AWF-110). UX audit revealed 6-tab layout mirrors system internals rather than user workflow (Config?un?esults?ill Gaps?epeat); AWF-118嚚WF-124 define targeted redesign. `AUTOWFO_TODO.md` updated with 16 new task entries, Phase 18/19 Execution Phase descriptions, and updated Current Focus Window.
- 2026-02-27: **Architecture V2 direction approved.** Role shift: planning/architecture responsibilities assigned to Claude (Sonnet 4.6); implementation delegated to other AI agents. Key decisions confirmed: (1) Cross-asset trigger+action model (trigger asset may differ from action asset); (2) Cross-timeframe signals (T1 ??T2, both directions); (3) Indicator plugin system (`indicators/` auto-discovery directory); (4) Experiment as fundamental testable unit (JSON schema with trigger/action/risk/wf layers); (5) Two-layer storage ??SQLite per-run (fast writes) + DuckDB analytics (cross-run OLAP); (6) Mode C ??both hypothesis-driven (Mode A) and pool-discovery (Mode B) co-exist; (7) Fresh start on existing artifacts acceptable; (8) Freqtrade bridge deferred; (9) vectorbt retained as compute engine; (10) Control panel remains sole user interface. Full spec written to `plans/AUTOWFO_ARCHITECTURE_V2.md`. Phases 20-24 (AWF-125~145) added to MASTER_PLAN. AWF-113~116 decomposition debt deferred to parallel housekeeping.
- 2026-02-26: Phase 18 (AWF-109~117) and Phase 19 (AWF-118~124) implementation complete. AWF-109: `DEFAULT_CONFIG` single-source (control_panel.py imports from engine_helpers). AWF-110: Run button now calls `python -m autowfo run` via CLI. AWF-111: Cross-platform `_python_path()` helper (Windows/Linux/macOS/fallback). AWF-112: `constants.py` UTF-8 normalization (direct strings, HTML escape at render layer). AWF-118: Config instant validation hints for walk-forward parameters. AWF-119: Quick Test panel moved from Overview to Config (collapsed). AWF-120: Overview operations hub with smart next-action guidance card. AWF-121: Unified execution entry ??combo/refine mode selector on Overview Start Run; Coverage "Start Batch" removed. AWF-122: Coverage "Fill All Gaps" one-click flow + `POST /coverage/fill-all-gaps` endpoint. AWF-123: Results "蝎曆耨" button sets `store.pendingRunMode` and navigates to Overview. AWF-124: Dashboard "銝活?湔" freshness label + "撘瑕??渡?" rename. AWF-117: Archived AWF-000~063 to `plans/AUTOWFO_TODO_ARCHIVE.md`; TODO.md slimmed to AWF-064+; Phase 16 summary condensed. Remaining debt: AWF-113/114 (control_panel.py / cli.py decomposition), AWF-115/116 (engine private exports / sys.path).

- 2026-02-28: Phase 25 structural debt closure completed (AWF-113~116). `scripts/control_panel.py` and `autowfo/cli.py` are now thin facades; responsibility surfaces split into `control_panel_*` and `autowfo/commands/*`; `scripts/autowfo/engine.py` now exports only `DEFAULT_CONFIG`; package-path cleanup landed (`pyproject.toml` include covers `autowfo*` + `scripts*`, plus `scripts/__init__.py` and `scripts/autowfo/__init__.py`), and runtime `sys.path.insert` hack was removed.

- 2026-03-01: Phase 20-29 全部交付，Architecture V2 feature-complete。
- 2026-03-01: Phase 20-33 全部交付，系統進入生產就緒狀態。
- 2026-03-01: Phase 34 完成交付，系統達成長期無人值守運行之營運就緒狀態。
- 2026-03-01: Phase 35 完成交付（AWF-174~176）：新增 `autowfo export-signal` 將 DuckDB 最佳策略導出為 live signal config；導入 paper position 狀態追蹤（`paper_positions.json` + `/paper/*` API）；`/paper/close` 自動寫入 analytics paper feedback，leaderboard 新增 nullable `paper_avg_pnl` 欄位，形成 WFO→paper→analytics 回饋閉環。
- 2026-03-01: Phase 36 完成交付（AWF-177~179）：paper feedback 新增 `(experiment_id, close_ts)` 去重 idempotency、paper position 狀態機加入重複開倉與無倉平倉防呆（API 回傳 400）；完成 vectorbt core 與新 pandas/NumPy 環境兼容修補（`ParamLoc` object-key normalization、`is_deep_equal` callable 比較、`dir` 穩定化），並通過完整回歸 `pytest tests -q --tb=short`（1426 passed, 0 failed）。
- 2026-03-01: Phase 37 完成交付（AWF-180~182）：依賴版本鎖定為 `pandas>=2,<3`、`numpy<2.4`、`numba<0.64`；新增 `autowfo schedule-signals` daemon（strategy 變更時自動 close/open + export）；`autowfo cron --scheduler-mode` 新增 `enable_signal_scheduling` opt-in tick，並完成文件凍結與回歸驗證。
- 2026-03-01: Phase 38 完成交付（AWF-183~185）：新增通知派發層 `notifier.py`（webhook + Telegram optional）與事件型別（STRATEGY_CHANGED/POSITION_OPENED/POSITION_CLOSED/PATROL_ANOMALY/PNL_THRESHOLD_HIT）；paper trading 升級為多策略並行（SignalScheduler top-N 預設 3，新增 `/paper/portfolio.json` unrealized PnL 視圖）；signal scheduler 加入重試與指數退避（上限 30s）並在重試耗盡時派發 PATROL_ANOMALY，完成回歸 `pytest tests -q --tb=short`（1439 passed, 0 failed）。
- 2026-03-12: Phase 40 完成交付（AWF-193~198）：AUTOWFO runtime 與 control panel namespace 收斂到 `autowfo.*`；`scripts.autowfo.*` 與 `scripts.control_panel*` 退出產品級 import surface；control panel 正式以 `python -m autowfo.control_panel` 啟動；`pyproject.toml` 僅打包 `vectorbt*` + `autowfo*` 並分發 packaged static assets；README、MASTER_PLAN、TODO 與 AWF 報告同步完成收尾。
- 2026-03-13: Phase 41 完成交付（AWF-199~204）：新增 `autowfo.control_panel.runtime` 統一路徑、process、data-refresh、scheduler 狀態；control panel 啟動入口支援 `--host/--port/--root/--artifacts-dir` 與環境變數覆寫；既有路由模組透過 alias/runtime 同步維持相容；README、RUNBOOK、MASTER_PLAN、TODO、AWF 報告與完整回歸同步完成收尾。
- 2026-03-13: Phase 42 完成交付（AWF-205~210）：新增 `autowfo.storage_contract` 統一 storage schema-version 常數；`run_meta.json`、scheduler queue、paper position、signal scheduler state 與 analytics DuckDB metadata 全部帶入顯式版本標記；legacy payload 透過 reader normalization 保持可讀；MASTER_PLAN、TODO、archive 與 AWF 報告同步完成收尾。
- 2026-03-13: Phase 43 完成交付（AWF-211~216）：新增 `autowfo.storage_ops` 作為 storage validation / migration / analytics rebuild 核心；CLI 新增 `doctor` 與 `storage validate|migrate|rebuild-analytics`；control panel Overview 新增 storage health 摘要並暴露 `/ops/storage-health.json`；README、RUNBOOK、MASTER_PLAN、TODO、archive 與 AWF 報告同步完成收尾。
- 2026-03-14: Evidence-integrity risk formally escalated into Phase 44（AWF-217~224）。新結論：root-level `artifacts/` 共享工作區會破壞單 run provenance，run-specific 檔名不足以保證單 run 真相；後續方向改為 run isolation、shared-view derivation、legacy purge，以及只在新制度下重跑決策相關 campaign。MASTER_PLAN、TODO、PHASE44_SPEC、RUNBOOK 先行完成文件凍結。
