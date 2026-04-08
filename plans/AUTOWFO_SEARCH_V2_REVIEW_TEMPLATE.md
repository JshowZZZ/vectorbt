# AUTOWFO Search V2 Review Template

> Purpose: Standard response template for external AI reviewers evaluating
> `plans/AUTOWFO_SEARCH_V2_PROPOSAL.md`

---

## How To Use

Ask the reviewer to read:

- `plans/AUTOWFO_SEARCH_V2_PROPOSAL.md`
- `plans/AUTOWFO_TODO.md`
- relevant repo code if needed

Then ask them to reply using the exact section structure below.

The reviewer may answer in English or Chinese, but should keep the section headings
unchanged for easier comparison across reviewers.

The reviewer should:

- focus on concrete design critique, not broad restatement;
- cite proposal sections and repo files when making claims;
- distinguish **blockers** from **nice-to-have** suggestions;
- give an explicit recommendation on whether the project should proceed to:
  - pilot protocol cleanup,
  - pilot execution,
  - full Search V2,
  - or a different direction.

---

## Copy-Paste Template

```md
# Search V2 Review

## 1. Review Metadata

- Reviewer:
- Date:
- Documents reviewed:
- Code paths reviewed:

## 2. Executive Verdict

Choose one:

- `GO`
- `GO WITH REVISIONS`
- `NARROW-GO`
- `NO-GO`

Short verdict:

## 3. Executive Summary

Provide a concise 1-3 paragraph summary covering:

- whether the revised priority order is correct;
- whether the pilot is worth running;
- whether full Search V2 should remain conditional on pilot results.

## 4. Scores

Score each item from `1` to `5`, where:

- `1` = very weak
- `3` = acceptable but needs work
- `5` = strong

| Area | Score | Rationale |
|------|------:|-----------|
| Problem framing |  |  |
| Architecture fit |  |  |
| Statistical rigor |  |  |
| Runtime / cost realism |  |  |
| Evidence / provenance design |  |  |
| Decision-gate quality |  |  |

## 5. Major Findings

List findings in severity order.

Use this structure for each finding:

### Finding 1

- Severity: `blocker` / `high` / `medium` / `low`
- Area:
- Statement:
- Evidence:
- Why it matters:
- Recommended fix:

### Finding 2

- Severity:
- Area:
- Statement:
- Evidence:
- Why it matters:
- Recommended fix:

Add more findings as needed.

If there are no major findings, state that explicitly.

## 6. Answers To Proposal Review Questions

### Q1. Is the revised ordering more rational than immediate full Search V2?

Answer:

### Q2. Is using the legacy path for the pilot the right pragmatic choice, or should the pilot already be run inside the V2 experiment stack?

Answer:

### Q3. Is the 7-indicator shortlist appropriate for the first cross-symbol pilot?

Answer:

### Q4. Is the 3-regime trend-only preset a good first pilot, or does it bias the result too much?

Answer:

### Q5. Which WFO setting is the best compromise on `180d`?

Choose one and justify:

- `45/30/30`
- `60/30/30`
- other

Answer:

### Q6. Is ATR-relative exit normalization sufficient for the pilot, or should another execution normalization be added?

Answer:

### Q7. Are the proposed `go / narrow-go / no-go` thresholds reasonable?

Answer:

### Q8. If the pilot is strongly positive, should the first full Search V2 be limited to size `1..3` and the 3-regime preset, or widened immediately?

Answer:

## 7. Pilot Protocol Assessment

Comment specifically on these pilot assumptions:

- `180d` data window
- explicit WFO reconfiguration
- fixed ATR-relative median exit overlay
- 7-indicator subset
- combo sizes `1..3`
- 3-regime preset
- target evaluation count around `3,780` under pilot-mode freezes

For each item, say whether it is:

- `acceptable`
- `acceptable with revision`
- `not recommended`

## 8. Decision Gate Assessment

Evaluate the proposed decision table:

| Pilot result | Proposed action | Your assessment |
|-------------|-----------------|-----------------|
| `3+` combos positive across `6/10` or more symbols | full Search V2 with narrow initial scope |  |
| `1-2` combos only, marginal or unstable | focused discovery only |  |
| `0` meaningful cross-symbol combos | pivot away from universal-signal search |  |

State whether you agree with:

- the thresholds;
- the interpretation;
- the recommended next action in each row.

## 9. Recommended Changes Before AWF-239 Signoff

List only the changes you believe must be made before the proposal is considered frozen.

1.
2.
3.

If none, write `None`.

## 10. Optional Improvements

List improvements that are useful but not required before the pilot starts.

1.
2.
3.

## 11. Final Recommendation

Choose one:

- `Proceed to AWF-240 as written`
- `Proceed to AWF-240 with revisions`
- `Do not proceed; rewrite proposal first`

Final note:
```

---

## Notes For Aggregation

If you are collecting multiple AI reviews, compare them on:

- blockers in common
- preferred WFO setting
- opinion on 3-regime pilot bias
- whether the legacy pilot path is acceptable
- whether the go / narrow-go / no-go thresholds need revision

This should make it easier to synthesize a final scope freeze for `AWF-239`.

