# AUTOWFO TODO

## Usage Rules
- This file tracks only active-phase execution items.
- Completed historical items are archived in `plans/AUTOWFO_TODO_ARCHIVE.md`.
- Allowed statuses: `todo`, `doing`, `blocked`, `done`.

## Active Phase

- No active phase.
- Last closed phase: Phase 49: Trusted Ranking Rollout.
- Active items: none.

## Backlog

- `done` `AWF-239` Cross-symbol pilot protocol review and scope freeze.
  Review `plans/AUTOWFO_SEARCH_V2_PROPOSAL.md`, confirm the revised priority order, and freeze the pilot protocol before implementation.
- `done` `AWF-240` Legacy pilot protocol cleanup.
  Added indicator subset support, 3-regime pilot preset, default-only pilot param freeze, single-trend-momentum freeze, ATR-relative exit mode, and a reproducible pilot config path on the legacy engine. Validation: `python -m pytest tests/test_autowfo_engine.py tests/test_run_btc_regime_sweep.py tests/test_autowfo_pruning.py -q` (`137 passed`).
- `done` `AWF-241` Cross-symbol pilot execution and Search V2 decision gate.
  Completed pilot runs `20260408_144415` and `20260408_151900`, wrote `plans/AUTOWFO_SEARCH_V2_PILOT_DECISION_20260408.md`, and concluded `NARROW-GO` for focused follow-up but `NO-GO` for full Search V2 funding under the realized pilot protocol.
- `done` `AWF-242` Pilot evidence hardening: symbol-level OOS cohort output and overlap-window audit.
  Added `param_sweep_symbol_oos_summary.csv`, persisted `timeframe_diagnostics` into run metadata, and verified via rerun `20260408_163100` that the shared-window shrink was caused by late-start BTC crosses rather than missing protocol wiring.
- `done` `AWF-243` Focused follow-up on boundary candidate family versus symbol clustering.
  Re-ran the `60/30/30` sensitivity pass with symbol-level OOS artifacts (`20260409_000100`) and then ran cluster-limited subgroup pilots (`20260409_001500`, `20260409_001700`) for `LTC/BTC`, `LINK/BTC`, and `SOL/BTC` on the `mfi/cmf/obv_roc` family. Result: the original `mfi + cmf + obv_roc` boundary candidate becomes internally consistent inside the subgroup, but an even narrower `mfi + obv_roc` family outperforms it, so the next branch should be subgroup-focused discovery rather than universal Search V2 revival.

## Maintenance
- Dependency tracking: pandas 2.x baseline validation and upgrade-readiness checks (targeted periodic smoke + full regression).
- Warning cleanup: reduce third-party and internal deprecation/future warnings without suppressing project-critical warnings (AWF-189 closed — 30 warnings baseline).

## Notes
- 2026-03-29: Phase 49 opened. Focus: use the now-complete trusted coverage set to decide whether `low_trade_mode=relative` should be rolled into shared views via `compare-ranking` + `rescore`, then validate that the control panel absorbs the rescored leaderboard correctly.
- 2026-04-08: `AWF-240` implemented on the legacy path.
  - Added config/runtime support for `indicator_subset`, `regime_preset`, `pilot_fixed_indicator_params`, `pilot_single_trend_mom`, and `risk_mode`.
  - Added ATR-relative stop handling using per-symbol ATR ratios in timeframe context and evaluator.
  - Added pilot-ready config template: `artifacts/sweep_config_pilot_cross_symbol_7ind_2h_180d.json`.
  - Targeted regression is green: `137 passed`.
- 2026-04-08: `AWF-241` completed with a two-run pilot gate.
  - Main run `20260408_144415` (`45/30/30`) produced one boundary candidate at a loose trade floor, but none at a stricter `>=5` trades-per-symbol floor.
  - Sensitivity run `20260408_151900` (`60/30/30`) did not reproduce the boundary candidate's positive OOS result.
  - Effective shared data overlap was only about `124d` (`2025-12-05` to `2026-04-08`), so both runs emitted only `2` OOS segments.
  - Decision memo: `plans/AUTOWFO_SEARCH_V2_PILOT_DECISION_20260408.md`.
  - Current outcome: `NARROW-GO` for focused follow-up, `NO-GO` for full Search V2 funding.
- 2026-04-08: `AWF-242` completed.
  - Added symbol-level OOS cohort artifact: `param_sweep_symbol_oos_summary.csv`.
  - Added run metadata `timeframe_diagnostics` with requested window, realized shared window, and per-symbol data ranges.
  - Verified on rerun `20260408_163100`: requested `180d` clipped to about `125d` shared overlap because `ADA/BTC`, `DOGE/BTC`, `DOT/BTC`, `LINK/BTC`, `LTC/BTC`, and `AVAX/BTC` start later than the oldest symbols in the cohort.
- 2026-04-09: `AWF-243` completed.
  - Re-ran the 10-symbol WFO sensitivity pilot with hardened symbol-level OOS outputs (`20260409_000100`) and confirmed the boundary family still does not support a universal-signal interpretation.
  - Ran cluster-limited subgroup pilots for `LTC/BTC`, `LINK/BTC`, and `SOL/BTC` using only `mfi`, `cmf`, and `obv_roc` (`20260409_001500` main, `20260409_001700` sensitivity).
  - Within this subgroup, `mfi + cmf + obv_roc` becomes consistently positive, but `mfi + obv_roc` is stronger and more stable than the original three-indicator family.
  - Conclusion: proceed, if at all, via subgroup-focused discovery; do not reopen universal Search V2 based on the current BTC-cross evidence.
- 2026-03-29: Phase 49 closed. `storage compare-ranking` was run on `46` trusted runs for both `legacy -> composite` and `absolute -> relative`.
  - `legacy -> composite`: average OOS return delta `-0.6002` (`0/44` improved returns), but OOS min-trades delta `+2.9159` (`44/44` improved) and drawdown delta `+0.5235` (`37/38` improved). This confirms composite is a sample-sufficiency / risk-shaping upgrade, not a raw-return maximizer.
  - `absolute -> relative`: average OOS return delta `+0.2994` (`42/44` improved returns) and Sharpe-like delta `+0.1834` (`20/30` improved), at the cost of OOS min-trades delta `-1.6545` (`41/44` worsened) and drawdown delta `-0.2848` (`34/44` worsened).
  - Operator decision: accept `low_trade_mode=relative` for trusted shared views, because the current campaign priority is ranking discrimination on low-frequency pairs and the paired evidence improved returns broadly enough to justify a ranking-layer rollout.
- 2026-03-29: Applied `python -m autowfo storage rescore --ranking-config artifacts/reports/ranking_candidate_relative_low_trade.json --cwd .` to all `46` trusted runs. Shared views were rebuilt successfully, and the control panel validated the updated state:
  - `Coverage` now reflects `18/18` tested cells (`BNB/BTC`, `ETH/BTC`, `SOL/BTC`, `SOL/USDT`, `WBTC/BTC`, `XRP/BTC` across `1h/2h/4h`).
  - `Dashboard` live payload now reports `46` trusted runs and updated rescored OOS metrics.
  - `Results` live payload now serves rescored combo/top10/leaderboard data from the rebuilt shared views.
- 2026-03-28: Phase 48 opened to turn the rerun campaign plan into a safe operator workflow inside the control panel.
- 2026-03-28: Phase 48 closed. Config saves now preserve hidden runtime fields, rerun campaign presets are available in the Config tab, and targeted control-panel regression is green (`82 passed`).
- 2026-03-28: Rerun/backtest campaign planning is tracked in `plans/AUTOWFO_RERUN_CAMPAIGN_20260328.md` and should be executed primarily through the control panel Coverage/Batch workflow.
- 2026-03-28: Phase 48 follow-up hardening closed a queue-integrity bug in the control panel. Coverage/Batch enqueue now reserves historical `job_name` values from `artifacts/batch_state.json`, so clearing the queue and re-enqueuing no longer marks fresh jobs as already done. Validation: `python -m pytest tests/test_control_panel.py -q` (`84 passed`).
- 2026-03-28: Local shared views were rebuilt from run-local artifacts (`8` trusted runs visible again). Wave 0 is visible in Coverage/Results, and Wave 1 (`AMP/BTC`, `FTT/BTC`, `GTO/BTC`, `JASMY/BTC`, `TCT/BTC` on `1h/60d`) has been queued and started through the control panel.
- 2026-03-28: Wave 1 execution is now split into two conclusions. Control-panel queue integrity and Coverage retest semantics are validated, but `AMP/BTC`, `FTT/BTC`, `GTO/BTC`, `JASMY/BTC`, and `TCT/BTC` produce header-only Binance cache files and `No overlapping data after download` on rerun. These five cells should be treated as exchange-data unavailable for the current feed, not as active retry debt. The next active rerun track is Wave 2 (`BNB/BTC 2h`, `SOL/BTC 2h`, `XRP/BTC 4h`, optional `SOL/USDT 2h`).
- 2026-03-28: Phase 48 post-close verification completed through the web control panel. A missing shared-view rebuild after `autowfo batch` was fixed, so Coverage-triggered reruns now update Batch, Coverage, Results, and Dashboard without manual `storage rebuild-shared-views`. Browser validation used `ETH/BTC 1h` retest via Coverage -> Batch and confirmed new combo/refine runs (`20260328_070150` / `20260328_070616`) surfaced automatically.
- 2026-03-28: Phase 47 opened. Focus narrowed to ranking evidence parity: rescore correctness and trusted-run config comparison before any new rerun campaign.
- 2026-03-28: Phase 47 closed. `storage rescore` now follows finalize-time selection/filter rules, `storage compare-ranking` ships JSON/HTML trusted-run reports, and targeted regression is green (`76 passed`).
- Phase 40 (`AWF-193`~`AWF-198`) closed after namespace and packaging convergence.
- Phase 41 (`AWF-199`~`AWF-204`) closed after control-panel runtime/service hardening.
- Phase 42 (`AWF-205`~`AWF-210`) closed after storage contract hardening and migration-readiness validation.
- Phase 43 (`AWF-211`~`AWF-216`) closed after storage validation/migration/rebuild tooling and control-panel health surfacing.
- Phase 44 (`AWF-217`~`AWF-224`) closed after evidence integrity reset: run isolation, shared-view derivation, legacy purge, and targeted reruns.
- Phase 45 (`AWF-225`~`AWF-228`) closed after search ranking quality: Top10 combo dedup, relative low-trade penalty, before/after comparison (1→5 unique combos in Top10).
- 2026-03-15: Phase 46 opened. Baseline workflow gap, rescore CLI, leaderboard dedup, and coverage retest identified during Phase 45 verification.
- 2026-03-15: Phase 46 closed. Baseline workflow VBT_RUN_ID migration, `storage rescore`, leaderboard `is_latest`, and coverage force-retest shipped.
- AWF-113~AWF-238 completed items are archived in `plans/AUTOWFO_TODO_ARCHIVE.md`.
