# AUTOWFO Survival Gate Policy

**Status**: Policy design baseline
**Frozen protocol**: `plans/protocols/survival_gate_policy_v1.json`
**Depends on**: `plans/AUTOWFO_EVIDENCE_WAREHOUSE_V1.md`

---

## 1. Purpose

Survival Gate decides whether a strategy candidate should be promoted,
observed, rejected, halted, or rescored. It is not a fixed forever threshold
set. It is a versioned policy surface.

The policy exists to prevent this failure mode:

```text
strong backtest -> weak paper/live behavior -> capital loss before the gap is understood
```

---

## 2. Core Rule

```text
Gate policy can evolve.
Gate verdict history cannot be silently rewritten.
```

Every verdict must record:

- `policy_id`
- `policy_version`
- candidate identity
- metric snapshot
- failed rules
- warning rules
- generated time
- source artifact paths

If the policy changes, rerun the gate and write a new verdict.

---

## 3. Policy Layers

### Layer 1 - Backtest Survival

Checks that a candidate has plausible edge after costs and enough evidence to
deserve replay.

Example dimensions:

- trade count
- win rate
- payoff ratio
- expectancy after cost
- profit factor
- max drawdown
- symbol support
- temporal stability

### Layer 2 - Freqtrade Replay Survival

Checks whether AUTOWFO signal truth survives a second engine.

Example dimensions:

- open match ratio
- exact match ratio
- trade-count drift
- pair-direction concentration
- source consistency

### Layer 3 - Paper Survival

Checks whether dry-run behavior remains close enough to replay/backtest.

Example dimensions:

- signal freshness
- entry match rate
- exit match rate
- zero-fill days
- paper PnL vs expected PnL
- observed cost drag
- unclassified gap count

### Layer 4 - Micro-Live Readiness

Checks whether a candidate can receive minimal live capital for calibration.

Example dimensions:

- active kill switch
- max position and exposure caps
- daily and weekly loss caps
- operator sign-off
- exchange/funding/stop behavior reviewed

---

## 4. Verdicts

Allowed verdicts:

- `pass`: may move to the next lifecycle stage
- `observe`: continue collecting evidence before promotion
- `reject`: close the candidate branch unless a new hypothesis is written
- `halt`: stop new entries or promotion because execution/risk evidence is bad

Verdicts are evidence records, not opinions. A verdict without source artifacts
is invalid.

---

## 5. Threshold Policy

Do not freeze unsupported numbers in this document.

Thresholds must come from one of:

- existing frozen parity gate evidence
- dry-run aggregate evidence
- micro-live observed distributions
- explicitly approved operator risk tolerance

Current examples such as win rate, profit factor, max drawdown, and paper days
are dimensions, not automatically accepted thresholds.

When deriving a numeric gate from a distribution, follow the statistical policy
in `plans/AUTOWFO_DEVELOPMENT_PRINCIPLES.md`.

---

## 6. Win Rate Policy

Win rate is never sufficient by itself.

A high-win-rate strategy can still be negative expectancy if average losses,
fees, slippage, spread, or funding overwhelm average wins. Survival Gate must
evaluate expectancy and cost drag before promotion.

---

## 7. Capital Stages

Allowed capital stages:

- `backtest`
- `ft_replay`
- `paper`
- `micro_live`
- `scaled_live`

`scaled_live` is not available until later phases define portfolio-level risk,
allocation, and multi-strategy correlation controls.

---

## 8. Relationship To Kill Switch

Survival Gate promotes or blocks candidates. Kill switch halts execution or
promotion after bad live/paper evidence.

Kill-switch thresholds remain provisional until re-derived from evidence. They
must not be activated without:

- policy version
- evidence fields
- operator sign-off path
- halt action path
- restart/review path

---

## 9. Agent Handoff

The first implementation should not build a full risk engine. It should support:

- loading a gate policy definition
- validating required policy fields
- writing immutable verdict records
- refusing verdict writes without `candidate_id`, `policy_id`, and evidence
  artifact paths
