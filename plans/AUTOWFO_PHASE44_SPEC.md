# AUTOWFO Phase 44 Spec

## Phase 44: Evidence Reset and Run Isolation

### Goal
Reset AUTOWFO's evidence model so that future runs are isolated by construction, shared artifacts become derived views instead of the primary truth source, and legacy root-level outputs with broken provenance are removed rather than preserved as ongoing technical debt.

### Scope Rules
- Do not change strategy logic, scoring rules, or indicator behavior in this phase.
- Fix evidence integrity at the execution/storage layer before running more strategy campaigns.
- Prefer deletion or quarantine over speculative legacy "repair" when provenance cannot be proven.
- Do not leave root-level legacy outputs in a state where control panel, analytics, or operators can still treat them as trusted evidence.
- Finish the phase only after trusted-source boundaries, purge tooling, and rerun protocol are all documented and validated.

### Root Cause Summary
- `autowfo run` currently treats `cwd/artifacts/` as a shared mutable workspace.
- Runtime config is written to shared `artifacts/sweep_config.json`.
- Checkpoints append directly to shared CSV/DB outputs under `artifacts/`.
- Run-specific snapshots are derived from shared result frames, so a `{run_id}` suffix does not guarantee single-run provenance.
- `seen_keys` are built from shared result tables, so separate runs can influence each other's skip behavior.
- Registry/leaderboard updates occur in the same shared space, mixing single-run truth with global aggregation.

### Validation Baseline
- `python -m pytest tests/test_autowfo_cli.py tests/test_autowfo_storage_ops.py tests/test_control_panel.py -q`
- `python -m pytest tests/test_control_panel_experiments.py tests/test_experiments_ui_integration.py tests/test_e2e_experiment_lifecycle.py -q`

---

## AWF-217: Phase 44 documentation freeze + evidence policy

### Objective
Freeze the evidence-reset scope before any run-isolation code lands.

### Required changes
- Create this spec file.
- Add Phase 44 to planning docs as the active execution phase.
- Define evidence classes:
  - `trusted`: run-local outputs produced under the new isolated model
  - `legacy`: historical root-level outputs retained only until purge/remediation completes
  - `invalid`: outputs whose provenance cannot be safely used by the product
- Define a delete-first policy for invalid legacy evidence.

### Exit criteria
- Phase 44 scope and evidence policy are written down before implementation closure.

---

## AWF-218: Run-local workspace and artifact isolation

> **Implementation note**: This AWF is the critical-path item for Phase 44. It touches the engine's most sensitive write paths and is therefore split into three sub-items (a/b/c) to keep each step reviewable with a clear regression checkpoint.

### AWF-218a: RunWorkspace abstraction + path derivation

#### Objective
Introduce a `RunWorkspace` (or equivalent) abstraction that derives all run-local paths from `artifacts/runs/{run_id}/` without changing any existing write behavior yet.

#### Required changes
- Define a workspace object/module that computes run-local paths for: runtime config, status, result CSV/DB, reports, metadata, top10, and seen_keys.
- Expose a factory or builder that engine code can call to obtain paths.
- No existing write paths are modified in this sub-item — the abstraction is purely additive.

#### Exit criteria
- `RunWorkspace` is importable and unit-tested for correct path derivation.
- Existing engine behavior is unchanged (no writes redirected yet).

### AWF-218b: Engine write-path migration to run-local

#### Objective
Migrate engine write paths one-by-one from root `artifacts/` to `RunWorkspace`-derived run-local paths, with bit-identical output verification at each step.

#### Required changes
- Redirect runtime config, status files, result CSV/DB files, reports, and metadata writes to run-local paths via `RunWorkspace`.
- For each migrated write path, verify that the output content is identical to what would have been written to root (dual-write + diff during migration, removed after verification).
- Update `seen_keys` construction to read from run-local results instead of shared root tables.

#### Exit criteria
- A single run completes with all primary evidence files written under `artifacts/runs/{run_id}/`.
- Dual-write smoke test confirms run-local output matches root output content for at least one full run.
- Existing tests remain green.

### AWF-218c: Remove root-workspace assumption

#### Objective
Remove the engine's assumption that `cwd/artifacts/` is the primary writable workspace. After this sub-item, root-level writes are no longer produced by `autowfo run`.

#### Architect review (2026-03-14)
Entry point (`run_btc_regime_sweep.py`) already routes all primary path variables through `workspace.*` properties. Tests already assert root-level evidence files do **not** exist. Core isolation is complete; remaining work is cleanup of transitional scaffolding.

#### Required changes (refined after review)
1. **Rename `out_dir` → `artifacts_root`** in `run_btc_regime_sweep.py`. The variable is only used for read-path derivation (config loading, cache dir) and parent directory creation — not evidence writes. The name `out_dir` is misleading now that writes go through `workspace`.
2. **Remove dual-write mirror scaffolding** in `engine_finalize.py`:
   - `_write_workspace_result_mirrors()` — now redundant because `out_dir` already equals `workspace.results_dir`, so `_write_run_snapshot_files()` already writes to the run-local path. Remove the mirror call and the function.
   - `_mirror_file()` for registry — registry is now written directly to `workspace.registry_path` via `update_run_registry_fn`. If the primary `registry_path` argument already points to workspace, the mirror is a no-op (caught by `abspath` equality check). Remove the mirror call; keep `_mirror_file()` only if other callers remain.
   - `_mirror_file()` for `db_path` — same situation: if `db_path` is already workspace-local, the mirror is redundant. Remove.
3. **Verify no duplicate writes**: after removing mirrors, confirm that each evidence file is written exactly once per run (no double CSV writes to the same path).

#### Exit criteria
- A single run can complete without writing primary evidence files to the root `artifacts/` directory.
- Two runs in the same repo no longer share output state.
- No dual-write scaffolding remains (`_write_workspace_result_mirrors`, mirror calls for registry/db removed).
- `out_dir` variable renamed to `artifacts_root` to reflect read-only/cache usage.

---

## AWF-219: Shared aggregation becomes a derived view

### Objective
Separate single-run truth from cross-run summaries so registry/leaderboard/analytics no longer mutate during run execution.

### Required changes
- Stop writing shared leaderboard/registry/root summary files during the run lifecycle.
- Rebuild shared views from trusted run roots via explicit aggregation steps.
- Add invariants that prevent a registry entry from disagreeing with its run-local metadata/top10/report set.

### Backward-compatibility constraint
Rebuilt shared views must preserve the same file formats, path conventions, and API response shapes as the current root-level outputs. This ensures AWF-221 (trusted-source control panel) can be implemented as a gradual migration rather than a big-bang switch. Specifically:
- `run_registry.json`, `leaderboard.csv`, and aggregate summary files retain their current schema.
- Control-panel HTTP endpoints continue to return the same payload shapes.
- Any format changes require explicit versioning via the existing storage-contract mechanism (Phase 42).

### Exit criteria
- Shared views can be rebuilt from trusted run roots and are no longer the source of truth for a run.
- Rebuilt shared views are format-compatible with existing control-panel and analytics consumers.

---

## AWF-220: Legacy purge tooling

### Objective
Provide an explicit tool that removes or quarantines root-level legacy evidence so it cannot continue to pollute later operations.

### Required changes
- Add a purge command with `--dry-run`.
- Scan root `artifacts/` for legacy run outputs such as:
  - `param_sweep_*.csv`
  - `leaderboard.csv`
  - `run_registry.json`
  - `run_metadata*.json`
  - `results.db`
  - `btc_regime_*.html`
- Support either permanent deletion or relocation into a quarantine path that the product never reads.

### Exit criteria
- Operators can enumerate and purge legacy root-level evidence without hand-curating file lists.

---

## AWF-221: Trusted-source control panel and analytics

### Objective
Make UI and analytics surfaces consume only trusted run roots or derived views rebuilt from them.

### Required changes
- Update control-panel result/overview/coverage readers to stop treating root `artifacts/` files as run truth.
- Ensure analytics rebuild and storage health checks target trusted runs.
- Surface evidence-source status in operator-facing outputs where helpful.

### Exit criteria
- Control panel and analytics do not rely on root-level legacy run outputs as primary evidence.

---

## AWF-222: Regression guards and integrity checks

### Objective
Add tests that make evidence pollution regressions hard to reintroduce.

### Required changes
- Add regression coverage for:
  - run-local path creation
  - shared-state isolation across multiple runs
  - registry/top10/metadata consistency
  - purge-tool dry-run and execution behavior
- Add integrity assertions where run-scoped files are generated or consumed.

### Exit criteria
- Evidence-integrity invariants are enforced by tests and fail loudly when broken.

---

## AWF-223: Legacy evidence reset execution

### Objective
Execute the legacy cleanup once the new model is live so the repository stops carrying ambiguous evidence.

### Required changes
- Run the purge workflow against root-level legacy artifacts.
- Rebuild shared registry/analytics from trusted run roots only.
- Record what was deleted or quarantined.

### Exit criteria
- Root `artifacts/` no longer contains ambiguous legacy run outputs that product code can mistake for trusted evidence.

---

## AWF-224: Targeted rerun protocol

### Objective
Re-establish a clean evidence baseline by rerunning only the campaigns that still matter.

### Required changes
- Define a rerun shortlist based on recent decision-relevant campaigns.
- Re-run those campaigns only after run isolation and legacy reset are complete.
- Record the new trusted replacements for any prior results that were used in interpretation.

### Exit criteria
- Decision-relevant campaigns have trusted replacements under the new evidence model.
- Phase 44 closes with a documented rerun baseline instead of ambiguous historical carry-over.
