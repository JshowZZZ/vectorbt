# AWF-184 Implementation Report

---

## Header

| Field | Value |
|-------|-------|
| AWF ID | AWF-184 |
| Title | Multi-strategy paper portfolio — 同時追蹤 N 個策略倉位 |
| Phase | 38 |
| Codex completion date | 2026-03-01 |
| Spec reference | Phase 38 user prompt (AWF-184 scope) |
| Architect review date |  |
| Review result |  |

---

## 1. Files Created / Modified **(Codex)**

| Status | File | Reason |
|--------|------|--------|
| ✏️ | `scripts/autowfo/paper_position.py` | 擴充 open positions read-model（`list_open_positions` + `portfolio_snapshot`） |
| ✏️ | `scripts/autowfo/signal_scheduler.py` | 由單策略切換為 top-N（預設 3）並行追蹤；新上榜 open、落榜 close |
| ✏️ | `scripts/control_panel_experiments.py` | 新增 `/paper/portfolio.json` handler（open positions + unrealized PnL） |
| ✏️ | `scripts/control_panel.py` | 註冊 `/paper/portfolio.json` route |
| ✏️ | `tests/test_autowfo_paper_position.py` | 新增多策略並行 open 與 portfolio snapshot 測試 |
| ✏️ | `tests/test_autowfo_signal_scheduler.py` | 新增 top-3 同時 open + 落榜 auto-close 測試 |
| ✏️ | `tests/test_control_panel_experiments.py` | 新增 `/paper/portfolio.json` endpoint schema/數值測試 |

**Files intentionally NOT touched**:
- `scripts/autowfo/experiment.py`
- `scripts/autowfo/signal_composer.py`

---

## 2. Implementation Summary **(Codex)**

`SignalScheduler` 現在以 top-N 策略集合做狀態同步，預設追蹤前 3 名：集合新增即開倉、集合移除即平倉。`PaperPositionStore` 提供 portfolio 快照，回傳所有 open 倉位與以 mark price 估算的 unrealized PnL。control panel 新增 `GET /paper/portfolio.json`，閉合多策略 paper 倉位的讀取與監控路徑。

---

## 3. Deviations from Spec **(Codex)**

None.

---

## 4. Exit Criteria Checklist **(Codex)**

- [x] `PaperPositionStore` 支援多策略並行 open（不同 strategy/signal 可同時持倉）
- [x] 新增 `GET /paper/portfolio.json`（open 倉位 + unrealized PnL）
- [x] `SignalScheduler` 切換至 top-N（預設 3）追蹤模式
- [x] top-3 同時 open 測試覆蓋
- [x] 落榜策略自動 close 測試覆蓋

---

## 5. Test Results **(Codex)**

**Verification command run**:
```bash
pytest tests/test_autowfo_paper_position.py tests/test_autowfo_signal_scheduler.py -k "parallel or portfolio_snapshot or top3 or dropped_strategy" -v
pytest tests/test_control_panel_experiments.py -k "paper_portfolio_endpoint" -v
```

**Result**:
```
3 passed, 7 deselected
1 passed, 17 deselected
```

**New tests added**: 4
- `test_open_position_allows_multiple_strategies_in_parallel`
- `test_portfolio_snapshot_unrealized_pnl_with_latest_prices`
- `test_signal_scheduler_top3_opens_and_closes_dropped_strategy`
- `test_paper_portfolio_endpoint_returns_open_positions_with_unrealized_pnl`

**Specific test coverage for exit criteria**:

| Exit criterion | Test name | Result |
|----------------|-----------|--------|
| top-3 同時持倉 | `test_signal_scheduler_top3_opens_and_closes_dropped_strategy` | ✅ pass |
| 落榜自動平倉 | `test_signal_scheduler_top3_opens_and_closes_dropped_strategy` | ✅ pass |
| portfolio endpoint schema | `test_paper_portfolio_endpoint_returns_open_positions_with_unrealized_pnl` | ✅ pass |
| multi-strategy store behavior | `test_open_position_allows_multiple_strategies_in_parallel` | ✅ pass |

---

## 6. Cross-Phase Interface Exposure **(Codex)**

N/A — this AWF has no cross-phase interface.

---

## 7. Known Issues / Risks **(Codex)**

- unrealized PnL 估值目前使用 `paper_latest_prices.json`（若有）或歷史 close/open fallback，未直接接交易所即時報價。

---

## 8. BLOCKER (if applicable) **(Codex)**

**Status**: NOT BLOCKED

---
# ARCHITECT REVIEW
> Everything below is filled by Architect only. Codex does not edit this section.
---

**Architect review date**: 2026-03-01
**Review result**: ✓ APPROVED

### R1 — Architecture Alignment
- [x] `SignalScheduler` 改為 top-N (預設 3) 集合同步 — 新上榜 open、落榜 close
- [x] `PaperPositionStore` 支援多策略並行 open (不同 experiment_id)
- [x] `GET /paper/portfolio.json` — open positions + unrealized PnL

### R2 — Code Quality
- [x] 不破壞既有 single-strategy API 合約 — additive extension
- [x] unrealized PnL 使用 paper_latest_prices.json fallback — 已記錄非即時報價限制
- [x] No changes to Experiment/SignalComposer

### R3 — Test Quality
- [x] `test_signal_scheduler_top3_opens_and_closes_dropped_strategy` — top-3 + 落榜 close
- [x] `test_open_position_allows_multiple_strategies_in_parallel` — multi-strategy store
- [x] `test_portfolio_snapshot_unrealized_pnl_with_latest_prices` — pnl 估值
- [x] `test_paper_portfolio_endpoint_returns_open_positions_with_unrealized_pnl` — endpoint

### R4 — Report Quality
- [x] File list accurate
- [x] No deviations
- [x] Test count stated: 4 passed
