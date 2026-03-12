# AWF-132 Implementation Report

## Header

| Field | Value |
|-------|-------|
| AWF ID | AWF-132 |
| Title | Multi-Asset Data Layer |
| Phase | 21 |
| Codex completion date | 2026-02-27 |
| Spec reference | `plans/AUTOWFO_PHASE21_SPEC.md#AWF-132` |
| Architect review date | 2026-02-28 |
| Review result | APPROVED |

## 1. Files Created / Modified (Codex)

| Status | File | Reason |
|--------|------|--------|
| created | `scripts/autowfo/data_multi.py` | Implemented multi-asset OHLCV loader, parquet cache, concurrent-safe atomic writes, experiment pair loader, and cache metadata listing |
| created | `tests/test_autowfo_data_multi.py` | Added offline unit tests for cache miss/hit/merge, experiment pair loading, cache info, and concurrent access safety |
| modified | `plans/AUTOWFO_TODO.md` | Marked AWF-132 as done and appended session log entry |

**Files intentionally NOT touched**:
- `scripts/autowfo/data.py` (kept untouched per AWF-132 constraint)
- `scripts/autowfo/engine_*.py` (not modified)
- `scripts/control_panel*.py` (not modified)

## 2. Implementation Summary (Codex)

Added a new `data_multi.py` module rather than changing legacy `data.py`, with `load_ohlcv()` as the primary entrypoint using a deterministic cache filename format `{exchange}_{asset-safe}_{timeframe}.parquet`. The loader now performs cache coverage checks, fetches missing ranges, merges and de-duplicates by timestamp, normalizes to timezone-naive UTC `DatetimeIndex`, and writes through an atomic replace guarded by a lock file for concurrent safety. Implemented `load_experiment_data()` to load trigger/action OHLCV as a tuple from experiment config, and `cache_info()` to expose file-level metadata for UI cache management. Added fully offline tests using monkeypatched fetch/parquet I/O to verify behavior without real API calls.

## 3. Deviations from Spec (Codex)

None.

## 4. Exit Criteria Checklist (Codex)

- [x] `load_ohlcv()` returns DataFrame with correct columns and DatetimeIndex
- [x] Cache hit: loads from Parquet without API call
- [x] Cache miss: fetches data (mocked in tests), saves Parquet, returns DataFrame
- [x] `load_experiment_data()` returns `(trigger_ohlcv, action_ohlcv)` tuple
- [x] `cache_info()` lists cached files with metadata
- [x] Asset name normalization: `BTC/USDT` -> `btc-usdt` in filename
- [x] Tests use `tmp_path` and mocked fetch; no real API calls
- [x] All tests pass: N passed, 0 failed

## 5. Test Results (Codex)

**Verification command run**:

```bash
pytest tests/test_autowfo_data_multi.py -v
python -c "from scripts.autowfo.data_multi import load_ohlcv, load_experiment_data, cache_info; print('OK')"
```

**Result**:

```text
6 passed, 0 failed, 0 errors
OK
```

**New tests added**: 6 tests in `tests/test_autowfo_data_multi.py`

**Specific test coverage for exit criteria**:

| Exit criterion | Test name | Result |
|----------------|-----------|--------|
| `load_ohlcv()` returns normalized OHLCV/DatetimeIndex | `test_load_ohlcv_cache_miss_fetches_and_writes` | pass |
| Cache hit does not call fetch | `test_load_ohlcv_cache_hit_does_not_fetch` | pass |
| Cache insufficient range fetches and merges | `test_load_ohlcv_insufficient_cache_fetches_and_merges` | pass |
| `load_experiment_data()` returns trigger/action tuple | `test_load_experiment_data_returns_trigger_and_action` | pass |
| `cache_info()` metadata output | `test_cache_info_lists_cached_files` | pass |
| Concurrent safety (atomic write + lock path) | `test_load_ohlcv_concurrent_calls_are_safe` | pass |

## 6. Cross-Phase Interface Exposure (Codex)

N/A - this AWF has no cross-phase interface.

## 7. Known Issues / Risks (Codex)

Runtime usage still requires at least one Parquet engine (`pyarrow` or `fastparquet`) installed, and `load_ohlcv()` intentionally raises a clear error if neither is available.

## 8. BLOCKER (if applicable) (Codex)

**Status**: NOT BLOCKED

---
# ARCHITECT REVIEW
> Everything below is filled by Architect only. Codex does not edit this section.
---

## R1. Architecture Alignment

- [x] Files match AWF spec (no unexpected additions/omissions)
- [x] Module contracts follow Architecture V2 §4.2
- [x] No unexpected cross-module imports
- [x] Cross-phase interface defined correctly (if applicable)

**Notes**:
Single file `scripts/autowfo/data_multi.py` as specified — existing `data.py` untouched. Three public functions match spec exactly: `load_ohlcv()`, `load_experiment_data()`, `cache_info()`. Cache filename format `{exchange}_{asset-safe}_{timeframe}.parquet` per spec. Only imports: `pandas`, `os`, `time`, `pathlib`, `contextlib` + TYPE_CHECKING guard for `Experiment`. No cross-module coupling beyond expected experiment config access.

## R2. Code Quality

- [x] No hardcoded config values
- [x] No circular imports
- [x] Error handling only at boundaries
- [x] Scope limited to AWF no over-engineering

**Notes**:
`_select_parquet_engine()` tries pyarrow→fastparquet with clear RuntimeError — good boundary error. `_file_lock()` context manager with `O_CREAT|O_EXCL` is correct for atomic file locking on both Windows and Linux. `_write_parquet_atomic()` uses tmp+replace pattern — correct for crash safety. `_fetch_ohlcv()` tries ccxt first, falls back to vectorbt — matches spec preference. `_covers_date_range()` correctly handles cache coverage check. `_normalize_ohlcv()` deduplicates and sorts — defensive without being over-engineered. ccxt pagination loop in `_fetch_ohlcv_ccxt()` handles edge cases (empty batch, last batch < limit, end_ms boundary).

## R3. Test Quality

- [x] All exit criteria have corresponding tests
- [x] Edge cases covered (None, NaN, empty)
- [x] Cross-phase interface has contract test
- [x] Test depth is reasonable

**Notes**:
6 tests cover: cache miss (fetch+write), cache hit (no fetch assertion), insufficient cache (merge), experiment data tuple, cache_info metadata, concurrent safety (2 threads, fetch_count=1). The `_mock_parquet_engine` autouse fixture that swaps Parquet I/O for pickle is a clever offline testing pattern. Concurrent test with `time.sleep(0.15)` and `fetch_count` verification confirms file lock prevents double-fetch. N/A for cross-phase contract test.

## R4. Review Result

**Result**: APPROVED

**Correction AWFs issued**: None

**Soft gate status**: N/A (no cross-phase interface)
