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
   - `python -m autowfo.control_panel --help`
3. Check the target config parses:
   - `python -m autowfo run --help`
   - `python -m autowfo baseline --help`
   - `python -m autowfo batch --help`
   - `python -m autowfo plan --help`
   - `python -m autowfo doctor --help`
   - `python -m autowfo storage validate --help`
   - `python -m autowfo gate-c --help`
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
4. Unattended multi-config batch run:
   - `python -m autowfo batch --plan artifacts/batch_plan.json --cwd .`
5. Resume-safe batch run with explicit state file:
   - `python -m autowfo batch --plan artifacts/batch_plan.json --state artifacts/batch_state.json --cwd .`
6. Generate batch plan from registry coverage gaps:
   - `python -m autowfo plan --registry artifacts/run_registry.json --template-config artifacts/sweep_config.json --out-plan artifacts/batch_plan.auto.json --out-config-dir artifacts/planned_configs --max-jobs 20 --cwd .`
7. Run Gate C reproducibility check (dual-run + schema validation + top-N comparison):
   - `python -m autowfo gate-c --config artifacts/sweep_config_window11_quick.json --workflow run --mode combo --target-mode combo --out-json artifacts/reproducibility/gate_c_window11_quick.json --cwd .`
8. Start the packaged control panel against an explicit working root/artifacts root:
   - `python -m autowfo.control_panel --host 127.0.0.1 --port 8787 --root . --artifacts-dir artifacts`
   - Environment fallback: `AUTOWFO_CONTROL_PANEL_HOST`, `AUTOWFO_CONTROL_PANEL_PORT`, `AUTOWFO_ROOT`, `AUTOWFO_ARTIFACTS_DIR`, `AUTOWFO_DATA_REFRESH_INTERVAL_SECONDS`
9. Validate storage health without mutating files:
   - `python -m autowfo doctor --cwd .`
   - `python -m autowfo storage validate --cwd . --json`
10. Preview or apply storage normalization:
   - `python -m autowfo storage migrate --dry-run --cwd .`
   - `python -m autowfo storage migrate --cwd .`
11. Rebuild analytics from experiment artifacts:
   - `python -m autowfo storage rebuild-analytics --cwd .`

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
- Gate C report:
  - `artifacts/reproducibility/gate_c_<label>.json` (or custom `--out-json` path)
- Baseline archive root:
  - `artifacts/runs/<run_label>/`
  - Includes `combo/`, `refine/`, `comparison.json`, `trigger_decision.json`, `ranking_mode_comparison.json`, `ranking_mode_comparison.html`, `manifest.json`
- Batch state:
  - `artifacts/batch_state.json` (seen-keys + job history for crash-safe resume)

## Evidence Gate Interpretation
- Ranking-upgrade trigger file:
  - `artifacts/runs/<run_label>/trigger_decision.json`
- Current governance (2026-02-11 and later):
  - `D1` / `D2` / `D3` are health-monitoring indicators, not activation gates.
  - Use these ratios to detect drift and sample-quality issues over time.
- Ranking comparison artifacts:
  - `artifacts/runs/<run_label>/ranking_mode_comparison.json`
  - `artifacts/runs/<run_label>/ranking_mode_comparison.html`
  - These provide same-window legacy vs composite paired comparison and 3-axis diagnostics:
    - strategy quality
    - sample sufficiency
    - combo scarcity

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
6. Batch interrupted or host restarted:
   - Re-run the same batch command with the same `--state` path.
   - Completed jobs are skipped using `seen_keys`; unfinished jobs continue.
7. Batch should continue despite a failed job:
   - Add `--continue-on-error` and inspect failed entries in `artifacts/batch_state.json`.
8. Storage doctor reports warnings / needs migration:
   - Start with `python -m autowfo storage migrate --dry-run --cwd .`.
   - If the planned rewrites look correct, rerun without `--dry-run`.
9. Analytics store looks stale or metadata is missing:
   - Run `python -m autowfo storage rebuild-analytics --cwd .`.
   - Recheck with `python -m autowfo doctor --cwd .`.

## Post-Run Checklist
1. Confirm pass completion in `manifest.json` (`run_done == run_total`).
2. Confirm `comparison.json`, `trigger_decision.json`, and `ranking_mode_comparison.json` exist.
3. Update:
   - `plans/AUTOWFO_TODO.md` (status + session log)
   - `plans/AUTOWFO_MASTER_PLAN.md` (change log if direction/evidence changed)
4. Commit with sign-off:
   - `git commit -s`

## Operational Defaults
- Keep protocol and metric contracts unchanged unless explicitly planned.
- Prefer one-command execution via `python -m autowfo`.
- Walk-forward mode is configured by `wf_mode` in sweep config (`anchored` default, `rolling` for true-WFO windowing experiments).
- Current true-WFO behavior (`wf_mode=rolling`): each window selects train-time execution policy (`filtered` vs `unfiltered`) and applies it to that window's OOS segment.
- Treat each baseline run as evidence; use same-window paired comparison artifacts to evaluate ranking-rule changes.
