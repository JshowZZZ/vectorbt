# AWF-195 Implementation Report

## Header

| Field | Value |
|-------|-------|
| AWF ID | AWF-195 |
| Title | control panel package migration + new module entrypoint |
| Phase | 40 |
| Codex completion date | 2026-03-12 |
| Spec reference | `plans/AUTOWFO_PHASE40_SPEC.md#awf-195-control-panel-package-migration--new-entrypoint` |
| Architect review date |  |
| Review result |  |

## 1. Files Created / Modified

| Status | File | Reason |
|--------|------|--------|
| created | `autowfo/control_panel/__init__.py` | Declare packaged control-panel surface |
| created | `autowfo/control_panel/__main__.py` | Support `python -m autowfo.control_panel` |
| created | `autowfo/control_panel/static/*` and `static_legacy/*` | Package current and legacy UI assets with the control panel |
| created | `autowfo/control_panel/*.py` | Move control-panel backend modules into packaged namespace |
| deleted | `scripts/control_panel.py` and `scripts/control_panel_*.py` | Remove retired control-panel module surface |
| deleted | `autowfo/control_panel/legacy.py` | Drop unsupported forwarding layer |
| modified | `tests/test_control_panel.py`, `tests/test_control_panel_experiments.py`, `tests/test_e2e_experiment_lifecycle.py`, `tests/test_experiments_ui_integration.py` | Point tests at `autowfo.control_panel.server` |

## 2. Implementation Summary

The control panel now lives fully inside `autowfo.control_panel`, with `server.py` as the HTTP entrypoint and `__main__.py` as the supported module launcher. Static assets were moved into the package so the control panel no longer depends on the repo-local `scripts/control_panel/` tree.

## 3. Deviations from Spec

None.

## 4. Exit Criteria Checklist

- [x] `python -m autowfo.control_panel` is a valid startup path.
- [x] Static assets resolve relative to the installed package.
- [x] Product code and tests no longer import `scripts.control_panel*`.

## 5. Test Results

Covered by AWF-197 validation:

```bash
python -c "import autowfo.control_panel"
python -m pytest tests/test_control_panel.py tests/test_control_panel_experiments.py tests/test_e2e_experiment_lifecycle.py -q
```

## 6. Cross-Phase Interface Exposure

N/A - this AWF has no cross-phase interface.

## 7. Known Issues / Risks

The packaged control panel still uses process-global runtime state. Phase 40 moved the namespace/package boundary, not the control-panel runtime model.

## 8. BLOCKER

Status: NOT BLOCKED
