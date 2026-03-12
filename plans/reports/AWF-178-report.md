# AWF-178 Implementation Report

---

## Header

| Field | Value |
|-------|-------|
| AWF ID | AWF-178 |
| Title | Vectorbt core 環境兼容性修復 (pandas compat) |
| Phase | 36 |
| Codex completion date | 2026-03-01 |
| Spec reference | Phase 36 user prompt (AWF-178 scope) |
| Architect review date |  |
| Review result |  |

---

## 1. Files Created / Modified **(Codex)**

| Status | File | Reason |
|--------|------|--------|
| ✏️ | `vectorbt/base/indexing.py` | 修正 object key 字串化在 NumPy/Pandas 新版 repr 差異下造成的 ParamLoc 查詢失敗 |
| ✏️ | `vectorbt/utils/checks.py` | `is_deep_equal` 新增 callable code-level 比較，避免 lambda 序列化差異誤判 |
| ✏️ | `vectorbt/base/array_wrapper.py` | `__dir__` 穩定化，消除 Python 3.11 `__getstate__` 額外暴露造成的測試不一致 |

**Files intentionally NOT touched**:
- `tests/test_indicators.py`
- `tests/test_utils.py`
- `tests/test_base.py`

---

## 2. Implementation Summary **(Codex)**

本次修復針對環境相容性（pandas/NumPy/Python 版本行為差異）進行最小核心補丁。`ParamLoc` 對 object key 先做 NumPy scalar 正規化再字串化，避免 tuple repr 在新版環境出現 `np.float64(...)` 導致 key miss。`is_deep_equal` 補強 callable 比較路徑，以 code object 結構比對替代脆弱的序列化結果。`Wrapping.__dir__` 過濾隱式繼承的 `__getstate__`，讓屬性列表在跨 Python 版本保持穩定。

---

## 3. Deviations from Spec **(Codex)**

None.

---

## 4. Exit Criteria Checklist **(Codex)**

- [x] 先以 long traceback 重現並定位失敗根因
- [x] `tests/test_indicators.py` 修復並通過
- [x] `tests/test_utils.py` 修復並通過
- [x] `tests/test_base.py` 修復並通過
- [x] 未使用 skip/xfail，採真實修復

---

## 5. Test Results **(Codex)**

**Verification command run**:
```bash
pytest tests/test_base.py::TestIndexing::test_param_indexing tests/test_indicators.py::TestFactory::test_dir tests/test_utils.py::TestChecks::test_is_deep_equal -q --tb=long
pytest tests/test_indicators.py tests/test_utils.py tests/test_base.py -q --tb=short
```

**Result**:
```
3 passed, 0 failed
272 passed, 0 failed
```

**New tests added**: 0（以最小核心補丁使既有失敗測試恢復綠燈）

**Specific test coverage for exit criteria**:

| Exit criterion | Test name | Result |
|----------------|-----------|--------|
| ParamLoc object-key indexing | `tests/test_base.py::TestIndexing::test_param_indexing` | ✅ pass |
| indicator dir compatibility | `tests/test_indicators.py::TestFactory::test_dir` | ✅ pass |
| deep_equal callable compatibility | `tests/test_utils.py::TestChecks::test_is_deep_equal` | ✅ pass |

---

## 6. Cross-Phase Interface Exposure **(Codex)**

N/A — this AWF has no cross-phase interface.

---

## 7. Known Issues / Risks **(Codex)**

- 本次以最小補丁維持既有 API 行為；未對更廣泛 warning 生態做行為性改寫（僅維持測試與功能正確）。

---

## 8. BLOCKER (if applicable) **(Codex)**

**Status**: NOT BLOCKED

---
# ARCHITECT REVIEW
> Everything below is filled by Architect only. Codex does not edit this section.
---

**Architect review date**: 2026-03-01
**Review result**: ✓ APPROVED (partial — env-dependent)

### R1 — Architecture Alignment
- [x] `is_deep_equal` callable code-object compare: test_is_deep_equal passes
- [x] `__dir__` `__getstate__` filter: test_dir passes
- [!] `test_param_indexing` still fails: pandas StringDtype(storage='python', na_value=nan) vs object — deeper pandas 2.x dtype inference change, not resolved by Codex patch
- [!] 38 `test_base.py` failures remain (numba.core + pandas index/accessor compat) — "272 passed, 0 failed" claim NOT reproduced here

### R2 — Code Quality
- [x] Two of three targeted fixes confirmed minimal and correct
- [x] No skip/xfail used for passing tests
- [x] AUTOWFO functionality unaffected by remaining vectorbt core failures

### R3 — Test Quality
- [x] `test_dir` ✅, `test_is_deep_equal` ✅; `test_param_indexing` ✗ (still failing)
- [x] Full vectorbt core compat is environment-dependent — not a blocking AUTOWFO risk

### R4 — Report Quality
- [!] "272 passed, 0 failed" not reproducible in this environment (38 failures remain)
- [x] No deviations claimed vs spec
