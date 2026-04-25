# AUTOWFO Survivalism Framework

**Status**: Accepted planning baseline, 2026-04-25
**Role**: North-star document for the next AUTOWFO development cycle
**Scope**: Personal-account crypto quantitative trading survival framework

---

## 1. Purpose

AUTOWFO is moving from a strategy-search platform into a strategy survival
experiment platform.

The goal is not:

```text
find a perfect strategy -> automate trading -> expect stable profit
```

The goal is:

```text
find simple strategies with plausible edge
-> reject backtest illusions
-> measure Freqtrade replay and dry-run gaps
-> calibrate micro-live fills and costs
-> limit the cost of being wrong
-> compound a durable strategy portfolio over time
```

This document captures the direction agreed before implementation. It should be
read before new evidence, risk, gate, strategy-lifecycle, or micro-live work.

---

## 2. Source-Of-Truth Placement

AUTOWFO governance documents live under `plans/`, not `docs/`.

Reason:

- `docs/` is the upstream vectorbt MkDocs surface.
- `plans/` is the existing AUTOWFO planning, protocol, and decision surface.
- `plans/protocols/` is the frozen schema/protocol surface.
- `AGENTS.md` already exists and is managed by repo workflow; do not treat it as
  an ordinary planning file.

Core references:

- `plans/AUTOWFO_MASTER_PLAN.md`
- `plans/AUTOWFO_ARCHITECTURE_V2.md`
- `plans/AUTOWFO_DEVELOPMENT_PRINCIPLES.md`
- `plans/AUTOWFO_TODO.md`
- `plans/AUTOWFO_DECISION_LOG.md`
- `plans/AUTOWFO_EVIDENCE_WAREHOUSE_V1.md`
- `plans/AUTOWFO_SURVIVAL_GATE_POLICY.md`
- `plans/AUTOWFO_STRATEGY_LIFECYCLE.md`

---

## 3. Operating Principles

1. **Survival before return**
   - A strategy that cannot survive execution gaps, costs, and regime drift is
     not useful even if its backtest is strong.

2. **Evidence before optimization**
   - PnL-driven changes require reproducible backtest, replay, paper, or live
     artifacts. Chat-only judgments are not evidence.

3. **AUTOWFO owns strategy truth**
   - Indicator logic, signal rules, candidate identity, ranking, and promotion
     evidence stay in AUTOWFO.

4. **Freqtrade owns execution validation**
   - Freqtrade is the second engine, dry-run/paper runner, and future live
     execution adapter. It must not become a separate strategy source.

5. **Survival Gate policies are versioned**
   - Gate thresholds can change with market regime, capital stage, and observed
     drift. Historical verdicts must keep the policy version used at the time.

6. **Old strategies are baselines, not baggage**
   - Existing promoted candidates become Champion baselines. New tests become
     Challengers and must beat or explain their gap against the Champion set.

7. **Micro-live is calibration first**
   - Initial live trading exists to measure fills, slippage, fees, funding,
     stop behavior, and exchange/API edge cases. Profit is not the first goal.

---

## 4. Development Direction

The agreed order is:

```text
Framework
-> Evidence Warehouse
-> Survival Gate Policy
-> Strategy Lifecycle
-> Reality Gap Reports
-> Control-panel cockpit
-> Risk Engine / Micro-live readiness
```

Rationale:

- Risk rules need evidence inputs before they can be implemented responsibly.
- Strategy lifecycle needs stable candidate and verdict identity.
- UI changes should expose evidence, not redefine strategy logic.
- New strategies can be tested freely only after they are comparable to the old
  Champion set under the same evidence schema.

---

## 5. Required Direction Check

Before opening a new AUTOWFO task in this workstream, answer:

| Question | Required answer |
|---|---|
| Which survivalism principle does this support? | One of Section 3 |
| What evidence artifact will exist after the task? | Path, schema, or report |
| Which decision or protocol does it depend on? | File reference |
| Does it improve candidate discovery, comparison, execution-gap measurement, risk control, or traceability? | At least one |
| What is explicitly out of scope? | One sentence |

If the answer is unclear, update the planning surface before coding.

---

## 6. Non-Goals

- Do not rewrite the control panel before the evidence cockpit requirements are
  known.
- Do not switch to Freqtrade-native strategy discovery.
- Do not accept win rate alone as a promotion criterion.
- Do not hard-code permanent Survival Gate thresholds.
- Do not make micro-live funds available before kill-switch and operator
  sign-off rules are active.
- Do not bulk-migrate old artifacts before candidate identity and evidence
  schema are frozen.

---

## 7. First Implementation Target

The first implementation target after this planning packet is:

```text
AUTOWFO Evidence Warehouse v1
```

Specification:

- `plans/AUTOWFO_EVIDENCE_WAREHOUSE_V1.md`
- `plans/protocols/evidence_warehouse_v1.json`

Risk engine work is intentionally deferred until the warehouse can provide
candidate, cost, gap, and verdict evidence.
