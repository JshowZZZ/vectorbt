# AUTOWFO Master Plan

## Objective
Build a long-term, reproducible, and automation-first workflow for discovering robust strategy-indicator combinations using time stacking (walk-forward style), not one-off best-parameter picks.

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
- Keep vectorbt core simulation and indicator engines as compute primitives.
- Add orchestration layer on top (AUTOWFO) rather than forcing major core refactors.
- Treat each run as an experiment with fixed seed, dataset snapshot, config, and metrics.
- **Decompose monolith first**: the current `run_btc_regime_sweep.py` (3000 lines) contains all logic in one file; it must be split into focused modules before protocols can be individually frozen and tested.

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
- Linked TODO IDs: `AWF-001`, `AWF-002`, `AWF-003`, `AWF-004`.

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
- Add caching and duplicate elimination (basic `seen_keys` dedup exists).
- Add runtime and memory profiling baselines.
- Exit criteria: meaningful speedup vs brute-force baseline.
- Linked TODO IDs: `AWF-008` (done), `AWF-009`.

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
- [ ] Split schema config/YAML finalized and committed.
- [ ] Metric contract doc finalized and committed.
- [ ] Schema validation tests pass locally.
- [ ] `plans/AUTOWFO_TODO.md` focus window updated.
- [ ] `Change Log` entry added with `Protocol frozen at commit <hash>`.

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
