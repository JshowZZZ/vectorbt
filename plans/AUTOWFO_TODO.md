# AUTOWFO TODO

## Usage Rules
- This file is the execution backlog for AUTOWFO.
- Every implementation task must map to one TODO ID.
- Update status immediately after task completion.
- Allowed statuses: `todo`, `doing`, `blocked`, `done`.

## Priorities
- P0: Foundation and correctness
- P1: Core automation and ranking quality
- P2: Scale, usability, and continuous operation

## Backlog
| ID | Priority | Status | Owner | Est. Date | Task | Deliverable | Exit Criteria |
|---|---|---|---|---|---|---|---|
| AWF-001 | P0 | todo | JshowZZZ + AI agent | TBD | Define canonical split protocol (range/rolling/expanding, set_lens policy) | Protocol section in docs/config | Fixed schema used by all runs |
| AWF-002 | P0 | todo | JshowZZZ + AI agent | TBD | Define metric contract (IS/OOS, drawdown, Sharpe, stability terms) | Metric spec doc | Metric names/formulas frozen for MVP |
| AWF-003 | P0 | todo | JshowZZZ + AI agent | TBD | Define strategy spec schema for indicator combos and signal logic | Schema file + validator | Invalid specs fail fast with clear errors |
| AWF-004 | P0 | todo | JshowZZZ + AI agent | TBD | Define experiment artifact schema | Artifact contract doc | Every run emits reproducible metadata |
| AWF-005 | P1 | todo | JshowZZZ + AI agent | TBD | Build orchestration MVP pipeline | Runnable module/script | End-to-end run from spec to leaderboard |
| AWF-006 | P1 | todo | JshowZZZ + AI agent | TBD | Implement stability-first ranking function | Ranking module + tests | Top-N based on OOS robustness works |
| AWF-007 | P1 | todo | JshowZZZ + AI agent | TBD | Add benchmark scenario for regression | Baseline config + expected outputs | Repeated runs are deterministic |
| AWF-008 | P1 | todo | JshowZZZ + AI agent | TBD | Add two-stage search (coarse->focused) | Search module extension | Runtime improves vs brute-force |
| AWF-009 | P2 | todo | JshowZZZ + AI agent | TBD | Add run registry (history + diff) | Experiment index artifacts | Can compare current run vs prior run |
| AWF-010 | P2 | todo | JshowZZZ + AI agent | TBD | Add one-command execution entrypoint | CLI/script command | Full pipeline runnable by one command |
| AWF-011 | P2 | todo | JshowZZZ + AI agent | TBD | Add regression tests for split and ranking invariants | Test suite additions | CI/local tests catch protocol regressions |
| AWF-012 | P2 | todo | JshowZZZ + AI agent | TBD | Add operational playbook | Runbook doc | New run can be operated without notebook |

## Current Focus Window
- Active milestone: Protocol and Constraints
- Allowed implementation now: only tasks AWF-001 to AWF-004
- Blocked until protocol freeze: AWF-005 and beyond

## Session Log
| Date | Task IDs | Status Change | Decision | Next Action | Commit/Ref |
|---|---|---|---|---|---|
| 2026-02-06 | AWF-ALL | initialized | Backlog skeleton created | Start protocol freeze tasks AWF-001~004 | initial planning commit |
| 2026-02-06 | AWF-ALL | metadata_update | Added owner/date columns and structured logging format | Populate Est. Date during next planning sync | docs refinement |
