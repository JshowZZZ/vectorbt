# AGENT

Start here. Read `AGENTS.md` for coding and process rules, and read `plans/` documents for scope and stage gates before starting implementation.

This repository's primary agent instructions are maintained in `AGENTS.md`.

For long-term automation planning, follow:
- `plans/AUTOWFO_MASTER_PLAN.md`
- `plans/AUTOWFO_TODO.md`

For local overlay workflow, see:
- `plans/AGENTSMD_INTEGRATION.md`

## Decomposition Rules (for monolith extraction)

- Constants first: Extract pure data (maps, field lists, labels) before any logic. They are zero-risk and unblock all downstream modules.
- One module per commit: Each extraction is an atomic commit that can be individually reverted. Never create empty skeleton files "to be filled later."
- Re-export for backward compatibility: When moving a function from module A to module B, module A must re-export it until all callers are migrated. Existing tests must never break.
- Bit-identical output: Pure code movement must produce identical results. Any numerical difference is a bug, not acceptable tolerance.
- Test before, not after: Run existing tests before each extraction to establish green baseline. If tests are missing for the code being moved, write characterization tests first.
