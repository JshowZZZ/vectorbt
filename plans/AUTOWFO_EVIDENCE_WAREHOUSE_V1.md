# AUTOWFO Evidence Warehouse V1

**Status**: Implementation-ready specification
**Depends on**: `plans/AUTOWFO_SURVIVALISM_FRAMEWORK.md`
**Frozen protocol**: `plans/protocols/evidence_warehouse_v1.json`
**First implementation target**: yes

---

## 1. Purpose

Evidence Warehouse V1 is the first foundation for the survivalism workstream.
It creates one queryable model for:

- strategy candidate identity
- backtest evidence
- Freqtrade replay evidence
- dry-run paper evidence
- future micro-live evidence
- execution-gap attribution
- cost observations
- Survival Gate policy and verdict history

It does not replace run-local artifacts. It indexes and normalizes evidence so
old and new strategy tests can be compared under one contract.

---

## 2. Design Principles

1. **Artifacts remain source evidence**
   - Existing JSON, CSV, SQLite, and parquet outputs remain the audit trail.
   - DuckDB is the analytics and evidence warehouse layer.

2. **Stable identities before migration**
   - Do not bulk-import old artifacts until `candidate_id`, `run_id`,
     `policy_id`, and `verdict_id` contracts are stable.

3. **Old and new strategies share one schema**
   - Existing promoted rows and future fresh tests must be comparable.

4. **Reality gaps are first-class**
   - Differences between backtest, replay, paper, and live behavior are stored
     as evidence, not narrative comments.

5. **Versioned policies, immutable verdicts**
   - Gate policies can change. Verdict records must keep policy identity and
     metric snapshots.

---

## 3. Identity Contract

| Identity | Purpose |
|---|---|
| `candidate_id` | Stable identity for one strategy candidate definition |
| `run_id` | Stable identity for one produced run or replay artifact |
| `policy_id` | Stable identity for one Survival Gate policy version |
| `verdict_id` | Stable identity for one gate evaluation event |
| `cost_profile_id` | Fee, slippage, funding, spread, and delay assumption set |
| `data_profile_id` | Data source, exchange, pair universe, timeframe, and date scope |

`candidate_id` must be deterministic from candidate definition fields whenever
possible. If a candidate is manually created, the manual source and rationale
must be recorded.

Candidate definition fields:

- strategy family
- indicator set
- parameter set
- timeframe
- market universe
- direction scope
- entry rule
- exit rule
- risk rule
- cost profile
- data profile
- source system

---

## 4. Logical Tables And Views

### 4.1 `strategy_candidates`

One row per candidate definition.

Required fields:

- `candidate_id`
- `candidate_version`
- `strategy_family`
- `indicator_set`
- `parameter_set`
- `timeframe`
- `market_universe`
- `direction_scope`
- `entry_rule`
- `exit_rule`
- `risk_rule`
- `cost_profile_id`
- `data_profile_id`
- `source_system`
- `created_utc`

### 4.2 `backtest_runs`

One row per AUTOWFO backtest or WFO run.

Required fields:

- `run_id`
- `candidate_id`
- `artifact_root`
- `engine`
- `run_mode`
- `timeframe`
- `data_start_utc`
- `data_end_utc`
- `created_utc`
- `config_hash`
- `data_fingerprint`

### 4.3 `backtest_metrics`

Metric snapshot for one candidate/run/scope.

Required fields:

- `run_id`
- `candidate_id`
- `scope`
- `trade_count`
- `win_rate`
- `expectancy_after_cost`
- `profit_factor`
- `max_drawdown_pct`
- `oos_return_pct`
- `stability_score`
- `symbol_support_count`
- `avg_symbol_trades`

### 4.4 `ft_replay_results`

Freqtrade backtest/replay cross-check result.

Required fields:

- `run_id`
- `candidate_id`
- `signal_bundle_id`
- `parity_bundle_id`
- `open_match_ratio`
- `exact_match_ratio`
- `trade_count_delta_pct`
- `verdict`
- `artifact_path`

### 4.5 `paper_trades`

Dry-run paper trade facts from Freqtrade.

Required fields:

- `paper_trade_id`
- `candidate_id`
- `freqtrade_trade_id`
- `pair`
- `direction`
- `opened_utc`
- `closed_utc`
- `open_rate`
- `close_rate`
- `profit_abs`
- `profit_ratio`
- `fee_abs`
- `funding_abs`
- `source_db_path`

### 4.6 `live_trades`

Future micro-live trade facts.

Required fields mirror `paper_trades` and add:

- `exchange_order_ids`
- `fill_status`
- `slippage_bps`
- `operator_session_id`

### 4.7 `execution_gap_events`

One row per observed gap between expected and actual behavior.

Required fields:

- `gap_id`
- `candidate_id`
- `expected_source`
- `actual_source`
- `pair`
- `direction`
- `event_time_utc`
- `gap_type`
- `severity`
- `expected_value`
- `actual_value`
- `attribution`
- `artifact_path`

Allowed `gap_type` values:

- `data_gap`
- `signal_gap`
- `adapter_gap`
- `execution_gap`
- `cost_gap`
- `regime_gap`

### 4.8 `cost_observations`

Observed or assumed cost profile records.

Required fields:

- `cost_profile_id`
- `source`
- `pair`
- `timeframe`
- `fee_bps`
- `slippage_bps`
- `spread_bps`
- `funding_rate`
- `delay_bars`
- `observed_utc`

### 4.9 `gate_policies`

Versioned Survival Gate policy records.

Required fields:

- `policy_id`
- `policy_name`
- `policy_version`
- `capital_stage`
- `scope`
- `created_utc`
- `policy_path`
- `rationale`

### 4.10 `gate_verdicts`

Immutable verdict events.

Required fields:

- `verdict_id`
- `candidate_id`
- `policy_id`
- `verdict`
- `metric_snapshot`
- `failed_rules`
- `warning_rules`
- `generated_utc`
- `artifact_path`

### 4.11 `promotion_decisions`

Human or operator decisions after evidence review.

Required fields:

- `decision_id`
- `candidate_id`
- `from_state`
- `to_state`
- `decision`
- `rationale`
- `evidence_paths`
- `operator`
- `decided_utc`

### 4.12 `benchmark_results`

Champion/Challenger and market baseline comparison rows.

Required fields:

- `benchmark_id`
- `candidate_id`
- `benchmark_type`
- `benchmark_candidate_id`
- `metric_snapshot`
- `comparison_result`
- `artifact_path`

---

## 5. Ingestion Priority

1. Existing Phase 61-62 Freqtrade replay and drift artifacts.
2. Phase 63 dry-run paper reconcile artifacts.
3. Existing AUTOWFO backtest and pilot analysis reports that have stable
   artifact paths and candidate identity.
4. New low-frequency large-cap strategy tests.
5. Future micro-live fills.

Do not ingest decision-critical legacy data blindly. If an artifact lacks enough
identity or provenance, classify it as `legacy_unresolved` and rerun only when
the result matters for a current decision.

---

## 6. Reality Gap Model

Evidence Warehouse V1 must support this loop:

```text
backtest expectation
-> Freqtrade replay result
-> dry-run paper actual
-> micro-live actual
-> gap attribution
-> gate verdict
-> next search/risk decision
```

Minimum attribution values:

- `data_gap`: source data differs
- `signal_gap`: signal columns differ
- `adapter_gap`: bridge or strategy wrapper changes semantics
- `execution_gap`: order/fill/position behavior differs
- `cost_gap`: fee, slippage, spread, or funding consumes edge
- `regime_gap`: strategy logic is intact but market regime changed

---

## 7. Implementation Boundaries

In scope for V1:

- protocol definition
- DuckDB logical views or tables
- read-only import from existing artifacts
- CLI command to build or validate the warehouse
- targeted tests for schema invariants and stable IDs

Out of scope for V1:

- replacing run-local artifacts
- full historical artifact migration
- risk engine enforcement
- micro-live execution
- control-panel rewrite

---

## 8. Validation

Required checks for the first implementation:

- JSON protocol validates as JSON.
- Warehouse builder can run without mutating source artifacts.
- Rebuild is idempotent on the same inputs.
- Candidate identity is stable across repeated imports.
- Missing optional legacy fields produce warnings, not silent bad rows.
- Gate verdict rows cannot be written without `policy_id`.

---

## 9. Agent Handoff

The first implementation agent should start with:

```text
Implement Evidence Warehouse V1 from:
- plans/AUTOWFO_EVIDENCE_WAREHOUSE_V1.md
- plans/protocols/evidence_warehouse_v1.json
```

Suggested first AWF slice:

```text
AWF-360: Add evidence warehouse protocol validator and candidate identity helper.
```

This slice should not import all legacy artifacts. It should freeze the minimal
contract and prove stable IDs plus protocol validation first.
