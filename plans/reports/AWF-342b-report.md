# AWF-342b Implementation Report

## Header

| Field | Value |
|-------|-------|
| AWF ID | AWF-342b |
| Title | Read-only Freqtrade runtime MCP wrapper |
| Phase | 61-62 optional checkpoint |
| Codex completion date | 2026-04-18 |
| Spec reference | `plans/AUTOWFO_PHASE61_62_PLAN_V2.md#awf-342b-add-freqtrade-mcp-if-runtime-supports-it` |
| Architect review date |  |
| Review result |  |

## 1. Files Created / Modified

| Status | File | Reason |
|--------|------|--------|
| created | `autowfo/freqtrade_mcp.py` | Add the read-only stdio MCP wrapper exposing runtime summary and recent trade inspection over the local Freqtrade SQLite runtime |
| created | `tests/test_autowfo_freqtrade_mcp.py` | Add focused runtime-summary, recent-trades, stdio smoke, read-only URI, and API sanitization coverage |
| created | `scripts/run_awf342b_freqtrade_mcp_smoke.py` | Provide a reproducible local smoke runner that saves MCP tool outputs under `artifacts/scratch/freqtrade_mcp_smoke/` |
| created | `.mcp.json` | Register the local `freqtrade_awf342b` MCP server entry used by operators in this commit scope |
| created | `plans/reports/AWF-342b-report.md` | Record AWF-342b scope, TDD evidence, security posture, and follow-up pointer |

**Files intentionally NOT touched**:
- `plans/AUTOWFO_TODO.md` — excluded from this commit to keep AWF-342b separate from Phase 61/62 drift-plan closure work
- `plans/AUTOWFO_MASTER_PLAN.md` — excluded from this commit to keep AWF-342b separate from broader phase bookkeeping
- `autowfo/duckdb_smoke.py` — AWF-342a deliverable, left out of index
- `autowfo/drift_prototypes.py` — AWF-344 deliverable, left out of index
- `plans/protocols/execution_drift_report_v1.json` — AWF-345 deliverable, left out of index

## 2. Implementation Summary

AWF-342b adds a small read-only MCP surface around the local Freqtrade dry-run runtime so operators can inspect runtime metadata without opening the SQLite file directly. The wrapper exposes `runtime_summary()` and `recent_trades(limit=10)` as stdio tools and reuses the existing Freqtrade config/db resolution helpers from `paper_dryrun_reconcile`. During hardening, the SQLite access path was tightened to `file:...?...mode=ro` URIs with `uri=True`, so both summary and recent-trades reads now open the DB explicitly in read-only mode. The runtime summary payload is also intentionally sanitized with a white-listed `api_server` object that omits `password` even if it exists in the config. A standalone smoke script writes tool discovery and output payloads to `artifacts/scratch/freqtrade_mcp_smoke/` for reproducible local verification.

## 3. Deviations from Spec

None.

## 4. Exit Criteria Checklist

- [x] Local read-only Freqtrade MCP wrapper exists and exposes runtime inspection tools over stdio.
- [x] TDD evidence exists for read-only SQLite URI access (`mode=ro`, `uri=True`) in both runtime summary and recent trades paths.
- [x] Runtime summary sanitization is enforced through a white-listed `api_server` payload that excludes `password`.
- [x] Local smoke runner produces reproducible outputs under `artifacts/scratch/freqtrade_mcp_smoke/`.
- [x] AWF-342b commit scope stays isolated from AWF-342a, AWF-344, and AWF-345 work.

## 5. Test Results

**Verification commands run**:

```bash
python -m pytest tests/test_autowfo_freqtrade_mcp.py -v -k readonly_uri_mode
python -m pytest tests/test_autowfo_freqtrade_mcp.py -v
python scripts/run_awf342b_freqtrade_mcp_smoke.py
```

**Result**:

- Red phase (`readonly_uri_mode`) before production patch:

```text
=========================== short test summary info ===========================
FAILED tests/test_autowfo_freqtrade_mcp.py::test_runtime_summary_opens_db_in_readonly_uri_mode
FAILED tests/test_autowfo_freqtrade_mcp.py::test_recent_trades_opens_db_in_readonly_uri_mode
====================== 2 failed, 3 deselected in 16.24s =======================
```

- Green phase after production patch:

```text
====================== 2 passed, 3 deselected in 11.91s =======================
```

- Final focused suite:

```text
============================= 5 passed in 27.36s ==============================
```

**New tests added**: 5 tests in `tests/test_autowfo_freqtrade_mcp.py`

**Specific test coverage for exit criteria**:

| Exit criterion | Test name | Result |
|----------------|-----------|--------|
| Runtime summary omits password and exposes only approved API keys | `test_load_runtime_summary_sanitizes_config_and_counts_trades` | pass |
| Recent trades returns latest rows from the local runtime DB | `test_load_recent_trades_reads_latest_trade_rows` | pass |
| MCP stdio server exposes both tools and responds to `runtime_summary` | `test_freqtrade_mcp_stdio_smoke_lists_tools_and_calls_runtime_summary` | pass |
| Runtime summary opens SQLite in read-only URI mode | `test_runtime_summary_opens_db_in_readonly_uri_mode` | pass |
| Recent trades opens SQLite in read-only URI mode | `test_recent_trades_opens_db_in_readonly_uri_mode` | pass |

## 6. Cross-Phase Interface Exposure

N/A.

## 7. Known Issues / Risks

- `.mcp.json` in this AWF still points at the local Windows Freqtrade config path `E:/Project/freqtrade/user_data/config_autowfo_dryrun.json`; env-var normalization is deferred to a follow-up AWF.
- The current dry-run runtime snapshot reports `trades_total=0` and `open_trades=0`, so `recent_trades.json` is empty even though the MCP path is working.
- This wrapper is intentionally read-only and inspection-focused; it does not expose mutating runtime controls.

## 8. Security Notes

- SQLite access is forced through `file:{path}?mode=ro` with `uri=True`, so the MCP wrapper opens the Freqtrade DB in explicit read-only mode.
- The expected behavior for a hypothetical attacker attempting `INSERT` through this connection is a SQLite write failure because the connection itself is read-only.
- `runtime_summary()` sanitizes `api_server` through a white list: only `enabled`, `listen_ip_address`, `listen_port`, and `username` are emitted.
- Sensitive config fields such as `api_server.password` are intentionally not returned by either tool.

## 9. Runtime Snapshot

Source: `artifacts/scratch/freqtrade_mcp_smoke/runtime_summary.json` generated by `python scripts/run_awf342b_freqtrade_mcp_smoke.py`.

- `dry_run=true`
- `trading_mode=futures`
- `strategy=AutowfoLiveSignalStrategyLongShort`
- `pair_count=8`
- `trades_total=0`
- `open_trades=0`
- `recent_trades.json=[]`

Smoke artifacts:

- `artifacts/scratch/freqtrade_mcp_smoke/tools.json`
- `artifacts/scratch/freqtrade_mcp_smoke/runtime_summary.json`
- `artifacts/scratch/freqtrade_mcp_smoke/recent_trades.json`

## 10. BLOCKER

Status: NOT BLOCKED

## 11. Follow-up Pointer

The next bounded cleanup for this surface is the pending config-path normalization: replace the hardcoded local Windows config path in `.mcp.json` and the smoke script with an environment-variable driven contract while preserving AWF-342b's read-only runtime behavior.
