# AWF-196 Implementation Report

## Header

| Field | Value |
|-------|-------|
| AWF ID | AWF-196 |
| Title | Packaging metadata + static asset distribution |
| Phase | 40 |
| Codex completion date | 2026-03-12 |
| Spec reference | `plans/AUTOWFO_PHASE40_SPEC.md#awf-196-packaging-metadata--static-asset-distribution` |
| Architect review date |  |
| Review result |  |

## 1. Files Created / Modified

| Status | File | Reason |
|--------|------|--------|
| modified | `pyproject.toml` | Remove `scripts*` from package discovery and add control-panel package data |
| modified | `autowfo/control_panel/server.py` | Keep static asset paths module-relative |
| modified | `autowfo/control_panel/state.py` | Resolve `/static/*` requests through packaged static root |

## 2. Implementation Summary

Packaging metadata now exposes only `vectorbt*` and `autowfo*`, matching the new supported namespace. Control-panel HTML/CSS/JS assets are declared as package data so editable install and wheel builds include the UI files without needing any repo-local `scripts/` directory.

## 3. Deviations from Spec

None.

## 4. Exit Criteria Checklist

- [x] Editable install succeeds.
- [x] Build succeeds.
- [x] Installed package can serve control-panel assets without repo `scripts/`.

## 5. Test Results

Covered by AWF-197 validation:

```bash
python -m pip install -e .
python -m build
```

## 6. Cross-Phase Interface Exposure

N/A - this AWF has no cross-phase interface.

## 7. Known Issues / Risks

Wheel validation proves assets are packaged, but runtime artifacts still default to the current working directory as intended for operator workflows.

## 8. BLOCKER

Status: NOT BLOCKED
