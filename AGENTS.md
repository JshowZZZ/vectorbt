# AGENTS

## Project Overview
- `vectorbt` is a Python library for fast, vectorized strategy backtesting and analytics.
- Prioritize minimal, behavior-preserving changes unless the task explicitly requests otherwise.

## Repository Map
- `.github/` - GitHub workflows and repository metadata.
- `apps/` - app-like examples.
- `docs/` - MkDocs source content and generation scripts.
- `examples/` - notebooks and demo assets.
- `scripts/` - utility scripts.
- `tests/` - pytest suite.
- `vectorbt/` - main package.
  - `base/`, `generic/`, `utils/` - shared core abstractions and helpers.
  - `data/` - data loaders/providers.
  - `indicators/`, `signals/`, `labels/` - signal/indicator/label functionality.
  - `portfolio/`, `records/`, `returns/` - simulation and analytics.
  - `messaging/` - notification helpers.
  - `templates/` - JSON templates.

## Environment and Setup
- Editable install: `pip install -e .`
- Optional dependencies: `pip install -U ".[full]"` or `pip install -U ".[full-no-talib]"`
- Run tests: `pytest`
- Run focused tests first when possible: `pytest tests/path/to/test_file.py -k "<pattern>"`

## Coding Guidelines
- Follow existing Python conventions:
  - `snake_case` for functions/variables.
  - `PascalCase` for classes.
- Keep edits small and localized; avoid broad refactors.
- Avoid reformat-only diffs.
- Add type hints/comments only when they clarify non-obvious logic.
- Keep public API exports stable (especially `vectorbt/__init__.py`) unless change is requested.

## Change and Validation Rules
- Preserve existing behavior and defaults unless explicitly asked to change them.
- If behavior changes, update or add tests in `tests/`.
- Prefer targeted tests during iteration, then run `pytest` before handing off when feasible.
- Do not modify notebooks, docs, or examples unless relevant to the requested change.

## Git Commit Rules
- Commit only files related to the current task.
- Use clear, structured commit messages:
  - First line: `<type>: <summary>` (for example: `docs: clarify AGENTS workflow`).
  - Body: `Why`, `What`, and `Validation` in short bullet points.
- Add sign-off when committing (`git commit -s`) to keep authorship traceable.
- If tests were not run, state that explicitly in the commit body.

## Long-Term Planning Source of Truth
- Keep long-horizon strategy work anchored to:
  - `plans/AUTOWFO_MASTER_PLAN.md` (vision, milestones, gates, risks)
  - `plans/AUTOWFO_TODO.md` (execution backlog and status)
- Before implementing any new strategy-search feature:
  - Confirm the requested task maps to an item in `AUTOWFO_TODO.md`.
  - If not mapped, add/update plan items first, then implement.
- After each implementation task:
  - Update TODO status and notes in `AUTOWFO_TODO.md`.
  - Record scope change in `AUTOWFO_MASTER_PLAN.md` if direction changed.

## Paths to Ignore
- `/bin/`
- `/obj/`
- `/node_modules/`
- `/.git/`
- `/dist/`
- `/build/`
- `/.venv/`
- `/__pycache__/`
- `/.pytest_cache/`
- `/.mypy_cache/`
- `/.idea/`
- `/.vscode/`
- `/site/`
