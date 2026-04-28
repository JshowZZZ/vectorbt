# AWF-348 Canonical Paper Evidence Recovery Report

## Header

| Field | Value |
|-------|-------|
| AWF ID | AWF-348 |
| Title | Canonical paper evidence recovery |
| Phase | 63 paper trading exploitation |
| Codex completion date | 2026-04-28 |
| Spec reference | `plans/AUTOWFO_TODO.md`, `plans/AUTOWFO_PHASE63_PLAN.md` |

## Scope

This recovery pass restored the Phase 63 paper pipeline to the frozen canonical
rank 1 Champion lane. It did not add Risk Engine behavior, live activation,
control-panel APIs, or new strategy-search dimensions.

Canonical source:

- `artifacts/freqtrade_bridge/20260411_microcohort_dropsol_main_canonical_r1/signal_manifest.json`
- selection: `canonical_gate_passed`
- rank: `1`
- source pairs: `8`

## Runtime Recovery

Forced restart command:

```bash
.\scripts\start_ft_dryrun.ps1 -ProjectRoot E:\Project\vectorbt-master -FreqtradeRoot E:\Project\freqtrade -ManifestJson artifacts\freqtrade_bridge\20260411_microcohort_dropsol_main_canonical_r1\signal_manifest.json -ForceRestart
```

Observed runtime status after restart:

- live signal producer: running, PID `804`
- Freqtrade dry-run: running, PID `15312`
- Freqtrade state: `RUNNING`

The first post-restart watch still showed the previous stable-rank manifest.
Per recovery runbook, a one-shot live signal export was run:

```bash
python -m autowfo bridge-live-signal --manifest-json artifacts/freqtrade_bridge/20260411_microcohort_dropsol_main_canonical_r1/signal_manifest.json --out-dir artifacts/live_signal_store --interval 0 --cwd .
```

Resulting live manifest:

- path: `artifacts/live_signal_store/live_manifest.json`
- `created_utc`: `2026-04-28T15:07:34+00:00`
- `selection`: `canonical_gate_passed`
- `rank`: `1`
- signal rows: `48`
- signal pairs: `8`
- signal `last_bar_utc`: `2026-04-28T14:00:00`
- freshness at validation: `< 30 minutes`

## Reconcile And Warehouse Import

Daily reconcile command:

```bash
python -m autowfo bridge-dryrun-reconcile --live-manifest-json artifacts/live_signal_store/live_manifest.json --freqtrade-config E:/Project/freqtrade/user_data/config_autowfo_dryrun.json --out-dir artifacts/paper_dryrun --date 2026-04-28 --cwd .
```

Daily summary result:

- output: `artifacts/paper_dryrun/daily_summary_20260428.json`
- opened trades: `0`
- closed trades: `0`
- entry match rate: `None`
- exit match rate: `None`

Evidence Warehouse import command:

```bash
python -m autowfo storage evidence-warehouse --mode import-phase63-paper --paper-dir artifacts/paper_dryrun --live-manifest-path artifacts/live_signal_store/live_manifest.json --cwd . --json
```

Import result:

- `ok`: `true`
- daily summaries seen: `5`
- imported candidates: `2`
- imported paper trades: `0`
- imported execution gap events: `5`
- warnings: zero-trade day warnings for the available daily summaries
- stale manifest warning: absent

## Zero-Trade Classification

Classification: `strategy_no_signal_today`.

Rationale:

- `manifest_wrong_lane`: no; live manifest points to `canonical_gate_passed` rank `1`.
- `manifest_stale`: no; manifest freshness was below 30 minutes at validation.
- `signal_rows_empty`: no; current signal store contains `48` rows across `8` pairs.
- `pair_mapping_gap`: no; all 8 BTC source pairs map to USDT Freqtrade pairs.
- `freqtrade_process_down`: no; both managed processes were running.
- `db_trade_table_missing`: no; `E:\Project\freqtrade\tradesv3.dryrun.sqlite` exists and contains a `trades` table.
- `strategy_no_signal_today`: yes; the current signal window had zero `enter_long`, `enter_short`, `exit_long`, and `exit_short` rows, and the dry-run DB had zero trades.

## Outcome

AWF-348 is complete as a recovery and health checkpoint:

- canonical rank 1 paper lane restored
- live manifest refreshed to canonical rank 1
- live signal producer and Freqtrade dry-run observed running
- one-day reconcile summary written for `2026-04-28`
- zero-trade day classified without changing strategy logic

This is not a paper Survival Gate pass. Phase 63 still needs AWF-349 evidence
accumulation and AWF-350 aggregate paper evidence before any paper verdict can
be considered.

## Validation

Runtime validation:

- `watch_ft_dryrun.ps1` showed the live signal producer and Freqtrade dry-run
  running.
- `artifacts/live_signal_store/live_manifest.json` pointed to
  `canonical_gate_passed` rank `1` and was fresh at validation time.
- `bridge-dryrun-reconcile` wrote
  `artifacts/paper_dryrun/daily_summary_20260428.json`.
- Evidence Warehouse `import-phase63-paper` completed with zero-trade warnings
  and no stale-manifest warning.

Focused verification:

```bash
python -m pytest tests/test_autowfo_live_signal_producer.py tests/test_autowfo_freqtrade_bridge.py tests/test_autowfo_paper_dryrun_reconcile.py tests/test_autowfo_evidence_warehouse.py -q
python -m compileall autowfo scripts/freqtrade_generic_signal_strategy.py
git diff --check
```

Result:

```text
44 passed
compileall completed successfully
git diff --check completed with no whitespace errors
```

## Follow-Up

- Continue AWF-349 until at least 7 daily summaries exist.
- Keep AWF-350 and AWF-351 blocked on sufficient paper evidence.
- Do not pivot to broad Challenger search unless canonical reconcile remains
  healthy and `strategy_no_signal_today` persists across multiple days.
