# AWF-173 Implementation Report

## Header

| Field | Value |
|-------|-------|
| AWF ID | AWF-173 |
| Title | CLI polish + deprecation cleanup + final regression |
| Phase | 34 |
| Codex completion date | 2026-03-01 |
| Spec reference | Phase 34 prompt (2026-03-01), AWF-173 |
| Architect review date |  |
| Review result |  |

## 1. Files Created / Modified **(Codex)**

| Status | File | Reason |
|--------|------|--------|
| ?? | `autowfo/cli.py` | Added `--version` support resolved from `pyproject.toml` dynamic version metadata |
| ?? | `pyproject.toml` | Added pytest `filterwarnings` rules to suppress known third-party deprecation warnings only |
| ?? | `tests/test_autowfo_cli.py` | Added CLI regression tests for `--version` output and `--help` subcommand visibility |
| ?? | `plans/AUTOWFO_MASTER_PLAN.md` | Added Phase 34 delivery snapshot and operational-readiness changelog entry |
| ?? | `plans/AUTOWFO_ARCHITECTURE_V2.md` | Extended stability hardening section to include Phase 34 operational guardrails |
| ?? | `plans/AUTOWFO_TODO.md` | Updated active phase and archive note for Phase 34 completion |
| ?? | `plans/AUTOWFO_TODO_ARCHIVE.md` | Archived AWF-171~173 entries |

**Files intentionally NOT touched**:
- Core strategy execution modules (`scripts/autowfo/engine_*`, `signal_composer.py`, `experiment.py`)

## 2. Implementation Summary **(Codex)**

Polished CLI ergonomics with version introspection from project metadata and confirmed subcommand discoverability via help regression tests. Added scoped warning filters for known third-party deprecations (binance/websockets/telegram) without suppressing project-origin warnings. Completed final documentation freeze updates through Phase 34 and executed full AUTOWFO/control-panel regression scope with zero failures.

## 3. Deviations from Spec **(Codex)**

None.

## 4. Exit Criteria Checklist **(Codex)**

- [x] Added `autowfo --version` output from `pyproject.toml`-resolved version metadata
- [x] Verified `autowfo --help` subcommands visibility via regression test
- [x] Added pytest deprecation filters for third-party warnings only
- [x] Executed full AUTOWFO/control-panel scope regression with 0 failed
- [x] Updated MASTER_PLAN + TODO + ARCHITECTURE_V2 freeze records for Phase 34

## 5. Test Results **(Codex)**

**Verification commands run**:
```bash
pytest tests/test_autowfo_cli.py -k "cli_version_outputs_version or cli_help_lists_all_subcommands" -v
pytest tests -q --tb=short -k "autowfo or control_panel or e2e or experiments or real_data or patrol_stability or validate_patrol_dryrun"
```

**Result**:
```text
2 passed, 0 failed
557 passed, 858 deselected, 0 failed
```

**New tests added**: 2 tests in `tests/test_autowfo_cli.py`

**Specific test coverage for exit criteria**:

| Exit criterion | Test name | Result |
|----------------|-----------|--------|
| `--version` outputs resolved project version | `test_cli_version_outputs_version` | ? pass |
| `--help` includes expected subcommands | `test_cli_help_lists_all_subcommands` | ? pass |
| full AUTOWFO/control-panel regression is clean | full regression command above | ? pass |

## 6. Cross-Phase Interface Exposure **(Codex)**

N/A �X this AWF has no cross-phase interface.

## 7. Known Issues / Risks **(Codex)**

- Deprecation filters are intentionally narrow to third-party modules; if upstream warning signatures change, filters may require periodic refresh.

## 8. BLOCKER (if applicable) **(Codex)**

**Status**: NOT BLOCKED

---
# ARCHITECT REVIEW
> Everything below is filled by Architect only. Codex does not edit this section.
---

**Architect review date**: 2026-03-01
**Review result**: ✓ APPROVED

### R1 — Architecture Alignment
- [x] `--version` wired from pyproject.toml dynamic metadata — single source of truth
- [x] filterwarnings scoped to third-party modules only — project warnings remain visible
- [x] Full regression: 557 passed (Codex); Architect independent: 4 Phase 34 CLI tests + 9 patrol/discovery + 215 core = clean

### R2 — Code Quality
- [x] Deprecation filters narrowly targeted — no blanket suppression
- [x] Version + help tests are regression anchors, not test bloat
- [x] Documentation freeze complete: MASTER_PLAN/ARCHITECTURE_V2/TODO/ARCHIVE updated

### R3 — Test Quality
- [x] `test_cli_version_outputs_version` — version string from metadata verified
- [x] `test_cli_help_lists_all_subcommands` — all subcommands discoverable
- [x] 2 new tests pass independently

### R4 — Report Quality
- [x] File list accurate
- [x] No deviations
- [x] Test count stated: 557 passed
