# AUTOWFO Phase 48 Spec

## Title
Control-Panel Rerun Campaign Readiness

## Date
2026-03-28

## Background
- `plans/AUTOWFO_RERUN_CAMPAIGN_20260328.md` already defines which reruns should happen through the control panel.
- The current Config tab still has two operator-facing gaps:
  - saving config from the panel rebuilds from `DEFAULT_CONFIG`, so fields not exposed in the UI can be reset unintentionally
  - rerun waves exist only in docs; operators still have to hand-edit timeframe/day/symbol combinations before using Coverage/Batch

## Problem Statement
- The rerun campaign is planned, but the control panel is not yet safe or efficient enough to execute that plan directly.
- A save from Config can silently overwrite preserved runtime knobs such as:
  - `ranking`
  - `max_workers`
  - `checkpoint_every_n`
  - `progress_every_n`
- Wave 0 / Wave 2 rerun combinations are not available as first-class presets inside the panel.

## Scope
- Make Config save preserve existing config fields that are not explicitly edited in the UI.
- Add rerun campaign presets to the Config tab so operators can apply documented Wave 0 / Wave 2 targets without manual JSON editing.
- Expose preset metadata and preset-apply actions through control-panel endpoints.
- Add regression coverage for both behaviors.

## Non-Goals
- No broad redesign of the Config tab layout.
- No multi-timeframe campaign planner UI in this phase.
- No automatic batch start when applying a preset.

## Deliverables

### AWF-237 Config Preservation
- Backend save path merges UI payload into the current stored config rather than rebuilding from defaults.
- Preserved keys must include nested config sections such as `ranking`.
- Guardrails such as `wf_step_days >= wf_test_days` remain enforced.

### AWF-238 Rerun Campaign Presets
- `GET /config/presets.json` returns operator-facing preset metadata.
- `POST /config/apply-preset` applies a preset and writes the resulting `artifacts/sweep_config.json`.
- Config tab shows preset cards/buttons for:
  - Wave 0 smoke (`ETH/BTC`, `BNB/BTC`, `SOL/BTC`, `1h`, `60d`)
  - Wave 2 core historical rebuild (`BNB/BTC`, `SOL/BTC`, `2h`, `120d`)
  - Wave 2 XRP rebuild (`XRP/BTC`, `4h`, `180d`)
  - Wave 2 optional non-BTC quote check (`SOL/USDT`, `2h`, `120d`)

## Validation
- Targeted control-panel regression:
  - preserve non-UI config fields on save
  - presets endpoint contract
  - preset apply endpoint writes expected config
- Frontend syntax validation for touched JS files.

## Exit Criteria
- Operators can execute Wave 0 / Wave 2 rerun preparation directly from Config + Coverage + Batch.
- Saving from Config no longer resets hidden runtime fields back to defaults.
- Targeted regression is green.
