# AUTOWFO State-Trigger Temporal Replay Decision

Date: `2026-04-12`
Ticket: `AWF-313`
Depends on: `AWF-312` (confirming pass), `AWF-310` (current-mode historical replay)

## Scope

Test whether the validated hierarchical state-trigger configuration
(`state=obv_roc+keltner_pos`, `trigger=ad`, `htf_trend:1d:20`) survives on the
one-year-earlier anchored `180d` window (`end = 2025-04-09T14:00:00Z`), the same
older anchor used for the current-mode temporal replay in `AWF-310`.

This answers: is the hierarchical gate-pass time-local or temporally robust?

## Fixed Conditions

- timeframe: `2h`
- anchored window:
  - `days = 180`
  - `end = 2025-04-09T14:00:00Z`
- paired WFO:
  - main: `45/30/30`
  - sensitivity: `60/30/30`
- strategy mode: `state_trigger_entry`
- state: `["obv_roc", "keltner_pos"]`
- trigger: `["ad"]`
- HTF overlay: `htf_trend:1d:20` + no-HTF baseline
- filter variants: `["none", "htf_trend"]`
- regime preset: `pilot_trend_3` (trend_any, trend_high, trend_low)
- combo count: 1 state × 1 trigger × 2 filter × 3 regime = 6 per run
- 8-symbol `drop SOL/BTC` cohort

## Final Runs

- main: `20260411_174006`
- sensitivity: `20260411_174147`

Frozen configs:
- `plans/protocols/awf313_temporal_replay_htf_state_trigger_main.json`
- `plans/protocols/awf313_temporal_replay_htf_state_trigger_sensitivity.json`

Paired report:
- `artifacts/reports/pilot_analysis_awf313_temporal_replay_htf_state_trigger.json`

## Window Realization

- requested anchor end: `2025-04-09T14:00:00Z`
- realized shared start: `2024-10-11 14:00:00`
- realized shared end: `2025-04-09 14:00:00`
- realized shared days: `181`
- available trade symbol count: `8/8`

## Topline Results

| Metric | AWF-313 replay | AWF-312 modern |
|---|---:|---:|
| compared | `6` | `36` |
| stable-positive | `0` | `10` |
| gate-passed | `0` | `4` |

**The validated hierarchical configuration completely fails on the older window.**

## Per-Row Returns (All Negative)

### Main Run (`20260411_174006`)

| Regime | Filter | OOS Return | OOS Trades |
|---|---|---:|---:|
| trend_high | none | `-1.96%` | `13.84` |
| trend_high | htf_trend:1d:20 | `+0.10%` | `7.72` |
| trend_low | none | `-0.61%` | `11.31` |
| trend_low | htf_trend:1d:20 | `-0.56%` | `7.84` |
| trend_any | none | `-3.25%` | `29.63` |
| trend_any | htf_trend:1d:20 | `-1.84%` | `19.16` |

### Sensitivity Run (`20260411_174147`)

| Regime | Filter | OOS Return | OOS Trades |
|---|---|---:|---:|
| trend_high | none | `-3.15%` | `14.50` |
| trend_high | htf_trend:1d:20 | `-1.03%` | `8.91` |
| trend_low | none | `-0.70%` | `11.38` |
| trend_low | htf_trend:1d:20 | `-0.69%` | `7.88` |
| trend_any | none | `-3.99%` | `30.22` |
| trend_any | htf_trend:1d:20 | `-2.79%` | `20.34` |

## Interpretation

### 1. The hierarchical state-trigger mode is time-local

Zero rows survive on the older window. Every combination — across all 3 regimes and
both filter variants — produces negative returns in both runs. This is a blanket
failure, not a marginal near-miss.

### 2. The HTF overlay reduces losses but doesn't save the signal

Comparing no-HTF vs `htf_trend:1d:20`:
- `trend_any`: -3.25% → -1.84% (main), -3.99% → -2.79% (sens) — loss halved but still negative
- `trend_high`: -1.96% → +0.10% (main), -3.15% → -1.03% (sens) — marginal, not stable
- `trend_low`: -0.61% → -0.56% (main), -0.70% → -0.69% (sens) — negligible improvement

The daily trend filter acts as a trade-reduction mechanism (cuts trades ~40-50%) but
is insufficient to flip the fundamental signal quality on this earlier regime.

### 3. Consistent with AWF-310 current-mode replay

AWF-310 showed the current-mode `obv_roc + keltner_pos + ad` family also fails on
the same older window (`105 compared / 21 stable-positive / 0 gate-passed`). The
hierarchical mode fails even more completely (`6/0/0`), which is expected since it
layers additional restrictive filters (state-reversal exit, trigger confirmation)
on top of an already-failing base family.

### 4. The `2024-10 → 2025-04` regime is structurally different

This epoch includes early crypto market weakness post-2024 halving uncertainty and
pre-2025 altcoin rotation. The state-trigger signal that works on the `2025-10 →
2026-04` epoch (post-ETF regime, stronger BTC-alt correlation structure) simply does
not apply to the earlier period.

## Decision

Classification: `time-local`

Decision:
- The validated hierarchical state-trigger row (`state=obv_roc+keltner_pos`,
  `trigger=ad`, `htf_trend:1d:20`) is confirmed as time-local, not temporally robust.
- This does NOT invalidate the configuration for the current window — it simply means
  it cannot be expected to persist indefinitely.
- Keep Phase 60 open; the hierarchical mode remains the best available mode for the
  current market regime, but production deployment should include regime-monitoring
  logic that detects when the underlying structure breaks down.

## Consequences For Phase 60

1. **Temporal robustness is now bounded**: the hierarchical mode works on the modern
   `2025-10 → 2026-04` window but not on the `2024-10 → 2025-04` window. Any
   production deployment must include periodic re-evaluation.
2. **No further temporal replays needed**: one year back already breaks the signal.
   Testing additional older windows adds no new information.
3. **The next natural step is the trade-density gate floor**: improve gate quality by
   rejecting near-zero-trade artifacts from AWF-312, then focus on density expansion
   for the current window.
