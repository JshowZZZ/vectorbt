# AUTOWFO TODO

## Usage Rules
- This file tracks only active-phase execution items.
- Completed historical items are archived in `plans/AUTOWFO_TODO_ARCHIVE.md`.
- Allowed statuses: `todo`, `doing`, `blocked`, `done`.

## Active Phase

- Phase 54: Symbol-Support Boundary Mapping.
- Last closed phase: Phase 53: Current-Mode Family Refinement.
- Active items:
  - `doing` `AWF-284` Freeze the symbol-support boundary protocol.
    Keep the anchored `2h / 180d` protocol and the current-mode core family fixed, then define a bounded symbol-membership matrix that can identify supporters versus draggers without reopening indicator or exit breadth.
  - `todo` `AWF-285` Execute the symbol-support boundary mapping campaign.
    Run the bounded symbol-membership matrix around the core family and its closest local extension, persisting all evidence through the existing pilot-analysis contract.
  - `todo` `AWF-286` Analyze symbol supporters/draggers and re-evaluate current-mode breadth.
    Decide whether the current mode remains broad-cohort viable, narrows to a bounded BTC-cross cluster interpretation, or has flattened enough to reopen the deferred hierarchical mode.

## Backlog

- `doing` `AWF-284` Freeze the symbol-support boundary protocol.
  Turn the Phase 53 decision into a fixed follow-up protocol: same anchored `2h / 180d`, same 10-symbol BTC-cross majors, same fixed ATR exit, but fixed core family plus bounded symbol-membership variations. The purpose is to map supporters versus draggers, not to reopen indicator breadth.

- `todo` `AWF-285` Execute the symbol-support boundary mapping campaign.
  Run the agreed symbol-membership matrix around the current-mode core family and its closest local extension, then persist all evidence using the existing pilot-analysis and artifact contracts.

- `todo` `AWF-286` Analyze symbol supporters/draggers and re-evaluate current-mode breadth.
  Convert the symbol-boundary campaign into a decision memo: does the current mode still generalize on bounded BTC-cross cohorts, or is the apparent breadth fragile enough to reopen the deferred hierarchical mode?

- `done` `AWF-281` Freeze the bounded current-mode family-refinement protocol.
  Wrote `plans/AUTOWFO_CURRENT_MODE_FAMILY_REFINEMENT_PROTOCOL.md` and froze a narrow family-neighborhood campaign around the Phase 52 breadth winner: `obv_roc`, `keltner_pos`, `ad`, `cmf`, `dpo`, and `chop` with combo sizes `3..4` under the same anchored `2h / 180d` 10-symbol protocol.

- `done` `AWF-282` Execute the bounded family-refinement campaign.
  Completed the paired family-refinement runs:
  - `20260411_family_refine_main`
  - `20260411_family_refine_sens`
  The bounded campaign produced `105` compared rows, `33` stable-positive rows, and `2` gate-passed rows.

- `done` `AWF-283` Analyze the family-refinement outputs and re-evaluate the deferred mode split.
  Wrote `plans/AUTOWFO_FAMILY_REFINEMENT_DECISION_20260411.md`. Decision: stay in the current single-layer combo-entry mode. The breadth winner `obv_roc + keltner_pos + ad` is not isolated; it sits inside a real local family, and the next justified branch is symbol-support boundary mapping rather than immediate implementation of the deferred hierarchical state/trigger mode.

- `done` `AWF-277` Freeze the breadth-first baseline campaign protocol.
  Wrote `plans/AUTOWFO_BASELINE_CLUE_HARVESTING_PROTOCOL.md` and froze the anchored `2h / 180d` breadth-first matrix: 25 indicators, 10 BTC-cross majors, fixed ATR exit, Stage 1 singles + pairs, and Stage 2 bounded triples selected from evidence.

- `done` `AWF-278` Execute the baseline clue-harvesting campaign.
  Completed the full breadth-first campaign under anchored conditions:
  - Stage 1 singles + pairs: `20260411_clue_pairs_main`, `20260411_clue_pairs_sens`
  - Stage 2 evidence-selected triples: `20260411_clue_triples_main`, `20260411_clue_triples_sens`
  Added a formal clue-ranking contract via `pilot-build-clue-map`, which produced `artifacts/reports/indicator_clue_map_awf278_pairs.json` and selected the Stage 2 top 10 indicators.

- `done` `AWF-279` Analyze clue-harvesting outputs and choose the next branch.
  Wrote `plans/AUTOWFO_CLUE_HARVESTING_DECISION_20260411.md`. Decision: stay in the current single-layer combo-entry mode for one more bounded family-refinement phase. The breadth campaign found one strict gate-passed anchored family on the full 10-symbol cohort: `obv_roc + keltner_pos + ad` / `trend_any` / `any`. Across the full `44` stable-positive triples, the dominant blocker is worst-symbol support (`43/44`), not trade-only failure (`0/44`).

- `done` `AWF-280` Freeze the hierarchical state/trigger/add-on mode as a technical note.
  Captured the new idea as `plans/AUTOWFO_STATE_TRIGGER_MODE_NOTE.md` so the design does not get lost while the baseline clue-harvesting campaign is completed first. The note defines the intent, required system changes, compatibility with the current single-layer combo-entry mode, and why implementation is deferred until after the breadth-first baseline campaign.

- `done` `AWF-274` Anchored exact-lane overlap validation.
  Re-ran the canonical `2h / 180d` exact lane with fixed `end=2026-04-09T14:00:00Z` (`20260411_anchored_exact_main`, `20260411_anchored_exact_sens`). Result: the backfill-aware loader achieved the full anchored shared window (`realized_shared_days = 181`), which validates the anchored-window contract on real `2h` BTC-cross data. Under the stricter full-window evidence, however, the exact lane downgraded to `hold` (`30` stable-positive rows, `0` gate-passed).

- `done` `AWF-275` Anchored controlled widening across indicators and symbols.
  Ran two bounded widening pairs on the same fixed `end`: a 5-indicator neighborhood on the exact 4-symbol cluster (`20260411_anchored_4sym5ind_main`, `20260411_anchored_4sym5ind_sens`) and the same 5-indicator neighborhood on the bounded 5-symbol cluster (`20260411_anchored_5sym5ind_main`, `20260411_anchored_5sym5ind_sens`). Result: both broader campaigns produced stable-positive rows (`17` and `10` respectively), but neither produced any gate-passed candidates under the fixed full-window contract.

- `done` `AWF-276` Anchored widening decision gate.
  Compared the anchored exact lane and both widening branches under the same pilot-analysis contract. Decision: keep anchored-window/backfill support, but do not widen indicator or symbol scope yet. The exact lane stays usable only as a frozen `hold` replay candidate, not as a promotive lane, and the broadened 5-indicator / 4-symbol and 5-indicator / 5-symbol branches are both `no-go` for expansion under the current fixed-window evidence.

- `done` `AWF-273` Parameterize fixed data windows and historical cache backfill.
  Extended timeframe config to accept optional anchored window bounds while preserving `days` as the adjustable size control; current operator path exposes optional `end` for fixed-window reruns. The data loader now backfills older OHLCV rows when the requested window starts before the existing cache, so widening a study window later can remain a config-only change instead of requiring manual cache deletion.

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
- `done` `AWF-253` Exact-cluster lane freeze and next-stage search scope definition.
  Froze the exact viable lane and ran the smallest justified risk-space micro-search on it (`20260410_000500`, `20260410_000700`). Result: `108` comparable rows produced `36` stable-positive rows and `9` gate-passed rows, confirming the canonical lane has a real local risk plateau rather than a single isolated risk point.
- `done` `AWF-254` Exact-lane plateau boundary mapping.
  Mapped the outer TP/SL boundary on the frozen exact lane (`20260410_001200`, `20260410_001300`). Result: `90` comparable rows produced `30` gate-passed rows, all in `trend_high` with `max_hold=4`, confirming a broad exact-lane risk plateau rather than a narrow knife-edge.
- `done` `AWF-255` Canonical lane protocol summary extraction.
  Extended the pilot-analysis contract so canonical gate-passed rows emit machine-readable protocol ranges. The exact-lane report now directly exposes the surviving field ranges for `indicator_list`, `regime_name`, `vol_mode`, `tp_stop`, `sl_stop`, and `max_hold`, so the lane can be replayed without manual JSON inspection.
- `done` `AWF-256` Exact-lane protocol freeze and replay/export path.
  Added exact-lane replay/export support via `pilot-export-config`, plus exact `regime_name_filter` support in the legacy engine. Verified by exporting [pilot_analysis_awf254_exact_lane_plateau.json](e:/Project/vectorbt-master/artifacts/reports/pilot_analysis_awf254_exact_lane_plateau.json) into `artifacts/pilot_replay_exact_lane_2h_4sym.json` and replaying it as run `20260410_073700`, which reproduced the expected `30` exact-lane rows.
- `done` `AWF-257` Exact-lane promotion and operator preset path.
  Added an operator-facing control-panel preset `exact-lane-2h-4sym` and extended config sanitization so exact-lane hidden fields survive apply/save. The frozen exact lane can now be reused directly from the control panel without manual artifact selection.
- `done` `AWF-258` Export/preset parity guard for the exact lane.
  Added regression coverage that compares the canonical replay config derived from the exact-lane protocol summary against the operator preset `exact-lane-2h-4sym`. This now guards against silent drift between the CLI export/replay path and the control-panel preset path.
- `done` `AWF-259` Exact-lane preset consumption in operator workflow.
  Added control-panel endpoints that turn a preset directly into a planned config plus queued batch job, so the frozen exact lane can be consumed deliberately from operator workflow rather than only via config parity tests.
- `done` `AWF-260` Exact-lane scope-test phase entry path.
  Added paired scope-test enqueue support for preset-defined WFO variants (`45/30/30` main and `60/30/30` sensitivity), so the exact lane now has a first-class entry into the next range/scope-testing phase without manual JSON editing.
- `done` `AWF-261` Execute and evaluate the exact-lane paired scope-test workflow.
  Ran the operator-generated exact-lane main/sensitivity pair (`20260410_100403`, `20260410_100537`) and analyzed it with `pilot_analysis_awf261_exact_lane_scope_test.json`. Result: `30/30` compared rows were stable-positive and `30/30` passed the current gate.
- `done` `AWF-262` Exact-lane temporal range test on `2h / 120d`.
  Ran a shorter-window paired range test (`20260410_101315`, `20260410_101628`) and analyzed it under both strict and relaxed trade floors. Result: the lane retained `24/30` stable-positive rows, but strict `min_combo_trades=0.5` reduced gate-passed rows to `0`; relaxing to `0.375` restored `24` gate-passed rows.
- `done` `AWF-263` Exact-lane density follow-up on `1h / 180d`.
  Ran the frozen exact lane on `1h` (`20260410_102301`, `20260410_102302`) to test whether higher bar density rescues short-window sample pressure. Result: `0/30` stable-positive and `0/30` gate-passed rows despite full `181d` overlap.
- `done` `AWF-264` Exact-lane trade-floor policy review.
  Added a formal trade-gate policy layer to `autowfo pilot-analyze` with `flat` and conservative `window_aware` modes. The new `window_aware` policy keeps the baseline `0.5` trade floor for full `180d` windows, but relaxes short-window exact-lane review to `max(data_days / 180, 0.75) * 0.5`. Re-analyzing `20260410_101315` / `20260410_101628` under this policy restored `24` gate-passed rows at `2h / 120d`, while `20260410_102301` / `20260410_102302` remained `0` gate-passed on `1h / 180d`. This closes the question in favor of a conservative window-aware policy for short-window exact-lane review.
- `done` `AWF-265` Exact-lane promotion policy freeze.
  Carried the exact-lane promotion policy into the control-panel preset contract. `exact-lane-2h-4sym` now publishes explicit `full_window_gate`, `short_window_gate`, and rejected `1h` density-lane metadata through `/config/presets.json`, `/config/apply-preset`, `/config/apply-preset-and-enqueue`, and `/config/apply-preset-scope-test`, so operator workflows can consume the same promotion criteria that closed `AWF-264`.
- `done` `AWF-266` Exact-lane promotion verdict automation.
  Added `python -m autowfo pilot-evaluate-promotion`, which reads a pilot-analysis report plus preset promotion policy and emits an explicit `promote` / `hold` / `no_go` verdict. Verified on real exact-lane reports: `AWF-261` scope-test -> `promote`, `AWF-264` short-window `2h / 120d` -> `hold`, `AWF-264` rejected `1h / 180d` density lane -> `no_go`.
- `done` `AWF-267` Operator-facing exact-lane promotion verdict endpoint.
  Added `/config/evaluate-preset-promotion`, so the control-panel workflow can evaluate an analysis report against the frozen exact-lane promotion policy and optionally persist a machine-readable verdict JSON without dropping back to ad hoc scripts.
- `done` `AWF-268` Exact-lane verdict bundle and operator handoff.
  Added `python -m autowfo pilot-build-bundle`, which packages the frozen preset policy, multiple pilot-analysis reports, and their derived promotion verdicts into one operator-facing JSON bundle. Generated `artifacts/reports/pilot_bundle_awf268_exact_lane_operator.json` for the current exact-lane scope/range set.
- `done` `AWF-269` Surface the exact-lane operator bundle in the control panel.
  Added `/config/build-preset-bundle`, so the control panel can package a frozen preset plus multiple analysis reports into one operator-facing bundle JSON without shelling out to CLI.
- `done` `AWF-270` Present exact-lane bundle summaries in operator UI.
  Added a lightweight `Verdict Summary` block to the existing Config preset card for `exact-lane-2h-4sym`. The UI lazily loads the frozen bundle verdicts via `/config/build-preset-bundle`, renders the canonical `promote` / `hold` / `no_go` rows inline, and does not require a new tab or raw JSON inspection.
- `done` `AWF-271` Exact-lane verdict-to-action runbook policy.
  Updated `plans/AUTOWFO_RUNBOOK.md` so operator workflow now has an explicit read-only decision path after viewing the exact-lane verdict summary: `promote` keeps the `2h / 180d` lane eligible for paired scope/range execution, `hold` means observe and do not widen scope, and `no_go` means do not reopen the rejected density lane without a protocol-level reason.
- `done` `AWF-272` Exact-lane overlap-growth re-validation policy.
  Froze an overlap-based re-validation trigger in `plans/AUTOWFO_RUNBOOK.md`: rerun the `AWF-261`-style `2h / 180d` paired scope test when the realized shared overlap improves by at least `30d` from the last promotive baseline (currently `127d`) or reaches the full `180d` cap, and also rerun immediately after any protocol or promotion-policy change that affects the frozen lane.

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
- 2026-04-10: `AWF-253` completed.
  - Froze the exact viable lane (`LTC/BTC`, `LINK/BTC`, `SOL/BTC`, `AVAX/BTC` + `mfi + obv_roc + atr_ratio`) and ran a risk-space micro-search over `3` ATR TP values, `3` ATR SL values, and `4` `max_hold` values (`20260410_000500`, `20260410_000700`).
  - Contract-based analysis (`artifacts/reports/pilot_analysis_awf253_exact_lane_risk_micro.json`) reported `108` comparable rows, `36` stable-positive rows, and `9` gate-passed rows.
  - All `9` gate-passed rows remained in `trend_high` with `max_hold=4`, and they formed a TP plateau from `1.25` to `1.75`; no canonical redundancy remained.
- 2026-04-10: `AWF-254` opened.
  - Next step: keep `trend_high` and `max_hold=4` fixed and map the exact TP/SL boundary around the canonical lane.
  - Goal: determine whether stop-loss variation matters materially and where the profitable TP plateau actually ends.
- 2026-04-10: `AWF-254` completed.
  - Ran the plateau-boundary sweep on the exact lane with `max_hold=4`, ATR TP values `[1.0, 1.25, 1.5, 1.75, 2.0, 2.25]`, and ATR SL values `[0.5, 0.75, 1.0, 1.25, 1.5]` (`20260410_001200`, `20260410_001300`).
  - Contract-based analysis (`artifacts/reports/pilot_analysis_awf254_exact_lane_plateau.json`) reported `90` comparable rows, `30` stable-positive rows, and `30` gate-passed rows.
  - All gate-passed rows stayed in `trend_high` with `max_hold=4`; the surviving TP range spans at least `1.0` to `2.25`, while tighter `sl_stop=0.5` remains viable but produces lower minimum returns than `sl_stop>=0.75`.
- 2026-04-10: `AWF-255` completed.
  - Added machine-readable protocol summaries to the pilot-analysis contract for canonical and redundant gate-passed rows.
  - Re-reading `AWF-254` now yields an explicit canonical protocol summary: `indicator_list=mfi,obv_roc,atr_ratio`, `regime_name=trend_high`, `vol_mode=high`, `mom_lookback=6`, `trade_mom_lookback=3`, `max_hold=4`, `tp_stop in [1.0, 2.25]`, `sl_stop in [0.5, 1.5]`.
- 2026-04-10: `AWF-256` opened.
  - Next step: promote the explicit canonical lane into a reusable replay/export path for the next stage.
  - The goal is to stop doing exploratory sweeps for this lane and start treating it as a frozen protocol candidate.
- 2026-04-10: `AWF-256` completed.
  - Added exact `regime_name_filter` support and a new CLI/export path: `python -m autowfo pilot-export-config`.
  - Exported `artifacts/reports/pilot_analysis_awf254_exact_lane_plateau.json` into `artifacts/pilot_replay_exact_lane_2h_4sym.json`.
  - Replayed the exported config as run `20260410_073700`, which produced exactly `30` rows with `indicator_list=mfi,obv_roc,atr_ratio`, `regime_name=trend_high`, TP range `[1.0..2.25]`, SL range `[0.5..1.5]`, and `max_hold=4`.
- 2026-04-10: `AWF-257` opened.
  - Next step: turn the frozen exact lane into the smallest operator-facing replay/preset path.
  - This is now a promotion/reuse problem, not a discovery problem.
- 2026-04-10: `AWF-257` completed.
  - Added the control-panel preset `exact-lane-2h-4sym` with the exact cluster, canonical indicator family, exact regime filter, ATR risk plateau, and `max_hold=4`.
  - Extended config sanitization so `indicator_subset`, `regime_name_filter`, ATR risk arrays, and pilot flags survive preset apply/save.
  - Verified via targeted control-panel regression that the preset appears in `/config/presets.json` and applying it persists the exact-lane controls into `CONFIG_JSON`.
- 2026-04-10: `AWF-258` opened.
  - Next step: add a parity guard so the operator preset and the exported replay config do not silently drift apart.
  - This should stay small and defensive; the lane itself is already frozen.
- 2026-04-10: `AWF-258` completed.
  - Added a parity regression that compares the replay config built from the canonical exact-lane protocol summary against the control-panel preset `exact-lane-2h-4sym`.
  - This now protects the operator preset from drifting away from the CLI export/replay path as the canonical lane evolves.
- 2026-04-10: `AWF-259` opened.
  - Next step: use the frozen exact-lane preset in a deliberate operator workflow, not just in config/preset tests.
  - The purpose is to validate reuse ergonomics, not to reopen discovery.
- 2026-04-10: `AWF-259` completed.
  - Added `/config/apply-preset-and-enqueue`, which applies a preset, writes a planned config, and queues the corresponding batch job in one step.
  - Verified on the exact lane that the queued job preserves the canonical indicator subset, regime filter, ATR plateau, and deliberate rerun semantics (`allow_seen_key_reuse=True`).
- 2026-04-10: Phase 50 opened.
  - Focus: move the frozen exact lane from replay/preset readiness into explicit scope testing with operator-safe entry points and paired WFO execution.
- 2026-04-10: `AWF-260` completed.
  - Added `/config/apply-preset-scope-test`, which turns preset-defined WFO variants into paired planned configs and queued jobs.
  - The exact lane now exposes the canonical `45/30/30` main and `60/30/30` sensitivity pair as a first-class control-panel workflow.
- 2026-04-10: `AWF-261` opened.
  - Next step: execute the exact-lane scope-test pair from the new operator workflow and re-evaluate the lane with the pilot-analysis contract before attempting wider range testing.
- 2026-04-10: `AWF-261` completed.
  - Operator-generated exact-lane scope test runs `20260410_100403` and `20260410_100537` reproduced the full plateau under the paired WFO contract.
  - `pilot_analysis_awf261_exact_lane_scope_test.json` reported `30` compared rows, `30` stable-positive rows, and `30` gate-passed rows.
- 2026-04-10: `AWF-262` completed.
  - A shorter-window `2h / 120d` range test (`20260410_101315`, `20260410_101628`) retained `24` stable-positive rows but `0` gate-passed rows at the strict paired trade floor.
  - Re-analyzing the same pair with `min_combo_trades=0.375` restored `24` gate-passed rows, which localizes the failure mode to trade density rather than edge collapse.
- 2026-04-10: `AWF-263` completed.
  - A `1h / 180d` density follow-up (`20260410_102301`, `20260410_102302`) produced `0` stable-positive rows and `0` gate-passed rows.
  - Conclusion: higher bar density does not rescue the lane; current evidence still supports a `2h` lane-specific interpretation.
- 2026-04-10: `AWF-264` opened.
  - Next step: review whether the short-window exact-lane failure should be treated as a hard no-go, or as a sample-sufficiency policy issue tied to the current paired trade gate.
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
