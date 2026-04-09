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
- `done` `AWF-244` Subgroup-focused discovery on the stable BTC-cross cluster.
  Ran the full 7-indicator pilot protocol on the `LTC/BTC`, `LINK/BTC`, and `SOL/BTC` subgroup (`20260409_003200`, `20260409_003500`). Result: a narrow cluster-first discovery track is justified, but the strongest 2h combos still have low trade counts, so the next stress test should increase trade density before any larger expansion.
- `done` `AWF-245` Higher-trade-density subgroup stress test.
  Re-ran the same stable-cluster pilot on `1h` (`20260409_004200`, `20260409_004600`). Result: `1h` restored full `180d` overlap and increased trade density, but it did not produce any all-symbol-nonnegative stable combos across both WFO settings, so the evidence still favors the `2h` subgroup lane rather than a general "more bars will fix it" story.
- `done` `AWF-246` Pilot analysis contract and decision-gate hardening.
  Added `autowfo pilot-analyze` plus `autowfo.pilot_analysis` to formalize stable identity matching, symbol-support aggregation, gate evaluation, and machine-readable JSON output. Verified on existing subgroup runs: `2h` analysis (`pilot_analysis_awf244_2h.json`) reports `4` gate-passed candidates, while the `1h` stress test (`pilot_analysis_awf245_1h.json`) reports `0`.
- `done` `AWF-247` ATR-aware subgroup refinement on the confirmed `2h` lane.
  Added ATR-aware refine-step semantics, then ran narrow `2h` subgroup baseline/refine cycles (`20260409_151530`/`20260409_151643` and `20260409_152657`/`20260409_152756`). Result: refine produced `27` symbol-supported comparable candidates but `0` stable-positive and `0` gate-passed rows across the WFO pair, so current evidence does not justify deeper same-lane parameter refinement.
- `done` `AWF-248` Limited cluster expansion on the `2h` subgroup winners.
  Expanded the narrow `2h` lane from `LTC/BTC` + `LINK/BTC` + `SOL/BTC` to a 4-symbol cluster by adding `AVAX/BTC` (`20260409_154200`, `20260409_154400`). Result: the lane survived soft expansion with `13` stable-positive rows and `1` gate-passed candidate, led by `mfi + obv_roc + atr_ratio` / `trend_high` / `max_hold=4`.
- `done` `AWF-249` Boundary expansion on the `2h` cluster lane.
  Expanded the same narrow `2h` lane to 5 symbols by adding `BNB/BTC` (`20260409_155100`, `20260409_155300`). Result: the lane retained `7` stable-positive rows but fell to `0` gate-passed candidates, which marks the current practical boundary of the cluster-first interpretation.
- `done` `AWF-250` Family-first neighborhood campaign on the confirmed 4-symbol lane.
  Ran a narrow family-first campaign on the fixed `2h` 4-symbol cluster (`20260409_235800`, `20260409_235900`). Result: the lane is not a single surviving point. The neighborhood produced `16` stable-positive rows and `2` gate-passed rows under the paired WFO contract, which confirms a real but still narrow local family around the winner.
- `done` `AWF-251` Canonical-family extraction for family-first analysis.
  Extended the pilot-analysis contract so evidence-equivalent supersets are marked as redundant. Re-analyzing `AWF-250` showed the `2` gate-passed rows collapse to `1` canonical family plus `1` redundant superset, confirming the local lane should be represented by the canonical core `mfi + obv_roc + atr_ratio`, not by inflated combo counts.
- `done` `AWF-252` Boundary replacement stress test on the canonical 4-symbol lane.
  Re-ran the same family-first neighborhood campaign with `BNB/BTC` replacing `AVAX/BTC` (`20260409_235950`, `20260409_235955`). Result: the lane fell to `6` stable-positive rows and `0` gate-passed rows, which confirms the current boundary is about specific cluster membership, not just raw cluster size.
- `todo` `AWF-253` Exact-cluster lane freeze and next-stage search scope definition.
  Freeze the currently supported lane as the exact 4-symbol cluster (`LTC/BTC`, `LINK/BTC`, `SOL/BTC`, `AVAX/BTC`) plus the canonical family `mfi + obv_roc + atr_ratio`, then define the smallest justified next-stage search around that exact cluster instead of continuing ad hoc boundary probes.

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
- 2026-04-09: `AWF-244` completed.
  - Ran the full 7-indicator subgroup discovery protocol on `LTC/BTC`, `LINK/BTC`, and `SOL/BTC` (`20260409_003200` main, `20260409_003500` sensitivity).
  - Several combos remained positive across both WFO settings, and a subset stayed non-negative for all three symbols in both runs.
  - The strongest all-symbol-nonnegative families were `cmf + obv_roc + macd_hist` / `trend_high` / `max_hold=4` and `mfi + obv_roc + atr_ratio` / `trend_high` / `max_hold=4`.
  - Even so, subgroup `2h` trade counts remain low, so the next step is a `1h` stress test rather than immediate cluster expansion.
- 2026-04-09: `AWF-245` completed.
  - Re-ran the stable-cluster subgroup protocol on `1h` with the same `45/30/30` and `60/30/30` WFO pair (`20260409_004200`, `20260409_004600`).
  - `1h` restored full shared overlap (`181d`) for `LTC/BTC`, `LINK/BTC`, and `SOL/BTC`, eliminating the late-start overlap shrink seen on `2h`.
  - Despite that, `1h` did not produce any all-symbol-nonnegative stable combos across both WFO settings, while `2h` still had multiple such candidates.
  - Conclusion: the current subgroup evidence is lane-specific; keep the focus on `2h` subgroup refinement rather than assuming that more bars or fuller overlap automatically improve robustness.
- 2026-04-09: `AWF-246` completed.
  - Added `autowfo.pilot_analysis` and CLI entrypoint `python -m autowfo pilot-analyze` to replace ad hoc subgroup/pilot comparison scripts with a stable contract.
  - The new contract matches stable candidates by a fixed identity schema, aggregates symbol-level OOS support for each candidate, applies explicit return/trade/symbol-support gates, and writes machine-readable JSON.
  - Targeted regression is green: `python -m pytest tests/test_autowfo_pilot_analysis.py tests/test_autowfo_cli.py -q` (`62 passed`).
  - Verified on existing subgroup runs:
    - `2h`: `python -m autowfo pilot-analyze --main-run 20260409_003200 --sensitivity-run 20260409_003500 --out-json artifacts/reports/pilot_analysis_awf244_2h.json --min-combo-trades 0.5 --cwd .` -> `4` gate-passed candidates.
    - `1h`: `python -m autowfo pilot-analyze --main-run 20260409_004200 --sensitivity-run 20260409_004600 --out-json artifacts/reports/pilot_analysis_awf245_1h.json --min-combo-trades 0.5 --cwd .` -> `0` gate-passed candidates.
- 2026-04-09: `AWF-247` completed.
  - Added ATR-aware refine-step semantics so `risk_mode=atr_multiple` no longer reuses the tiny fixed-percentage refine deltas.
  - Ran narrow `2h` subgroup baseline/refine cycles for the stable lane (`20260409_151530` / `20260409_151643` and `20260409_152657` / `20260409_152756`).
  - Contract-based analysis on the refine pair (`artifacts/reports/pilot_analysis_awf247_refine_2h.json`) found `27` symbol-supported comparable rows but `0` stable-positive and `0` gate-passed candidates.
  - Conclusion: current evidence does not justify deeper same-lane parameter refinement.
- 2026-04-09: `AWF-248` completed.
  - Ran a soft 4-symbol expansion of the `2h` lane by adding `AVAX/BTC` (`20260409_154200` main, `20260409_154400` sensitivity).
  - Contract-based analysis (`artifacts/reports/pilot_analysis_awf248_expand_2h_4sym.json`) reported `13` stable-positive rows and `1` gate-passed candidate.
  - The surviving gate-passed family was `mfi + obv_roc + atr_ratio` / `trend_high` / `max_hold=4`.
- 2026-04-09: `AWF-249` completed.
  - Ran a 5-symbol boundary expansion of the same `2h` lane by adding `BNB/BTC` (`20260409_155100` main, `20260409_155300` sensitivity).
  - Contract-based analysis (`artifacts/reports/pilot_analysis_awf249_expand_2h_5sym.json`) reported `7` stable-positive rows but `0` gate-passed candidates.
  - Conclusion: the current practical expansion boundary is the 4-symbol cluster, not the 5-symbol one.
- 2026-04-09: `AWF-250` opened.
  - Next step: keep the now-confirmed 4-symbol `2h` lane fixed and test whether the surviving `mfi + obv_roc + atr_ratio` winner is supported by a broader local family.
  - The campaign will stay narrow: family-centered indicator subset, fixed `pilot_trend_3`, ATR-relative exits, and the same paired WFO protocol.
- 2026-04-09: `AWF-251` opened.
  - Early AWF-250 results indicate the top two gate-passed rows may be a core combo plus an evidence-equivalent superset.
  - Next step: formalize canonical-family extraction so later expansion stages count real neighborhoods instead of redundant supersets.
- 2026-04-09: `AWF-250` completed.
  - Ran the family-first neighborhood campaign on the fixed `2h` 4-symbol lane (`20260409_235800`, `20260409_235900`) using the 5-indicator winner neighborhood with size `2..4`, `pilot_trend_3`, `ATR` exits, and `max_hold=4`.
  - Contract-based analysis (`artifacts/reports/pilot_analysis_awf250_family_2h_4sym.json`) reported `75` comparable rows, `16` stable-positive rows, and `2` gate-passed rows.
  - Conclusion: the surviving `2h` 4-symbol lane is supported by a small local family, not just a single isolated combo.
- 2026-04-09: `AWF-251` completed.
  - Added canonical-family extraction to the pilot-analysis contract so evidence-equivalent supersets are marked as redundant.
  - Re-analyzing `AWF-250` showed the `2` gate-passed rows reduce to `1` canonical family and `1` redundant superset.
  - The current canonical family is `mfi + obv_roc + atr_ratio` / `trend_high` / `max_hold=4`; `mfi + obv_roc + atr_ratio + macd_hist` is currently an evidence-equivalent superset, not a separate winner.
- 2026-04-09: `AWF-252` opened.
  - Next step: run a boundary replacement stress test by swapping `AVAX/BTC` for `BNB/BTC` while keeping the family-neighborhood protocol fixed.
  - Goal: determine whether the current boundary is primarily about cluster size, or about specific symbol membership.
- 2026-04-09: `AWF-252` completed.
  - Ran the same family-neighborhood protocol with `BNB/BTC` replacing `AVAX/BTC` (`20260409_235950`, `20260409_235955`).
  - Contract-based analysis (`artifacts/reports/pilot_analysis_awf252_family_2h_4sym_bnbswap.json`) reported `6` stable-positive rows but `0` gate-passed candidates.
  - Conclusion: the current viable lane is specific to the exact 4-symbol cluster; replacing `AVAX/BTC` with `BNB/BTC` is enough to break the canonical-family lane.
- 2026-04-09: `AWF-253` opened.
  - Next step: freeze the currently supported exact cluster and define the smallest justified next-stage search around that lane.
  - This should be planned as a scope-definition step, not as another uncontrolled expansion run.
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
