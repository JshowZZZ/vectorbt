# AUTOWFO Phase 61–62 Plan V2

> Status: in progress (`AWF-341`, `AWF-343`, `AWF-338`, `AWF-339`, and `AWF-340` complete; Gate A passed, Phase 61C active)
> Date: 2026-04-17
> Scope: parity reset, development-principle freeze, TODO context slimming, drift-report foundation

## Intent

This plan replaces the earlier Phase 61–62 draft with a stricter execution order.
The main change is simple:

- fix evidence quality before adding more evidence
- reduce context overhead before expanding planning surface
- treat MCP as an accelerator, not as the foundation itself

## Why This Reorder

The previous draft had the right direction but mixed three different concerns:

1. contract validation
2. repo/process hygiene
3. operator tooling

Those concerns should not be executed in the same order.

The actual dependency chain is:

1. freeze rules
2. slim context
3. freeze rerun baseline
4. rerun parity
5. derive gate thresholds from data
6. add query tooling
7. build reusable drift artifacts

## Hard Rules

1. Contract before results: parity gate must be rerun on the corrected adapter contract before any new strategy evidence is accepted.
2. Hypothesis before execution: each AWF must declare hypothesis, metrics, acceptance threshold, and rollback condition before work starts.
3. Observation before optimization: no PnL-driven system changes before a reproducible parity/drift artifact exists.
4. Phase 60 freeze: no new pilot work until Gate B passes.
5. Time-local is not an adapter problem: if a candidate remains time-local after parity is fixed, route it to rolling-anchor replay rather than patching execution logic.
   - Caveat: this rule assumes parity repair does not materially change replay outcomes. If AWF-339 shows parity repair substantially shifts per-row PnL or trade counts versus the pre-fix AWF-331 baseline, revisit this rule before applying it to any time-local candidate. The quantitative threshold for "substantially" is deferred to AWF-339 result review.
6. Kill-switch principle must be written, not activated: the live kill-switch rule (reconcile mismatch threshold, zero-fill day threshold, halt action) must be frozen in the repo policy surface before activation. Activation belongs to a later phase. Writing the rule early prevents downstream work from designing around its absence.

## Decision Memo Policy

Do not write a decision memo for every AWF.

Write a memo only when the change is one of:

- gate-level
- cross-cutting across multiple modules
- schema or protocol freezing
- irreversible operator policy

Everything else should be summarized in one line in `plans/AUTOWFO_TODO.md` with file references.

## Gate A

Gate A exit requires all of:

- AWF-341 principles frozen in repo
- AWF-343 TODO slimming completed
- AWF-338 rerun baseline frozen
- AWF-339 parity rerun artifact generated
- AWF-340 parity-gate v1 derived from rerun data

## Gate B

Gate B exit requires all of:

- AWF-345 drift-report schema frozen
- AWF-346 storage CLI implemented
- AWF-347 first real drift artifact rebuilt through the CLI and validated

## Execution Order

### Phase 61A: Rule and Context Reset

| AWF | Task | Why | Deliverable |
|---|---|---|---|
| AWF-341 | Freeze development principles in repo | Stop relying on chat memory for execution policy | `plans/AUTOWFO_DEVELOPMENT_PRINCIPLES.md` plus references from `AGENTS.md` and `plans/AUTOWFO_MASTER_PLAN.md`. Required sections: (1) Hard Rules (copied verbatim from this plan), (2) Hypothesis Template, (3) Decision Memo Policy, (4) Time-local routing rule, (5) Kill-switch principle (threshold + halt action, not activation), (6) Statistical Policy. Once frozen, the development-principles file is the authoritative policy source and this plan should point back to it. Each section must fit on one screen; lazy-load detail via links to this plan or `plans/protocols/`. |
| AWF-343 | Slim `AUTOWFO_TODO.md` | Reduce context waste before starting a new execution cycle | `plans/AUTOWFO_TODO.md` under 80 active lines; historical done items moved into `plans/AUTOWFO_TODO_ARCHIVE.md` |

### Phase 61B: Parity Rerun Baseline

| AWF | Task | Why | Deliverable |
|---|---|---|---|
| AWF-338 | Freeze rerun inputs | Prevent false conclusions from config/version drift | frozen list of bundle, FT version, config path, pair mapping, output path |
| AWF-339 | Rerun AWF-331 on corrected adapter contract | This is the first real fact check after the raw-signal fix | `artifacts/freqtrade_bridge/awf331_rerun_summary.json`. Row scope must match the original AWF-331 artifact exactly: current canonical lane plus the stable top 10 from `pilot_analysis_awf300_microcohort_dropsol.json`. A narrower rerun is not a valid AWF-339 output. |
| AWF-340 | Derive parity gate v1 from rerun data | Gate thresholds must be backed by observed distributions, not adjectives | `plans/AUTOWFO_PARITY_GATE_V1.md` |

### Phase 61C: Query Tooling

| AWF | Task | Why | Deliverable |
|---|---|---|---|
| AWF-342a | Add DuckDB MCP | Directly reduces context cost and accelerates drift exploration | root `.mcp.json` entry plus three named smoke queries: (a) row count and pair distinct count of `awf331_rerun_summary.json`, (b) `head(10)` against a frozen `signals.parquet` (not the live one), (c) join count between `tradesv3.dryrun.sqlite` trades table and frozen signals on pair + entry timestamp. Save queries under `artifacts/scratch/duckdb_smoke/*.sql`. |
| AWF-342b | Add Freqtrade MCP if local runtime supports it | Useful for operator observation, but not required to validate parity | root `.mcp.json` entry plus smoke check against local FT runtime |

`AWF-342b` is explicitly optional at this stage. If the Windows + local FT runtime path is unstable, defer it without blocking Phase 62.

## Phase 62: Drift / Parity Artifact Path

| AWF | Task | Why | Deliverable |
|---|---|---|---|
| AWF-344 | Prototype drift queries with DuckDB | SQL is the cheapest way to prove the joins and metrics before committing to Python code | query notebook or saved SQL snippets plus sample outputs |
| AWF-345 | Freeze `execution_drift_report_v1` schema | Schema should be derived from the proven query shape | protocol file in `plans/protocols/` |
| AWF-346 | Implement `autowfo storage drift-report` | Drift must be a reproducible artifact, not a one-off analysis | CLI support plus versioned artifact writer |
| AWF-347 | Rebuild the first real drift artifact from AWF-339 outputs | Schema is only real if it can regenerate a real report | `artifacts/.../execution_drift_report.json` validated through the CLI |

## Statistical Policy for AWF-340

The authoritative statistical policy lives in
`plans/AUTOWFO_DEVELOPMENT_PRINCIPLES.md` §6.
This plan must not redefine that policy locally.
Use the principles file when deriving `plans/AUTOWFO_PARITY_GATE_V1.md`.

## TODO Slimming Policy for AWF-343

Archive only done items.

Keep in `plans/AUTOWFO_TODO.md`:

- todo
- doing
- blocked
- frozen gate state
- current phase summary

Compress archived done items into one-line entries only when the line still preserves:

- the contract or protocol affected
- the main artifact or file path
- the residual risk if the item closed in `review` rather than true pass

Do not compress these categories into vague labels:

- schema freezes
- protocol freezes
- parity/execution contract changes
- route-B pair-mapping decisions
- anything still referenced by an active gate

## Known Risks

### Highest Risk

- `AWF-342b` may fail or be unstable on the current Windows + local Freqtrade setup.
- live `current_signals.parquet` should not be the first target of drift SQL if it can be read while the producer is writing.
  - Mitigation: all Phase 61/62 DuckDB queries must point at frozen bundle parquet (the AWF-331/AWF-339 source bundle) or an explicit snapshot copy under `artifacts/scratch/duckdb_snapshots/`. Live `current_signals.parquet` is off-limits until Phase 63 introduces a producer-aware read protocol.

### Medium Risk

- if AWF-339 still shows low `open_match_ratio`, the plan must pause and insert `AWF-339a` adapter debug rather than continue into threshold design
- TODO slimming can accidentally remove crucial context for schema- or gate-linked items if compressed too aggressively

## Branch Conditions

- If AWF-339 reports `open_match_ratio < 0.5`, stop and insert `AWF-339a` before AWF-340.
- If DuckDB MCP works but Freqtrade MCP does not, proceed with Phase 62 anyway.
- If TODO slimming cannot safely get below 80 lines without losing gate-critical context, accept a slightly larger file and preserve traceability.
- Freqtrade MCP re-entry: revisit `AWF-342b` at Gate B. Reopen if any of the following is true: (a) AWF-347 drift artifact shows live-vs-backtest mismatch that requires iterative inspection, (b) dry-run reconcile needs multi-day cross-checks that are painful via CLI, (c) Phase 63 kill-switch activation is scheduled. Otherwise leave deferred with no SLA.

## Hypothesis Template

Every AWF must open with this block before any work:

```
Hypothesis:       <one sentence; what we expect to observe>
Metric:           <the specific artifact field or SQL result this answers>
Accept threshold: <numeric or boolean condition that says "done">
Rollback:         <what we undo / revert if the threshold is not met>
```

Paste the filled block into the AWF's one-line TODO summary file reference and into the decision memo when one is required. Block lines under 120 chars each so the entry stays cheap in context.

## Human Review Checkpoints

Agent must stop and wait for human review at each of these points, not auto-advance:

- After `AWF-339` produces `awf331_rerun_summary.json`, before `AWF-340` derives thresholds. Reason: gate thresholds are irreversible policy; a human must confirm the rerun data is clean.
- After `AWF-341` writes `AUTOWFO_DEVELOPMENT_PRINCIPLES.md`, before wiring references into `AGENTS.md` / `AUTOWFO_MASTER_PLAN.md`. Reason: principle wording must be final before downstream files quote it.
- After `AWF-345` freezes drift schema, before `AWF-346` implements the CLI. Reason: CLI changes are hard to revert once artifacts start depending on the schema.

At each checkpoint, agent posts: summary of what was produced, the proposed next action, and a request for go/no-go. No silent advance.

## Out of Scope for This Plan

- new pilot search
- anchor expansion
- benchmark matrix execution
- live kill-switch activation
- production execution-policy changes beyond the already-corrected signal contract

Those belong to the next phase after Gate B.
