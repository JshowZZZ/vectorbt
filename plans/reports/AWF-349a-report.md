# AWF-349a Paper Evidence Collector Report

## Header

| Field | Value |
|-------|-------|
| AWF ID | AWF-349a |
| Title | Phase 63 one-click paper evidence collector |
| Phase | 63 paper trading exploitation |
| Codex completion date | 2026-04-29 |
| Spec reference | `plans/AUTOWFO_TODO.md`, `plans/AUTOWFO_PHASE63_PLAN.md` |

## Scope

This slice automates daily evidence collection for AWF-349 without producing a
paper Survival Gate verdict and without changing strategy logic, Risk Engine
behavior, live activation, or control-panel APIs.

Implemented behavior:

- New CLI: `python -m autowfo bridge-paper-evidence-day`.
- New bounded API: `autowfo.paper_evidence_day.collect_phase63_paper_evidence_day`.
- Daily collector checks live manifest lane/freshness, refreshes the live signal
  store when needed, runs dry-run reconcile, imports Phase 63 paper evidence into
  the Evidence Warehouse, and writes a health JSON artifact.
- Daily health output includes `day_quality`, `zero_trade_reason`,
  `zero_signal_explainability`, runtime process health, warehouse warnings, and
  aggregate paper survival blockers.
- `build_phase63_paper_survival_report` now exposes valid evidence day counts and
  lane/date filters so old stable-rank paper summaries do not permanently block
  the canonical rank 1 aggregate.

## Runtime Smoke

Command:

```bash
python -m autowfo bridge-paper-evidence-day --manifest-json artifacts/freqtrade_bridge/20260411_microcohort_dropsol_main_canonical_r1/signal_manifest.json --freqtrade-config E:/Project/freqtrade/user_data/config_autowfo_dryrun.json --date 2026-04-28 --min-date 2026-04-28 --cwd . --json
```

Observed result:

- `ok`: `true`
- manifest: `fresh`, `selection=canonical_gate_passed`, `rank=1`
- live signal producer: running
- Freqtrade dry-run: running
- reconcile: `opened_trades_day=0`, `closed_trades_day=0`
- day quality: `zero_trade_day`
- zero-trade reason: `strategy_no_signal_today`
- aggregate filter: `expected_selection=canonical_gate_passed`, `expected_rank=1`, `min_date_utc=2026-04-28`
- aggregate count: `source_summary_count=5`, `daily_summary_count=1`, `valid_evidence_day_count=0`
- verdict: not allowed

## Validation

TDD red evidence:

```text
6 failed, 73 deselected
2 failed, 26 deselected
```

Focused green evidence:

```bash
python -m pytest tests/test_autowfo_paper_evidence_day.py tests/test_autowfo_evidence_warehouse.py tests/test_autowfo_cli.py -q -k "paper_evidence_day or phase63_paper or survival_gate or gate_verdict or quality_reasons or minimum_quality_is_met"
```

Result:

```text
21 passed, 86 deselected
```

Final verification:

```bash
python -m pytest tests/test_autowfo_paper_evidence_day.py tests/test_autowfo_evidence_warehouse.py tests/test_autowfo_cli.py tests/test_autowfo_paper_dryrun_reconcile.py -q
python -m compileall autowfo scripts/freqtrade_generic_signal_strategy.py
git diff --check
```

Result:

```text
113 passed
compileall completed successfully
git diff --check completed with no whitespace errors
```

## Follow-Up

- Continue AWF-349 by running the collector once per UTC evidence day.
- Keep using `--min-date 2026-04-28` for the canonical post-recovery aggregate.
- Do not treat zero-trade days as paper pass evidence.
- If `strategy_no_signal_today` persists across multiple healthy days, prioritize
  zero-signal explainability depth and AWF-356 canonical 360d validation before
  broad Challenger search.
