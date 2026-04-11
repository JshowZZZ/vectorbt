# AUTOWFO State-Trigger First Pilot Decision

Date: `2026-04-12`
Ticket: `AWF-304`
Protocol: `plans/AUTOWFO_STATE_TRIGGER_MODE_PROTOCOL.md`

## Scope

Judge the first hierarchical state-trigger pilot against the strongest frozen
current-mode reference branch.

The question was:
- does the first hierarchical seed matrix beat the frozen `drop SOL/BTC`
  current-mode micro-cohort baseline on the same anchored paired-WFO contract, or
- is the new mode still directionally interesting but not yet strong enough to
  replace the current-mode reference?

## Valid Evidence

Final paired runs:
- main:
  - `20260411_154620`
- sensitivity:
  - `20260411_154758`

Corrected paired report:
- `artifacts/reports/pilot_analysis_awf304_state_trigger.json`

Frozen current-mode comparison reference:
- `artifacts/reports/pilot_analysis_awf300_microcohort_dropsol.json`

Frozen replay configs:
- `plans/protocols/awf304_state_trigger_main.json`
- `plans/protocols/awf304_state_trigger_sensitivity.json`

### Analysis correction note

The first paired analysis initially reported only `15` compared rows because the
pilot-analysis default identity schema still matched current-mode assumptions and
did not include:
- `strategy_mode`
- `state_indicator_list`
- `trigger_indicator_list`

That merged multiple role-distinct hierarchical rows that share the same union
indicator list.

The analysis path was fixed before this memo by making the paired-report identity
role-aware. The corrected report below is the valid evidence for `AWF-304`.

## Fixed Conditions

- timeframe: `2h`
- anchored window:
  - `days = 180`
  - `end = 2026-04-09T14:00:00Z`
- paired WFO:
  - main: `45/30/30`
  - sensitivity: `60/30/30`
- working cohort:
  - `LTC/BTC`
  - `LINK/BTC`
  - `AVAX/BTC`
  - `ETH/BTC`
  - `XRP/BTC`
  - `ADA/BTC`
  - `DOGE/BTC`
  - `DOT/BTC`
- state candidates:
  - `obv_roc + keltner_pos`
  - `obv_roc + keltner_pos + ad`
- trigger candidates:
  - `ad`
  - `cmf`
  - `chop`
- overlap allowed
- exit rule:
  - `state_reversal`
- fixed execution overlay:
  - `risk_mode = atr_multiple`
  - `tp_atr_multipliers = [1.5]`
  - `sl_atr_multipliers = [1.0]`
  - `max_holds = [4]`

## Topline Results

Shared-overlap diagnostics:
- realized shared window: full `180d`
- requested symbols available: `8 / 8`

Paired report summary:

| Branch | compared | stable-positive | gate-passed |
|---|---:|---:|---:|
| first state-trigger pilot | `18` | `5` | `0` |
| frozen current-mode `drop SOL/BTC` reference | `75` | `25` | `3` |

So the first hierarchical pilot does not beat the frozen current-mode reference on
any of the protocol's strict decision counts.

## Best Hierarchical Candidate

Strongest corrected hierarchical row:
- state: `obv_roc + keltner_pos`
- trigger: `ad`
- regime: `trend_any` / `any`
- main avg OOS return: `18.1634%`
- sensitivity avg OOS return: `20.7424%`
- minimum paired average trades: `2.4375`

Why it still fails:
- main symbol support: `7 / 8` nonnegative
- sensitivity symbol support: `7 / 8` nonnegative
- worst symbol return:
  - main: `-1.4495%`
  - sensitivity: `-2.4275%`

This is the key result of the first pilot: the best hierarchical row is not failing
because it lacks return or trade density. It fails because one symbol still turns
negative under the strict all-symbol support gate.

## Interpretation

### 1. The first hierarchical seed matrix is a bounded fail

There are no gate-passed rows.

That alone is enough to reject promotion above the frozen current-mode reference.

### 2. The failure mode is symbol support, not entry scarcity

The top stable-positive rows all pass:
- return gate
- trade gate

They all fail the same thing:
- full-symbol nonnegative support

So the first pilot does not disprove the state-trigger idea outright. It shows that
the current seed matrix still cannot carry the whole 8-symbol cohort cleanly.

### 3. The hierarchy does recover the expected local center

The strongest hierarchical row is exactly the most plausible evidence-backed split:
- state = `obv_roc + keltner_pos`
- trigger = `ad`

That means the Phase 60 starting intuition was directionally correct.
But it is still weaker than the frozen current-mode branch once strict paired support
is enforced.

### 4. Role-aware reporting matters, but it does not change the decision

After restoring role-aware identity handling:
- compared rows moved from `15` to `18`
- stable-positive rows moved from `4` to `5`
- gate-passed rows stayed at `0`

So the reporting correction was necessary, but the strategic decision remains the
same: the first hierarchical pilot is not promotable.

## Decision

Classification: `bounded fail`

Decision:
- close `AWF-304` as a negative first pilot result
- do not promote the first state-trigger seed matrix above the frozen
  current-mode `drop SOL/BTC` reference
- keep the `AWF-303` implementation as valid and replayable infrastructure
- keep Phase 60 open only as a bounded research track, not as the new default
  production branch

## Consequences For Phase 60

The current strongest frozen reference remains:
- `artifacts/reports/pilot_analysis_awf300_microcohort_dropsol.json`

If hierarchical work continues, it should be narrow and repair-oriented:
- start from the only near-pass row:
  - state `obv_roc + keltner_pos`
  - trigger `ad`
- focus on symbol-support repair first
- do not reopen the full first-pilot `2 x 3` seed matrix unchanged and call it a new
  search phase

Daily HTF confirmation from `AWF-309` remains the most plausible bounded add-on if a
future rescue attempt is justified, but it is not yet promoted into the first
hierarchical pilot result itself.