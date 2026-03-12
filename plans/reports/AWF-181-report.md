# AWF-181 Implementation Report

---

## Header

| Field | Value |
|-------|-------|
| AWF ID | AWF-181 |
| Title | Signal scheduling daemon — 定時自動 export-signal + paper open/close |
| Phase | 37 |
| Codex completion date | 2026-03-01 |
| Spec reference | Phase 37 user prompt (AWF-181 scope) |
| Architect review date |  |
| Review result |  |

---

## 1. Files Created / Modified **(Codex)**

| Status | File | Reason |
|--------|------|--------|
| ✅ | `scripts/autowfo/signal_scheduler.py` | 新增 signal scheduling daemon 與 state 原子寫入 |
| ✏️ | `autowfo/commands/plan.py` | 新增 `schedule-signals` 子命令 parser + handler |
| ✏️ | `autowfo/cli.py` | 新增 `_cmd_schedule_signals` dispatch |
| ✅ | `tests/test_autowfo_signal_scheduler.py` | 新增 strategy changed / unchanged 核心行為測試 |
| ✏️ | `tests/test_autowfo_cli.py` | 新增 `schedule-signals` CLI 行為測試與 help 清單更新 |

**Files intentionally NOT touched**:
- `scripts/autowfo/experiment_runner.py`
- `scripts/autowfo/analytics.py`（僅讀取既有 query，未改寫寫入路徑）

---

## 2. Implementation Summary **(Codex)**

新增 `SignalScheduler` daemon：定時讀取 analytics top strategy，若策略未變更則 skip；若變更則自動 close 舊 paper 倉位、open 新倉位並輸出最新 `live_signal_config.json`。狀態持久化到 `artifacts/signal_schedule_state.json`，採用 tmp->rename 原子寫入。CLI 新增 `autowfo schedule-signals [--interval N]` 供 daemon 執行與排程整合。

---

## 3. Deviations from Spec **(Codex)**

None.

---

## 4. Exit Criteria Checklist **(Codex)**

- [x] 新增 `scripts/autowfo/signal_scheduler.py`
- [x] 狀態持久化到 `artifacts/signal_schedule_state.json`（原子寫入）
- [x] `autowfo schedule-signals [--interval N]` 可執行
- [x] strategy 改變時自動 close+open；相同時 skip
- [x] state file 正確更新（`last_experiment_id/last_export_ts/schedule_interval_seconds`）

---

## 5. Test Results **(Codex)**

**Verification command run**:
```bash
pytest tests/test_autowfo_signal_scheduler.py -v
pytest tests/test_autowfo_cli.py -q
```

**Result**:
```
2 passed
50 passed
```

**New tests added**: 3（`tests/test_autowfo_signal_scheduler.py` 2 筆 + CLI 新增 1 筆）

**Specific test coverage for exit criteria**:

| Exit criterion | Test name | Result |
|----------------|-----------|--------|
| strategy changed -> close+open | `test_signal_scheduler_switches_strategy_close_then_open` | ✅ pass |
| strategy unchanged -> skip | `test_signal_scheduler_skips_when_top_strategy_unchanged` | ✅ pass |
| CLI schedule-signals wiring | `test_cli_schedule_signals_runs_daemon_with_interval_and_max_ticks` | ✅ pass |

---

## 6. Cross-Phase Interface Exposure **(Codex)**

N/A — this AWF has no cross-phase interface.

---

## 7. Known Issues / Risks **(Codex)**

- scheduler 目前以 polling daemon 模式運作；實務部署仍需外層 process supervisor 管理長時運行。

---

## 8. BLOCKER (if applicable) **(Codex)**

**Status**: NOT BLOCKED

---
# ARCHITECT REVIEW
> Everything below is filled by Architect only. Codex does not edit this section.
---
# ARCHITECT REVIEW
> Everything below is filled by Architect only. Codex does not edit this section.
---

**Architect review date**: 2026-03-01
**Review result**: ✓ APPROVED

### R1 — Architecture Alignment
- [x] `SignalScheduler`: top-strategy compare → close prev + open new + export config
- [x] State: `artifacts/signal_schedule_state.json` atomic write (`{last_experiment_id, last_export_ts, schedule_interval_seconds}`)
- [x] `autowfo schedule-signals [--interval N]` CLI wired through existing dispatch

### R2 — Code Quality
- [x] Skip-on-unchanged is idempotent — no spurious close/open churn
- [x] analytics.py read-only — no write path changes
- [x] process supervisor dependency for long-running daemon documented

### R3 — Test Quality
- [x] `test_signal_scheduler_switches_strategy_close_then_open` — close+open flow verified
- [x] `test_signal_scheduler_skips_when_top_strategy_unchanged` — skip semantics verified
- [x] `test_cli_schedule_signals_runs_daemon_with_interval_and_max_ticks` — CLI integration

### R4 — Report Quality
- [x] File list accurate
- [x] No deviations
- [x] Test count stated: 2+50 passed
