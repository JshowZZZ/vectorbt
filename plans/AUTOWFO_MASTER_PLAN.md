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
- ~~Decompose monolith first~~: **completed** (AWF-000, commit `c059646`). Modules live in `scripts/autowfo/`.

## Current Implementation Reality
> Updated 2026-02-10. Modules extracted into `scripts/autowfo/`, protocols frozen, Gates A+D passed.

| Component | Status | Quality | Key Gap |
|---|---|---|---|
| Walk-forward eval | ??Modular (`split.py` + protocol) | True-WFO enabled (`anchored` + `rolling`) | No validation set yet |
| IS/OOS metrics (8+15) | ??Modular (`metrics.py` + contract) | Upgraded | Sharpe-like/stability/low-trade penalty metrics added (AWF-002b complete) |
| Indicator framework (13) | ??Schema-backed (`strategy_schema.py`) | Frozen | Adding indicators is config-only |
| Regime logic (8 types) | ??Schema-backed | Frozen | Adding regimes is config-only |
| Combo search (1079+) | ??Modular (`search.py`) | Working | No intelligent pruning |
| Two-stage search | ??combo?efine modes | Working | AWF-008 done |
| Ranking | ??Modular (`ranking.py`) | Upgraded | Composite score default + legacy mode preserved + config-driven weights; paired comparison report pipeline ready (AWF-006/007 complete) |
| Artifacts (CSV/DB/HTML) | ??Reproducible (`artifacts.py` + contract) | Frozen | Config hash + data fingerprint included |
| Parallel evaluation | ??3-worker (`parallel.py`) | ?2.66 speedup | Bit-identical verified |
| Run registry | ??(`registry.py`) | Working | Coverage map across timeframe?symbol |
| CLI entrypoint | ??`python -m autowfo` | Working | `run` + `baseline` + `batch` + `plan` + `report` subcommands |
| Regression tests | ??87 tests / 18 files | Green | Split + ranking invariants covered |
| Operational runbook | `AUTOWFO_RUNBOOK.md` | Complete | Preflight/run/post-run checklist |
| Web control panel | Static tabs + batch + coverage + dashboard/history | Complete (Phase 8) | Next gap is ranking-quality upgrades (AWF-002b/006) ??now immediate |

## Milestones

### Phase 1: Decompose (AWF-000) [Done]
- Extracted 10 modules from 3000-line monolith into `scripts/autowfo/`.
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
- Tab-based navigation (??? / ?? / ?? / ??? / ??).
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

### Phase 9: Ranking Upgrade ??Immediate (AWF-002b/006/007)
- Sharpe + stability scoring, composite ranking function, legacy vs composite paired comparison.
- Governance change: D1/D2/D3 repurposed as health-monitoring indicators, no longer activation gates.
- Rationale: 13 baseline windows persistently D3-only proves single-metric ranking pushes low-trade combos
  to top; this is itself the strongest evidence that ranking upgrade is needed.
- AWF-002b: ??Added `oos_sharpe_like`, `oos_return_std`, `oos_positive_segment_ratio` plus low-trade penalty fields to metrics + contract.
- AWF-006: ??Composite score = return + stability + risk-adjust ??drawdown penalty ??low-sample penalty.
  Legacy mode preserved for A/B comparison, default switched to composite, weights configurable in `sweep_config.json`.
- AWF-007: ??Same-window paired comparison (legacy vs composite) implemented in baseline workflow with fixed-format JSON/HTML report;
  includes 3-axis diagnostic: strategy quality / sample sufficiency / combo scarcity.
- Gate B checklist must pass before Phase 10.
- Linked TODO: `AWF-002b`, `AWF-006`, `AWF-007`.

### Phase 10: Advanced Modes (AWF-001b/005)
- True WFO mode (per-window re-optimization).
- Full engine refactor using modular pipeline.
- Gate C reproducibility checks.
- Linked TODO: `AWF-001b`, `AWF-005`.

## Stage Gates (Do Not Skip)
- Gate 0: Monolith decomposed before protocol freeze (Phase 1). **??Passed.**
- Gate A: Protocol freeze before scale/automation work (Phase 2??). **??Passed at `524f837`.**
- Gate D: Regression suite green before automation expansion (Phase 4??). **??Passed at `a147972`.**
- Gate B: Ranking rule freeze before advanced modes (Phase 9??0). In progress (checklist 3/4 complete; commit freeze record pending).
- Gate C: Reproducibility checks before broadening strategy universe (Phase 10). In progress (checklist 3/4 complete; freeze commit record pending).

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
- [ ] `Change Log` entry added with `Ranking frozen at commit <hash>`.

Gate C (Reproducibility Check) owner: Maintainer + AI agent pair sign-off
- [x] Fixed seed and dataset snapshot identifiers recorded.
- [x] Repeated runs produce stable top-N within defined tolerance.
- [x] Experiment artifact schema validation passes.
- [ ] `Change Log` entry added with `Reproducibility verified at commit <hash>`.

Gate D (Regression Green) owner: Maintainer + AI agent pair sign-off
- [x] Regression suite green (split and ranking invariants).
- [x] No unresolved critical drift issues in latest session log.
- [x] Runbook updated for any operator-impacting change.
- [x] `Change Log` entry added with `Regression gate passed at commit <hash>`.

## Anti-Drift Rules
- No feature implementation unless linked to a TODO item.
- No metric changes without changelog entry in this file.
- No selection-rule changes without before/after comparison artifacts.
- Prefer additive modules over invasive rewrites.

## Risks and Mitigations
- Overfitting to in-sample:
  - Mitigation: OOS-first score and split consistency constraints.
- Combinatorial explosion:
  - Mitigation: staged search, pruning, and caching.
- Non-reproducible results:
  - Mitigation: strict seed handling, dataset snapshot IDs, and config hashing.
- Direction drift:
  - Mitigation: mandatory TODO linkage and stage gates.

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
- 2026-02-06: Initial long-term AUTOWFO master plan created.
- 2026-02-06: Added milestone-to-TODO mapping and quantified gate checklists with sign-off ownership.
- 2026-02-06: Architecture review ??documented existing implementation inventory; added Milestone 0 (monolith decomposition); updated Milestones 1/4/5 to reflect extract-from-existing approach; added Gate 0; added AWF-000, AWF-002b, AWF-001b; marked AWF-008 as done.
- 2026-02-07: Gate 0 passed ??AWF-000 decomposition exit criteria verified (module importability coverage + deterministic bit-identical artifact characterization at commit `c059646`).
- 2026-02-07: Real-data two-pass baseline executed via `scripts/run_autowfo_baseline.py` (combo then refine) with archived outputs in `artifacts/runs/20260207_103734`; quantitative trigger decision recorded as `false` (D2-only), so AWF-002b/AWF-006 deferred pending a next window with non-empty OOS segments.
- 2026-02-07: Second real-data two-pass baseline executed with non-empty OOS segments at `artifacts/runs/20260207_161041`; quantitative trigger decision remained `false` (D1/D2/D3 all false), so AWF-002b/AWF-006 continue to be deferred. Runtime config parsing was hardened to accept UTF-8 BOM and avoid unintended fallback to defaults.
- 2026-02-07: Third baseline window executed at `artifacts/runs/20260207_172457` (`1h/300d` temporary window, baseline config restored afterward); trigger remained `false` with D1/D2/D3 all false. Refine stage ran with `0/0` additional combos, so next evidence cycle must ensure non-zero refine candidate execution before using comparison deltas for ranking decisions.
- 2026-02-07: Baseline runner now records pass-level workload (`run_total/run_done/run_skipped/run_stage`) from `run_status.json` and emits a warning when refine processes zero candidates, preventing non-informative combo-vs-refine comparisons from being misread as strong evidence.
- 2026-02-08: Refine candidate selection now reuses activity fallback behavior to avoid zero-candidate collapse on low-frequency windows; quality filter thresholds (`min_avg_daily_trades_target`, `min_oos_trades_target`) are now configurable via `sweep_config.json` with unchanged defaults.
- 2026-02-08: Fourth baseline window executed at `artifacts/runs/20260208_034213` with non-zero refine execution (`486/486`); trigger decision remained `false` (D3-only), so AWF-002b/AWF-006 stay deferred pending additional multi-window evidence.
- 2026-02-08: Fifth baseline window executed at `artifacts/runs/20260208_055709` (`4h/365d`, segmented combo window) with non-zero refine execution (`1107/1107`); trigger again remained `false` with D3-only while combo-vs-refine comparison stayed informative (positive OOS return delta), so AWF-002b/AWF-006 remains deferred pending one more stricter-floor evidence pass.
- 2026-02-08: Sixth baseline window executed at `artifacts/runs/20260208_081420` using stricter activity floor (`min_avg_daily_trades_target=1.0`); refine remained non-zero (`5508/5508`) and trigger still stayed `false` with D3-only. This suggests current non-trigger outcome is stable across multiple non-zero-refine windows, so AWF-002b/AWF-006 continues to be deferred pending targeted cross-window confirmation.
- 2026-02-08: **Platform mindset shift** ??reframed AUTOWFO as a reusable strategy-exploration platform (correctness > extensibility > speed). Reordered phases: Protocol Freeze (Phase 2) reactivated as immediate focus with AWF-003 first; added AWF-013 (parallelization) to Milestone 5; promoted AWF-009/010 to P1; AWF-002b/006 remain evidence-gated. Updated AGENTS.md, AUTOWFO_TODO.md, and this file.
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
- 2026-02-10: Added AWF-017a/b/c/d (control panel enhancement) to backlog ??architecture refactor, batch queue UI, coverage map UI, cross-run dashboard UI. Restructured TODO from 6+3.5 phases into clean 10-phase roadmap: Phases 1-4 completed, Phase 5 (panel refactor) as current focus, Phases 6-8 pair backend+frontend per feature, Phases 9-10 remain evidence-gated. Updated milestones and stage gates in this file to match.
- 2026-02-10: AWF-017a implemented: control panel frontend moved to file-based static assets under scripts/control_panel/static (index.html, css/app.css, modular JS app.js plus tabs.js/batch.js/coverage.js/dashboard.js), backend retains existing API contracts while serving /static/*, and tab navigation scaffolding is now decoupled from Python source edits.
- 2026-02-10: AWF-014 implemented: added `python -m autowfo batch --plan <file>` backend with structured plan parsing, preflight checks (config/cwd/disk), crash-safe resume state (`artifacts/batch_state.json`, seen-key dedup), and `--continue-on-error` behavior. Added CLI regression coverage for success, resume-skip, missing-config preflight, and partial-failure continuation paths.
- 2026-02-10: AWF-017b implemented: control panel now exposes batch queue APIs (`/batch/queue.json`, `/batch/enqueue`, `/batch/start`, `/batch/cancel`, `/batch/clear`, `/batch/remove`) and frontend batch tab actions (enqueue/start/cancel/clear + live queue/log refresh) wired to `autowfo batch` and `artifacts/batch_state.json`. Added queue lifecycle tests in `tests/test_control_panel.py`.
- 2026-02-10: AWF-015 implemented: added `python -m autowfo plan` coverage planner to generate executable batch plans from `run_registry.json` `untested_pairs`, including per-gap config generation and controls for `--max-jobs`, `--workflow`, `--mode`, and `--workers`. Added CLI tests for both populated and empty-gap planning paths.
- 2026-02-10: AWF-017c implemented: control panel coverage tab now renders timeframe?symbol matrix from `/coverage/matrix.json` with tested/queued/untested states and supports one-click scheduling through `/coverage/enqueue` (per-pair config generation + batch queue insertion). Added regression tests for coverage matrix classification and enqueue behavior.
- 2026-02-11: AWF-016 and AWF-017d implemented and marked done. Added `scripts/autowfo/cross_run.py`, CLI subcommand `python -m autowfo report`, dashboard report endpoints (`/dashboard/cross_run.json`, `/dashboard/report`, `/dashboard/report/generate`), and live dashboard/history UI rendering for summary KPI, global leaderboard, combo stability, and run timeline. Focused regression suite covering aggregation, CLI, and control-panel hooks passed (`22 passed`).
- 2026-02-11: Additional evidence window executed (`python -m autowfo baseline --config artifacts/sweep_config_window12_symbols.json`) and archived at `artifacts/runs/20260211_103459` (`4h/180d`, `ETH/USDT+BNB/USDT`). Both passes were non-zero (`combo=3840`, `refine=1161`) and comparison remained informative (`delta_avg_oos_return_pct=+0.3130`, `delta_avg_oos_drawdown_pct=-0.2822`), while trigger remained `false` with D3-only (`D1=false`, `D2=false`, `D3=true`), so AWF-002b/AWF-006 continue to stay deferred.
- 2026-02-11: Additional timeframe-variant evidence window executed (`python -m autowfo baseline --config artifacts/sweep_config_window13_2h.json`) and archived at `artifacts/runs/20260211_105818` (`2h/180d`, `ETH/USDT+BNB/USDT`). Both passes were non-zero (`combo=3840`, `refine=2403`) and comparison remained informative (`delta_avg_oos_return_pct=+1.1668`, `delta_avg_oos_drawdown_pct=-0.7468`), while trigger remained `false` with D3-only (`D1=false`, `D2=false`, `D3=true`), so AWF-002b/AWF-006 remain deferred.
- 2026-02-11: **Governance change** ??D1/D2/D3 repurposed from activation gates to health-monitoring indicators. 13 baseline windows all persistently D3-only (low-trade combos in top-10) constitutes sufficient evidence that single-metric ranking is the bottleneck. AWF-002b/AWF-006/AWF-007 unblocked for immediate implementation. Phase 9 title changed from "Evidence-Gated" to "Immediate". Gate B proceeds without D1/D2 trigger prerequisite. Updated AGENTS.md, AUTOWFO_TODO.md, and this file.
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
- 2026-02-13: AWF-005 modular refactor step 17 completed. Consolidated remaining timeframe main-loop orchestration into higher-level engine runners: `scripts/autowfo/engine.py::_build_timeframe_execution_callbacks` (prepare/body callback assembly) and `_run_timeframe_search_and_finalize` (loop + finalize orchestration wrapper). `scripts/run_btc_regime_sweep.py` now delegates these orchestration layers and removes local per-timeframe closures plus direct loop/finalize stitching. Added regression tests for callback wiring contract and loop?inalize handoff behavior. Validation remains green (`80 passed` targeted sweep/engine tests, `167 passed`, `846 deselected` AUTOWFO subset).
- 2026-02-13: AWF-005 modular refactor step 18 completed. Added finalize-result completion handler `scripts/autowfo/engine.py::_handle_finalize_result` (warn path + completion progress emit + ordered output print) and pipeline wrapper `scripts/autowfo/engine.py::_run_timeframe_pipeline` to combine callback-build and loop/finalize execution into one engine call. `scripts/run_btc_regime_sweep.py` now delegates to these helpers and removes remaining local finalize output wiring. Added regression tests for warn/completion paths and wrapper wiring contract. Validation remains green (`83 passed` targeted sweep/engine tests, `170 passed`, `846 deselected` AUTOWFO subset).
- 2026-02-13: AWF-005 modular refactor step 19 completed. Added shared runtime context builder `scripts/autowfo/engine.py::_build_shared_pipeline_runtime_context` and shared adapters (`_build_prepare_timeframe_runtime_context_from_shared`, `_build_timeframe_ready_search_context_from_shared`, `_build_finalize_pipeline_context_from_shared`) so prepare/ready/finalize context assembly reuses one canonical runtime bundle. Also moved sweep-local helper logic into engine (`_safe_int`, `_safe_float`, `_has_all_config_fields`) and rewired `scripts/run_btc_regime_sweep.py` to consume engine-level helpers. Added regression coverage for shared adapters and helper behavior. Validation remains green (`88 passed` targeted sweep/engine tests, `175 passed`, `846 deselected` AUTOWFO subset).
- 2026-02-13: AWF-005 modular refactor step 20 completed. Added sweep adapter builder `scripts/autowfo/engine.py::_build_sweep_adapter_functions` and removed sweep-local wrapper helpers (`_combo_key_from_dict`, `_indicator_combo_label`, `_format_indicator_list`, `_df_to_html`) from `scripts/run_btc_regime_sweep.py`. Entry point now wires adapter callables once and reuses them across seen-key filtering, timeframe-ready search context, and finalize report rendering. Updated report-equivalence tests to validate adapter behavior directly; validation remains green (`91 passed` targeted sweep/engine/report tests, `176 passed`, `846 deselected` AUTOWFO subset).
- 2026-02-13: AWF-005 modular refactor step 21 completed. Added schema-field helper `scripts/autowfo/engine.py::_build_sweep_schema_fields` to centralize `COMBO_KEY_FIELDS`, `COMBO_RESULT_FIELDS`, `SYMBOL_RESULT_FIELDS`, and `STRICT_CONFIG_FIELDS` contracts, and rewired `scripts/run_btc_regime_sweep.py` to consume generated schema maps instead of inline constant blocks. Added schema contract regression test coverage and verified behavior-preserving output contracts. Validation remains green (`92 passed` targeted sweep/engine/report tests, `177 passed`, `846 deselected` AUTOWFO subset).
- 2026-02-13: Gate C preflight implementation completed. Artifact contract now requires `combo_seed` in `run_metadata`, and engine finalize metadata pipeline propagates seed into persisted run metadata (`scripts/autowfo/engine.py`). Added reproducibility utility module `scripts/autowfo/reproducibility.py` with `compare_top_n_stability` for identity-overlap + metric-tolerance checks across repeated runs. Added regression coverage for contract enforcement, seed propagation, and reproducibility comparison behavior. Validation remains green (`99 passed` targeted tests, `180 passed`, `846 deselected` AUTOWFO subset).
- 2026-02-13: Gate C execution tooling and run evidence completed. Added artifact-schema validator `scripts/autowfo/reproducibility.py::validate_run_artifact_schema` and new CLI workflow `python -m autowfo gate-c` (dual-run orchestration + schema validation + top-N stability comparison) with `workflow=run` output-dir handling fix. Executed real dual-run check using fixed seed/config (`artifacts/sweep_config_window11_quick.json`) and generated `artifacts/reproducibility/gate_c_window11_quick.json` (`schema_valid=true`, `stable=true`, `gate_c_passed=true`; run IDs `20260213_133808`/`20260213_134556`). Validation remains green (`18 passed` targeted CLI/repro tests, `186 passed`, `846 deselected` AUTOWFO subset).
