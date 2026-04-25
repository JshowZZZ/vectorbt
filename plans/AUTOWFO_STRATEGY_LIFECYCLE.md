# AUTOWFO Strategy Lifecycle

**Status**: Accepted planning baseline
**Depends on**:
- `plans/AUTOWFO_SURVIVALISM_FRAMEWORK.md`
- `plans/AUTOWFO_EVIDENCE_WAREHOUSE_V1.md`
- `plans/AUTOWFO_SURVIVAL_GATE_POLICY.md`

---

## 1. Purpose

This document defines how a strategy candidate moves from idea to rejection,
paper observation, micro-live calibration, or promotion.

It also defines how old AUTOWFO candidates and new strategy tests are compared
without forcing new ideas into old assumptions.

---

## 2. Champion / Challenger Model

- **Champion**: existing best-supported strategy candidates from prior AUTOWFO
  evidence.
- **Challenger**: any new strategy family, indicator combination, timeframe,
  universe, cost model, or risk rule under test.

New Challengers may be structurally different from existing Champions, but they
must be comparable through the same evidence warehouse and gate policy.

The initial Champion set should include:

- the frozen canonical AUTOWFO lane
- the strongest `obv_roc + keltner_pos` family variants
- simple market baselines such as buy-and-hold or cash where available

---

## 3. Lifecycle States

| State | Meaning | Required evidence |
|---|---|---|
| `candidate` | Strategy definition exists | Candidate identity |
| `backtest_candidate` | Candidate has a runnable backtest spec | Config and data profile |
| `backtest_passed` | Backtest evidence passes current gate layer | Backtest metrics |
| `ft_replay_checked` | Freqtrade replay/cross-check exists | Replay artifact |
| `paper_observed` | Dry-run/paper evidence exists | Daily reconcile artifacts |
| `micro_live_ready` | Candidate is eligible for minimal live calibration | Gate verdict and operator sign-off |
| `promoted` | Candidate is accepted into the active strategy set | Promotion decision |
| `rejected` | Candidate branch is closed | Failed verdict and rationale |
| `halted` | Candidate must stop new entries or promotion | Halt verdict |
| `retired` | Candidate is no longer active but remains historical evidence | Retirement decision |

---

## 4. Promotion Flow

```text
candidate
-> backtest_candidate
-> backtest_passed
-> ft_replay_checked
-> paper_observed
-> micro_live_ready
-> promoted
```

Promotion is not automatic. A candidate can move forward only when the relevant
Survival Gate policy produces a `pass` verdict or a documented human decision
keeps it in `observe`.

---

## 5. Rejection And Halt Flow

Reject when evidence shows the candidate has no useful edge or lacks enough
support to justify more compute.

Halt when execution, paper, or live evidence indicates operational danger.

Examples:

- replay mismatch cannot be explained
- paper shows repeated zero-fill behavior
- live cost drag overwhelms backtest edge
- kill-switch threshold is breached
- candidate is time-local and fails replay windows

Rejected candidates may be reopened only with a new hypothesis that explains
what changed.

---

## 6. Fresh Strategy Tests

Fresh tests are allowed and encouraged, especially low-frequency large-cap
trend or swing candidates.

However, each fresh test must declare:

- candidate identity fields
- market universe
- data profile
- cost profile
- benchmark set
- expected lifecycle stage
- comparison target Champion
- rollback rule

This keeps new work from becoming disconnected reports.

---

## 7. Micro-Live Rule

Micro-live is a calibration stage, not a profit target.

Before `micro_live_ready`, the candidate needs:

- paper evidence
- cost-gap evidence
- active kill-switch policy
- position/exposure cap
- operator sign-off
- clear stop/restart procedure

The first live capital allocation should be treated as data acquisition.

---

## 8. Agent Handoff

Implementation agents should use this lifecycle when adding:

- candidate records
- gate verdict records
- promotion decisions
- cockpit views
- paper/live reconcile reports

Do not add a new strategy runner that bypasses lifecycle states.
