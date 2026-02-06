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

## Milestones
1. Protocol and Constraints
- Define canonical split protocol (train/valid/test, horizons, overlap policy).
- Define metric set and ranking policy (return, drawdown, Sharpe, stability penalty).
- Define experiment schema and artifact layout.
- Exit criteria: protocol doc approved; no coding without protocol references.
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
- Add ranking models beyond single metric max:
  - median OOS performance
  - dispersion penalty
  - drawdown penalty
  - split-consistency score
- Exit criteria: same config reruns produce stable top-N under fixed seed/data.
- Linked TODO IDs: `AWF-006`, `AWF-011`.

5. Scale and Performance
- Add two-stage search (coarse then focused).
- Add caching and duplicate elimination.
- Add runtime and memory profiling baselines.
- Exit criteria: meaningful speedup vs brute-force baseline.
- Linked TODO IDs: `AWF-008`, `AWF-009`.

6. Automation and Governance
- Add CLI or script entrypoint for scheduled runs.
- Persist experiment records and diffs between runs.
- Add regression tests for ranking and split correctness.
- Exit criteria: one-command reproducible run and report.
- Linked TODO IDs: `AWF-010`, `AWF-011`, `AWF-012`.

## Stage Gates (Do Not Skip)
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
