# AUTOWFO Architect Protocol
**Version**: 1.0 — 2026-02-27
**Architect**: Claude Sonnet 4.6 (planning + review only)
**Implementer**: Codex (implementation only)

---

## 1. Roles

### Architect (Claude)
- Owns architecture decisions, module contracts, phase planning
- Reviews completed AWF reports (triggered by user)
- Writes correction AWFs when issues found (new sequential IDs)
- Approves cross-phase interfaces before next phase depends on them
- Does NOT write implementation code

### Implementer (Codex)
- Implements AWF items strictly per spec in `plans/AUTOWFO_PHASE20_SPEC.md`
- Writes `plans/reports/AWF-{ID}-report.md` after each AWF completion
- Reads correction AWFs from `plans/AUTOWFO_TODO.md` and fixes without re-architecting
- Does NOT make architectural decisions — flags blockers in report instead

---

## 2. Workflow

```
Codex implements AWF-N
        ↓
Codex writes plans/reports/AWF-N-report.md
        ↓
User triggers Architect: "請 review AWF-N"
        ↓
Architect reads: report + referenced files + tests
        ↓
   Issues found?
   ├── YES → Architect adds AWF-M [fix AWF-N] to AUTOWFO_TODO.md
   │          Architect writes "REVIEW: ⚠️ corrections issued" in report
   └── NO  → Architect writes "REVIEW: ✓ approved" in report
        ↓
If ⚠️ cross-phase interface: soft gate check (see §4)
```

---

## 3. Correction AWF Rules

- **Numbering**: New sequential ID continuing from current max (e.g., AWF-146, AWF-147)
- **Title format**: `AWF-M [fix AWF-N] — <specific issue in one line>`
- **Priority**: Same as or higher than original AWF
- **Owner**: Codex
- **Location**: Added to `plans/AUTOWFO_TODO.md` pipe table AND detailed spec added to `plans/AUTOWFO_PHASE20_SPEC.md`
- **Trigger**: Codex implements correction after seeing it in TODO; does NOT re-read original AWF

---

## 4. Soft Gate — Cross-Phase Interface

AWF items marked **⚠️ Cross-phase interface** in the spec expose contracts that the next phase depends on.

### Rule
Before Phase N+1 starts using Phase N interfaces:
1. All Phase N AWFs must have submitted reports (`plans/reports/AWF-*.md` exists)
2. All ⚠️ items must have architect review result (`REVIEW: ✓` or correction AWFs issued)

### What Codex may do while waiting for review
- Implement Phase N+1 AWFs that have no dependency on the ⚠️ interface
- Write stubs/mocks for the pending interface
- Must NOT write production code that imports the unreviewed interface

---

## 4b. Next Action Directive

After every review, Architect produces a **Next Action** block. User copies this directly to Codex as its next instruction. Format:

```
AWF-{N} 已通過/未通過 Architect review。

請繼續實作 AWF-{N+1} ({title})。
步驟：
1. 閱讀 plans/AUTOWFO_PHASE20_SPEC.md#AWF-{N+1} 的完整規格
2. 建立/修改列出的檔案
3. 建立對應測試檔
4. 執行 pytest {test_file} -v 確認全部通過
5. 完成後依 plans/reports/AWF-TEMPLATE.md 格式寫入 plans/reports/AWF-{N+1}-report.md

注意：
- {AWF-specific warnings from spec}

下一個 AWF：AWF-{N+2} (如果有依賴關係，說明順序)
```

If corrections are required, the Next Action block instructs Codex to fix the correction AWFs before proceeding.

---

## 5. Architect Review Checklist

When reviewing an AWF report, I check all of the following.

### 5.1 Architecture Alignment
- [ ] Files created/modified match AWF spec (no extra, no missing)?
- [ ] Module contracts follow `plans/AUTOWFO_ARCHITECTURE_V2.md` section referenced in AWF?
- [ ] No unexpected imports (from modules not listed in AWF spec)?
- [ ] Cross-phase interface (if any) defined exactly as Architecture V2 specifies?

### 5.2 Code Quality
- [ ] No hardcoded values that belong in config?
- [ ] No circular imports introduced?
- [ ] Error handling only at system boundaries (user input, external API) — not internal?
- [ ] Scope limited to AWF — no features added beyond exit criteria?
- [ ] No backwards-compatibility shims for code that didn't exist before?

### 5.3 Test Quality
- [ ] Every exit criterion has at least one corresponding test?
- [ ] Edge cases covered (empty input, None/NaN, zero-length series)?
- [ ] Cross-phase interface exposed by this AWF has contract tests?
- [ ] No tests that mock away the thing being tested (testing the mock, not the code)?
- [ ] Test count is reasonable (not trivially low, not obsessively exhaustive)?

### 5.4 Report Quality
- [ ] Report clearly states actual file list (can I verify against git diff?)?
- [ ] Deviations from spec are explicit with justification?
- [ ] Test result number is stated (N passed, 0 failed)?
- [ ] All exit criteria are checked (not just "tests pass")?

---

## 6. File Map

| File | Owner | Purpose |
|------|-------|---------|
| `plans/ARCHITECT_PROTOCOL.md` | Architect | This document — rules |
| `plans/AUTOWFO_ARCHITECTURE_V2.md` | Architect | System architecture spec |
| `plans/AUTOWFO_PHASE20_SPEC.md` | Architect | Detailed AWF specs (Phase 20+) |
| `plans/AUTOWFO_TODO.md` | Architect + Codex | Status tracking (pipe table) |
| `plans/AUTOWFO_MASTER_PLAN.md` | Architect | Phase-level plan and change log |
| `plans/reports/AWF-{ID}-report.md` | Codex (writes) + Architect (reviews) | Per-AWF implementation report |
| `plans/reports/AWF-TEMPLATE.md` | Architect | Template Codex copies for each report |

---

## 7. What Codex Must Read Before Starting Any AWF

1. `plans/ARCHITECT_PROTOCOL.md` (this file) — understand the rules
2. `plans/AUTOWFO_ARCHITECTURE_V2.md` — understand the target architecture
3. `plans/AUTOWFO_PHASE20_SPEC.md#AWF-{ID}` — read the specific AWF block
4. `plans/reports/AWF-TEMPLATE.md` — know what report to write after completion

Codex does NOT need to read AUTOWFO_TODO.md for implementation details — it only reads TODO to check for correction AWFs assigned to it.

---

## 8. Escalation (Codex → Architect)

If Codex encounters any of the following, it writes a **BLOCKER** section in the report and stops:

| Situation | Action |
|-----------|--------|
| AWF spec is ambiguous about a design decision | Report BLOCKER: "Spec unclear on X — options are A or B" |
| Exit criterion is technically impossible | Report BLOCKER: "Exit criterion Y cannot be met because Z" |
| Implementing AWF would require modifying a file marked "do not modify" | Report BLOCKER: "AWF-N requires modifying {file} which is restricted" |
| Discovered that Architecture V2 assumption is incorrect | Report BLOCKER: "Architecture V2 §X assumes Y but actual system state is Z" |

User then brings the BLOCKER to Architect for decision.

---

*Protocol effective from 2026-02-27. Updates require Architect approval.*
