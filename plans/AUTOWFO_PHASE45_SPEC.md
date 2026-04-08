# AUTOWFO Phase 45 Spec

## Phase 45: Search Ranking Quality

### Goal
Fix ranking display and penalty logic so that coarse search results surface diverse indicator combinations instead of risk-parameter variants of the same combo, and low-trade penalties retain discriminative power on inherently low-frequency asset/timeframe pairs.

### Scope Rules
- Do not change the search grid generation logic (`_iter_coarse_plan`, `_build_indicator_param_options_coarse`).
- Do not change the refine pipeline (it already deduplicates by `combo_group_fields`).
- Do not change the composite score formula beyond the low-trade penalty term.
- Changes are confined to finalize-time ranking, top10/leaderboard selection, and the penalty calculation.
- All changes must be backward-compatible: existing reports remain readable, and `ranking_config` additions have defaults that preserve current behavior.

### Root Cause Summary
- `_top_by_score()` sorts all evaluated rows globally and takes `head(top_n)`. When multiple risk-parameter variants (tp/sl/max_hold) of the same indicator combo score similarly, they fill all top-N slots, crowding out different indicator combinations.
- Refine already deduplicates by `combo_group_fields = ["indicator_list", "regime_name", "vol_mode"]`, but this dedup is not applied to the operator-facing Top10, Leaderboard, or HTML report.
- `oos_low_trade_penalty` uses an absolute threshold (`low_trade_threshold = 30`). On inherently low-frequency asset/timeframe pairs (e.g., BNB/BTC 2h), all combos trigger the penalty equally, eliminating its ability to differentiate between combos.

### Validation Baseline
- `python -m pytest tests/test_autowfo_engine.py tests/test_run_btc_regime_sweep.py -q`
- `python -m pytest tests/test_autowfo_ranking.py -q` (if exists, or ranking-related tests in test_autowfo_engine.py)

---

## AWF-225: Top10 and Leaderboard combo deduplication

### Objective
Ensure that Top10 and Leaderboard show at most one entry per unique indicator combination, so operators see diverse strategy candidates instead of risk-parameter variants of the same combo.

### Required changes
- In `engine_finalize.py`, where `_top_by_score()` is called for Top10 selection, add a deduplication step by `combo_group_fields` **before** taking `head(top_n)`. For each unique combo group, keep only the row with the highest composite score (best risk-param variant).
- Apply the same dedup to the Leaderboard row selection.
- The full `param_sweep_combo_summary.csv` remains unmodified — dedup is only for display/selection outputs.
- Add a `top10_dedup_fields` key to `ranking_config` with default `["indicator_list", "regime_name", "vol_mode"]`, allowing operators to override if needed.

### Exit criteria
- Given a run where multiple risk-param variants of the same combo score positively, Top10 contains at most one entry per unique `(indicator_list, regime_name, vol_mode)` tuple.
- A run where only one combo has positive score shows that combo as #1, with #2-#10 being the best representative of each of the next 9 distinct combos (even if their scores are negative).
- `param_sweep_combo_summary.csv` still contains all evaluated rows (no data loss).

---

## AWF-226: Relative low-trade penalty mode

### Objective
Make the low-trade penalty discriminative on inherently low-frequency asset/timeframe pairs by supporting a relative mode that compares each combo's trade frequency against the run's population, in addition to the existing absolute threshold.

### Required changes
- Add a `low_trade_mode` key to `ranking_config` with values `"absolute"` (current default) and `"relative"`.
- In `"relative"` mode:
  - Compute the P75 (75th percentile) of `oos_avg_daily_trades` across all combos in the current run.
  - Penalty = `max(0, (P75 - combo_daily_trades) / P75)` — combos at or above P75 get zero penalty, combos well below P75 get proportionally penalized.
  - If `P75 == 0` (no combo has any trades), penalty is 0 for all (no differentiation possible).
- In `"absolute"` mode, behavior is unchanged from current.
- Default is `"absolute"` for backward compatibility. Operators can switch via `sweep_config.json`.

### Exit criteria
- In `"absolute"` mode, all existing tests and ranking behavior are preserved.
- In `"relative"` mode, a run where all combos have similar trade frequency produces near-zero penalty spread (correct — no differentiation needed), while a run with high variance in trade frequency produces meaningful penalty differentiation.
- `ranking_config` schema change is documented and validated by storage contract (Phase 42 mechanism).

---

## AWF-227: Before/after ranking comparison and validation rerun

### Objective
Validate that the ranking changes produce measurably better Top10 diversity without degrading score quality, using an existing trusted run as the comparison baseline.

### Required changes
- Re-score one of the Phase 44 trusted runs (e.g., `20260314_104729` BNB/BTC 2h) with both old and new ranking logic.
- Produce a comparison artifact (`ranking_comparison_phase45.json`) containing:
  - Old Top10 (pre-dedup) and new Top10 (post-dedup) side by side.
  - Number of unique combos in each Top10.
  - Composite score distribution change.
- Record the comparison result in the Phase 45 closure docs.

### Exit criteria
- New Top10 has strictly more unique indicator combos than old Top10 (or equal if the data genuinely has only one positive combo).
- No regression in existing test suite.
- Comparison artifact is committed and referenced in phase closure.

---

## AWF-228: Regression closure and Phase 44 close

### Objective
Close Phase 44 formally in planning docs, archive completed items, and return to steady state with Phase 45 as the active phase.

### Required changes
- Archive AWF-217~AWF-224 to `plans/AUTOWFO_TODO_ARCHIVE.md`.
- Update `plans/AUTOWFO_MASTER_PLAN.md` with Phase 44 closure snapshot and Phase 45 opening.
- Update `plans/AUTOWFO_TODO.md` to reflect Phase 45 as the active phase.
- Run full regression (`python -m pytest tests -q --tb=short`) and record result.

### Exit criteria
- Phase 44 items archived.
- Phase 45 is the active phase in all planning docs.
- Full regression green.
