# AUTOWFO Phase 40 Spec

## Phase 40: Namespace and Packaging Convergence

### Goal
Move AUTOWFO from a mixed `autowfo.*` + `scripts.*` layout to a single packaged namespace rooted at `autowfo.*`, while keeping behavior stable and validation evidence explicit.

### Scope Rules
- Do not add new strategy, analytics, scheduler, or UI features.
- Do not keep compatibility forwarding layers for `scripts.autowfo.*` or `scripts.control_panel*`.
- Keep `python -m autowfo` behavior stable.
- Make `python -m autowfo.control_panel` the supported control-panel startup path.
- Finish the phase only after docs, tests, and packaging metadata match the new namespace.

### Validation Baseline
- `rg -n "scripts\\.autowfo|scripts\\.control_panel|from scripts import control_panel" autowfo tests scripts`
- `python -m autowfo --help`
- `python -c "import autowfo, autowfo.control_panel"`
- `python -m pytest tests/test_autowfo_module_imports.py tests/test_autowfo_cli.py tests/test_control_panel.py tests/test_control_panel_experiments.py tests/test_e2e_experiment_lifecycle.py -q`
- `python -m pip install -e .`
- `python -m build`

---

## AWF-193: Phase 40 documentation freeze + namespace contract

### Objective
Freeze the Phase 40 scope in plan documents before implementation proceeds.

### Required changes
- Add Phase 40 to `plans/AUTOWFO_MASTER_PLAN.md`.
- Record Phase 40 closure/status in `plans/AUTOWFO_TODO.md`.
- Create this spec file.
- Prepare AWF-193~198 report placeholders/output requirements.

### Exit criteria
- Phase 40 is described in the master plan.
- TODO reflects Phase 40 ownership/status.
- The namespace contract is written down before code closure.

---

## AWF-194: `scripts.autowfo.*` -> `autowfo.*` runtime migration

### Objective
Make `autowfo.*` the only supported runtime namespace for AUTOWFO product code.

### Required changes
- Move reusable runtime modules from `scripts/autowfo/` into `autowfo/`.
- Update runtime, tests, and leaf scripts to import `autowfo.*`.
- Remove `scripts/__init__.py`.
- Remove `autowfo/cli_legacy.py`.

### Exit criteria
- Product code and tests no longer import `scripts.autowfo.*`.
- Leaf scripts import `autowfo.*` directly.
- Runtime smoke imports succeed from `autowfo.*`.

---

## AWF-195: control panel package migration + new entrypoint

### Objective
Turn the control panel into a packaged AUTOWFO subsystem under `autowfo.control_panel`.

### Required changes
- Move `scripts/control_panel.py` to `autowfo/control_panel/server.py`.
- Move `scripts/control_panel_*.py` to `autowfo/control_panel/*.py`.
- Move static assets into `autowfo/control_panel/static/` and `static_legacy/`.
- Add `autowfo/control_panel/__main__.py`.
- Update tests and runtime imports to use `autowfo.control_panel.*`.

### Exit criteria
- `python -m autowfo.control_panel` is a valid startup path.
- Static assets resolve relative to the installed package.
- Product code and tests no longer import `scripts.control_panel*`.

---

## AWF-196: packaging metadata + static asset distribution

### Objective
Make the new package structure installable without relying on repo-local `scripts/` paths.

### Required changes
- Update `pyproject.toml` package discovery to `vectorbt*` + `autowfo*`.
- Include control panel HTML/CSS/JS/static assets as package data.
- Ensure path resolution uses module-relative locations for packaged assets.

### Exit criteria
- Editable install succeeds.
- Build succeeds.
- Installed package can serve control-panel assets without repo `scripts/`.

---

## AWF-197: import-surface cleanup + regression validation

### Objective
Prove the new namespace is the only active one and that behavior remains stable.

### Required changes
- Remove remaining `scripts.autowfo` / `scripts.control_panel` imports from product code and tests.
- Update validation scripts to import the new package paths.
- Run targeted regression suites around CLI, module imports, control panel, and experiment lifecycle.

### Exit criteria
- Search shows no product/test imports from the retired namespaces.
- CLI and control-panel smoke checks pass.
- Targeted regression suites pass.

---

## AWF-198: README / plan closure + steady-state update

### Objective
Close the phase in user-facing and planning documents once validation is complete.

### Required changes
- Add AUTOWFO entrypoint guidance to `README.md`.
- Archive AWF-193~198 in `plans/AUTOWFO_TODO_ARCHIVE.md`.
- Write AWF completion reports for 193~198.
- Update steady-state wording in current planning docs.

### Exit criteria
- README documents the packaged AUTOWFO entrypoints.
- Master plan, TODO, archive, and AWF reports all reflect Phase 40 completion.
- Repository returns to steady-state documentation after validation.
