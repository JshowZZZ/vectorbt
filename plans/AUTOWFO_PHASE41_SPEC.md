# AUTOWFO Phase 41 Spec

## Phase 41: Service Boundary and Operations Hardening

### Goal
Turn the packaged control panel into a configurable, service-oriented runtime with an explicit path contract, centralized transient state, and repeatable startup behavior.

### Scope Rules
- Do not add new strategy-search, analytics, or UI features.
- Keep existing HTTP routes and payload contracts stable.
- Move runtime/process/thread state behind a single control-panel runtime container.
- Make control-panel startup configurable by CLI args and environment variables.
- Close the phase only after docs and regression evidence match the new runtime contract.

### Validation Baseline
- `python -m pytest tests/test_control_panel.py tests/test_control_panel_experiments.py tests/test_experiments_ui_integration.py tests/test_e2e_experiment_lifecycle.py -q`
- `python -m pytest tests -q --tb=short`
- `python -m autowfo.control_panel --help`
- `python -c "from autowfo.control_panel import configure_runtime, get_runtime; configure_runtime(root='.', artifacts_dir='artifacts', reset_state=True); print(get_runtime().paths.artifacts)"`

---

## AWF-199: Phase 41 documentation freeze + runtime contract

### Objective
Freeze the Phase 41 scope in plan documents before runtime refactoring is treated as complete.

### Required changes
- Add Phase 41 to `plans/AUTOWFO_MASTER_PLAN.md`.
- Record Phase 41 closure/status in `plans/AUTOWFO_TODO.md`.
- Create this spec file.
- Prepare AWF-199~204 implementation reports.

### Exit criteria
- Phase 41 is described in the master plan.
- TODO reflects Phase 41 ownership/status.
- The runtime/service contract is written down before closure.

---

## AWF-200: Configurable root/artifacts contract + startup options

### Objective
Make the control panel runnable against an explicit work root and artifacts root instead of implicit `cwd` assumptions.

### Required changes
- Introduce a runtime path model under `autowfo.control_panel`.
- Add `configure_runtime(...)` and `get_runtime()` helpers.
- Add `python -m autowfo.control_panel --host --port --root --artifacts-dir`.
- Add environment variable fallbacks for host/port/root/artifacts and data-refresh interval.

### Exit criteria
- Tests can configure isolated roots without monkeypatching raw module globals.
- The packaged entrypoint accepts CLI overrides for runtime paths.
- Control-panel path derivation stays deterministic after reconfiguration.

---

## AWF-201: Process + data-refresh runtime convergence

### Objective
Centralize run/test/batch process state and data-refresh thread state behind one runtime container.

### Required changes
- Add runtime dataclasses for path, process, and data-refresh state.
- Update control-panel run/test helpers to use the runtime container.
- Keep compatibility aliases in `server.py` synchronized for existing route modules/tests.
- Ensure data-refresh thread startup and reset paths update the shared runtime state.

### Exit criteria
- Run/test/batch subprocess references are no longer defined independently in multiple modules.
- Data-refresh thread state is managed via the runtime container.
- Existing routes continue to behave the same under regression tests.

---

## AWF-202: Scheduler runtime convergence + mutable-state sync

### Objective
Move experiment-scheduler thread/error/runtime state into the shared runtime container and keep legacy module aliases synchronized.

### Required changes
- Remove module-local scheduler globals from `autowfo.control_panel.experiments`.
- Store scheduler thread, stop event, and last-error metadata in the runtime container.
- Sync mutable alias surfaces (`BATCH_PROCESS`, caches, refresh thread) back into the runtime after routed module calls.
- Preserve queue/status/stop endpoint behavior.

### Exit criteria
- Scheduler runtime status is backed by the shared runtime container.
- Routed modules keep runtime state and server aliases consistent.
- Experiment queue/scheduler tests stay green.

---

## AWF-203: Regression validation for runtime contract

### Objective
Prove the new runtime container does not break control-panel behavior.

### Required changes
- Update tests to use `configure_runtime(...)` instead of raw global monkeypatching where appropriate.
- Add regression coverage for runtime reconfiguration and CLI startup overrides.
- Run focused control-panel suites and full repository regression.

### Exit criteria
- Focused control-panel suites pass.
- Full `pytest tests -q --tb=short` passes.
- New runtime configuration behavior has explicit regression coverage.

---

## AWF-204: Runbook / README / plan closure + steady-state update

### Objective
Close the phase with operator-facing docs and planning state aligned to the new runtime contract.

### Required changes
- Update `README.md` AUTOWFO entrypoint guidance with startup options/environment variables.
- Update `plans/AUTOWFO_RUNBOOK.md` with explicit control-panel startup commands.
- Archive AWF-199~204 in `plans/AUTOWFO_TODO_ARCHIVE.md`.
- Write AWF implementation reports and return TODO to steady state.

### Exit criteria
- README and runbook explain the new control-panel startup contract.
- Master plan, TODO, archive, and AWF reports reflect Phase 41 completion.
- Repository returns to steady-state documentation after validation.
