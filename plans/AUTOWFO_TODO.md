# AUTOWFO TODO

## Usage Rules
- This file tracks only active-phase execution items.
- Completed historical items are archived in `plans/AUTOWFO_TODO_ARCHIVE.md`.
- Allowed statuses: `todo`, `doing`, `blocked`, `done`.

## Active Phase

- Phase 44: Evidence Reset and Run Isolation
- Goal: replace shared-root run evidence with isolated run-local outputs, purge invalid legacy artifacts, and rebuild trusted evidence before more strategy conclusions are drawn.
- Active items:
  - `AWF-217` `done` - Freeze Phase 44 scope, evidence classes, and delete-first legacy policy in planning docs.
  - `AWF-218a` `done` - Introduce RunWorkspace abstraction + path derivation (additive, no write-path changes).
  - `AWF-218b` `done` - Dual-write migration verified for runtime config, status, result CSV/DB, reports, metadata, registry, and leaderboard via RunWorkspace-backed regressions.
  - `AWF-218c` `done` - Root evidence writes removed from `autowfo run`; transitional mirror scaffolding cleaned up; run-local outputs are the only primary evidence path.
  - `AWF-219` `done` - Added explicit `storage rebuild-shared-views` to rebuild root compatibility views from trusted run roots while preserving existing file formats.
  - `AWF-220` `done` - Added manifest-aware `storage purge-legacy` with dry-run, quarantine, and explicit delete mode while protecting rebuilt shared compatibility views.
  - `AWF-221` `done` - Switch control panel and analytics to trusted sources only.
  - `AWF-222` `done` - Add regression guards and integrity checks for run isolation and purge behavior.
  - `AWF-223` `done` - Executed evidence reset against root legacy artifacts via quarantine-mode purge; rebuilt empty compatibility views and removed stale cross-run caches from the primary artifacts root.
  - `AWF-224` `done` - Re-run the decision-relevant campaigns under the new trusted model.

## Backlog

No items.

## Maintenance
- Dependency tracking: pandas 2.x baseline validation and upgrade-readiness checks (targeted periodic smoke + full regression).
- Warning cleanup: reduce third-party and internal deprecation/future warnings without suppressing project-critical warnings (AWF-189 closed — 30 warnings baseline).

## Notes
- Phase 40 (`AWF-193`~`AWF-198`) closed after namespace and packaging convergence.
- Phase 41 (`AWF-199`~`AWF-204`) closed after control-panel runtime/service hardening.
- Phase 42 (`AWF-205`~`AWF-210`) closed after storage contract hardening and migration-readiness validation.
- Phase 43 (`AWF-211`~`AWF-216`) closed after storage validation/migration/rebuild tooling and control-panel health surfacing.
- Phase 44 (`AWF-217`~`AWF-224`) opened to reset evidence integrity: run isolation, shared-view derivation, legacy purge, and targeted reruns. AWF-218 split into 218a/b/c after architect review (2026-03-13).
- 2026-03-14: AWF-218a completed. Added `autowfo.run_workspace` with run-local path derivation plus focused regression coverage; no engine write paths changed yet.
- 2026-03-14: AWF-218b completed. Engine now dual-writes runtime config, status, combo/symbol summaries, top10, reports, metadata, registry, leaderboard, and results DB into `artifacts/runs/{run_id}`; focused regressions verify run-local copies and deterministic parity where byte-identical output is meaningful.
- 2026-03-14: AWF-218c architect review — core isolation already complete (entry point routes all paths through workspace, tests assert root files absent). Remaining cleanup: rename `out_dir` → `artifacts_root`, remove dual-write mirror scaffolding (`_write_workspace_result_mirrors`, mirror calls for registry/db), verify no duplicate writes.
- 2026-03-14: AWF-218c completed. `run_btc_regime_sweep.py` now treats `artifacts_root` as read/cache input only; finalize duplicate-write scaffolding removed; focused regressions confirm root evidence files are absent and run-local outputs remain deterministic.
- 2026-03-14: AWF-219 completed. Added `python -m autowfo storage rebuild-shared-views` to rebuild root `run_registry.json`, `leaderboard.csv`, aggregate combo/symbol summaries, and latest compatibility files from trusted run roots only; focused storage/CLI regressions added.
- 2026-03-14: AWF-220 completed. Added manifest-aware `python -m autowfo storage purge-legacy` with `--dry-run`, quarantine, and explicit `--delete`; purge skips any root files currently protected by the shared-view manifest emitted by AWF-219.
- 2026-03-14: AWF-221/222 progressed. Control-panel results/coverage/dashboard/overview now surface a unified `source_status`, storage validation reports shared-view trust state, and `top10_latest_run` / `latest_report` no longer fall back to root legacy files without a trusted manifest.
- 2026-03-14: AWF-223 completed. Root legacy evidence was quarantined into `artifacts_legacy_deleted/` using `storage purge-legacy`; stale `cross_run_report.{json,html}` caches were removed from the primary root; root compatibility views remain present but empty until trusted reruns land.
- 2026-03-14: AWF-221/222 continued. `storage rebuild-shared-views` now trusts only Phase 44 run-local roots (`artifacts/runs/{run_id}/{results,metadata,reports}`) and no longer ingests pre-reset `combo/refine` pass trees as trusted evidence.
- 2026-03-14: Phase 44 runtime-config leak fixed. `autowfo run` now allocates `VBT_RUN_ID` in `core_workflow`, writes runtime config straight to `artifacts/runs/{run_id}/runtime/sweep_config.json`, and passes it via `VBT_RUNTIME_CONFIG_PATH`; `baseline` now uses an isolated `artifacts/baseline_runtime/` config file instead of rewriting root `artifacts/sweep_config.json`.
- 2026-03-14: AWF-224 progressed. Trusted reruns completed for `BNB/BTC 2h seg8` (`20260314_104729`), `SOL/BTC 2h seg16` (`20260314_113102`), `SOL/USDT 2h seg16` (`20260314_114333`), and `XRP/BTC 4h 180d` (`20260314_115559`); shared compatibility views were rebuilt from these trusted runs.
- 2026-03-14: AWF-221/222 completed. Notebook export now accepts structured `timeframes` metadata, removing the Phase 44 rerun warning during experiment notebook generation; notebook-focused regression and a real trusted-run notebook build both pass.
- AWF-113~AWF-216 completed items are archived in `plans/AUTOWFO_TODO_ARCHIVE.md`.
