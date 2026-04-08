# AUTOWFO Search V2 Proposal: Priority-Adjusted Cross-Symbol Discovery Plan

> Status: Draft for external AI review
> Date: 2026-04-08
> Author: Revised from prior Search V2 draft based on repo reality and updated research priority
> Purpose: Give external AI reviewers a clear, implementation-aware plan for deciding whether AUTOWFO should invest in full Search V2

---

## 0. Review Frame

This document intentionally changes the priority order of the earlier Search V2 idea.

The earlier direction was:

```text
indicator port
  -> campaign engine
  -> statistical validation
  -> large-scale search
```

This revised direction is:

```text
research protocol cleanup
  -> small cross-symbol pilot
  -> evidence-based decision gate
  -> full Search V2 only if justified
```

The key claim of this revision is:

> Before AUTOWFO invests in a full campaign orchestrator and large discovery budget,
> it should first improve the quality of each evaluation and cheaply test whether the
> "universal / cross-symbol signal" hypothesis is even strong enough to deserve that investment.

This proposal is therefore **not**:

- a rejection of Search V2;
- a reversion to legacy-only architecture;
- a claim that full campaign orchestration is unnecessary.

It **is**:

- a priority adjustment;
- a de-risking step;
- a recommendation to use a narrow legacy pilot path first because it is the fastest way
  to answer the core research question.

Reviewers should evaluate four things:

1. Is the new ordering more rational than building full Search V2 immediately?
2. Is the pilot design statistically and operationally meaningful?
3. Are the estimated evaluation counts realistic under current repo behavior?
4. Is the handoff from pilot -> full Search V2 well defined?

Companion reviewer response format:

- `plans/AUTOWFO_SEARCH_V2_REVIEW_TEMPLATE.md`

---

## 1. Current State (現況)

### 1.1 Architecture Reality

AUTOWFO currently has two relevant execution layers:

#### A. Legacy sweep/search path

Main files:

- `autowfo/run_btc_regime_sweep.py`
- `autowfo/engine_search.py`
- `autowfo/engine_runtime.py`
- `autowfo/engine_helpers.py`
- `autowfo/strategy.py`
- `autowfo/ranking.py`

Characteristics:

- flat cartesian-product style search;
- trusted historical search evidence exists here;
- current regime logic exists here;
- current 25-indicator search space exists here;
- run evidence is already isolated under `artifacts/runs/{run_id}/...`.

#### B. Approved V2 experiment/discovery/analytics path

Main files:

- `autowfo/experiment.py`
- `autowfo/experiment_runner.py`
- `autowfo/pool_discovery.py`
- `autowfo/discovery_loop.py`
- `autowfo/artifact_store.py`
- `autowfo/analytics.py`
- `autowfo/control_panel/experiments.py`

Characteristics:

- experiment is the fundamental unit;
- each run writes to run-local SQLite;
- cross-run views are maintained in DuckDB;
- this is the correct long-term base for a true Search V2.

### 1.2 Current Legacy Search Reality

The legacy engine still generates a broad flat search plan roughly shaped like:

```text
regime
  x volatility params
  x momentum params
  x tp/sl/max_hold
  x indicator combo
  x indicator param expansion
```

Important current defaults and behaviors:

- indicator pool: 25
- combo sizes: `[2, 3, 4]`
- current combo builder uses all `INDICATOR_META.keys()`
- regime builder currently creates:
  - `trend_high`
  - `trend_low`
  - `trend_any`
  - `rsi_revert_low` x 3 RSI pairs
  - `rsi_revert_high` x 3 RSI pairs
  - `bb_revert_low`
  - `bb_revert_high`
  - `bb_breakout_high`
- trend regimes currently also iterate multiple `mom_lookback` values
- TP/SL are currently fixed-percentage grids
- coarse indicator search currently still expands indicator params, not just structure

### 1.3 Existing V2 Search Reality

The V2 stack exists, but it is not yet the right place to immediately launch a huge
cross-symbol search campaign because:

- `ExperimentRunner` still uses fixed-percent exits;
- `ExperimentRunner` currently passes `valid_days=0`;
- V2 risk/validation layers are not yet aligned with the desired universal-signal research protocol;
- building full campaign infrastructure first would consume engineering effort before the
  universal-signal hypothesis is validated.

### 1.4 Current Research Hypothesis

The operator's current research question is:

> "Do there exist signal structures that remain meaningfully positive across a cohort of symbols,
> not just on one symbol?"

This is more specific than the generic "find better strategies" objective.

It implies a stricter requirement:

- robust across multiple symbols;
- not just best-in-class per symbol;
- not dependent on fixed-percentage exits that distort volatility differences.

### 1.5 Current Evidence and Provenance Constraints

Phase 44 already froze an important evidence policy:

- run-local outputs are primary evidence;
- shared views are derived artifacts;
- no new globally writable primary evidence store should be introduced.

Any revised Search V2 path must preserve that.

---

## 2. Current Problems (現況問題)

### 2.1 The Core Question Is Still Unanswered

Neither the legacy search path nor the current V2 experiment loop directly optimizes for:

> cross-symbol robustness as the primary objective

The result is that AUTOWFO still lacks a rigorous answer to whether a universal or
near-universal signal family exists in the current symbol cohort.

### 2.2 Evaluation Quality Is Too Weak to Justify Large-Scale Search Yet

The earlier Search V2 proposal assumed that the right next step was to scale search.

The revised position is:

> scale is premature if each evaluation still contains avoidable noise.

Three concrete quality issues matter before we search wider:

1. **data window is too short for reliable cohort comparison**
2. **fixed-percent TP/SL distort cross-symbol comparability**
3. **regime space is too wide relative to what we need for the first hypothesis test**

This is not a statement that current data is worthless. It is a statement that it is
not yet clean enough to justify a large campaign investment.

### 2.3 "180d" Alone Does Not Automatically Solve Fold Count

A subtle but important correction:

Increasing the data window to `180d` does **not** automatically produce `4-5` OOS folds
under the current default walk-forward settings.

Under the current split logic:

- `120/30/30` on `180d` gives only `1` fold
- `90/30/30` on `180d` gives `2` folds
- `60/30/30` on `180d` gives `3` folds
- `45/30/30` on `180d` gives `4` folds

Therefore the pilot must explicitly choose a walk-forward setting aligned with the
desired fold count. Simply extending `data_days` is not enough.

### 2.4 ATR-Relative Exits Are Not Yet Available in the Legacy Path

The revised strategy correctly prioritizes ATR-relative TP/SL, but this is **not**
currently available as a pure config toggle.

Today:

- legacy path uses fixed `tp_stops` / `sl_stops`
- experiment path uses fixed `risk_stoploss_pct` / `risk_take_profit_pct`

So "use ATR-relative TP/SL first" is a good idea, but it still requires a small targeted
implementation step.

### 2.5 Three-Regime Pilot Is Sensible, but It Is a Biased Pilot

The proposed three-regime set:

- `trend_any`
- `trend_high`
- `trend_low`

is a reasonable simplification for a first pilot because it dramatically shrinks search.

But it changes the research claim from:

> "universal signal across all regime families"

to:

> "universal signal within a trend-biased pilot protocol"

This is acceptable, but it must be stated explicitly so reviewers do not over-interpret
pilot results.

### 2.6 Full Search V2 Before Pilot Would Be Premature

The strongest argument for changing priority is this:

If AUTOWFO builds:

- campaign orchestration,
- new ranking layers,
- new validation machinery,
- and broader search budgets

before confirming that cross-symbol signals survive a cleaner pilot,

then the project risks building a sophisticated system around a weak or false premise.

### 2.7 Current Legacy Count Estimates Are Misleading Unless the Pilot Protocol Is Explicit

The operator's desired pilot estimate is:

```text
7 indicators
  x combo size 1..3
  = 63 structures
  x 3 regimes
  x 2 max_hold
  x 10 symbols
  = 3,780 evaluations
```

This estimate is valid only if the pilot protocol also freezes:

- indicator parameters to a single default point;
- trend momentum dimension to a single value;
- TP/SL to a single ATR-relative median overlay;
- no refine-stage expansion.

Under the current legacy engine, those dimensions are **not** frozen by default.

Therefore the pilot proposal must explicitly define a **pilot protocol mode** instead of
pretending the current engine already behaves that way.

---

## 3. Revised Proposal Goals (提案目標)

### 3.1 Primary Goal: De-Risk the Universal-Signal Hypothesis Cheaply

Before building full Search V2, AUTOWFO should answer:

- does a cleaner pilot produce cross-symbol winners at all?
- are the winners numerous enough to justify further search?
- is the result strong enough to justify architecture investment?

### 3.2 Protocol Goal: Improve Signal-to-Noise Per Evaluation First

The pilot should first improve each evaluation by:

- extending the history window to `180d`;
- selecting a walk-forward configuration that yields multiple OOS folds;
- replacing fixed-percent exits with ATR-relative exits;
- collapsing the regime set to a narrow pilot preset;
- restricting the indicator set to a high-priority shortlist.

### 3.3 Decision Goal: Create an Explicit Investment Gate for Full Search V2

The pilot is not just an experiment. It is a decision gate.

Its purpose is to classify the situation into one of three outcomes:

- strong cross-symbol evidence;
- weak/marginal evidence;
- no meaningful evidence.

### 3.4 Architecture Goal: Use Legacy Path for the Pilot, V2 Stack for the Full System

This revised plan deliberately uses different layers for different purposes:

- **legacy path** for the fast pilot;
- **V2 experiment/discovery stack** for the eventual full Search V2, if justified.

This is not architectural inconsistency. It is pragmatic sequencing.

### 3.5 Evidence Goal: Preserve Run Isolation and Derived Shared Views

All pilot and future campaign work must preserve:

- run-local evidence;
- derived shared analytics;
- rebuildability from trusted artifacts.

---

## 4. Proposal Details (提案細節)

### 4.1 Revised Priority Order

The proposal is now intentionally staged as:

```text
Step 1  research protocol cleanup on legacy pilot path
Step 2  small cross-symbol pilot on 7 indicators
Step 3  explicit decision gate
Step 4  full Search V2 only if pilot evidence is strong enough
```

This changes the burden of proof:

- full Search V2 is no longer the starting assumption;
- it becomes the result of a successful pilot.

### 4.2 Step 1: Legacy Pilot Protocol Cleanup

#### Objective

Improve the quality of each test case before scaling the search.

#### Why this step comes first

Because these changes improve signal-to-noise directly:

1. **Longer window**
   - more OOS folds and more trades, if WFO is also adjusted properly

2. **ATR-relative exits**
   - removes part of the fake edge created by comparing symbols with different volatility

3. **Three-regime preset**
   - shrinks the search by about 5x relative to the current regime family set

4. **7-indicator shortlist**
   - forces the first pilot to focus on the strongest currently suspected signals

#### Proposed pilot indicator shortlist

Use only:

- `mfi`
- `cmf`
- `obv_roc`
- `macd_hist`
- `trix`
- `donchian_pos`
- `atr_ratio`

#### Required legacy-pilot protocol changes

This step is **not** zero-code. It is small-code.

Recommended additions to legacy search:

1. `indicator_subset`
   - allow legacy combo generation to use a specified subset instead of all 25 indicators

2. `regime_preset`
   - add a preset that yields exactly:
     - `trend_any`
     - `trend_high`
     - `trend_low`

3. `pilot_fixed_indicator_params`
   - force the pilot to use one default param row per active indicator

4. `pilot_single_trend_mom`
   - freeze the trend-only extra momentum dimension to one default value

5. `risk_mode = atr_multiple`
   - add ATR-based stop/target support to the legacy runtime

6. explicit pilot WFO config
   - choose a WFO config that matches the intended fold count

#### Recommended WFO setting for the pilot

Two practical options:

| Option | Data window | WFO | Approx folds on 180d | Tradeoff |
|--------|-------------|-----|----------------------|----------|
| A | `180d` | `45/30/30` | `4` | more folds, weaker train window |
| B | `180d` | `60/30/30` | `3` | stronger train window, fewer folds |

Recommendation:

- start with `180d + 45/30/30` if the priority is statistical repetition;
- use `180d + 60/30/30` as a sensitivity check if training-window sufficiency becomes a concern.

#### ATR-relative exit design for the pilot

Pilot goal is not to fully optimize exits. It is to normalize them.

So the pilot should use:

- one fixed ATR period, initially `14`
- one median TP multiplier
- one median SL multiplier

Example pilot defaults:

- `tp_mult = 2.5`
- `sl_mult = 1.5`
- `atr_period = 14`

No exit-grid expansion in the pilot.

#### Step 1 expected search count

If the pilot protocol freezes the extra dimensions correctly:

```text
7 indicators
combo sizes 1..3
= C(7,1)+C(7,2)+C(7,3)
= 7 + 21 + 35
= 63 structures

63
  x 3 regimes
  x 2 max_hold
  x 10 symbols
  x 1 fixed ATR exit overlay
= 3,780 evaluations
```

This is the desired pilot budget.

Without the pilot-specific freezes, the real count will be materially larger.

#### Step 1 output

- legacy pilot mode implemented;
- reproducible pilot config;
- frozen 7-indicator, 3-regime, ATR-relative test protocol.

### 4.3 Step 2: Cross-Symbol Pilot

#### Objective

Use the cleaned-up pilot protocol to directly test whether cross-symbol signal validity
exists in a meaningful way.

#### What the pilot is trying to answer

Not:

> "What is the best final production strategy?"

But:

> "Does the universal / cross-symbol signal hypothesis survive a cleaner, lower-noise protocol?"

#### Pilot cohort

Recommended initial cohort:

- `10` symbols
- one chosen timeframe, ideally `2h` if prior evidence still suggests it is the strongest
- `180d` data window
- one WFO scheme chosen explicitly, not inherited silently

#### Pilot scoring philosophy

The pilot should keep scoring simple and transparent.

Use separate layers:

##### Hard validity gates

For each candidate:

1. `valid_symbol_count >= 6 / 10`
2. each counted symbol must have at least a minimum trade count
3. no catastrophic worst-symbol return below policy floor

##### Ranking / comparison metrics

Track at least:

- symbol-level OOS return
- symbol-level OOS Sharpe-like
- symbol-level trade count
- number of positive symbols
- number of symbols above minimum trade threshold
- worst symbol result
- mean or median cohort result

The pilot should avoid hiding everything inside one blended score.

#### Suggested pilot outcome table

For each candidate, produce:

| Field | Meaning |
|------|---------|
| combo_signature | indicator set + default params |
| combo_size | 1 / 2 / 3 |
| regime_name | one of the 3 pilot regimes |
| max_hold | hold horizon |
| positive_symbols | number of symbols with positive OOS return |
| valid_symbols | number of symbols above trade threshold |
| worst_symbol_return | cohort floor |
| mean_oos_return | cohort average |
| median_oos_return | cohort median |
| mean_oos_sharpe | cohort average quality |

#### Why this pilot is valuable

Because it can answer the strategic question very cheaply:

- if the cleaned-up pilot still finds nothing cross-symbol, large Search V2 is much harder to justify;
- if the cleaned-up pilot finds several clear winners, Search V2 becomes much easier to justify.

#### Step 2 output

- a ranked cohort-level pilot table;
- direct evidence about whether cross-symbol candidates exist;
- input for the Step 3 decision gate.

### 4.4 Step 3: Decision Gate

#### Objective

Convert the pilot result into an explicit project decision.

#### Proposed gate

| Pilot result | Interpretation | Recommended action |
|-------------|----------------|--------------------|
| `3+` combos positive across `6/10` or more symbols | strong evidence that cross-symbol structures exist | proceed to Search V2, but keep first full version narrow |
| `1-2` combos only, marginal or unstable | weak but non-zero evidence | do focused discovery only; do not fund full wide search yet |
| `0` meaningful cross-symbol combos | universal-signal hypothesis not supported by pilot | stop universal Search V2 and pivot to symbol clustering / subgroup discovery |

#### Important interpretation rule

If the pilot fails, the correct conclusion is:

> "The hypothesis failed under this pilot protocol."

Not:

> "Cross-symbol discovery is impossible in all forms forever."

But it does mean that a full Search V2 should not be the default next step.

#### Step 3 output

- explicit go / narrow-go / no-go outcome;
- updated scope recommendation for the next implementation phase.

### 4.5 Step 4: Full Search V2, Only If Warranted

#### Trigger condition

Only proceed if the pilot gives strong enough evidence.

#### Architecture direction

If the pilot is positive, then the full Search V2 should be built on:

- `experiment.py`
- `experiment_runner.py`
- `pool_discovery.py`
- `discovery_loop.py`
- `artifact_store.py`
- `analytics.py`

not on the legacy engine as the permanent home.

#### Initial scope if pilot is positive

The first full Search V2 should still be narrower than the original maximal vision:

- combo sizes `1..3` first
- 3-regime pilot preset first
- campaign orchestration second
- full statistical validation after pilot confirmation

This means the pilot does not just answer yes/no.

It also determines the **initial scope ceiling** of Search V2.

#### Only after that should the system consider

- larger combo sizes such as `4` or `5`
- broader regime families
- wider indicator pool expansion
- richer campaign orchestration
- larger cohort budgets

### 4.6 Proposed Module-Level Plan

#### Step 1 module impacts

| Module | Required pilot change |
|--------|-----------------------|
| `run_btc_regime_sweep.py` | accept pilot protocol config: indicator subset, regime preset, ATR risk mode |
| `engine_helpers.py` | add regime preset support and subset-aware combo generation |
| `engine_search.py` | honor pilot dimension freezes if needed |
| `engine_runtime.py` | support ATR-relative stop/target arrays or equivalent legacy exit wiring |
| `strategy.py` | expose default-only param path cleanly for pilot mode |

#### Step 4 module impacts, if pilot passes

| Module | Full Search V2 direction |
|--------|--------------------------|
| `experiment.py` | extend schema for campaign/search parameters, holdout metadata, ATR risk mode |
| `experiment_runner.py` | support `wf_valid_days`, ATR exits, richer per-symbol metrics |
| `pool_discovery.py` | support controlled combo-size and sampling expansion |
| New campaign orchestrator | manage cohort-level phases and child experiment execution |
| `analytics.py` | add campaign-derived ranking and validation tables |
| `storage_ops.py` | validate and rebuild new campaign-derived analytics surfaces |

### 4.7 Storage and Evidence Design

This revision keeps the earlier evidence principle unchanged.

#### Source of truth

- run-local SQLite
- run-local metadata
- trusted runs only

#### Derived artifacts

- pilot summary tables
- cohort comparison tables
- later campaign ranking tables

These should live as derived views or derived tables in analytics, not as a new globally
writable evidence database.

#### What must not be introduced

- a new primary `shared_combo_results.db`
- multi-machine writable SQLite as the source evidence layer
- a shared mutable root-level result store that bypasses run-local provenance

### 4.8 Scope Boundaries

#### In scope for this revised proposal

- protocol cleanup
- legacy pilot mode
- 7-indicator cross-symbol pilot
- explicit decision gate
- conditional plan for full Search V2

#### Out of scope for the first wave

- full campaign orchestration immediately
- immediate size `1..5` full-search rollout
- full 25-indicator port before the pilot
- full UI redesign before protocol stability
- portfolio optimizer or live trading

### 4.9 Acceptance Criteria

This revised proposal should be considered successfully implemented only if:

1. A legacy pilot protocol exists with:
   - indicator subset support
   - 3-regime preset
   - ATR-relative exits
   - explicit WFO settings
2. The pilot can run the 7-indicator cohort search reproducibly.
3. Pilot outputs make cross-symbol comparison explicit and transparent.
4. The project can classify the result into:
   - go
   - narrow-go
   - no-go
5. If the result is go, the next-stage Search V2 scope is frozen before coding begins.

---

## 5. Feasibility Assessment (技術可行性評估)

### 5.1 Is the new ordering reasonable?

Yes. More reasonable than immediate full Search V2.

Reason:

- it answers the central research question first;
- it avoids architecture investment before hypothesis validation;
- it uses the fastest existing path for the pilot;
- it still preserves the V2 stack as the long-term home if the pilot succeeds.

### 5.2 Is Step 1 really low-cost?

Moderately low-cost, not zero-cost.

It is still much cheaper than building full Search V2 immediately because it needs:

- targeted legacy changes;
- no new campaign orchestration yet;
- no full indicator port yet;
- no large new storage layer yet.

### 5.3 Is the pilot statistically meaningful?

Potentially yes, but only if the WFO configuration is chosen consciously.

Important caveat:

- `180d` alone is not enough;
- the fold count depends on `train/test/step`.

The proposal therefore explicitly makes WFO choice part of the pilot protocol.

### 5.4 Is the `3,780` count realistic?

Yes, but only under the defined pilot protocol mode:

- default-only indicator params
- single trend momentum default
- no refine expansion
- 3 regime preset
- ATR exits fixed to one median overlay

Without those freezes, the current engine will evaluate more than `3,780`.

### 5.5 What is the biggest strategic advantage of this revision?

It turns Search V2 from an assumption into an earned investment.

That is the core improvement in this revised proposal.

---

## 6. Comparison: Old Ordering vs Revised Ordering

| Aspect | Earlier ordering | Revised ordering |
|--------|------------------|------------------|
| First investment | architecture and broad search | protocol quality and small pilot |
| Burden of proof | assumes Search V2 is needed | requires pilot evidence first |
| Initial code target | V2 architecture immediately | legacy pilot path first |
| Statistical cleanliness | deferred until after architecture work | raised to top priority |
| Risk of overbuilding | high | lower |
| Risk of false premise | high | lower |

---

## 7. Review Questions for External AI

1. Is the revised ordering more rational than immediate full Search V2?
2. Is using the legacy path for the pilot the right pragmatic choice, or should the pilot already be run inside the V2 experiment stack?
3. Is the 7-indicator shortlist appropriate for the first cross-symbol pilot?
4. Is the 3-regime trend-only preset a good first pilot, or does it bias the result too much?
5. Which WFO setting is the best compromise on `180d`:
   - `45/30/30`
   - `60/30/30`
   - something else?
6. Is ATR-relative exit normalization sufficient for the pilot, or should another execution normalization be added?
7. Are the proposed go / narrow-go / no-go thresholds reasonable?
8. If the pilot is strongly positive, should the first full Search V2 be limited to size `1..3` and the 3-regime preset, or widened immediately?

---

## 8. Summary for Reviewers

This revised proposal takes a clear position:

> Search V2 is probably directionally correct, but it should not be the first
> engineering investment.

The first investment should be:

1. improve the test protocol;
2. run a cheap, clean cross-symbol pilot;
3. let the pilot decide whether full Search V2 is justified.

The practical slogan of this revision is:

> first polish the lens, then check whether the target is real, then decide whether
> to build the bigger telescope.

If the pilot succeeds, the project should still build full Search V2 on the approved
experiment/discovery/analytics architecture.

If the pilot fails, the project should not default into larger universal-signal search.
It should instead narrow scope or pivot toward symbol clustering.
