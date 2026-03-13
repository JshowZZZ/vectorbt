# AUTOWFO Phase 43 Spec

## Phase 43: Storage Operations and Migration Tooling

### Goal
Turn the Phase 42 storage contracts into operator-usable tooling: validation, normalization/migration, analytics rebuild, and a lightweight health surface in the control panel.

### Scope Rules
- Do not change strategy logic, experiment scoring, or UI navigation structure.
- Reuse the Phase 42 storage contracts instead of inventing parallel state formats.
- Prefer additive operator tooling over silent background mutation.
- Finish the phase only after CLI, endpoint, and regression coverage are all in place.

### Validation Baseline
- `python -m pytest tests/test_autowfo_storage_ops.py tests/test_autowfo_cli.py tests/test_control_panel_experiments.py -q`
- `python -m pytest tests/test_control_panel_experiments.py tests/test_e2e_experiment_lifecycle.py tests/test_experiments_ui_integration.py -q`

---

## AWF-211: Phase 43 documentation freeze + operations contract

### Objective
Freeze the storage-operations scope before implementation starts.

### Required changes
- Create this spec file.
- Define ordered AWFs for validation, migration, analytics rebuild, endpoint exposure, and closure.

### Exit criteria
- Phase 43 scope is written down before implementation closure.

---

## AWF-212: Storage validation and inspection core

### Objective
Provide a reusable inspection layer that can report storage health without mutating state.

### Required changes
- Add a storage-ops module that inspects:
  - experiment run metadata
  - scheduler queue state
  - paper-position state
  - signal-scheduler state
  - analytics metadata
- Return machine-readable summary + issues.

### Exit criteria
- Storage validation can report health and schema-version status for major mutable-state surfaces.

---

## AWF-213: Storage migration / normalization tooling

### Objective
Provide an explicit operator command that rewrites legacy-readable payloads into the current versioned shapes.

### Required changes
- Add a migration command with dry-run support.
- Normalize writable legacy payloads through the canonical readers/writers.
- Report changed files and failures.

### Exit criteria
- Operators can dry-run and apply storage normalization without hand-editing JSON files.

---

## AWF-214: Analytics rebuild tooling

### Objective
Make analytics rebuild a first-class supported operation instead of an implicit manual recovery step.

### Required changes
- Add a rebuild command that recreates `analytics.duckdb` from experiment run stores.
- Preserve explicit reporting of imported runs/combos and metadata version.

### Exit criteria
- Operators can rebuild analytics from artifacts with a single command.

---

## AWF-215: Control-panel storage health endpoint and surfacing

### Objective
Expose storage health to the packaged control panel so operators can inspect system state without leaving the UI.

### Required changes
- Add a control-panel JSON endpoint for storage health.
- Surface a compact storage-health summary in the control panel overview.

### Exit criteria
- Control panel exposes machine-readable storage health and a visible summary panel.

---

## AWF-216: Regression validation + plan closure

### Objective
Prove the tooling works and close the phase in planning docs.

### Required changes
- Add regression tests for validation, migration, rebuild, and the control-panel endpoint.
- Update master plan / TODO / archive.
- Write AWF-211~216 reports.

### Exit criteria
- Phase 43 code paths are covered by focused regression tests and planning docs return to steady state.
