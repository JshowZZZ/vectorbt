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
| Walk-forward eval | ✅ Modular (`split.py` + protocol) | Frozen | Not true per-window WFO; no validation set |
| IS/OOS metrics (8+10) | ✅ Modular (`metrics.py` + contract) | Frozen | No Sharpe, no stability score (deferred to AWF-002b) |
| Indicator framework (13) | ✅ Schema-backed (`strategy_schema.py`) | Frozen | Adding indicators is config-only |
| Regime logic (8 types) | ✅ Schema-backed | Frozen | Adding regimes is config-only |
| Combo search (1079+) | ✅ Modular (`search.py`) | Working | No intelligent pruning |
| Two-stage search | ✅ combo→refine modes | Working | AWF-008 done |
| Ranking | ✅ Modular (`ranking.py`) | Simplistic | Single sort by OOS return (AWF-006 deferred) |
| Artifacts (CSV/DB/HTML) | ✅ Reproducible (`artifacts.py` + contract) | Frozen | Config hash + data fingerprint included |
| Parallel evaluation | ✅ 3-worker (`parallel.py`) | ×2.66 speedup | Bit-identical verified |
| Run registry | ✅ (`registry.py`) | Working | Coverage map across timeframe×symbol |
| CLI entrypoint | ✅ `python -m autowfo` | Working | `run` + `baseline` subcommands |
| Regression tests | ✅ 87 tests / 18 files | Green | Split + ranking invariants covered |
| Operational runbook | ✅ `AUTOWFO_RUNBOOK.md` | Complete | Preflight→run→post-run checklist |
| Web control panel | ⚠️ 2250-line monolith | Working | No batch/coverage/dashboard; needs refactor (AWF-017a) |

## Milestones

### Phase 1: Decompose (AWF-000) ✅
- Extracted 10 modules from 3000-line monolith into `scripts/autowfo/`.
- Bit-identical artifact output verified.
- Linked TODO: `AWF-000`.

### Phase 2: Protocol Freeze (AWF-003/002/004/001) ✅
- Strategy schema, metric contract, artifact contract, split protocol frozen with JSON/YAML specs.
- Gate A passed at commit `524f837`.
- Linked TODO: `AWF-003`, `AWF-002`, `AWF-004`, `AWF-001`.

### Phase 3: Scale & Experiment Management (AWF-013/009/010) ✅
- Multi-process parallelization (×2.66 speedup, bit-identical).
- Run registry with timeframe×symbol coverage map.
- CLI entrypoint (`python -m autowfo run|baseline`).
- Linked TODO: `AWF-013`, `AWF-009`, `AWF-010`.

### Phase 4: Quality Guardrails (AWF-011/012) ✅
- Regression test suite (87 tests, 18 files).
- Operational runbook (`plans/AUTOWFO_RUNBOOK.md`).
- Gate D passed at commit `a147972`.
- Linked TODO: `AWF-011`, `AWF-012`.

---

### Phase 5: Control Panel Architecture Refactor (AWF-017a)
- Restructure 2250-line single-file control panel into maintainable architecture.
- Front/back separation: Python API backend + `static/` HTML/JS/CSS assets.
- Tab-based navigation (控制台 / 結果 / 覆蓋 / 儀表板 / 歷史).
- Lightweight CSS framework for consistent styling.
- Prerequisite for all Phase 6-8 UI work.
- Linked TODO: `AWF-017a`.

### Phase 6: Batch Execution (AWF-014 + AWF-017b)
- Batch runner backend: `autowfo batch --plan batch_plan.json`, preflight checks, crash-safe resume.
- Batch queue UI: enqueue/start/cancel buttons, per-job status/progress, live refresh.
- Exit criteria: queue 3 configs from browser → batch runs unattended → registry accumulates.
- Linked TODO: `AWF-014`, `AWF-017b`.

### Phase 7: Coverage Intelligence (AWF-015 + AWF-017c)
- Coverage planner backend: `autowfo plan` reads registry gaps, generates batch plan.
- Coverage map UI: color-coded timeframe×symbol matrix, click-to-enqueue.
- Exit criteria: planner output feeds directly into batch queue; visual gap identification.
- Linked TODO: `AWF-015`, `AWF-017c`.

### Phase 8: Cross-Run Insight (AWF-016 + AWF-017d)
- Cross-run dashboard backend: `autowfo report` producing aggregate analysis.
- Dashboard UI: run history table, combo stability timeline, global leaderboard.
- Exit criteria: ≥3 runs produce meaningful stability trend visualization from browser.
- Linked TODO: `AWF-016`, `AWF-017d`.

### Phase 9: Ranking Upgrade — Evidence-Gated (AWF-002b/006/007)
- Sharpe + stability scoring, composite ranking function, benchmark scenario.
- Trigger: only activated when baseline runs show D1 or D2 pass.
- Current evidence: 11 baseline windows all D3-only; deferred.
- Linked TODO: `AWF-002b`, `AWF-006`, `AWF-007`.

### Phase 10: Advanced Modes (AWF-001b/005)
- True WFO mode (per-window re-optimization).
- Full engine refactor using modular pipeline.
- Gate C reproducibility checks.
- Linked TODO: `AWF-001b`, `AWF-005`.

## Stage Gates (Do Not Skip)
- Gate 0: Monolith decomposed before protocol freeze (Phase 1). **✅ Passed.**
- Gate A: Protocol freeze before scale/automation work (Phase 2→3). **✅ Passed at `524f837`.**
- Gate D: Regression suite green before automation expansion (Phase 4→5). **✅ Passed at `a147972`.**
- Gate B: Ranking rule freeze before advanced modes (Phase 9→10). Pending D1/D2 trigger.
- Gate C: Reproducibility checks before broadening strategy universe (Phase 10). Pending.

## Gate Checklists
Gate A (Protocol Freeze) owner: Maintainer + AI agent pair sign-off
- [x] Split schema config/YAML finalized and committed.
- [x] Metric contract doc finalized and committed.
- [x] Schema validation tests pass locally.
- [x] `plans/AUTOWFO_TODO.md` focus window updated.
- [x] `Change Log` entry added with `Protocol frozen at commit <hash>`.

Gate B (Ranking Freeze) owner: Maintainer + AI agent pair sign-off
- [ ] Ranking formula spec finalized (including penalties).
- [ ] Before/after ranking comparison artifacts stored.
- [ ] Selection-rule regression tests pass.
- [ ] `Change Log` entry added with `Ranking frozen at commit <hash>`.

Gate C (Reproducibility Check) owner: Maintainer + AI agent pair sign-off
- [ ] Fixed seed and dataset snapshot identifiers recorded.
- [ ] Repeated runs produce stable top-N within defined tolerance.
- [ ] Experiment artifact schema validation passes.
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
- 2026-02-06: Architecture review — documented existing implementation inventory; added Milestone 0 (monolith decomposition); updated Milestones 1/4/5 to reflect extract-from-existing approach; added Gate 0; added AWF-000, AWF-002b, AWF-001b; marked AWF-008 as done.
- 2026-02-07: Gate 0 passed ??AWF-000 decomposition exit criteria verified (module importability coverage + deterministic bit-identical artifact characterization at commit `c059646`).
- 2026-02-07: Real-data two-pass baseline executed via `scripts/run_autowfo_baseline.py` (combo then refine) with archived outputs in `artifacts/runs/20260207_103734`; quantitative trigger decision recorded as `false` (D2-only), so AWF-002b/AWF-006 deferred pending a next window with non-empty OOS segments.
- 2026-02-07: Second real-data two-pass baseline executed with non-empty OOS segments at `artifacts/runs/20260207_161041`; quantitative trigger decision remained `false` (D1/D2/D3 all false), so AWF-002b/AWF-006 continue to be deferred. Runtime config parsing was hardened to accept UTF-8 BOM and avoid unintended fallback to defaults.
- 2026-02-07: Third baseline window executed at `artifacts/runs/20260207_172457` (`1h/300d` temporary window, baseline config restored afterward); trigger remained `false` with D1/D2/D3 all false. Refine stage ran with `0/0` additional combos, so next evidence cycle must ensure non-zero refine candidate execution before using comparison deltas for ranking decisions.
- 2026-02-07: Baseline runner now records pass-level workload (`run_total/run_done/run_skipped/run_stage`) from `run_status.json` and emits a warning when refine processes zero candidates, preventing non-informative combo-vs-refine comparisons from being misread as strong evidence.
- 2026-02-08: Refine candidate selection now reuses activity fallback behavior to avoid zero-candidate collapse on low-frequency windows; quality filter thresholds (`min_avg_daily_trades_target`, `min_oos_trades_target`) are now configurable via `sweep_config.json` with unchanged defaults.
- 2026-02-08: Fourth baseline window executed at `artifacts/runs/20260208_034213` with non-zero refine execution (`486/486`); trigger decision remained `false` (D3-only), so AWF-002b/AWF-006 stay deferred pending additional multi-window evidence.
- 2026-02-08: Fifth baseline window executed at `artifacts/runs/20260208_055709` (`4h/365d`, segmented combo window) with non-zero refine execution (`1107/1107`); trigger again remained `false` with D3-only while combo-vs-refine comparison stayed informative (positive OOS return delta), so AWF-002b/AWF-006 remains deferred pending one more stricter-floor evidence pass.
- 2026-02-08: Sixth baseline window executed at `artifacts/runs/20260208_081420` using stricter activity floor (`min_avg_daily_trades_target=1.0`); refine remained non-zero (`5508/5508`) and trigger still stayed `false` with D3-only. This suggests current non-trigger outcome is stable across multiple non-zero-refine windows, so AWF-002b/AWF-006 continues to be deferred pending targeted cross-window confirmation.
- 2026-02-08: **Platform mindset shift** — reframed AUTOWFO as a reusable strategy-exploration platform (correctness > extensibility > speed). Reordered phases: Protocol Freeze (Phase 2) reactivated as immediate focus with AWF-003 first; added AWF-013 (parallelization) to Milestone 5; promoted AWF-009/010 to P1; AWF-002b/006 remain evidence-gated. Updated AGENTS.md, AUTOWFO_TODO.md, and this file.
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
- 2026-02-10: Added AWF-017a/b/c/d (control panel enhancement) to backlog — architecture refactor, batch queue UI, coverage map UI, cross-run dashboard UI. Restructured TODO from 6+3.5 phases into clean 10-phase roadmap: Phases 1-4 completed, Phase 5 (panel refactor) as current focus, Phases 6-8 pair backend+frontend per feature, Phases 9-10 remain evidence-gated. Updated milestones and stage gates in this file to match.
