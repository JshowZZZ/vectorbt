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
> The following already exists (as of 2026-02-06) but is embedded in a monolithic script.
> The first milestone is to extract, not to build from scratch.

| Component | Exists? | Quality | Key Gap |
|---|---|---|---|
| Walk-forward eval | Yes (anchored mode) | Working | Not true per-window WFO; no validation set |
| IS/OOS metrics (8+10) | Yes | Working | No Sharpe, no stability score |
| Indicator framework (13) | Yes | Working | Hard-coded dicts, no schema |
| Regime logic (8 types) | Yes | Working | Hard-coded, no external spec |
| Combo search (1079+) | Yes | Working | No intelligent pruning |
| Two-stage search | Yes (combo→refine) | Working | AWF-008 effectively done |
| Ranking | Yes | Simplistic | Single sort by OOS return |
| Artifacts (CSV/DB/HTML) | Yes | Working | No config hash, no data fingerprint, TEXT-only DB |
| Web control panel | Yes (8787) | Working | Tightly coupled to monolith |

## Milestones

0. Monolith Decomposition (Prerequisite)
- Extract `run_btc_regime_sweep.py` core logic into importable, testable modules.
- Confirm identical output before and after decomposition.
- Exit criteria: each module importable independently; sweep script produces same results.
- Linked TODO IDs: `AWF-000`.

1. Protocol and Constraints
- Extract and freeze split protocol from existing `_build_walk_forward_slices()` into versioned spec.
- Extract and freeze metric contract from existing `_calc_pf_series/_aggregate_*` functions.
- Extract and freeze strategy spec schema from existing `INDICATOR_META/REGIME_NAME_MAP`.
- Extract and freeze artifact schema; add config hash and data fingerprint.
- Exit criteria: protocol docs committed with schema validation tests passing.
- Linked TODO IDs: `AWF-003`, `AWF-002`, `AWF-004`, `AWF-001` (execution order).

2. Search Space and Strategy Spec
- Define strategy spec schema:
  - indicator blocks
  - signal logic
  - risk controls (SL/TP/trailing/size policy)
- Add validation for invalid combinations before simulation.
- Exit criteria: strategy specs can be linted and normalized deterministically.
- Linked TODO IDs: `AWF-003` (primary), `AWF-005` (consumer).

3. Engine MVP (Batch + Walk-Forward)
- Implement orchestration pipeline:
  - generate candidates
  - run backtests by split
  - compute IS/OOS metrics
  - produce ranked leaderboard
- Exit criteria: end-to-end run on at least one known benchmark strategy.
- Linked TODO IDs: `AWF-005`, `AWF-007`.

4. Stability-First Selection
- Add Sharpe ratio and stability scoring to metric module (prerequisite for ranking upgrade).
- Add ranking models beyond single metric max:
  - median OOS performance
  - per-segment Sharpe ratio
  - cross-segment dispersion penalty
  - drawdown penalty weight
  - split-consistency score
- Add true WFO mode (per-window re-optimization) alongside existing anchored eval.
- Exit criteria: same config reruns produce stable top-N under fixed seed/data.
- Linked TODO IDs: `AWF-002b`, `AWF-006`, `AWF-001b`, `AWF-011`.

5. Scale and Performance
- Two-stage search (coarse then focused): **already implemented** (`combo` → `refine` modes).
- Add multi-process parallelization (ProcessPoolExecutor, centralized IO) for combo evaluation.
- Add caching and duplicate elimination (basic `seen_keys` dedup exists).
- Add run registry and one-command execution entrypoint.
- Add runtime and memory profiling baselines.
- Exit criteria: meaningful speedup vs brute-force baseline; coverage tracking operational.
- Linked TODO IDs: `AWF-008` (done), `AWF-013`, `AWF-009`, `AWF-010`.

6. Automation and Governance
- Add CLI or script entrypoint for scheduled runs.
- Persist experiment records and diffs between runs.
- Add regression tests for ranking and split correctness.
- Exit criteria: one-command reproducible run and report.
- Linked TODO IDs: `AWF-010`, `AWF-011`, `AWF-012`.

## Stage Gates (Do Not Skip)
- Gate 0: Monolith decomposed before protocol freeze work begins.
- Gate A: Protocol freeze before writing search logic.
- Gate B: Ranking rule freeze before tuning performance.
- Gate C: Reproducibility checks before adding new features.
- Gate D: Regression suite green before broadening strategy universe.

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
- [ ] Regression suite green (split and ranking invariants).
- [ ] No unresolved critical drift issues in latest session log.
- [ ] Runbook updated for any operator-impacting change.
- [ ] `Change Log` entry added with `Regression gate passed at commit <hash>`.

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
