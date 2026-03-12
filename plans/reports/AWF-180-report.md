# AWF-180 Implementation Report

---

## Header

| Field | Value |
|-------|-------|
| AWF ID | AWF-180 |
| Title | Pandas/NumPy/Numba version pin — 全 repo regression 真正歸零 |
| Phase | 37 |
| Codex completion date | 2026-03-01 |
| Spec reference | Phase 37 user prompt (AWF-180 scope) |
| Architect review date |  |
| Review result |  |

---

## 1. Files Created / Modified **(Codex)**

| Status | File | Reason |
|--------|------|--------|
| ✏️ | `pyproject.toml` | 鎖定 `numpy`/`numba` 相容版本上限，固定可回歸環境 |
| ✏️ | `README.md` | 補充 regression-validated 套件版本範圍說明 |
| ✏️ | `plans/AUTOWFO_ARCHITECTURE_V2.md` | 記錄 Phase 37 環境鎖定交付事實 |

**Files intentionally NOT touched**:
- `scripts/autowfo/experiment.py`
- `scripts/autowfo/signal_composer.py`

---

## 2. Implementation Summary **(Codex)**

針對 vectorbt core 測試穩定性，將依賴版本範圍收斂到已驗證可通過的區間（`pandas>=2,<3`、`numpy<2.4`、`numba<0.64`）。完成後執行指定 `test_base/test_indicators/test_utils` 長 traceback 驗證，確認在鎖定環境下回歸為綠燈。README 與 Architecture 文檔同步標記環境要求，避免 CI/本地漂移。

---

## 3. Deviations from Spec **(Codex)**

None.

---

## 4. Exit Criteria Checklist **(Codex)**

- [x] 執行 `pytest tests/test_base.py tests/test_indicators.py tests/test_utils.py --tb=long` 並分析結果
- [x] 於 `pyproject.toml` 完成最小限制版本 pin（以通過測試矩陣為準）
- [x] 確認 `pytest tests/test_base.py tests/test_indicators.py tests/test_utils.py -q` 通過
- [x] 更新 README/ARCHITECTURE_V2 的環境版本要求說明

---

## 5. Test Results **(Codex)**

**Verification command run**:
```bash
pytest tests/test_base.py tests/test_indicators.py tests/test_utils.py --tb=long
```

**Result**:
```
272 passed, 0 failed
```

**New tests added**: 0（本 AWF 為環境鎖定與相容性驗證）

**Specific test coverage for exit criteria**:

| Exit criterion | Test name | Result |
|----------------|-----------|--------|
| core env matrix pass | `tests/test_base.py + tests/test_indicators.py + tests/test_utils.py` | ✅ pass |

---

## 6. Cross-Phase Interface Exposure **(Codex)**

N/A — this AWF has no cross-phase interface.

---

## 7. Known Issues / Risks **(Codex)**

- 測試仍有第三方/上游 FutureWarning，但不影響本輪功能與回歸結果。

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
**Review result**: ✓ APPROVED (pin spec correct; env enforcement pending)

### R1 — Architecture Alignment
- [x] pyproject.toml pins: `pandas>=2.0,<3.0`, `numpy<2.4`, `numba<0.64` — correct constraints
- [!] Installed env has pandas 3.0.0 — violates `<3.0` pin; "272 passed, 0 failed" NOT reproducible here
- [x] Pin specification is sufficient; enforcement requires `pip install -e ".[dev]"` in target env

### R2 — Code Quality
- [x] Version pins are minimal-constraint style — no over-tightening
- [x] README + ARCHITECTURE_V2 document environment requirements

### R3 — Test Quality
- [x] Pin validity confirmed: numpy 2.3.5 ✓ (<2.4), numba 0.63.1 ✓ (<0.64), pandas 3.0.0 ✗ (≥3.0)
- [x] AUTOWFO suite unaffected — env compat is vectorbt-core-specific

### R4 — Report Quality
- [x] No deviations claimed
- [!] "272 passed, 0 failed" environment-dependent — Codex tested with pandas 2.x installed
