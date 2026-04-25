# AUTOWFO Architecture V2
**Status**: Approved by user 2026-02-27; refreshed to current Phase 63 reality and survivalism prework on 2026-04-25
**Role**: This document is the authoritative architecture spec for implementation AI.
**Architect**: Claude (planning only; implementation delegated to other AI)

---

## 1. Vision & Goals

### 1.1 What This System Is
A **strategy discovery and execution-validation platform** that systematically searches cross-asset, cross-timeframe signal strategies using vectorbt, then validates promotable candidates through a Freqtrade bridge. AUTOWFO owns the strategy truth source: indicators, signal rules, ranking, artifacts, and promotion evidence. Freqtrade owns second-engine replay, dry-run paper execution, exchange-runtime semantics, and eventual live execution.

The current operating goal is to find viable strategy-indicator combinations quickly without reopening the architecture: run bounded AUTOWFO searches, export frozen signal bundles, cross-check them through Freqtrade, collect paper/dry-run reconciliation evidence, and feed verdicts back into AUTOWFO planning.

The next architecture direction is the survivalism framework: AUTOWFO should not
only discover strategies, but also measure whether candidates survive costs,
execution gaps, paper/live drift, and operator risk limits. The core references
are `plans/AUTOWFO_SURVIVALISM_FRAMEWORK.md`,
`plans/AUTOWFO_EVIDENCE_WAREHOUSE_V1.md`,
`plans/AUTOWFO_SURVIVAL_GATE_POLICY.md`, and
`plans/AUTOWFO_STRATEGY_LIFECYCLE.md`.

Operators can use both:
- the packaged control panel for routine run/config/result workflows
- `python -m autowfo` CLI commands for reproducible batch, bridge, storage, drift, and report operations

### 1.2 What This System Is NOT
- Not an exchange order router inside AUTOWFO; execution stays in Freqtrade.
- Not a prediction model
- Not a portfolio optimizer
- Not a place for Freqtrade-native strategy logic to diverge from AUTOWFO signals.

### 1.3 Core Properties
1. **Automated**: Runs without human intervention; queue-driven
2. **Accumulative**: Every run adds evidence; nothing is wasted
3. **Data-driven**: Analytics layer reveals what works across experiments
4. **Extensible**: Adding a new indicator = adding one `.py` file
5. **Fresh-start safe**: Existing artifacts can be discarded and rerun from scratch
6. **Execution-aware**: candidate promotion is gated by Freqtrade parity, paper reconciliation, and drift artifacts
7. **Survival-first**: strategy promotion is gated by versioned Survival Gate policies, reality-gap evidence, cost observations, and operator sign-off before micro-live

---

## 2. Fundamental Concepts

### 2.1 Experiment
> An **Experiment** is a complete description of one testable idea.

An experiment specifies:
- **Trigger layer**: Which asset, timeframe, and indicators signal a potential entry
- **Action layer**: Which asset, timeframe, and conditions confirm the trade
- **Risk parameters**: Stop-loss, take-profit, max hold bars
- **WFO settings**: Train/test/step window sizes

Experiments are immutable after creation. Re-running the same experiment is encouraged to verify time-stability (Layer 2 accumulation).

### 2.2 Mode A ??Hypothesis-Driven
User defines a specific experiment (which indicators, which conditions). The system finds the best parameter values via Walk-Forward Optimization (WFO).

**Example**: "I want to test: if BTC 1h RSI drops below X, and ETH 4h is near Bollinger lower band, go long ETH."

### 2.3 Mode B ??Discovery-Driven (Pool Exploration)
User provides an indicator pool (e.g., [RSI, MACD, BB, Volume, EMA]). The system generates all indicator combinations C(N, 2..4) and tests each as a mini-experiment. Pruning.py limits the search space.

**Example**: "I want to discover which 2-3 indicators from this pool best predict ETH 4h moves."

### 2.4 Mode C ??Both (Default)
Both modes co-exist. User-defined experiments run as specified. Discovery runs explore the indicator pool in parallel. Analytics layer synthesizes findings from both.

### 2.4.1 Current Execution-Validation Loop
The active Phase 63 loop is:

```text
AUTOWFO search / frozen lane
  -> signal bundle / live signal manifest
  -> Freqtrade backtest cross-check or dry-run
  -> daily reconcile + execution drift report
  -> paper/search verdict memo
  -> next bounded AUTOWFO search or promotion decision
```

The bridge is a validation and execution adapter, not a second strategy source. Freqtrade strategies must consume AUTOWFO signal columns and preserve the corrected raw-signal / next-open execution contract.

### 2.4.2 Survivalism Evidence Loop

The next foundation layer turns the execution-validation loop into a survival
evidence loop:

```text
Champion/Challenger candidate
  -> AUTOWFO backtest evidence
  -> Freqtrade replay evidence
  -> dry-run paper actuals
  -> execution-gap attribution
  -> versioned Survival Gate verdict
  -> promote / observe / reject / halt
  -> future micro-live calibration
```

Key contracts:

- Candidate identity and evidence tables are defined by
  `plans/AUTOWFO_EVIDENCE_WAREHOUSE_V1.md`.
- Gate policy and immutable verdict history are defined by
  `plans/AUTOWFO_SURVIVAL_GATE_POLICY.md`.
- Lifecycle state transitions are defined by
  `plans/AUTOWFO_STRATEGY_LIFECYCLE.md`.

Risk-engine enforcement is deferred until the evidence warehouse can provide
stable candidate, cost, gap, and verdict records.

### 2.5 Cross-Asset Strategy Model
```
Trigger: [Asset A] + [Timeframe T1] + [Indicator conditions] ??SIGNAL
                              ??Action:  [Asset B] + [Timeframe T2] + [Confirm conditions] ??TRADE
```

- Trigger asset and Action asset can be the **same or different**
- Trigger timeframe (T1) and Action timeframe (T2) can be **different**
- Typical pattern: T1 ??T2 (higher-frequency trigger, lower-frequency action)
- Inverted pattern also supported (T1 > T2): trigger signal stays valid until next T1 candle close

**Cross-Timeframe Alignment Rule**:
> At each Action-timeframe (T2) candle close, check if any Trigger-timeframe (T1) signal fired within the preceding T2 window. If yes AND Action conditions are met ??generate trade signal.

### 2.6 Direction
Both LONG and SHORT are searched for every experiment. Results are tagged by direction. Analytics compares win rates across directions.

### 2.7 Condition Operators
Simple operators only (no ML, no complex multi-step logic):
- `below(threshold)` ??indicator value < threshold
- `above(threshold)` ??indicator value > threshold
- `crossover` ??indicator crosses above reference
- `crossunder` ??indicator crosses below reference
- `near_lower(pct)` ??value within pct% of lower band
- `near_upper(pct)` ??value within pct% of upper band
- `above_avg(multiplier)` ??value > multiplier ? N-period average
- `pct_move(pct, direction)` ??N-bar % change exceeds threshold

---

## 3. Experiment Configuration Schema

### 3.1 JSON Format (per experiment)
```json
{
  "experiment_id": "exp_btc1h_eth4h_rsi_bb_v1",
  "description": "BTC RSI trigger ??ETH Bollinger lower band entry",
  "version": 1,
  "created_utc": "2026-03-01T00:00:00Z",
  "mode": "hypothesis",

  "trigger": {
    "asset": "BTC/USDT",
    "timeframe": "1h",
    "indicators": ["RSI", "MACD"],
    "conditions": {
      "RSI": {
        "operator": "below",
        "param_name": "rsi_period",
        "param_values": [14, 21],
        "threshold_values": [25, 30, 35]
      },
      "MACD": {
        "operator": "crossunder",
        "fast_values": [12],
        "slow_values": [26],
        "signal_values": [9]
      }
    },
    "require_all": true
  },

  "action": {
    "asset": "ETH/USDT",
    "timeframe": "4h",
    "indicators": ["BB", "Volume"],
    "conditions": {
      "BB": {
        "operator": "near_lower",
        "period_values": [20],
        "std_values": [2.0],
        "pct_values": [0.02, 0.05]
      },
      "Volume": {
        "operator": "above_avg",
        "period_values": [20],
        "multiplier_values": [1.5, 2.0]
      }
    },
    "require_all": true,
    "direction": "both"
  },

  "risk": {
    "stoploss_pct_values": [-3, -5, -8],
    "take_profit_pct_values": [5, 10, 15],
    "max_hold_bars_values": [24, 48, 96]
  },

  "wf": {
    "train_days": 90,
    "test_days": 30,
    "step_days": 30
  }
}
```

### 3.2 Pool Config Format (Mode B)
```json
{
  "experiment_id": "pool_eth4h_discovery_v1",
  "mode": "discovery",
  "description": "Discover best 2-3 indicator combos for ETH 4h",
  "action": {
    "asset": "ETH/USDT",
    "timeframe": "4h",
    "direction": "both"
  },
  "indicator_pool": ["RSI", "MACD", "BB", "EMA", "Volume", "ATR"],
  "combo_sizes": [2, 3],
  "max_combos": 500,
  "wf": {
    "train_days": 90,
    "test_days": 30,
    "step_days": 30
  }
}
```

---

## 4. Storage Architecture

### 4.1 Two-Layer Design
| Layer | Technology | Purpose | When Written |
|-------|-----------|---------|--------------|
| Per-run results | SQLite (WAL mode) | Fast writes during WFO search | During run |
| Cross-run analytics | DuckDB | OLAP queries across all runs/experiments | After run finishes |

DuckDB can query SQLite files directly, so no ETL pipeline needed.

### 4.2 Directory Structure
```
artifacts/
|-- experiments/
|   |-- exp_btc1h_eth4h_rsi_bb_v1/
|   |   |-- config.json                    # immutable experiment config
|   |   `-- runs/
|   |       `-- 20260301_020000/
|   |           |-- results.db             # per-run SQLite combo results
|   |           `-- run_meta.json          # run metadata and schema version
|   `-- pool_eth4h_discovery_v1/
|       `-- runs/
|-- runs/<legacy-or-sweep-run-id>/          # trusted run-local evidence root
|-- ohlcv/                                  # cached exchange data
|-- live_signal_store/
|   |-- current_signals.parquet
|   |-- current_signals.csv
|   `-- live_manifest.json
|-- freqtrade_bridge/                       # frozen bundles and cross-check outputs
|-- paper_dryrun/                           # daily reconcile summaries and runtime logs
|-- reports/
|   `-- execution_drift_report.json
|-- analytics.duckdb                        # cross-experiment analytics store
|-- queue.json                              # experiment run queue
`-- scheduler.json                          # scheduler state
```

### 4.3 SQLite Schema (per run)
```sql
CREATE TABLE combo_results (
  combo_id TEXT PRIMARY KEY,
  experiment_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  direction TEXT NOT NULL,           -- 'long' / 'short'
  trigger_asset TEXT,
  action_asset TEXT NOT NULL,
  indicator_params TEXT NOT NULL,    -- JSON string
  condition_params TEXT NOT NULL,    -- JSON string
  risk_params TEXT NOT NULL,         -- JSON string
  oos_sharpe REAL,
  oos_win_rate REAL,
  oos_n_trades INTEGER,
  oos_total_return REAL,
  wf_score REAL,                     -- composite WFO score
  created_utc TEXT
);

CREATE INDEX idx_experiment ON combo_results(experiment_id);
CREATE INDEX idx_wf_score ON combo_results(wf_score DESC);
```

### 4.4 DuckDB Analytics Views
```sql
-- Cross-experiment indicator win rates
CREATE VIEW indicator_effectiveness AS
SELECT
  json_extract(indicator_params, '$.trigger_indicators') as trigger_indicators,
  json_extract(indicator_params, '$.action_indicators') as action_indicators,
  COUNT(*) as n_combos,
  AVG(oos_win_rate) as avg_win_rate,
  AVG(oos_sharpe) as avg_sharpe,
  COUNT(DISTINCT experiment_id) as n_experiments
FROM combo_results
WHERE oos_n_trades >= 10
GROUP BY 1, 2
ORDER BY avg_sharpe DESC;

-- Best combos across all time
CREATE VIEW all_time_best AS
SELECT * FROM combo_results
WHERE oos_n_trades >= 10
ORDER BY wf_score DESC
LIMIT 100;
```

---

## 5. Module Architecture

### 5.1 Current Module Map
```
autowfo/
|-- cli.py                         # command facade
|-- commands/                      # run/batch/plan/gate/cron/storage parser handlers
|-- control_panel/                 # packaged local UI and HTTP routes
|-- indicators/                    # indicator plugins
|-- conditions/                    # condition operator library
|-- experiment.py                  # experiment definition and validation
|-- experiment_runner.py           # experiment execution wrapper
|-- pool_discovery.py              # Mode-B indicator pool expansion
|-- discovery_loop.py              # scheduler/discovery tick orchestration
|-- engine_*.py                    # WFO search/runtime/report/finalize modules
|-- analytics.py                   # DuckDB cross-run analytics and paper feedback
|-- artifact_store.py              # per-experiment run store
|-- storage_ops.py                 # storage validation, migration, drift reports
|-- freqtrade_bridge.py            # frozen-lane signal bundle and FT cross-check helpers
|-- live_signal_producer.py        # rolling live signal store writer
|-- paper_dryrun_reconcile.py      # daily FT dry-run reconciliation
|-- freqtrade_mcp.py               # read-only local FT runtime inspection MCP
`-- signal_* / scheduler.py        # signal export, composition, scheduling

scripts/
|-- freqtrade_generic_signal_strategy.py
|-- start_live_signal_producer.ps1
|-- stop_live_signal_producer.ps1
|-- run_awf342b_freqtrade_mcp_smoke.py
`-- write_awf*_*.py                # reproducible one-off artifact writers
```

### 5.2 Current Ownership Boundaries
| Area | Owner Module(s) | Notes |
|---|---|---|
| Strategy search truth | `engine_*`, `search.py`, `ranking.py`, `metrics.py`, `strategy.py` | AUTOWFO remains the source of indicator and signal semantics |
| Experiment/discovery model | `experiment.py`, `pool_discovery.py`, `discovery_loop.py`, `scheduler.py` | Mode A and Mode B share artifact and analytics surfaces |
| Operator surfaces | `cli.py`, `commands/*`, `control_panel/*` | CLI is first-class for reproducible operations; UI is first-class for routine operators |
| FT bridge | `freqtrade_bridge.py`, `live_signal_producer.py`, `paper_dryrun_reconcile.py`, `scripts/freqtrade_generic_signal_strategy.py` | Freqtrade consumes AUTOWFO signals; it must not introduce independent strategy logic |
| Evidence storage | `artifact_store.py`, `artifacts.py`, `storage_ops.py`, `analytics.py` | Run-local artifacts, DuckDB analytics, protocol validation, and drift reports |

---

## 6. Indicator Plugin Interface

### 6.1 Contract
Every indicator plugin must implement:

```python
# scripts/autowfo/indicators/rsi.py

INDICATOR_ID = "RSI"
DISPLAY_NAME = "Relative Strength Index"
PARAMS = {
    "rsi_period": {"type": "int", "default": 14, "min": 5, "max": 50}
}
CONDITION_OPERATORS = ["below", "above", "crossover", "crossunder"]

def compute(ohlcv_df: pd.DataFrame, params: dict) -> pd.Series:
    """
    Returns a pd.Series (same index as ohlcv_df) with indicator values.
    """
    period = params.get("rsi_period", 14)
    # ... vectorbt or pandas-ta computation
    return rsi_series
```

### 6.2 Auto-Discovery
`indicators/__init__.py` scans the directory at import time:

```python
import importlib, pathlib
REGISTRY = {}

for path in pathlib.Path(__file__).parent.glob("*.py"):
    if path.name.startswith("_"):
        continue
    mod = importlib.import_module(f"scripts.autowfo.indicators.{path.stem}")
    REGISTRY[mod.INDICATOR_ID] = mod
```

Adding a new indicator requires only creating a new `.py` file ??no registration step.

### 6.3 Parameter Range Expansion
During experiment execution, `experiment_runner.py` calls `itertools.product()` over all `*_values` arrays in the experiment config to generate the full parameter grid. The grid is passed to `search.py` which handles seen-key dedup and pruning.

---

## 7. Signal Composition (Cross-Asset / Cross-Timeframe)

### 7.1 Signal Composer Responsibility
`signal_composer.py` takes:
- Trigger OHLCV (asset A, timeframe T1)
- Action OHLCV (asset B, timeframe T2)
- Experiment config (trigger conditions, action conditions)

And produces:
- `entry_long_signal`: boolean Series aligned to T2 index
- `entry_short_signal`: boolean Series aligned to T2 index
- `exit_signal`: boolean Series aligned to T2 index (from stop-loss / take-profit / max hold)

### 7.2 Cross-Timeframe Alignment Algorithm
```
For each T2 candle at time t:
  1. Find all T1 candles in window (t - T2_duration, t]
  2. Compute trigger indicator values for those T1 candles
  3. Apply trigger conditions ??get T1_signal (bool)
  4. If any T1 candle in window has T1_signal=True:
     ??Check action conditions on T2 candle at t
     ??If action conditions True: emit entry signal at t
```

For inverted timeframes (T1 > T2): T1 signal validity extends to the next T1 candle close.

### 7.3 vectorbt Integration
Signal Series are passed to vectorbt's `Portfolio.from_signals()`:
```python
import vectorbt as vbt

pf = vbt.Portfolio.from_signals(
    close=action_ohlcv["close"],
    entries=entry_long_signal,
    exits=exit_signal,
    short_entries=entry_short_signal,
    short_exits=exit_signal,
    init_cash=config["init_cash_usdt"],
    size=config["order_size_pct"],
    fees=config["slippage_bps"] / 10000,
)
```

---

## 8. Analytics Layer

### 8.1 Knowledge Accumulation Model
```
Layer 1: Parameter-level WFO     ??Best params for each combo
Layer 2: Time-stability           ??Same experiment rerun across time windows
Layer 3: Cross-experiment         ??Which indicators win across different experiments
Layer 4: Condition effectiveness  ??Which operators + thresholds work for which assets
Layer 5: Execution feedback       ??Freqtrade parity, paper dry-run reconcile, drift artifacts
```

### 8.2 Key Analytics Queries (exposed via control panel)
1. **Indicator leaderboard**: Which indicators appear most in top-performing combos?
2. **Asset pair matrix**: Which trigger?ction pairs have highest avg OOS Sharpe?
3. **Condition win rates**: For RSI "below", what threshold values work best?
4. **Time stability score**: How consistent is a combo's OOS performance across runs?
5. **Search coverage**: Which (asset, timeframe, indicator) spaces are untested?
6. **Execution drift**: Which frozen lanes diverge between AUTOWFO, Freqtrade backtest, and dry-run fills?
7. **Paper feedback**: Which promoted candidates remain viable after live-market dry-run costs and timing?

### 8.3 Analytics Computation Trigger
- After each run completes: `analytics.py::update_from_run(experiment_id, run_id)`
- On demand: user clicks "Refresh Analytics" in control panel
- Scheduled: nightly batch at 02:00 local time
- After bridge/reconcile work: `autowfo storage drift-report` rebuilds the execution drift artifact from frozen parity inputs

---

## 9. Control Panel ??Page Redesign

### 9.1 Tab Structure (new)
| Tab | Purpose |
|-----|---------|
| **Overview** | System status, queue depth, recent run summary, next-action suggestions |
| **Experiments** | NEW: Create/view/run experiments; Mode A hypothesis + Mode B pool config |
| **Config** | Global WFO params, data refresh, cost settings |
| **Analytics** | NEW: Indicator leaderboard, asset pair matrix, time stability scores |
| **Results** | Top combos (all-time + per-experiment) |
| **Coverage** | What's been tested, what gaps remain |
| **Batch** | Queue management, schedule editor |
| **Dashboard** | Cross-run report (existing) |

### 9.2 Experiments Tab
- **List view**: Table of all experiments with status (queued / running / done), last run UTC, best OOS Sharpe
- **Create experiment**: Form for hypothesis-driven (Mode A) or pool config (Mode B)
- **Experiment detail**: Per-experiment run history, parameter sensitivity charts, best combos
- **Quick actions**: Rerun, Clone, Add to queue

### 9.3 Analytics Tab
- Indicator effectiveness table (sortable by avg_sharpe, win_rate)
- Asset pair heatmap (trigger asset ? action asset ??avg OOS Sharpe)
- Condition parameter distribution charts
- Time stability: run-over-run correlation of top-10 combos

---

## 10. Development Phases

### Phase A ??Core Data Model & Plugin System
**Status**: Delivered (AWF-125~129)
**Goal**: Replace monolithic strategy schema with extensible plugin system.
**Deliverables**:
- `indicators/` directory with 5 built-in indicators (RSI, MACD, BB, EMA, Volume)
- `conditions/` directory with 4 operator modules
- `experiment.py`: Experiment definition, JSON schema validation, config loading
- Updated directory structure under `artifacts/experiments/`
- Tests: 100% coverage on indicator compute, condition operators, experiment validation

**Exit Criteria**: Can define an experiment via JSON, load it, expand the parameter grid, and verify signal computation for a simple same-asset case.

---

### Phase B ??Signal Composer (Cross-Asset / Cross-Timeframe)
**Status**: Delivered (AWF-130~133)
**Goal**: Multi-asset, multi-timeframe signal generation feeding vectorbt.
**Deliverables**:
- `signal_composer.py`: Cross-timeframe alignment algorithm, both-direction signal generation
- Updated `experiment_runner.py`: Uses signal composer instead of legacy evaluator
- Data layer: `data.py` extended to fetch and cache multiple assets + timeframes in Parquet
- Tests: Alignment correctness tests with synthetic OHLCV data, verified against manual calculation

**Exit Criteria**: Full experiment run (trigger BTC 1h RSI ??action ETH 4h BB) produces correct signals verified against hand-computed examples.

---

### Phase C ??Storage & Analytics Layer
**Status**: Delivered (AWF-134~137)
**Goal**: Two-layer storage (SQLite per run + DuckDB analytics).
**Deliverables**:
- Per-run SQLite output from `experiment_runner.py`
- `analytics.py`: DuckDB ingestion from SQLite, core views (indicator_effectiveness, all_time_best)
- Post-run hook in `engine_finalize.py` to trigger analytics update
- Tests: DuckDB query correctness, analytics update idempotency

**Exit Criteria**: After running 2+ experiments, analytics queries return consistent aggregated results. DuckDB can query SQLite files directly.

---

### Phase D ??Mode B (Discovery) + Scheduler
**Status**: Delivered (AWF-138~141)
**Goal**: Automated pool-based exploration and experiment queue management.
**Deliverables**:
- `scheduler.py`: Queue-based scheduler, priority ordering, nightly batch support
- Mode B pool expansion: C(N, 2..4) indicator combo generation with pruning
- Control panel batch integration: experiments added to queue from Experiments tab
- Tests: Scheduler queue ordering, pool expansion correctness, pruning integration

**Exit Criteria**: A pool config runs end-to-end without user intervention, discovers combos, stores results, updates analytics.

---

### Phase E ??Control Panel Redesign
**Status**: Delivered (AWF-142~145)
**Goal**: New Experiments tab, Analytics tab, updated Overview.
**Deliverables**:
- `control_panel_experiments.py`: Experiment CRUD endpoints
- `control_panel_analytics.py`: Analytics query endpoints
- Frontend: Experiments tab, Analytics tab (indicator leaderboard, asset pair heatmap)
- Refreshed Overview: experiment-aware next-action suggestions
- Tests: All new endpoints covered

**Exit Criteria**: User can create an experiment, add to queue, run it, view results, and see analytics ??all from control panel UI.

---

## 11. Post-V2 Stability Hardening

Phase 27~34 extended Architecture V2 from feature-complete to production-ready operation without changing core architecture direction:

- Phase 27: E2E lifecycle validation, scheduler graceful stop, discovery cold-start fallback, structured API error codes.
- Phase 28: E2E analytics readback fix and Analytics tab UI completion.
- Phase 29: Real-data smoke path, cron->scheduler integration, command-core decomposition, overview experiment awareness.
- Phase 30: Full AUTOWFO/control-panel regression closure, structural cleanup, and documentation freeze baseline.
- Phase 31: Cross-asset live validation, multi-round discovery burn-in, manual discovery-loop acceptance tooling.
- Phase 32: Discovery-to-experiment auto-mapping, unattended patrol loop, discovery/coverage observability surfaces.
- Phase 33: Multi-cycle patrol stability verification, append-only patrol telemetry (`patrol_log.ndjson`), overview patrol-history and analytics growth observability.
- Phase 34: Operational guardrails (patrol log rotation + cycle timeout), real-data patrol dry-run validation tooling, and CLI/runtime warning hygiene.
- Phase 35: Live-signal export bootstrap plus paper-trading write-back loop (`/paper/*` + leaderboard `paper_avg_pnl`) closed strategy-to-paper feedback chain.
- Phase 36: Paper feedback dedupe/idempotency and paper position state-machine guards, plus pandas/NumPy compatibility patches in vectorbt core (`indexing`, `checks`, `dir` behavior) to restore full regression stability.
- Phase 37: Environment lock finalized for vectorbt-core regression reliability (`pandas>=2,<3`, `numpy<2.4`, `numba<0.64`) and scheduler-mode patrol gained opt-in signal-scheduling automation.
- Phase 38: Notification dispatcher layer (webhook/Telegram optional), multi-strategy top-N paper scheduling, portfolio-level unrealized PnL read model, and scheduler retry/backoff anomaly signaling.

Resulting operational status:
- Discovery -> queue -> run -> analytics loop is unattended-capable under scheduler-mode patrol.
- Results and analytics read paths are closed and exposed through control panel APIs/UI.
- Stability/observability instrumentation exists for production operations and post-run diagnostics.

## 12. Steady State Declaration

Architecture V2 is now in steady-state maintenance after Phase 20~39 delivery.

Delivered capability set (non-exhaustive):
- Experiment model + plugin indicators + condition operators
- Cross-asset/cross-timeframe signal composition + experiment runner
- SQLite per-run + DuckDB analytics + control panel read paths
- Discovery/scheduler unattended loop with queue orchestration
- Paper-trading feedback loop (`/paper/*`) with multi-strategy top-N scheduling
- Operational observability: patrol logs/history, growth metrics, anomaly notifications
- Export surfaces: live signal config and self-contained research HTML report

Environment requirements (validated baseline):
- `pandas>=2.0,<3.0` (validated on 2.3.3)
- `numpy>=1.23,<2.4` (validated on 2.3.5)
- `numba>=0.60,<0.64` (validated on 0.63.1)

Maintenance guidance:
- Focus only on dependency compatibility, warning reduction, and reliability hardening.
- Keep API success contracts backward-compatible.
- No architecture-direction changes without a new explicitly approved phase.

## 13. Existing Code Reuse Map

### Keep As-Is (verified working, no changes needed)
- `split.py` ??WFO window splitting
- `metrics.py` ??OOS metric computation
- `ranking.py` ??combo ranking
- `pruning.py` ??search space pruning
- `engine_helpers.py` ??DEFAULT_CONFIG, seen-key logic (extend for new fields)
- `engine_runtime.py` ??per-combo vectorbt execution (adapt signal inputs)
- `engine_finalize.py` ??post-run finalization (add analytics hook)
- `engine_search.py` ??search loop (adapt for experiment-based combo grid)
- `search.py` ??seen-key dedup

### Keep With Extensions
- `data.py` ??Add multi-asset, multi-timeframe Parquet caching
- `engine_helpers.py` ??Add experiment config fields to DEFAULT_CONFIG

### Refactor Required
- `strategy_schema.py` ??decompose into `indicators/` + `conditions/`
- `strategy.py` ??per-indicator logic moves to `indicators/*.py`
- `evaluator.py` ??cross-asset version in `signal_composer.py`
- `artifacts.py` ??new directory structure
- `registry.py` ??new experiment model in `experiment.py`

### Legacy AWF-113~116 Status
AWF-113 (control_panel.py decomposition), AWF-114 (cli.py decomposition), AWF-115 (engine facade), and AWF-116 (sys.path cleanup) are **Delivered** in Phase 25/26 closure work.

---

## 14. Key Constraints & Guardrails

1. **No ML models**: All signal logic must be human-interpretable rule-based conditions
2. **No blocking I/O on UI thread**: All runs happen in background processes/threads
3. **Experiment immutability**: Config JSON is written once; reruns create new `runs/` subdirectory
4. **Analytics idempotency**: Running analytics update twice must produce identical results
5. **Operator interfaces are explicit**: use the control panel for routine operations and CLI commands for reproducible automation/audit work
6. **vectorbt as compute engine**: No replacement with other backtest frameworks
7. **Freqtrade is an execution adapter, not strategy ownership**: bridge code may read AUTOWFO signal artifacts, but strategy logic must stay in AUTOWFO

---

## 15. Open Questions (Deferred)

| Question | Status | Notes |
|----------|--------|-------|
| Freqtrade live activation | Deferred | Dry-run paper evidence and human verdict must pass before any live funds are considered |
| Real-time signal generation beyond current bar-based producer | Deferred | Current live producer is bar-based and tied to frozen lanes |
| Multi-exchange support | Deferred | Binance only initially |
| Experiment versioning (config changes) | Open | Increment `version` field in config JSON when semantics change |
| Max queue depth / rate limiting | Open | Scheduler design decision |

---

*Last updated: 2026-04-25*
*Next: Phase 63 paper-trading verdict plus bounded strategy-search expansion.*
