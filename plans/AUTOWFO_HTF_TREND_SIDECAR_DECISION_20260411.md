# AUTOWFO HTF Trend Sidecar Decision

Date: `2026-04-11`
Ticket: `AWF-309`
Protocol: `plans/AUTOWFO_NEW_FACTOR_EXPLORATION_PROTOCOL.md` Track C

## Scope

Evaluate `htf_trend` as a bounded overlay gate on the full 10-symbol BTC-cross cohort
under the frozen anchored current-mode contract:

- timeframe: `2h`
- anchored window:
  - `days = 180`
  - `end = 2026-04-09T14:00:00Z`
- paired WFO:
  - main: `45/30/30`
  - sensitivity: `60/30/30`
- fixed exit:
  - `risk_mode = atr_multiple`
  - `tp_stop = 1.5`
  - `sl_stop = 1.0`
  - `max_hold = 4`
- bounded family neighborhood:
  - `obv_roc`
  - `keltner_pos`
  - `ad`
  - `cmf`
  - `chop`
- combo sizes: `2`, `3`
- HTF overlay cells:
  - baseline (no overlay)
  - `htf_trend:8h:10`
  - `htf_trend:8h:20`
  - `htf_trend:1d:10`
  - `htf_trend:1d:20`

## Implementation Note

The first execution attempt (`20260411_newf_htf_main`, `20260411_newf_htf_sens`) exposed
a wiring bug: `filter_variants` was normalized and counted in the coarse plan, but
was not forwarded by `_build_timeframe_ready_search_kwargs()`. That caused the run to
execute only the baseline branch while still reporting a `300`-row coarse total.

The bug was fixed before final analysis by threading `filter_variants` into the
timeframe-ready search kwargs and adding regression coverage in
`tests/test_autowfo_engine.py`.

Only the rerun pair below is valid evidence for `AWF-309`.

## Final Runs

- main:
  - `20260411_awf309_htf_main_rerun`
- sensitivity:
  - `20260411_awf309_htf_sens_rerun`

Report:
- `artifacts/reports/pilot_analysis_awf309_htf_trend.json`

## Topline Results

Paired report summary:

- compared rows: `300`
- stable-positive rows: `66`
- gate-passed rows: `3`
- canonical gate-passed rows: `3`

Per-overlay distribution:

| Overlay branch | Compared | Stable-positive | Gate-passed |
|---|---:|---:|---:|
| baseline | 60 | 17 | 1 |
| `htf_trend:8h:10` | 60 | 12 | 0 |
| `htf_trend:8h:20` | 60 | 9 | 0 |
| `htf_trend:1d:10` | 60 | 12 | 1 |
| `htf_trend:1d:20` | 60 | 16 | 1 |

Canonical gate-passed rows:

1. `obv_roc + keltner_pos + ad` / `trend_any` / `any`
2. `obv_roc + keltner_pos + ad` / `trend_any` / `any` + `htf_trend:1d:10`
3. `obv_roc + keltner_pos + ad` / `trend_any` / `any` + `htf_trend:1d:20`

## Interpretation

### 1. Track C passes, but narrowly

Track C satisfies the protocol success criteria because it unlocks new gate-passed rows
on the full 10-symbol cohort:

- baseline branch contributes `1` canonical gate-passed row
- `1d` HTF overlays contribute `2` additional canonical gate-passed rows

So `htf_trend` is a valid sidecar pass and should be retained as a future candidate.

### 2. The useful signal is daily confirmation, not 8h confirmation

`8h` overlays underperform the baseline:

- `htf_trend:8h:10` -> `12` stable-positive / `0` gate-passed
- `htf_trend:8h:20` -> `9` stable-positive / `0` gate-passed

By contrast, both daily overlays survive:

- `htf_trend:1d:10` -> `12` stable-positive / `1` gate-passed
- `htf_trend:1d:20` -> `16` stable-positive / `1` gate-passed

Conclusion: if `htf_trend` is carried forward, the retained branch should be daily only.
The `8h` branch is rejected.

### 3. HTF confirmation does not create a new family

All three canonical gate-passed rows remain the same structural family:

- `obv_roc + keltner_pos + ad`

This matters because Track C improves the current winner; it does not replace the
winner or reveal a different family center.

### 4. Cohort pressure improves at the aggregate level, but not at the canonical weakest leg

Across the full branch average, the worst aggregate symbol shifts:

- baseline worst average symbol:
  - main: `BNB/BTC = -0.7481%`
  - sensitivity: `BNB/BTC = -0.8242%`
- daily overlay worst average symbol:
  - `1d:10`
    - main: `LTC/BTC = -0.6160%`
    - sensitivity: `LTC/BTC = -0.6477%`
  - `1d:20`
    - main: `LTC/BTC = -0.5209%`
    - sensitivity: `LTC/BTC = -0.5807%`

So the daily HTF gate does reduce broad `BNB/BTC` dragger pressure across the whole
branch.

But inside the canonical gate-passed rows, `BNB/BTC` is still the weakest symbol in
both main and sensitivity branches. That means Track C does **not** fully solve the
BNB-specific weakness; it only softens it at the branch level.

### 5. Trade density falls when HTF confirmation is added

The daily HTF overlays pass the gate under the current flat trade policy, but both have
lower minimum trade counts than the baseline canonical row:

- baseline canonical row:
  - min trades: `2.325`
- `htf_trend:1d:10`:
  - min trades: `1.775`
- `htf_trend:1d:20`:
  - min trades: `1.55`

So Track C is not a free improvement. It adds two valid gate-passed variants, but does
so by trading less often.

## Decision

Classification: `bounded pass`

Decision:

- keep `htf_trend` as a valid sidecar winner
- promote only the daily branch (`1d:10`, `1d:20`) into the Phase 60 candidate pool
- reject the `8h` branch
- do not let Track C displace the active Phase 60 implementation priority

## Consequences For Phase 60

Track C does **not** justify reopening broad current-mode work.

It does justify a small change to the future candidate pool:

- keep current state seeds unchanged:
  - `obv_roc + keltner_pos`
  - `obv_roc + keltner_pos + ad`
- add `htf_trend` as an optional daily state-alignment gate candidate
  - daily only
  - not mandatory in the first hierarchical pilot
  - not treated as evidence that `BNB/BTC` pressure has been fully solved

## Follow-up

- `AWF-307` and `AWF-308` remain pending, but still require external-data/instrument
  mapping before implementation.
- `AWF-303` remains the active engineering track.
- If Track C is reused in Phase 60, limit the first integration attempt to:
  - `1d:10`
  - `1d:20`
  - no `8h` variants
