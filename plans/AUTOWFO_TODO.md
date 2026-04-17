# AUTOWFO TODO

## Usage Rules
- This file tracks only active-phase execution items.
- Completed historical items are archived in `plans/AUTOWFO_TODO_ARCHIVE.md`.
- Allowed statuses: `todo`, `doing`, `blocked`, `done`.
- Policy is authoritative in `plans/AUTOWFO_DEVELOPMENT_PRINCIPLES.md`; plans and TODO entries must not override it.

## Active Phase
- Phase 61–62: Parity reset, policy freeze, TODO context slimming, drift-report foundation.
- Last frozen search phase: Phase 60: Hierarchical State-Trigger Mode Opening.
- Active plan: `plans/AUTOWFO_PHASE61_62_PLAN_V2.md`.

## Gate State
- `Gate A` passed: `AWF-341`, `AWF-343`, `AWF-338`, `AWF-339`, and `AWF-340` are complete.
- `Gate B` not started: `AWF-345~347` pending; `AWF-342b` remains optional.
- Next human review checkpoint: after `AWF-345` freezes `execution_drift_report_v1`, before `AWF-346`.

## Active Items

| ID | Status | Task | Hypothesis | Metric | Accept threshold | Rollback |
|---|---|---|---|---|---|---|
| AWF-341 | done | Freeze development principles in repo | repo policy drift drops when execution rules move from chat memory into one file | `plans/AUTOWFO_DEVELOPMENT_PRINCIPLES.md` exists and is wired as policy source | six required sections frozen; wording cleared by human review | revert downstream references if policy text is reopened |
| AWF-343 | done | Slim `AUTOWFO_TODO.md` | active execution becomes cheaper to reason about when done items leave the active file | active TODO line count and archive coverage | active TODO stays under `80` lines and done items move to archive with traceable one-line entries | restore archived items if gate-critical context is lost |
| AWF-338 | done | Freeze rerun inputs | parity conclusions stop drifting when bundle/version/config inputs are fixed first | `plans/protocols/awf338_rerun_input_manifest.json` | bundle, FT version, config path, pair mapping, row scope, and output path are fixed before rerun | discard rerun prep if any source input changes mid-task |
| AWF-339 | done | Rerun AWF-331 on corrected adapter contract | raw-signal consumer fix should raise parity quality versus pre-fix AWF-331 review state | `artifacts/freqtrade_bridge/awf331_rerun_summary.json` match-ratio and trade-delta fields | row scope exactly matches canonical lane + stable top `10`; artifact regenerated with `open_match_ratio min=0.9633`, `exact_match_ratio p10=0.5827`, `AWF-339a` not triggered | stop at `AWF-339a` if rerun still shows low open-match evidence |
| AWF-340 | done | Derive parity gate v1 from rerun data | observed rerun distributions can define thresholds without narrative guesswork | `plans/AUTOWFO_PARITY_GATE_V1.md` derived from `AWF-339` distribution summary | Gate V1 frozen with `p10(open)=0.9891`, `p10(exact)=0.5827`, `p90(abs(trade_count_delta_pct))=0.00952`, plus hard block conditions | reopen the gate if the frozen row scope or statistical-policy branch changes |
| AWF-342a | todo | Add DuckDB MCP | frozen-bundle SQL access should cut context cost for drift exploration | `.mcp.json` entry plus three smoke SQL files | DuckDB MCP configured and smoke queries saved under `artifacts/scratch/duckdb_smoke/` | defer MCP usage if queries cannot stay on frozen bundle or snapshot data |
| AWF-342b | todo | Add Freqtrade MCP if runtime supports it | local FT MCP can speed operator inspection without being required for parity validation | `.mcp.json` entry plus smoke check | MCP works against local FT runtime or is explicitly deferred without blocking Phase 62 | leave deferred if Windows/runtime path is unstable |
| AWF-344 | blocked | Prototype drift queries with DuckDB | proven SQL joins should shape drift schema before Python CLI work starts | saved SQL snippets and sample outputs | query shape is stable enough to freeze drift report fields | do not freeze schema until joins and metrics are demonstrated on frozen data |
| AWF-345 | blocked | Freeze `execution_drift_report_v1` schema | schema stability should follow proven query shape rather than intuition | protocol file in `plans/protocols/` | schema covers the proven drift query shape and passes human review checkpoint | reopen schema before CLI work if query shape still moves |
| AWF-346 | blocked | Implement `autowfo storage drift-report` | drift becomes reproducible when report generation is a CLI artifact instead of ad hoc analysis | CLI output artifact matching frozen schema | CLI writes versioned drift report artifacts from approved inputs | do not ship CLI until schema freeze is approved |
| AWF-347 | blocked | Rebuild the first real drift artifact | schema and CLI are only real if they can regenerate a concrete report from Phase 61 outputs | generated `execution_drift_report.json` | real artifact regenerates through the CLI from frozen inputs | treat schema/CLI as incomplete if first artifact cannot be reproduced |
