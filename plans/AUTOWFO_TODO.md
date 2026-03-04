# AUTOWFO TODO

## Usage Rules
- This file tracks only active-phase execution items.
- Completed historical items are archived in `plans/AUTOWFO_TODO_ARCHIVE.md`.
- Allowed statuses: `todo`, `doing`, `blocked`, `done`.

## Active Phase — UI-1: Control Panel UX Overhaul

| ID | Priority | Status | Task | Deliverable | Exit Criteria |
|---|---|---|---|---|---|
| AWF-190 | P1 | done | Sidebar navigation + responsive layout rebuild | `app.js`: horizontal tabs → collapsible icon sidebar; `app.css`: sidebar tokens + mobile breakpoints; `index.html`: viewport meta verified | Sidebar renders correctly on desktop (≥1024px) and collapses to icon-only on mobile (<768px); all 10 tabs accessible; no JS errors in console |
| AWF-191 | P1 | todo | Shared component library + i18n completion | `components.js`: KpiCard, StatusBadge, EmptyState, SearchInput, Pagination reusable components; `i18n.js`: 100% key coverage audit + missing keys filled; all tab files migrated to shared components | Zero hardcoded color/style in tab files; `i18n.js` coverage ≥95%; DataTable sort/filter works consistently across Results/Dashboard/Analytics/Experiments tabs |
| AWF-192 | P1 | todo | Page-level visual polish + micro-interactions | Per-tab template cleanup (overview/config/results/dashboard/coverage/experiments/analytics); skeleton loading states; toast feedback on all mutations; Chart.js theme-aware colors; empty-state illustrations | Visual consistency across all tabs; loading skeleton visible during data fetch; toast appears on save/delete/run actions; charts respect dark/light theme |

## Backlog

No items beyond UI-1 phase.

## Maintenance
- Dependency tracking: pandas 2.x baseline validation and upgrade-readiness checks (targeted periodic smoke + full regression).
- Warning cleanup: reduce third-party and internal deprecation/future warnings without suppressing project-critical warnings (AWF-189 closed — 30 warnings baseline).

## Notes
- AWF-113~AWF-189 completed items are archived in `plans/AUTOWFO_TODO_ARCHIVE.md`.
