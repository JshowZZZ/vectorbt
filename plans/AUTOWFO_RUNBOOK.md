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
12. Compare a candidate ranking config against trusted runs before rescoring:
   - `python -m autowfo storage compare-ranking --candidate-config artifacts/ranking_candidate.json --cwd .`
13. Rescore trusted runs after approving a ranking-only change:
   - `python -m autowfo storage rescore --ranking-config artifacts/ranking_candidate.json --cwd .`
14. Export and cross-check a frozen AUTOWFO lane through Freqtrade:
   - `python -m autowfo bridge-export-signal-store --analysis-json artifacts/reports/pilot_analysis.json --out-dir artifacts/freqtrade_bridge/<label> --cwd .`
   - `python -m autowfo bridge-cross-check --manifest-json artifacts/freqtrade_bridge/<label>/signal_manifest.json --out-dir artifacts/freqtrade_bridge/<label>/cross_check --prepare-only --cwd .`
15. Refresh live signal store and reconcile FT dry-run:
   - `python -m autowfo bridge-live-signal --manifest-json artifacts/freqtrade_bridge/<label>/signal_manifest.json --out-dir artifacts/live_signal_store --cwd .`
   - `python -m autowfo bridge-dryrun-reconcile --live-manifest-json artifacts/live_signal_store/live_manifest.json --freqtrade-config E:/Project/freqtrade/user_data/config_autowfo_dryrun.json --out-dir artifacts/paper_dryrun --date <YYYY-MM-DD> --cwd .`
16. Collect one Phase 63 canonical paper evidence day:
   - `python -m autowfo bridge-paper-evidence-day --manifest-json artifacts/freqtrade_bridge/20260411_microcohort_dropsol_main_canonical_r1/signal_manifest.json --freqtrade-config E:/Project/freqtrade/user_data/config_autowfo_dryrun.json --date <YYYY-MM-DD> --min-date 2026-04-28 --cwd . --json`
   - This command refreshes stale/wrong-lane live manifest evidence, reconciles the dry-run day, imports paper evidence into the Evidence Warehouse, updates the aggregate paper survival report, and writes `artifacts/paper_dryrun/health/phase63_paper_health_YYYYMMDD.json`.
17. Rebuild execution drift report from frozen parity inputs:
   - `python -m autowfo storage drift-report --output-json artifacts/reports/execution_drift_report.json --cwd .`

## Evidence Integrity Transition Policy
- Effective 2026-03-14, treat root-level run outputs under `artifacts/` as a legacy surface, not a primary evidence source.
- Phase 44 completed on 2026-03-14. Primary evidence now lives under `artifacts/runs/<run_id>/...`, and root compatibility views must be rebuilt from trusted run-local roots.
- Do not manually place run outputs under root `artifacts/` and treat them as single-run truth.
- If old root-level outputs are discovered outside the shared-view manifest, treat them as legacy evidence and quarantine/purge them via `python -m autowfo storage purge-legacy --dry-run`.

## Output Locations
- Trusted evidence (preferred):
  - `artifacts/runs/<run_id>/...`
  - Legacy isolated working roots used during the transition can remain for audit, but they are not part of the trusted rebuild set.
- Legacy root-level outputs (do not treat as trusted single-run evidence):
  - `artifacts/param_sweep_combo_summary.csv`
  - `artifacts/param_sweep_symbol_summary.csv`
  - `artifacts/leaderboard.csv`
  - `artifacts/run_registry.json`
  - `artifacts/run_metadata.json`
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
- Trusted-run config comparison artifacts:
  - `artifacts/reports/ranking_config_compare.json`
  - `artifacts/reports/ranking_config_compare.html`
  - Use these before `storage rescore` when evaluating ranking-only changes.

## Control Panel Rerun Workflow
1. Open `Config` and set the campaign template:
   - either hand-edit target `timeframes` / `trade_symbols`
   - or apply one of the built-in rerun presets:
     - `Wave 0 Smoke 1h/60d`
     - `Wave 2 Core 2h/120d`
     - `Wave 2 XRP 4h/180d`
     - `Wave 2 SOL/USDT 2h/120d` (optional)
   - worker count
   - ranking config if you are intentionally testing a ranking variant
2. Save config before using `Coverage`.
3. Use `Coverage` for pair-targeted runs:
   - `完整流程` = `baseline` (recommended for trusted evidence)
   - `只廣搜` = `run combo`
   - `只精煉` = `run refine` and should only be used when fresh combo-stage evidence already exists
4. Click an `Untested` cell to enqueue one focused pair/timeframe job.
5. Use `填補全部缺口` only after the template is correct for the current campaign wave.
6. Open `Batch` and click `Start Batch` to execute queued coverage jobs.
7. Validate in `Results` that Top10 / Leaderboard refresh after completion.
8. Validate in `Coverage` that the cell changes to `Tested`.
9. Click a `Tested` cell and use `重新測試` to validate the AWF-232 retest flow.
10. Use `Results -> 重測 Top 10` only for full-config reruns with data refresh; it is not a pair-targeted coverage action.
11. For the `Wave 0 Smoke 1h/60d` preset:
   - use Coverage cells individually
   - run `ETH/BTC` and `SOL/BTC` as `baseline`
   - run `BNB/BTC` as `run combo`

## Exact-Lane Operator Workflow
1. Open `Config` and locate the preset card `Exact Lane 2h 4-Symbol`.
2. Expand `Verdict Summary` before enqueuing new work:
   - `2h / 180d anchored -> hold`
   - `2h / 120d -> hold`
   - `1h / 180d -> no_go`
3. Treat the verdicts as read-only policy output:
   - `hold` means the current lane is still stable enough to keep as a frozen replay candidate, but not strong enough to justify wider indicator, symbol, or timeframe expansion.
   - `hold` on the shorter-window row remains supportive evidence only; do not widen symbols, indicators, or timeframe based on this row.
   - `no_go` means the rejected density lane stays closed; do not reopen `1h` exact-lane work without a protocol-level reason.
4. While the full-window row remains `hold`, the allowed operator actions are:
   - `Config -> Apply Preset and Enqueue` for a direct exact-lane replay or audit rerun.
   - paired scope/range execution only when you are explicitly re-validating the frozen lane, not widening it.
5. When either `2h` row is only `hold`, record the observation but keep the lane frozen:
   - do not treat it as a failure
   - do not widen the search scope
   - wait for the re-validation trigger below or an explicit protocol change before reopening broader indicator or symbol exploration

## Exact-Lane Re-Validation Trigger
1. The current full-window anchored baseline is `AWF-274`, with `realized_shared_days = 181` and verdict `hold` on the `2h / 180d` row.
2. The prior overlap-growth trigger is now exhausted because the anchored rerun reached the requested full-window ceiling.
3. Re-run the anchored paired `2h / 180d` scope test when either condition is met:
   - the fixed anchored `end` is intentionally moved forward by at least `60d`
   - a protocol or promotion-policy change is introduced to address the full-window trade-density or symbol-support failure modes
4. Re-run immediately after any frozen-lane contract change that affects:
   - symbol membership
   - indicator family
   - regime filter
   - ATR plateau bounds
   - promotion/trade-gate policy
5. Do not schedule periodic `1h` density re-checks by default. The current `1h / 180d` branch remains closed unless a protocol change explicitly reopens it.

## Failure Handling
1. `refine` run shows `run_total=0`:
   - Check `manifest.json` warnings under baseline archive.
   - Lower activity filter in config (`min_avg_daily_trades_target`) for evidence windows.
2. Runtime config not applied as expected:
   - Confirm the command `--config` path.
   - Check effective runtime file: `artifacts/sweep_config.json`.
   - If the run used shared root `artifacts/`, do not assume the resulting root-level summaries are trusted evidence.
3. Data/cache anomalies:
   - Inspect `artifacts/cache_ccxt`.
   - Re-run with same config to verify reproducibility.
   - For evidence-sensitive reruns, use an isolated `--cwd`.
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
10. You suspect run contamination or mixed-symbol outputs:
   - Stop using root-level `artifacts/` summaries for interpretation.
   - Re-run the campaign under a dedicated isolated `--cwd`.
   - Treat the affected root-level outputs as legacy evidence pending Phase 44 purge/reset.

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
- Timeframe configs may optionally pin a fixed window end via `timeframes[].end` (ISO UTC timestamp). Keep `timeframes[].days` as the adjustable size control when widening or narrowing the same study window over time.
- Current true-WFO behavior (`wf_mode=rolling`): each window selects train-time execution policy (`filtered` vs `unfiltered`) and applies it to that window's OOS segment.
- Treat each baseline run as evidence; use same-window paired comparison artifacts to evaluate ranking-rule changes.
- Keep AUTOWFO as the strategy truth source. Freqtrade consumes exported signals for replay, dry-run paper trading, and future execution.
- Use `python -m pytest` if the direct `pytest.exe` launcher is blocked by local Windows application control policy.
