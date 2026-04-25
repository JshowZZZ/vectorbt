# agentsmd Integration

## Purpose
This repository uses `AGENTS.md` as the shared instruction source and supports local overlays via `agentsmd`.

## What Was Set Up
- Installed Node.js LTS (required by `@adiasg/agentsmd`).
- Installed CLI globally: `@adiasg/agentsmd`.
- Enabled repo automation with `agentsmd enable`:
  - managed hooks in `.git/hooks/`
  - merge driver for `AGENTS.md` in `.git/info/attributes`
  - alias `git rebuild-agents`
- Added local wrapper for Windows usage: `scripts/agentsmd.cmd`.

## Local Files (Not Committed by Default)
- `.agentsmd` (private overlay)
- `~/.agentsmd/templates/*.md` (template snippets)

Use `.agentsmd.example` as a starting point.

## Recommended Commands (Windows)
- Status: `scripts\\agentsmd.cmd status`
- Render: `scripts\\agentsmd.cmd make`
- Enable automation: `scripts\\agentsmd.cmd enable`
- Disable automation: `scripts\\agentsmd.cmd disable`

## Notes
- `agentsmd` runs through Bash; this wrapper adds Git Bash to PATH.
- If Python is not found from Bash, ensure `python3` is available in Bash PATH.
- For AUTOWFO survivalism work, do not create a parallel `docs/` governance
  tree and do not edit `AGENTS.md` directly unless the managed overlay workflow
  is explicitly part of the task. Use the planning surfaces below instead.

## AUTOWFO Survivalism Agent Context

Before implementing evidence warehouse, Survival Gate, strategy lifecycle,
reality-gap, cockpit, risk-engine, or micro-live work, an agent should read:

- `plans/AUTOWFO_SURVIVALISM_FRAMEWORK.md`
- `plans/AUTOWFO_DECISION_LOG.md`
- `plans/AUTOWFO_EVIDENCE_WAREHOUSE_V1.md`
- `plans/AUTOWFO_SURVIVAL_GATE_POLICY.md`
- `plans/AUTOWFO_STRATEGY_LIFECYCLE.md`
- `plans/protocols/evidence_warehouse_v1.json`
- `plans/protocols/survival_gate_policy_v1.json`

The first implementation target is Evidence Warehouse V1. Risk-engine and
micro-live enforcement are intentionally deferred until evidence identity,
cost observations, execution-gap events, and immutable gate verdicts exist.

## Encoding Guardrails
- Keep technical docs and control-panel static files in UTF-8.
- Do not paste text from mixed-encoding terminals directly into tracked files.
- Before handoff, run quick mojibake checks:
  - `rg -n "\\uFFFD|\\?\\?" plans scripts/control_panel/static`
  - `node --check scripts/control_panel/static/js/*.js`
  - `pytest tests/test_control_panel.py -q`
- If any mojibake is found, rewrite the affected line immediately and re-run checks.

## Project Sync 2026-02-24
- Scope synced: AUTOWFO engine split modules, control-panel static modularization, protocol/doc updates.
- Upload validation baseline used in this batch:
  - `pytest tests/test_autowfo_cli.py tests/test_autowfo_cross_run.py tests/test_control_panel.py tests/test_autowfo_e2e.py tests/test_autowfo_gate_e.py -q` (`172 passed`).
- Git upload checklist for repeatable handoff:
  - `git status --short`
  - `git add -A`
  - `git commit -s -m "feat: synchronize autowfo engine and control panel delivery batch"`
  - `git push origin main`
