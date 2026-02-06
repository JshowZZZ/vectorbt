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

