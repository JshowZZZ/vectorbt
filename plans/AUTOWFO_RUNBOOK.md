# AUTOWFO Runbook

## Scope
- This runbook describes how to operate AUTOWFO without notebooks.
- It covers routine execution, evidence collection, and first-line troubleshooting.

## Prerequisites
- Python environment with project dependencies installed.
- Repository root as working directory.
- Network access for exchange data updates when cache misses.
- Baseline config file available (JSON or YAML).

## Preflight Checklist
1. Verify clean working tree if you want reproducible code-state tracking:
   - `git status --short`
2. Confirm CLI entrypoint is available:
   - `python -m autowfo --help`
3. Check the target config parses:
   - `python -m autowfo run --help`
   - `python -m autowfo baseline --help`
4. Check disk headroom before long sweeps:
   - Windows: `Get-PSDrive -Name E | Select-Object Name,Free,Used`
   - Recommended: keep at least `20GB` free before baseline.
5. Confirm the task aligns to TODO:
   - `plans/AUTOWFO_TODO.md`

## Standard Commands
1. Single sweep run (`combo` or `refine` via config/env override):
   - `python -m autowfo run --config artifacts/sweep_config.json --cwd .`
2. Two-pass evidence run (`combo` then `refine`):
   - `python -m autowfo baseline --config artifacts/sweep_config.json --cwd .`
3. Override workers for heavy runs:
   - `python -m autowfo baseline --config artifacts/sweep_config.json --workers 3 --cwd .`

## Output Locations
- Latest sweep artifacts:
  - `artifacts/param_sweep_combo_summary.csv`
  - `artifacts/param_sweep_symbol_summary.csv`
  - `artifacts/leaderboard.csv`
  - `artifacts/run_registry.json`
  - `artifacts/run_metadata.json`
- Run snapshots:
  - `artifacts/param_sweep_top10_<run_id>.csv`
  - `artifacts/run_metadata_<run_id>.json`
- Baseline archive root:
  - `artifacts/runs/<run_label>/`
  - Includes `combo/`, `refine/`, `comparison.json`, `trigger_decision.json`, `manifest.json`

## Evidence Gate Interpretation
- Ranking-upgrade trigger file:
  - `artifacts/runs/<run_label>/trigger_decision.json`
- Current gate rule:
  - Trigger AWF-002b/AWF-006 only when at least 2 of 3 conditions are true:
    - `D1` drawdown ratio threshold
    - `D2` insufficient OOS segment ratio threshold
    - `D3` low-trade-count ratio threshold
- If only `D3=true` and `D1=false`, `D2=false`, keep ranking upgrade deferred.

## Failure Handling
1. `refine` run shows `run_total=0`:
   - Check `manifest.json` warnings under baseline archive.
   - Lower activity filter in config (`min_avg_daily_trades_target`) for evidence windows.
2. Runtime config not applied as expected:
   - Confirm the command `--config` path.
   - Check effective runtime file: `artifacts/sweep_config.json`.
3. Data/cache anomalies:
   - Inspect `artifacts/cache_ccxt`.
   - Re-run with same config to verify reproducibility.
4. Indicator lookback/key mismatch errors:
   - Ensure current code includes evaluator coercion fix (`cf56d0a` or later).
   - Re-run the same baseline config to validate recovery.
5. `OSError: [Errno 28] No space left on device`:
   - Delete or archive old run outputs under `artifacts/runs/`.
   - Remove stale large snapshots in `artifacts/` (`param_sweep_*`, `results.db`) if needed.
   - Re-run the same baseline config after free space is restored.

## Post-Run Checklist
1. Confirm pass completion in `manifest.json` (`run_done == run_total`).
2. Confirm `comparison.json` and `trigger_decision.json` exist.
3. Update:
   - `plans/AUTOWFO_TODO.md` (status + session log)
   - `plans/AUTOWFO_MASTER_PLAN.md` (change log if direction/evidence changed)
4. Commit with sign-off:
   - `git commit -s`

## Operational Defaults
- Keep protocol and metric contracts unchanged unless explicitly planned.
- Prefer one-command execution via `python -m autowfo`.
- Treat each baseline run as evidence, not as immediate ranking-change justification.
