# AUTOWFO State/Trigger/Add-On Mode Note

## Purpose
Preserve a future strategy-mode direction that differs from the current single-layer
`indicator_list -> entry/exit` model, without losing focus while the baseline
clue-harvesting campaign is still in progress.

The idea is to support a hierarchical trading structure:
- long-horizon indicators define whether a directional state is active
- short-horizon indicators decide when to enter or add to a position inside that state
- the position exits when the long-horizon state reverses

This is intentionally **not** being implemented yet. The current decision is:
- finish the breadth-first baseline campaign first
- use that evidence to decide which indicators are worth promoting into this new mode

## User Intent Interpreted
The desired behavior is closer to:
1. A long-horizon indicator (or small long-horizon family) declares a bullish state.
2. While that bullish state remains active, one or more short-horizon indicators may:
   - open the first position
   - trigger one or more add-ons
3. The aggregate position is not closed by the short-horizon signal itself.
4. The aggregate position is closed when the long-horizon state reverses.

This is different from the current mode, where a single indicator combo mostly decides
entry and then a fixed execution overlay decides exit.

## Why This Is Interesting
This mode can express strategies that are difficult to encode in the current search:
- trend-state filter plus pullback trigger
- trend-state filter plus breakout add-on
- state-driven exit instead of static TP/SL-only interpretation

It may reveal signal structures where:
- long-horizon indicators are best used as regime/state gates rather than entries
- short-horizon indicators are best used as timing or scaling triggers
- add-on logic strengthens a trend-following edge instead of merely increasing risk

## Why It Is Deferred
The system already needs one more evidence round under the current mode:
- anchored `2h / 180d`
- fixed 10-symbol BTC-cross major cohort
- singles + pairs across all 25 indicators
- bounded triples from evidence-selected indicators

That breadth-first baseline is the cleanest way to answer:
- which indicators are promising at all
- which indicator families are repeatedly useful
- which symbols behave like cluster supporters or draggers
- whether trade-density or worst-symbol support is the main blocker

Implementing the new mode before that campaign would make later results much harder
to interpret, because signal identity, execution logic, and position-management logic
would all change at once.

## Compatibility Requirement
The future mode must be **additive**, not a replacement.

Current mode to preserve:
- one indicator combo decides entry
- fixed ATR-based execution overlay
- current search, artifacts, leaderboard, and pilot-analysis workflows remain valid

Future mode to add:
- explicit `strategy_mode = state_trigger_entry` (name tentative)
- long-horizon state layer
- short-horizon trigger layer
- optional bounded add-on policy
- state-reversal exit semantics

The existing single-layer combo-entry mode should remain available for:
- backward compatibility
- before/after paired comparison
- keeping the historical evidence chain valid

## Expected System Changes
This is more than a small option toggle. At minimum, it likely requires:

1. Strategy schema extension
- state indicator subset / family
- trigger indicator subset / family
- optional add-on controls
- exit-on-state-reversal semantics

2. Signal evaluation changes
- compute long-horizon state first
- evaluate short-horizon trigger only while state is active
- allow controlled re-entry/add-on while state persists
- close aggregate position when state invalidates

3. Artifact and analysis changes
- separate reporting for state family vs trigger family
- explicit add-on policy fields in results
- new comparison surfaces to measure whether the new mode improves:
  - symbol support
  - trade sufficiency
  - average return
  - worst-symbol behavior

## Minimal Future Version
When implementation begins, start with the smallest researchable version:

- one long-horizon indicator role
- one short-horizon indicator role
- zero or one add-on
- exit only on long-horizon reversal
- no staged take profit in the first version

Candidate long-horizon indicators will probably come from trend/state style signals such as:
- `ma_trend`
- `adx`
- `macd_hist`
- `vwma_trend`
- `donchian_pos`

Candidate short-horizon indicators will probably come from timing-style signals such as:
- `mfi`
- `rsi`
- `stoch`
- `obv_roc`
- `cmf`

The exact candidate sets should be chosen from the breadth-first baseline campaign,
not by intuition alone.

## Entry/Exit Semantics to Revisit Later
Open questions that should be answered only after the baseline campaign:
- Should short-horizon triggers allow one add-on or multiple add-ons?
- Should add-ons require existing floating profit before firing?
- Should a disaster stop remain under the state-reversal exit?
- Should partial take-profit be part of the first state/trigger mode, or deferred?

Current recommendation:
- do not mix staged take-profit or complex pyramiding into the first version
- validate the hierarchical state/trigger idea first

## Relationship to the Breadth-First Baseline Campaign
The baseline campaign is expected to feed this note in three ways:

1. Indicator roles
- identify which indicators look like state filters
- identify which indicators look like timing triggers

2. Symbol roles
- identify which BTC-cross majors behave similarly enough to share a state/trigger lane

3. Failure mode diagnosis
- determine whether the current mode is limited by signal structure
- or whether execution/trade-density constraints are the main issue

Only after that evidence is in place should this mode move from note to implementation phase.
