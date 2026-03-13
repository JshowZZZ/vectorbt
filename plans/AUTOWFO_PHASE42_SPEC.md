# AUTOWFO Phase 42 Spec

## Phase 42: Storage Contract Hardening and Migration Readiness

### Goal
Put explicit schema-version contracts around AUTOWFO's mutable state files and experiment artifacts so upgrades can remain backward-compatible and diagnosable.

### Scope Rules
- Do not add new strategy, analytics, or UI features.
- Keep existing readers backward-compatible with legacy unversioned payloads where feasible.
- Prefer additive storage changes over destructive format rewrites.
- Finish the phase only after tests cover both new-version writes and legacy-payload reads.

### Validation Baseline
- `python -m pytest tests/test_autowfo_artifact_store.py tests/test_autowfo_scheduler.py tests/test_autowfo_paper_position.py tests/test_autowfo_signal_scheduler.py tests/test_autowfo_analytics.py -q`
- `python -m pytest tests/test_control_panel_experiments.py tests/test_e2e_experiment_lifecycle.py -q`

---

## AWF-205: Phase 42 documentation freeze + storage contract scope

### Objective
Freeze the storage-hardening scope before code starts to change on-disk payloads.

### Required changes
- Add Phase 42 to planning docs.
- Create this spec file.
- Define ordered AWFs for versioned state/artifact surfaces and validation.

### Exit criteria
- Phase 42 scope is written down before implementation closure.

---

## AWF-206: Experiment artifact schema-version contract

### Objective
Add explicit schema-version metadata to experiment-scoped artifact payloads without breaking existing readers.

### Required changes
- Version `run_meta.json` written by `ArtifactStore`.
- Keep legacy run-meta files readable.
- Expose storage constants in a dedicated contract module.

### Exit criteria
- New run-meta writes include schema version.
- Old run-meta files still load successfully.

---

## AWF-207: Queue and paper-state schema-version contract

### Objective
Version the mutable state files that drive scheduler and paper-trading behavior.

### Required changes
- Version scheduler queue payloads.
- Version paper-position storage payloads while keeping legacy list payloads readable.
- Version signal-scheduler state payloads while keeping legacy state objects readable.

### Exit criteria
- New state files include schema version.
- Legacy state files migrate on read without crashing callers.

---

## AWF-208: Analytics metadata contract

### Objective
Make the analytics store self-describing enough for future migration/rebuild decisions.

### Required changes
- Add a metadata table or equivalent schema-version marker to the DuckDB analytics store.
- Expose a small metadata read surface for verification/tests.

### Exit criteria
- Analytics store can report its schema version.

---

## AWF-209: Regression + legacy-migration validation

### Objective
Prove the new storage contracts are backward-compatible and stable.

### Required changes
- Add regression coverage for new-version writes.
- Add regression coverage for legacy payload reads.
- Re-run focused experiment/control-panel suites that consume these artifacts.

### Exit criteria
- Focused storage and experiment suites pass.

---

## AWF-210: Plan closure + steady-state update

### Objective
Close the phase in planning docs once storage hardening is validated.

### Required changes
- Update master plan/TODO/archive.
- Write AWF-205~210 reports.

### Exit criteria
- Planning docs reflect Phase 42 completion and steady-state re-entry.
