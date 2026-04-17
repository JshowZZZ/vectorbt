# AUTOWFO Development Principles

This file freezes the execution-policy baseline introduced by
`plans/AUTOWFO_PHASE61_62_PLAN_V2.md`.
Downstream files should reference this document instead of re-stating the rules.
If this file and any AUTOWFO plan diverge, this file is authoritative for policy.
Plans may hold implementation detail but cannot override rules here.

## 1. Hard Rules

1. Contract before results: parity gate must be rerun on the corrected adapter contract before any new strategy evidence is accepted.
2. Hypothesis before execution: each AWF must declare hypothesis, metrics, acceptance threshold, and rollback condition before work starts.
3. Observation before optimization: no PnL-driven system changes before a reproducible parity/drift artifact exists.
4. Phase 60 freeze: no new pilot work until Gate B passes.
5. Time-local is not an adapter problem: if a candidate remains time-local after parity is fixed, route it to rolling-anchor replay rather than patching execution logic.
   - Caveat: this rule assumes parity repair does not materially change replay outcomes. If AWF-339 shows parity repair substantially shifts per-row PnL or trade counts versus the pre-fix AWF-331 baseline, revisit this rule before applying it to any time-local candidate. The quantitative threshold for "substantially" is deferred to AWF-339 result review.
6. Kill-switch principle must be written, not activated: the live kill-switch rule (reconcile mismatch threshold, zero-fill day threshold, halt action) must be frozen in the repo policy surface before activation. Activation belongs to a later phase. Writing the rule early prevents downstream work from designing around its absence.

## 2. Hypothesis Template

Every AWF must open with this four-field block before work starts.

| Hypothesis | Metric | Accept threshold | Rollback |
|---|---|---|---|
| `<one sentence; what we expect to observe>` | `<artifact field or SQL result>` | `<numeric or boolean done condition>` | `<what we undo or revert if it fails>` |

Usage rules:

- Paste the filled block into the AWF line in `plans/AUTOWFO_TODO.md`.
- Reuse the same block in the decision memo when a memo is required.
- Keep each field under 120 characters so the entry stays cheap in context.

## 3. Decision Memo Policy

Do not write a decision memo for every AWF.

Write a memo only when the change is one of:

- gate-level
- cross-cutting across multiple modules
- schema or protocol freezing
- irreversible operator policy

Everything else belongs in a one-line `plans/AUTOWFO_TODO.md` status entry with file references.

## 4. Time-Local Routing Rule

Treat time-local as an evidence classification, not as an execution bug.

- Only apply the label after the corrected parity contract has been rerun.
- If a candidate still fails replay after parity is fixed, route it to rolling-anchor replay or wider replay evidence.
- Do not patch adapter or execution logic just to rescue a time-local row.
- If `AWF-339` materially changes per-row PnL or trade counts versus the pre-fix `AWF-331` baseline, re-check this rule before classifying any candidate as time-local. The quantitative threshold for "materially" is deferred to `AWF-339` result review.

Detail lives in `plans/AUTOWFO_PHASE61_62_PLAN_V2.md`.

## 5. Kill-Switch Principle

This section records the future halt rule. It is not active in Phase 61/62.
Threshold values below are provisional placeholders and must be re-derived from
`AWF-347` drift artifact data before any activation.

- Reconcile mismatch threshold:
  - Treat a day as a mismatch incident when either `entry_signal_match_rate` or `exit_signal_match_rate` is below `0.80` (provisional; to be re-derived from `AWF-347` drift artifact data) on a day with at least `3` matched opportunities (provisional; to be re-derived from `AWF-347` drift artifact data).
  - `2` consecutive incident days (provisional; to be re-derived from `AWF-347` drift artifact data) breach the threshold.
- Zero-fill day threshold:
  - Treat a day as a zero-fill incident when the live manifest is fresh and non-empty, but dry-run records `0` opened trades (provisional; to be re-derived from `AWF-347` drift artifact data) and `0` closed trades (provisional; to be re-derived from `AWF-347` drift artifact data) for the UTC day.
  - `3` consecutive zero-fill incident days (provisional; to be re-derived from `AWF-347` drift artifact data) breach the threshold.
- Halt action:
  - Stop new entries.
  - Keep existing positions under protective exits and manual operator review.
  - Pause promotion to the next gate until a human signs off on the root cause and restart plan.
- Activation rule:
  - Do not enable this policy in code during Phase 61/62.
  - Activation is scheduled for Phase 63+ after `AWF-347` drift artifact data is available to re-derive thresholds.
  - Keep the provisional thresholds here so later drift/reconcile work produces the fields needed for activation.

## 6. Statistical Policy

This section is authoritative for policy.
Use it when deriving `plans/AUTOWFO_PARITY_GATE_V1.md`.

- `n >= 10`: use near-tail statistics (`p10` for match ratios, `p90(abs(delta_pct))` for trade-count delta).
- `n < 10`: use the second-worst observed value instead of `min` or max absolute delta.
- `n <= 3`: do not derive a gate; mark the item blocked and expand rerun scope first.

Do not replace this policy with ad-hoc medians, minima, or narrative judgments.
