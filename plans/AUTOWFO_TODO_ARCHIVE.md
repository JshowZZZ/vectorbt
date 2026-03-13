# AUTOWFO TODO Archive

> Phase 40 completion items (`AWF-193`~`AWF-198`) are archived at the end of this file.

> Completed items from Phase 1–15 (AWF-000~AWF-063). Archived from `AUTOWFO_TODO.md` on 2026-02-26.
> Active backlog starts at AWF-064 in `AUTOWFO_TODO.md`.

## Archived Backlog (Phase 1–15)

| ID | Priority | Status | Owner | Task | Deliverable | Exit Criteria |
|---|---|---|---|---|---|---|
| AWF-000 | P-1 | done | JshowZZZ + AI | Monolith decomposition extract `run_btc_regime_sweep.py` core logic into modules | `scripts/autowfo/split.py`, `metrics.py`, `strategy.py`, `artifacts.py`, `ranking.py`, `search.py`; main script becomes thin orchestrator | Each module importable + testable independently; sweep script still produces identical results |
| AWF-003 | P0 | done | JshowZZZ + AI | Extract + freeze strategy spec schema from `INDICATOR_META/REGIME_NAME_MAP` | `plans/protocols/strategy_schema.json` + JSON Schema validator | Invalid specs fail fast; all 13 indicators + 8 regimes representable; adding a new indicator only requires config change |
| AWF-002 | P0 | done | JshowZZZ + AI | Extract + freeze metric contract from `_calc_pf_series/_aggregate_*` | `plans/protocols/metric_contract.yaml` + `metrics.py` module + tests | All IS/OOS metric names and formulas frozen; cross-run comparability guaranteed |
| AWF-004 | P0 | done | JshowZZZ + AI | Extract + freeze artifact schema; add config hash + data fingerprint | `plans/protocols/artifact_contract.yaml` + artifact writer module | Every run emits config SHA256, data range hash, reproducible metadata |
| AWF-001 | P0 | done | JshowZZZ + AI | Extract + freeze split protocol from `_build_walk_forward_slices()` | `plans/protocols/split_protocol.yaml` + `split.py` module + unit tests | Schema covers train/valid/test, horizons, overlap, anchored vs rolling modes |
| AWF-005 | P1 | done | JshowZZZ + AI | Refactor orchestration pipeline into modular AUTOWFO engine | `scripts/autowfo/engine.py` using frozen protocol modules | End-to-end run from spec to leaderboard using modular pipeline |
| AWF-002b | P1 | done | JshowZZZ + AI | Add risk-adjusted + stability metrics to metric module | Extended `metrics.py`: `oos_sharpe_like`, `oos_return_std`, `oos_positive_segment_ratio`, `oos_low_trade_segment_ratio`, `oos_low_trade_penalty`; updated `metric_contract.yaml` | New stability/risk/low-trade metrics computable and contract-validated |
| AWF-006 | P1 | done | JshowZZZ + AI | Implement composite ranking function using AWF-002b metrics | `ranking.py`: composite score (return + stability + risk-adjust drawdown low-sample penalty); legacy mode preserved; default = composite; weights configurable via `sweep_config.json` and wired into search/finalize/leaderboard paths | Top-N selection now uses composite by default; legacy vs composite A/B comparison possible via config |
| AWF-007 | P1 | done | JshowZZZ + AI | Legacy vs composite paired comparison + 3-axis diagnostic | Added ranking-mode paired comparison artifacts in baseline archive: `ranking_mode_comparison.json` + `ranking_mode_comparison.html`; includes fixed schema, paired rows, and 3-axis diagnostic (strategy quality / sample sufficiency / combo scarcity) | Report machine-readable and HTML-readable; objective same-window comparison without subjective judgment |
| AWF-008 | P1 | done | | Two-stage search (coarse focused) | Already in `run_btc_regime_sweep.py` (`combo` + `refine` modes) | Working; to be extracted into `search.py` during AWF-000 |
| AWF-001b | P1 | done | JshowZZZ + AI | Add true WFO mode (per-window re-optimization) alongside anchored mode | `split.py` extension + engine integration | Can run both anchored eval and true WFO; results comparable |
| AWF-013 | P1 | done | JshowZZZ + AI | Multi-process parallelization for combo evaluation | `eval_combo` extracted to pure function + `ProcessPoolExecutor` with centralized IO | 3-worker parallel run produces bit-identical results to single-thread; x2.5 speedup measured |
| AWF-009 | P1 | done | JshowZZZ + AI | Add run registry (history + diff between runs) | Experiment index + coverage map across symbols/timeframes | Can see which symbol/timeframe combinations have been tested and which remain |
| AWF-010 | P1 | done | JshowZZZ + AI | Add one-command execution entrypoint | CLI command wrapping full pipeline | `python -m autowfo run --config experiment.yaml` works end-to-end |
| AWF-014 | P1 | done | JshowZZZ + AI | Batch runner sequential multi-config execution with preflight checks | `autowfo batch --plan batch_plan.json` CLI subcommand + batch orchestrator | 3-config batch completes unattended; registry accumulates; crash-restart skips completed jobs via seen_keys |
| AWF-015 | P1 | done | JshowZZZ + AI | Coverage planner auto-generate batch plan from untested pairs | `autowfo plan` CLI subcommand reading `run_registry.json` coverage gaps | Planner output feeds directly into `autowfo batch`; `--max-jobs N` limits scope |
| AWF-016 | P1 | done | JshowZZZ + AI | Cross-run dashboard aggregate analysis across accumulated runs | `autowfo report` CLI subcommand producing `artifacts/cross_run_report.html` | Coverage matrix + combo stability + global leaderboard from  runs |
| AWF-017a | P1 | done | JshowZZZ + AI | Control panel architecture refactor front/back separation, Tab navigation, CSS upgrade | `scripts/control_panel/` with `static/` assets, modular JS, Tab-based layout | Panel serves from file-based static assets; new tab addable without touching Python |
| AWF-017b | P1 | done | JshowZZZ + AI | Batch queue UI queue table, progress display, cancel buttons | Batch panel in control panel with enqueue/start/cancel/clear actions | Queue table live-refreshes; can enqueue config and start batch from browser |
| AWF-017c | P1 | done | JshowZZZ + AI | Coverage map UI timeframe/symbol matrix, one-click scheduling | Coverage tab with color-coded grid and click-to-enqueue interaction | Matrix shows tested/untested/queued; click adds to batch queue |
| AWF-017d | P1 | done | JshowZZZ + AI | Cross-run dashboard UI + run history timeline, global leaderboard | Dashboard tab with run history table, combo stability chart, aggregated KPIs | Registry data browsable;  runs produce stability trend visualization |
| AWF-011 | P1 | done | JshowZZZ + AI | Add regression tests for split and ranking invariants | Test suite additions | CI/local tests catch protocol regressions |
| AWF-012 | P1 | done | JshowZZZ + AI | Add operational playbook | Runbook doc | New run can be operated without notebook |
| AWF-018 | P1 | done | JshowZZZ + AI | Engine secondary decomposition split 4850-line `engine.py` by responsibility | `engine_helpers.py`(896L), `engine_runtime.py`(732L), `engine_report.py`(570L), `engine_search.py`(1589L), `engine_finalize.py`(1125L), `engine.py` re-export(121L) | All sub-modules 600 lines; 186/186 tests pass; imports via `engine.py` re-export unchanged |
| AWF-019 | P1 | done | JshowZZZ + AI | Fill coverage gaps expand registry to 1h/2h/4h + ETH/BNB/SOL (9 pairs) | `cli.py` plan --target-timeframes/--target-symbols/--timeframe-days + `_compute_coverage_gaps` + `registry._build_coverage_map` target dims + batch plan `artifacts/batch_plan_gap_fill.json` (4 jobs) | Plan generates 4 gap jobs (1h x3 + 2h SOL); 194/194 tests pass; execute `autowfo batch` to fill actual data |
| AWF-020 | P1 | done | JshowZZZ + AI | Baseline strategy benchmarks add buy-and-hold + random-entry as reference rows | `benchmark.py` (pure BH/random fns) + engine_finalize BH injection + `registry._build_run_entry` propagation + `cross_run.py` alpha/benchmark KPIs + leaderboard 3 new columns | Leaderboard includes BH/random baselines with alpha_vs_bh; summary KPIs show avg benchmarks; 16 new tests pass |
| AWF-021 | P2 | done | JshowZZZ + AI | Expand indicator universe add CCI, Williams %R, ADX, TRIX, DPO, EFI, VWMA, UltOsc, Keltner, Donchian, PPO, Choppiness to schema | `strategy_schema.json` expansion + data.py precompute + strategy.py apply + pipeline wiring (25 indicators total) | New indicators addable via config-only; C(N,2..4) search space 000 |
| AWF-022 | P2 | done | JshowZZZ + AI | Combo intelligent pruning early-stopping + warm-start from previous top-N | `pruning.py` module + `engine_search.py` wiring | Search time reduced 0% vs brute-force on equivalent space; top-N quality no regression |
| AWF-023 | P2 | done | JshowZZZ + AI | Cross-timeframe parallel execution batch-level parallelism beyond combo-level | `cli.py` batch runner: `_run_batch_job_single` + `_run_batch_jobs_parallel` + `--parallel-jobs N` | Batch throughput ? vs sequential per-timeframe |
| AWF-024 | P2 | done | JshowZZZ + AI | Validation set train/validation/test 3-way split protocol | `split_protocol.yaml` + `split.py` extension + engine wiring | Validation segment used for hyperparameter selection; test segment for final evaluation only |
| AWF-025 | P2 | done | JshowZZZ + AI | Combo stability trend analysis time-series visualization per combo across windows | `cross_run.py` trend helpers (linear slope, sparkline SVG, consistency %) + dashboard integration | Dashboard shows per-combo performance trajectory with trend arrows and sparklines |
| AWF-026 | P2 | done | JshowZZZ + AI | Regime-aware ranking conditional weighting by market regime | `ranking.py` regime-conditional mode (`_apply_regime_weight`, `_top_by_score_per_regime`, `_regime_summary`) + `cross_run.py` per-regime leaderboard/summary sections + HTML report | Ranking distinguishes regime-specific performance; per-regime leaderboard and summary views in report |
| AWF-027 | P2 | done | JshowZZZ + AI | Automated patrol cycle `autowfo cron` for plan/batch/report loop | `autowfo cron` CLI subcommand: `_run_patrol_cycle` (plan/batch/report orchestration with error recovery), `_cmd_cron` (interval/max-cycles loop with cycle logging), cron subparser (15+ args incl. interval/max-cycles/parallel-jobs/continue-on-error); sequential batch uses correct `_run_batch_job_single` calling convention with caller-level error handling | Unattended daily cycle with notification on anomaly/completion |
| AWF-028 | P2 | done | JshowZZZ + AI | Experiment notebook export auto-generate reproducible Jupyter notebook per run | `scripts/autowfo/notebook.py`: `build_experiment_notebook` (10-cell .ipynb with metadata table, CSV loaders, OOS analysis, combo stats, leaderboard row, notes placeholder); wired into `engine_finalize._run_finalize_pipeline` after metadata persist with non-critical error handling; completion_outputs includes `experiment_notebook` path | Each run emits `.ipynb` with full analysis code and inline results |
| AWF-030 | P1 | done | JshowZZZ + AI | Gate E closure bit-identical engine decomposition verification + changelog | 21 identity/completeness/isolation/line-count/signature tests in `tests/test_autowfo_gate_e.py`; Gate E checklist fully signed off | Gate E all  engine decomposition verified at commit `e43fe33` |
| AWF-031 | P1 | done | JshowZZZ + AI | End-to-end smoke test lightweight pipeline integration test | `tests/test_autowfo_e2e.py`: 11 tests across 4 integration seams (1) TestDataToContext: 6 tests (synthetic OHLCV `_prepare_timeframe_context` 40+ context keys/indicator maps), (2) TestWalkForwardWindows: 2 tests (context 6-tuple windows), (3) TestEvaluationSmoke: 1 test (context + task `evaluate_combo_task` metrics result dict), (4) TestFinalizeArtifacts: 2 tests (mock-based finalize pipeline leaderboard/metadata/registry/snapshot artifacts + empty combo warning path) | Pipeline breakage caught by automated test without real data |
| AWF-032 | P1 | done | JshowZZZ + AI | Cron patrol validation verify patrol cycle with synthetic data | 5 new tests in `tests/test_autowfo_cli.py`: (1) `test_patrol_cycle_state_timestamps` ISO timestamp fields in cycle result, (2) `test_patrol_cycle_target_filtering` `_compute_coverage_gaps` target-based planning, (3) `test_cmd_cron_multi_cycle_log` 3-cycle log accumulation with mocked sleep, (4) `test_patrol_cycle_max_jobs_limits` job cap enforcement, (5) `test_patrol_cycle_batch_failure_continue_on_error` partial failure + report attempt | cron cycle state tracking and report output verified |
| AWF-033 | P1 | done | JshowZZZ + AI | UI redesign design system + dark theme + Vue 3 + Tailwind setup | `static/index.html`, `static/css/app.css`, `static/js/store.js`, `static/js/api.js`, `static/js/i18n.js`, `static/js/components.js`; Tailwind Play CDN + Vue 3 ESM CDN; dark/light theme toggle; CSS custom properties; responsive layout | Dark-themed control panel renders correctly; theme toggle works; old UI preserved in `static_legacy/` |
| AWF-034 | P1 | done | JshowZZZ + AI | UI redesign layout + tab navigation rebuild | Top nav bar with logo + theme toggle; icon-based tab bar (6 tabs); responsive sidebar fold; all tabs mount correctly | Tab navigation works; layout responsive on desktop/mobile |
| AWF-035 | P1 | done | JshowZZZ + AI | UI redesign Overview + Config + Results tabs | Overview: KPI cards, progress display, quick actions, test panel. Config: grouped form (filters/risk settings). Results: filterable/sortable tables, charts, CSV export, Top-10 dedup, freshness bar, retest button. | All original control/results/config features preserved in new UI |
| AWF-036 | P1 | done | JshowZZZ + AI | UI redesign Batch Queue tab | Status badges, inline progress bars, terminal-style log panel, enqueue/start/cancel/clear actions | Batch queue fully operational from new UI |
| AWF-037 | P1 | done | JshowZZZ + AI | UI redesign Coverage + Dashboard + History tabs | Coverage: heatmap matrix with click-to-enqueue. Dashboard: cross-run KPIs, leaderboard, combo stability, regime summary. History: run timeline. | All analytics features working in new UI |
| AWF-038 | P1 | done | JshowZZZ + AI | UI redesign UX polish | Toast notifications  loading skeletons  confirmation modals  button hover/active animations  smooth tab transitions  error boundary | Professional UX with clear feedback on all user actions |
| AWF-039 | P2 | done | JshowZZZ + AI | Automatic OHLCV refresh and freshness plumbing for Results | `scripts/autowfo/data.py::refresh_ohlcv_cache`; control-panel refresh thread/state; Results payload `data_end`; `refresh_data=1` retest hook | Results freshness/data_end are updated automatically; regression tests for data + control panel pass |
| AWF-040 | P2 | done | JshowZZZ + AI | Cron notifications for Top-N changes and stale data | `autowfo/cli.py` cron supports Webhook/Telegram dispatch, Top-N diff alerts, freshness>7d alerts, and notify state tracking | Unattended patrol can notify on ranking drift and stale data without manual checks |
| AWF-041 | P2 | done | JshowZZZ + AI | Top-combo export + paper-feedback API loop | Added `/signals/export-top-config`, paper-feedback submit/spec/log endpoints, and Results-tab wiring | Top combo can be exported to live-signal config and paper feedback can be captured end-to-end |
| AWF-042 | P2 | done | JshowZZZ + AI | Monte Carlo analytics for Results tab | Added `compute_monte_carlo_return_stats`, `/results/advanced.json`, Results-tab controls/cards, and JSON download | Results now includes Monte Carlo distribution metrics (P05/P50/P95/CVaR) with downloadable payload |
| AWF-043 | P2 | done | JshowZZZ + AI | Paper Feedback Loop summary panel | Added `_paper_feedback_summary` + `/signals/paper-feedback-summary.json` and Results UI summary cards/table | Operators can see paper-feedback volume, PnL summary, and latest feedback state in one place |
| AWF-044 | P2 | done | JshowZZZ + AI | Paper-feedback diagnostics breakdown | Added diagnostics endpoint + UI blocks for top signal configs and action diagnostics | Feedback can be analyzed by config/action/symbol-timeframe for quick root-cause review |
| AWF-045 | P2 | done | JshowZZZ + AI | Feedback-driven recommendations and adjusted-config export | Added recommendation endpoint/profile controls and `/signals/export-feedback-adjusted-config` | Operators can export recommendation-adjusted config directly from Results |
| AWF-046 | P2 | done | JshowZZZ + AI | Enqueue adjusted batch from feedback recommendations | Added adjusted sweep-config builder + enqueue endpoint + Results action wiring | Recommendation output can be converted to runnable batch jobs with one click |
| AWF-047 | P2 | done | JshowZZZ + AI | Risk guardrails + warning propagation for adjusted enqueue | Added tp/sl/max_hold clamp rules, warning payload, enqueue warnings in UI, and endpoint regressions | Unsafe adjusted configs are clamped and warnings are visible before execution |
| AWF-048 | P2 | done | JshowZZZ + AI | Enqueue-warning i18n and smoke integration | Localized warning copy and added real HTTP smoke integration for enqueue-adjusted endpoint | Warning UX is readable and endpoint contract is regression-protected |
| AWF-049 | P2 | done | JshowZZZ + AI | Results feedback/advanced i18n + export smoke integration | Consolidated Results feedback/advanced copy to i18n and added export endpoint smoke integration | Results panel copy is centralized and export endpoint is integration-tested |
| AWF-050 | P2 | done | JshowZZZ + AI | App shell/shared components/dashboard i18n consolidation | Localized app shell, shared components, dashboard labels/toasts, and added i18n keys/tests | Core shell and dashboard UX copy is centralized in i18n map |
| AWF-051 | P2 | done | JshowZZZ + AI | Remaining tabs i18n consolidation (Overview / Config / Batch / Coverage) | `overview.js`/`config.js`/`batch.js`/`coverage.js` switched to `i18n key + fallback`; unified action/confirm/toast copy via `L` map | Remaining control-panel tabs no longer rely on hardcoded strings; cross-tab wording now centralized and maintainable |
| AWF-052 | P2 | done | JshowZZZ + AI | Control panel endpoint smoke integration expansion | Added real HTTP smoke coverage for `/coverage/matrix.json`, `/coverage/enqueue`, `/batch/enqueue`, `/batch/queue.json`, `/batch/remove` in `tests/test_control_panel.py` | Core queue + coverage endpoints validated end-to-end without mocking handler routing |
| AWF-053 | P2 | done | JshowZZZ + AI | Dashboard endpoint smoke integration expansion | Add real HTTP smoke coverage for `/dashboard/cross_run.json`, `/dashboard/report/generate`, `/dashboard/report` in `tests/test_control_panel.py` | Dashboard API/report generation paths are regression-protected without mocking handler routing |
| AWF-054 | P2 | done | JshowZZZ + AI | Store-layer confirm default i18n consolidation | `store.js` default confirm title/message/confirm/cancel sourced from i18n keys (with fallback), aligned with shared modal behavior | Global confirm defaults are centralized; no hardcoded copy remains in store layer |
| AWF-055 | P2 | done | JshowZZZ + AI | Dashboard failure-path hardening + smoke coverage | Add explicit 500 handling for `/dashboard/cross_run.json`; add smoke coverage for payload failure (500), report missing artifact (404), report generation failure (500) in `tests/test_control_panel.py` | Dashboard endpoints fail safely with deterministic HTTP responses and regression coverage |
| AWF-056 | P2 | done | JshowZZZ + AI | Cross-run payload contract + report consistency regression | Add payload contract checks for `global_leaderboard` and report consistency checks across `/dashboard/report/generate`, `cross_run_report.json`, and `/dashboard/cross_run.json` (including invalid JSON body fallback) | Dashboard/report outputs are schema-stable and summary-consistent across generation/read paths |
| AWF-057 | P2 | done | JshowZZZ + AI | Dashboard smoke integration fixtureization | Introduce shared server/client context manager in `tests/test_control_panel.py` and migrate dashboard integration tests to the shared harness | Dashboard endpoint tests are simpler, less duplicated, and easier to extend |
| AWF-058 | P2 | done | JshowZZZ + AI | Dashboard payload schema assertion helper | Add reusable schema assertions for cross-run payload top-level/summary keys and apply them in dashboard tests | Payload contract regressions are caught consistently across tests |
| AWF-059 | P2 | done | JshowZZZ + AI | Dashboard report HTML structure assertions | Add reusable report-HTML structure assertions and apply to `/dashboard/report/generate` + `/dashboard/report` checks | Report layout regressions are detected via deterministic structure checks |
| AWF-060 | P2 | done | JshowZZZ + AI | Endpoint smoke harness expansion (signals/coverage/batch) | Migrate endpoint smoke tests in `tests/test_control_panel.py` (`signals`, `coverage`, `batch`) to shared `_serve_handler_connection` harness | Endpoint integration tests share one deterministic server/client lifecycle and reduced boilerplate |
| AWF-061 | P2 | done | JshowZZZ + AI | Cross-run payload schema versioning | Add stable `schema_version` field (`autowfo.cross_run_payload/v1`) in `scripts/autowfo/cross_run.py` payload output | Payload consumers can validate schema compatibility explicitly |
| AWF-062 | P2 | done | JshowZZZ + AI | Schema-version regression enforcement | Extend dashboard/report consistency tests to assert payload schema version and reuse schema helper for generated report JSON | Schema version drift is caught across endpoint + artifact paths |
| AWF-063 | P2 | done | JshowZZZ + AI | Dashboard cross-run cached payload fallback | Add `/dashboard/cross_run.json` fallback path to load `artifacts/cross_run_report.json` when live payload build fails | Dashboard endpoint remains available when live aggregation fails but cached payload exists |

## Archived Completion Batch (AWF-113~AWF-158)

> Migrated from `AUTOWFO_TODO.md` during Phase 30 documentation freeze (2026-03-01).

| ID | Phase | Status | Task | Report |
|---|---|---|---|---|
| AWF-113 | 25 | done | `control_panel.py` decomposition | `plans/reports/AWF-113-report.md` |
| AWF-114 | 25 | done | `cli.py` decomposition | `plans/reports/AWF-114-report.md` |
| AWF-115 | 25 | done | `engine.py` facade cleanup | `plans/reports/AWF-115-report.md` |
| AWF-116 | 25 | done | `sys.path` elimination | `plans/reports/AWF-116-report.md` |
| AWF-117 | 18 | done | TODO archival restructuring | `plans/reports/AWF-117-report.md` |
| AWF-118 | 19 | done | Config instant validation | `plans/reports/AWF-118-report.md` |
| AWF-119 | 19 | done | Quick Test relocation | `plans/reports/AWF-119-report.md` |
| AWF-120 | 19 | done | Overview operations hub | `plans/reports/AWF-120-report.md` |
| AWF-121 | 19 | done | Unified execution entry | `plans/reports/AWF-121-report.md` |
| AWF-122 | 19 | done | Coverage fill-all-gaps flow | `plans/reports/AWF-122-report.md` |
| AWF-123 | 19 | done | Results refine shortcut | `plans/reports/AWF-123-report.md` |
| AWF-124 | 19 | done | Dashboard update workflow | `plans/reports/AWF-124-report.md` |
| AWF-125 | 20 | done | Indicator plugin system | `plans/reports/AWF-125-report.md` |
| AWF-126 | 20 | done | Condition operator library | `plans/reports/AWF-126-report.md` |
| AWF-127 | 20 | done | Experiment definition model | `plans/reports/AWF-127-report.md` |
| AWF-128 | 20 | done | Experiment artifact layout | `plans/reports/AWF-128-report.md` |
| AWF-129 | 20 | done | Experiment CRUD backend | `plans/reports/AWF-129-report.md` |
| AWF-130 | 21 | done | Signal composer | `plans/reports/AWF-130-report.md` |
| AWF-131 | 21 | done | Experiment runner | `plans/reports/AWF-131-report.md` |
| AWF-132 | 21 | done | Multi-asset data layer | `plans/reports/AWF-132-report.md` |
| AWF-133 | 21 | done | Dual-direction integration tests | `plans/reports/AWF-133-report.md` |
| AWF-134 | 22 | done | ArtifactStore read/query extension | `plans/reports/AWF-134-report.md` |
| AWF-135 | 22 | done | DuckDB analytics store | `plans/reports/AWF-135-report.md` |
| AWF-136 | 22 | done | Post-run analytics hook | `plans/reports/AWF-136-report.md` |
| AWF-137 | 22 | done | Results/analytics API endpoints | `plans/reports/AWF-137-report.md` |
| AWF-138 | 23 | done | Mode B pool discovery | `plans/reports/AWF-138-report.md` |
| AWF-139 | 23 | done | Scheduler queue | `plans/reports/AWF-139-report.md` |
| AWF-140 | 23 | done | Queue-driven execution | `plans/reports/AWF-140-report.md` |
| AWF-141 | 23 | done | Discovery loop | `plans/reports/AWF-141-report.md` |
| AWF-142 | 24 | done | Experiments CRUD UI | `plans/reports/AWF-142-report.md` |
| AWF-143 | 24 | done | Queue/scheduler panel UI | `plans/reports/AWF-143-report.md` |
| AWF-144 | 24 | done | Discovery trigger UI | `plans/reports/AWF-144-report.md` |
| AWF-145 | 24 | done | Integration smoke tests | `plans/reports/AWF-145-report.md` |
| AWF-146 | 26 | done | `control_panel_legacy` migration | `plans/reports/AWF-146-report.md` |
| AWF-147 | 26 | done | `cli_legacy` migration | `plans/reports/AWF-147-report.md` |
| AWF-148 | 26 | done | `engine_namespace` removal | `plans/reports/AWF-148-report.md` |
| AWF-149 | 27 | done | E2E lifecycle validation | `plans/reports/AWF-149-report.md` |
| AWF-150 | 27 | done | Scheduler graceful stop | `plans/reports/AWF-150-report.md` |
| AWF-151 | 27 | done | Discovery cold-start guard | `plans/reports/AWF-151-report.md` |
| AWF-152 | 27 | done | Structured error codes | `plans/reports/AWF-152-report.md` |
| AWF-153 | 28 | done | E2E leaderboard fix | `plans/reports/AWF-153-report.md` |
| AWF-154 | 28 | done | Analytics tab UI | `plans/reports/AWF-154-report.md` |
| AWF-155 | 29 | done | Real-data smoke test | `plans/reports/AWF-155-report.md` |
| AWF-156 | 29 | done | Nightly cron -> scheduler integration | `plans/reports/AWF-156-report.md` |
| AWF-157 | 29 | done | `commands/core.py` split | `plans/reports/AWF-157-report.md` |
| AWF-158 | 29 | done | Overview experiment-aware update | `plans/reports/AWF-158-report.md` |
| AWF-159 | 30 | done | Full regression + marker registration + temp cleanup | `plans/reports/AWF-159-report.md` |
| AWF-160 | 30 | done | Signals module slimming | `plans/reports/AWF-160-report.md` |
| AWF-161 | 30 | done | Documentation freeze (Phase 20-29) | `plans/reports/AWF-161-report.md` |
| AWF-162 | 31 | done | Cross-asset live integration test | `plans/reports/AWF-162-report.md` |
| AWF-163 | 31 | done | Discovery burn-in (3 rounds) | `plans/reports/AWF-163-report.md` |
| AWF-164 | 31 | done | Manual discovery-loop validation + analytics comparison extension | `plans/reports/AWF-164-report.md` |
| AWF-165 | 32 | done | Discovery config auto-mapping | `plans/reports/AWF-165-report.md` |
| AWF-166 | 32 | done | Patrol full-auto integration | `plans/reports/AWF-166-report.md` |
| AWF-167 | 32 | done | Discovery history UI + indicator coverage analytics | `plans/reports/AWF-167-report.md` |
| AWF-168 | 33 | done | Multi-cycle patrol stability test | `plans/reports/AWF-168-report.md` |
| AWF-169 | 33 | done | Patrol log persistence + overview/analytics observability | `plans/reports/AWF-169-report.md` |
| AWF-170 | 33 | done | Final docs freeze + full regression closure | `plans/reports/AWF-170-report.md` |
| AWF-171 | 34 | done | Patrol log rotation + operational guardrails | `plans/reports/AWF-171-report.md` |
| AWF-172 | 34 | done | Real-data patrol dry-run validation script | `plans/reports/AWF-172-report.md` |
| AWF-173 | 34 | done | CLI polish + deprecation cleanup + final regression | `plans/reports/AWF-173-report.md` |
| AWF-174 | 35 | done | Signal export pipeline (best-strategy → live signal config) | `plans/reports/AWF-174-report.md` |
| AWF-175 | 35 | done | Paper position tracker (JSON state + PnL accumulation) | `plans/reports/AWF-175-report.md` |
| AWF-176 | 35 | done | Paper feedback loop (position close → analytics leaderboard feedback) | `plans/reports/AWF-176-report.md` |
| AWF-177 | 36 | done | Paper feedback dedupe + position state-machine guards | `plans/reports/AWF-177-report.md` |
| AWF-178 | 36 | done | Vectorbt core pandas/NumPy compatibility fixes | `plans/reports/AWF-178-report.md` |
| AWF-179 | 36 | done | Full regression zero-fail + final documentation freeze | `plans/reports/AWF-179-report.md` |
| AWF-180 | 37 | done | Pandas/NumPy/Numba environment version pin + vectorbt core env lock verification | `plans/reports/AWF-180-report.md` |
| AWF-181 | 37 | done | Signal scheduling daemon (`schedule-signals`) + strategy-switch automation | `plans/reports/AWF-181-report.md` |
| AWF-182 | 37 | done | Cron scheduler-mode signal-scheduling integration + Phase 37 docs freeze | `plans/reports/AWF-182-report.md` |
| AWF-183 | 38 | done | Notification dispatcher (`notifier.py`) + scheduler/paper close event hooks | `plans/reports/AWF-183-report.md` |
| AWF-184 | 38 | done | Multi-strategy paper portfolio + top-N signal scheduling + `/paper/portfolio.json` | `plans/reports/AWF-184-report.md` |
| AWF-185 | 38 | done | Signal scheduler retry/backoff hardening + anomaly notification + docs freeze | `plans/reports/AWF-185-report.md` |
| AWF-186 | 39 | done | pandas 2.x environment finalization + full regression closure | `plans/reports/AWF-186-report.md` |
| AWF-187 | 39 | done | Research report HTML export (`export-report` + `/analytics/report.html`) | `plans/reports/AWF-187-report.md` |
| AWF-188 | 39 | done | Steady-state declaration + final documentation/regression freeze | `plans/reports/AWF-188-report.md` |
| AWF-189 | MAINT | done | Warning cleanup + pandas 2.x downgrade verification + CI-ready regression baseline | `plans/reports/AWF-189-report.md` |
| AWF-190 | UI-1 | done | Sidebar navigation + responsive layout rebuild (horizontal tabs → collapsible icon sidebar, mobile breakpoints) | `app.js`, `app.css` |
| AWF-191 | UI-1 | done | Shared component library + i18n completion (ActionButton 107處, KpiCard, DataTable empty state; i18n syntax fix) | `components.js`, `i18n.js`, all tab files |
| AWF-192 | UI-1 | done | Page-level visual polish (skeleton loading, Chart.js MutationObserver theme adaptation, toast feedback, CSS cleanup) | all tab files, `results.js`, `app.css` |
| AWF-193 | 40 | done | Phase 40 documentation freeze + namespace contract | `plans/reports/AWF-193-report.md` |
| AWF-194 | 40 | done | `scripts.autowfo.*` -> `autowfo.*` runtime migration | `plans/reports/AWF-194-report.md` |
| AWF-195 | 40 | done | control panel package migration + new module entrypoint | `plans/reports/AWF-195-report.md` |
| AWF-196 | 40 | done | Packaging metadata + static asset distribution | `plans/reports/AWF-196-report.md` |
| AWF-197 | 40 | done | Import-surface cleanup + regression validation | `plans/reports/AWF-197-report.md` |
| AWF-198 | 40 | done | README / plan closure + steady-state update | `plans/reports/AWF-198-report.md` |
| AWF-199 | 41 | done | Phase 41 documentation freeze + runtime contract | `plans/reports/AWF-199-report.md` |
| AWF-200 | 41 | done | Configurable root/artifacts contract + startup options | `plans/reports/AWF-200-report.md` |
| AWF-201 | 41 | done | Process + data-refresh runtime convergence | `plans/reports/AWF-201-report.md` |
| AWF-202 | 41 | done | Scheduler runtime convergence + mutable-state sync | `plans/reports/AWF-202-report.md` |
| AWF-203 | 41 | done | Regression validation for runtime contract | `plans/reports/AWF-203-report.md` |
| AWF-204 | 41 | done | Runbook / README / plan closure + steady-state update | `plans/reports/AWF-204-report.md` |
| AWF-205 | 42 | done | Phase 42 documentation freeze + storage contract scope | `plans/reports/AWF-205-report.md` |
| AWF-206 | 42 | done | Experiment artifact schema-version contract | `plans/reports/AWF-206-report.md` |
| AWF-207 | 42 | done | Queue and paper-state schema-version contract | `plans/reports/AWF-207-report.md` |
| AWF-208 | 42 | done | Analytics metadata contract | `plans/reports/AWF-208-report.md` |
| AWF-209 | 42 | done | Regression + legacy-migration validation | `plans/reports/AWF-209-report.md` |
| AWF-210 | 42 | done | Plan closure + steady-state update | `plans/reports/AWF-210-report.md` |
