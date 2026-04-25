# AUTOWFO Decision Log

**Status**: Active
**Purpose**: Preserve architecture and policy decisions that must survive
chat-context loss.

This file records accepted decisions for the survivalism workstream. Future
changes should add a new entry that supersedes an older one instead of editing
history silently.

---

## DEC-001 - Survivalism is the next north star

- **Status**: Accepted
- **Date**: 2026-04-25
- **Decision**: AUTOWFO development should optimize for personal-account crypto
  trading survival, not best-backtest discovery alone.
- **Implication**: Strategy work must pass through backtest, replay, paper,
  execution-gap, cost, and risk evidence before any micro-live promotion.
- **References**:
  - `plans/AUTOWFO_SURVIVALISM_FRAMEWORK.md`

## DEC-002 - AUTOWFO remains the strategy truth source

- **Status**: Accepted
- **Date**: 2026-04-25
- **Decision**: AUTOWFO owns strategy logic, candidate identity, signal truth,
  ranking, evidence, and promotion verdicts.
- **Implication**: Freqtrade strategies must consume AUTOWFO signals and must not
  introduce independent strategy logic.
- **References**:
  - `plans/AUTOWFO_ARCHITECTURE_V2.md`
  - `plans/AUTOWFO_FREQTRADE_BRIDGE_PROPOSAL.md`

## DEC-003 - Freqtrade is the execution-validation adapter

- **Status**: Accepted
- **Date**: 2026-04-25
- **Decision**: Freqtrade provides second-engine replay, dry-run paper trading,
  reconcile evidence, and future execution.
- **Implication**: Freqtrade is used to find reality gaps, not to replace
  AUTOWFO strategy search.
- **References**:
  - `plans/AUTOWFO_FREQTRADE_BRIDGE_PROPOSAL.md`
  - `plans/AUTOWFO_PHASE63_PLAN.md`

## DEC-004 - Survival Gate is a versioned policy

- **Status**: Accepted
- **Date**: 2026-04-25
- **Decision**: Survival Gate thresholds may change over time, but every
  verdict must record the exact policy version used.
- **Implication**: Historical verdicts are immutable. A new policy creates a
  new rescored verdict, not a silent overwrite.
- **References**:
  - `plans/AUTOWFO_SURVIVAL_GATE_POLICY.md`
  - `plans/protocols/survival_gate_policy_v1.json`

## DEC-005 - Evidence Warehouse v1 precedes Risk Engine v1

- **Status**: Accepted
- **Date**: 2026-04-25
- **Decision**: The next implementation foundation is the evidence warehouse,
  not the risk engine.
- **Implication**: Risk rules, sizing formulas, and micro-live gates must consume
  stable candidate, cost, drift, and verdict evidence.
- **References**:
  - `plans/AUTOWFO_EVIDENCE_WAREHOUSE_V1.md`
  - `plans/protocols/evidence_warehouse_v1.json`

## DEC-006 - Champion/Challenger comparison is mandatory

- **Status**: Accepted
- **Date**: 2026-04-25
- **Decision**: Existing AUTOWFO candidates become Champion baselines; new
  strategy tests are Challengers.
- **Implication**: New strategies can be tested broadly, but must be compared
  against Champion baselines under the same evidence schema and gate policy.
- **References**:
  - `plans/AUTOWFO_STRATEGY_LIFECYCLE.md`

## DEC-007 - Micro-live starts as calibration

- **Status**: Accepted
- **Date**: 2026-04-25
- **Decision**: Initial live deployment exists to measure fills, slippage, fees,
  funding, stop behavior, and API/exchange edge cases.
- **Implication**: Micro-live must be gated by paper evidence, kill-switch
  policy, sizing caps, and human sign-off.
- **References**:
  - `plans/AUTOWFO_SURVIVALISM_FRAMEWORK.md`
  - `plans/AUTOWFO_SURVIVAL_GATE_POLICY.md`

## DEC-008 - AUTOWFO governance stays in plans/

- **Status**: Accepted
- **Date**: 2026-04-25
- **Decision**: New AUTOWFO governance files live in `plans/` and frozen schemas
  live in `plans/protocols/`.
- **Implication**: Do not create parallel AUTOWFO governance under `docs/`.
  `docs/` remains the upstream vectorbt documentation surface.
- **References**:
  - `AGENTS.md`
  - `plans/AGENTSMD_INTEGRATION.md`

---

## Update Rule

When a new task changes direction, add a new decision entry with:

```text
Status:
Date:
Decision:
Implication:
Supersedes:
References:
```

Do not rely on chat context as the only record of a direction change.
