# AUTOWFO Phase 21 Implementation Spec
**Author**: Architect (Claude)
**Version**: 1.0 — 2026-02-27
**For**: Codex (implementation AI)

## How to use this document
1. Read `plans/ARCHITECT_PROTOCOL.md` first — understand your role and workflow
2. Find your assigned AWF block below
3. Read the full block before writing any code
4. After completion, copy `plans/reports/AWF-TEMPLATE.md` → `plans/reports/AWF-{ID}-report.md` and fill it in
5. Do NOT modify this spec file — if you find an error, report it as a BLOCKER

## Phase 20 → 21 Gate Status
Phase 20 (AWF-125~129) is **APPROVED**. All cross-phase interfaces verified:
- `indicators.REGISTRY[id].compute(ohlcv_df, params) -> pd.Series` ✓
- `conditions.apply(series, operator, params) -> pd.Series[bool]` ✓
- `Experiment.from_dict(config)`, `.expand_grid()`, `.validate()` ✓
- `ArtifactStore.init_run()`, `.init_results_db()` ✓

---

## AWF-130 — Signal Composer

**Phase**: 21 | **Priority**: P1 | **Status**: todo | **Owner**: Codex
**Arch Ref**: [AUTOWFO_ARCHITECTURE_V2.md §7](AUTOWFO_ARCHITECTURE_V2.md)
**Depends on**: AWF-125 (indicators), AWF-126 (conditions)
**Blocks**: AWF-131 (experiment_runner calls compose())
**⚠️ Cross-phase interface**: `compose(trigger_ohlcv, action_ohlcv, experiment, combo_params) -> SignalResult` — Phase 22+ depends on this contract. Architect must review before Phase 22 starts using it.

### Responsibility
`signal_composer.py` receives two OHLCV DataFrames (trigger asset + action asset, possibly different timeframes) and an experiment config with specific parameter values (one row from `expand_grid()`). It returns entry/exit boolean signals aligned to the **action timeframe** index.

### File to create
| File | Purpose |
|------|---------|
| `scripts/autowfo/signal_composer.py` | Cross-asset, cross-timeframe signal composition |
| `tests/test_autowfo_signal_composer.py` | Unit tests |

### Data Structures

```python
from dataclasses import dataclass
import pandas as pd

@dataclass
class SignalResult:
    """Output of signal composition — all Series share the action OHLCV index."""
    entry_long: pd.Series    # bool, aligned to action_ohlcv.index
    entry_short: pd.Series   # bool, aligned to action_ohlcv.index
    exit_long: pd.Series     # bool, aligned to action_ohlcv.index (optional — can be all-False if using SL/TP only)
    exit_short: pd.Series    # bool, aligned to action_ohlcv.index
```

### Core Function Signature

```python
def compose(
    trigger_ohlcv: pd.DataFrame,
    action_ohlcv: pd.DataFrame,
    experiment: "Experiment",
    combo_params: dict,
) -> SignalResult:
    """
    Generate entry/exit signals for one combo (one row from expand_grid()).

    Steps:
    1. Compute trigger indicators on trigger_ohlcv
    2. Apply trigger conditions → trigger_signal (bool Series, T1 index)
    3. Align trigger_signal to action timeframe (T2) via cross-timeframe rule
    4. Compute action indicators on action_ohlcv
    5. Apply action conditions → action_signal (bool Series, T2 index)
    6. Combined signal = trigger_aligned AND action_signal (if require_all)
    7. Split by direction from combo_params["direction"]
    """
```

### Cross-Timeframe Alignment Algorithm

Implement `_align_trigger_to_action(trigger_signal, trigger_index, action_index)`:

```
For each action candle at time t (T2 bar):
  1. Find T2 bar duration = action_index[1] - action_index[0]  (infer from index)
  2. Window start = t - T2_duration
  3. Window end = t (inclusive)
  4. Check if ANY trigger bar in (window_start, window_end] has trigger_signal == True
  5. If yes → aligned_signal[t] = True
  6. If no → aligned_signal[t] = False
```

Edge cases:
- If `trigger_ohlcv` and `action_ohlcv` have the **same** timeframe and **same** asset → skip alignment, use trigger_signal directly (reindex to action index)
- If trigger index is empty or all-NaN → return all-False
- First action bar always False (no preceding window)

### Condition Evaluation Helper

```python
def _evaluate_conditions(
    ohlcv: pd.DataFrame,
    indicators: list[str],
    conditions: dict,
    combo_params: dict,
    side: str,              # "trigger" or "action"
    require_all: bool,
) -> pd.Series:
    """
    For each indicator in `indicators`:
      1. Look up indicator in REGISTRY
      2. Extract relevant params from combo_params (keys prefixed with f"{side}_")
      3. Call indicator.compute(ohlcv, params) -> indicator_series
      4. Call conditions.apply(indicator_series, operator, condition_params) -> bool_series

    If require_all=True: AND all bool_series together
    If require_all=False: OR all bool_series together

    Returns: pd.Series[bool] aligned to ohlcv.index
    """
```

### Direction Handling
- `combo_params["direction"]` is either `"long"` or `"short"` (already split by `expand_grid()`)
- If `direction == "long"`: `entry_long = combined_signal`, `entry_short = all-False`
- If `direction == "short"`: `entry_short = combined_signal`, `entry_long = all-False`
- Exit signals: For Phase 21, set `exit_long` and `exit_short` to all-False. The experiment runner will use vectorbt's SL/TP/max-hold instead.

### Constraints
- Must NOT fetch or download any data — receives DataFrames as arguments
- Must NOT import from `engine_*.py` or `control_panel*.py`
- Must NOT write files
- Must handle NaN gracefully — NaN input bars → False signal output
- All returned Series must have dtype `bool` (not object, not float)

### Verification Commands
```bash
pytest tests/test_autowfo_signal_composer.py -v
python -c "from scripts.autowfo.signal_composer import compose, SignalResult; print('OK')"
```

### Exit Criteria
- [ ] `compose()` returns `SignalResult` with 4 bool Series, all same length as `action_ohlcv.index`
- [ ] Same-timeframe, same-asset case works (trigger_signal reindexed, no alignment needed)
- [ ] Cross-timeframe case: trigger 1h, action 4h → trigger signals within T2 window propagate correctly
- [ ] `require_all=True` ANDs conditions; `require_all=False` ORs them
- [ ] Direction "long" → `entry_short` all-False; "short" → `entry_long` all-False
- [ ] NaN indicator values → False signals (not NaN, not error)
- [ ] Exit signals are all-False (SL/TP delegated to runner)
- [ ] All tests pass: N passed, 0 failed

---

## AWF-131 — Experiment Runner

**Phase**: 21 | **Priority**: P1 | **Status**: todo | **Owner**: Codex
**Arch Ref**: [AUTOWFO_ARCHITECTURE_V2.md §6.3, §7.3](AUTOWFO_ARCHITECTURE_V2.md)
**Depends on**: AWF-127 (experiment.py), AWF-128 (artifact_store), AWF-130 (signal_composer)
**Blocks**: AWF-134 (per-run SQLite output), AWF-136 (post-run analytics hook)

### Responsibility
`experiment_runner.py` takes an `Experiment` and orchestrates the full run:
1. Expand parameter grid
2. For each combo: compose signals → run vectorbt WFO → collect OOS metrics
3. Store results in per-run SQLite via `ArtifactStore`

### Files to create
| File | Purpose |
|------|---------|
| `scripts/autowfo/experiment_runner.py` | Experiment execution orchestrator |
| `tests/test_autowfo_experiment_runner.py` | Unit tests (mocked data, no real OHLCV fetch) |

### Core Class

```python
class ExperimentRunner:
    def __init__(
        self,
        experiment: Experiment,
        trigger_ohlcv: pd.DataFrame,
        action_ohlcv: pd.DataFrame,
        artifact_store: ArtifactStore,
        run_id: str | None = None,       # auto-generate if None: datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    ):
        ...

    def run(self, progress_fn=None) -> RunResult:
        """
        Execute all combos in the experiment grid.

        For each combo_params in experiment.expand_grid():
          1. signals = compose(trigger_ohlcv, action_ohlcv, experiment, combo_params)
          2. wf_windows = split.generate_windows(action_ohlcv, wf_config)
          3. For each WFO window:
             - Run vectorbt backtest on train period → optimize
             - Run vectorbt backtest on test period → collect OOS metrics
          4. Aggregate OOS metrics across windows
          5. Insert combo result row into SQLite

        Returns: RunResult with summary stats
        """

    def _run_combo(self, combo_params: dict) -> dict:
        """Execute one combo, return result dict for SQLite insertion."""
        ...
```

### RunResult

```python
@dataclass
class RunResult:
    run_id: str
    experiment_id: str
    n_combos: int
    n_completed: int
    n_errors: int
    best_oos_sharpe: float | None
    duration_seconds: float
    run_dir: Path
```

### WFO Integration
Reuse existing `scripts/autowfo/split.py` for window generation. For each window:
- **Train period**: Run `vbt.Portfolio.from_signals()` on train data to evaluate parameter fitness
- **Test period**: Run on test data to get OOS metrics (Sharpe, win rate, n_trades, total return)

The WFO loop for Phase 21 is simplified:
- No in-sample optimization (that comes with existing engine integration later)
- Each combo_params is treated as a fixed parameter set
- WFO windows provide OOS robustness measurement: average OOS metrics across windows

### SQLite Result Insertion
Use `ArtifactStore.init_results_db()` to get connection, then:

```python
conn.execute("""
    INSERT INTO combo_results (
        combo_id, experiment_id, run_id, direction,
        trigger_asset, action_asset,
        indicator_params, condition_params, risk_params,
        oos_sharpe, oos_win_rate, oos_n_trades, oos_total_return,
        wf_score, created_utc
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
""", (...))
```

- `combo_id`: deterministic hash of `(experiment_id, combo_params)` — use `hashlib.sha256(json.dumps(combo_params, sort_keys=True)).hexdigest()[:16]`
- `indicator_params`: JSON string of trigger+action indicator params
- `condition_params`: JSON string of operator+condition params
- `risk_params`: JSON string of SL/TP/max_hold
- `wf_score`: simple composite = `0.5 * oos_sharpe_normalized + 0.3 * oos_win_rate + 0.2 * log(oos_n_trades+1)/5`
- `created_utc`: ISO 8601 string

### vectorbt Backtest
For each WFO test window:

```python
import vectorbt as vbt

pf = vbt.Portfolio.from_signals(
    close=action_ohlcv_window["close"],
    entries=signals.entry_long,
    exits=signals.exit_long,
    short_entries=signals.entry_short,
    short_exits=signals.exit_short,
    sl_stop=abs(combo_params["risk_stoploss_pct"]) / 100,
    tp_stop=combo_params["risk_take_profit_pct"] / 100,
    init_cash=10000,           # standardized for comparison
    fees=0.001,                # 10 bps default
)

# Extract OOS metrics
oos_sharpe = pf.sharpe_ratio()
oos_win_rate = pf.trades.win_rate() if pf.trades.count() > 0 else 0.0
oos_n_trades = pf.trades.count()
oos_total_return = pf.total_return()
```

### Constraints
- Must NOT fetch OHLCV data — receives DataFrames as constructor arguments
- Must NOT import from `control_panel*.py`
- Tests must mock OHLCV data (use `pd.DataFrame` with synthetic price series)
- Tests must use `tmp_path` for artifact storage
- Keep the runner stateless — all state flows through `ArtifactStore`

### Verification Commands
```bash
pytest tests/test_autowfo_experiment_runner.py -v
python -c "from scripts.autowfo.experiment_runner import ExperimentRunner, RunResult; print('OK')"
```

### Exit Criteria
- [ ] `ExperimentRunner.run()` returns `RunResult` with correct counts
- [ ] SQLite `combo_results` table contains one row per combo after run
- [ ] `combo_id` is deterministic (same params → same id)
- [ ] `wf_score` is computed per spec formula
- [ ] `run_meta.json` is written with run summary
- [ ] Progress callback is called during execution (if provided)
- [ ] Errors in individual combos don't crash the entire run (logged, counted in `n_errors`)
- [ ] Tests use synthetic OHLCV data + `tmp_path` only
- [ ] All tests pass: N passed, 0 failed

---

## AWF-132 — Multi-Asset Data Layer

**Phase**: 21 | **Priority**: P1 | **Status**: todo | **Owner**: Codex
**Arch Ref**: [AUTOWFO_ARCHITECTURE_V2.md §4.2](AUTOWFO_ARCHITECTURE_V2.md)
**Depends on**: Existing `scripts/autowfo/data.py`
**Blocks**: AWF-131 (runner needs multi-asset OHLCV)

### Responsibility
Extend the existing `data.py` with multi-asset Parquet cache support. The experiment runner needs to load OHLCV for **two different assets at two different timeframes** simultaneously.

### Files to create / modify
| File | Purpose |
|------|---------|
| `scripts/autowfo/data_multi.py` | Multi-asset OHLCV loader with Parquet cache |
| `tests/test_autowfo_data_multi.py` | Unit tests (offline, no real API calls) |

**Do NOT modify** existing `scripts/autowfo/data.py` — create a new module to avoid breaking existing functionality.

### Core Functions

```python
def load_ohlcv(
    asset: str,
    timeframe: str,
    start_date: str,          # ISO format "2025-01-01"
    end_date: str | None = None,
    exchange: str = "binance",
    cache_dir: str | Path = "artifacts/ohlcv",
) -> pd.DataFrame:
    """
    Load OHLCV data for a single asset+timeframe.

    1. Check Parquet cache: {cache_dir}/{exchange}_{asset_safe}_{timeframe}.parquet
    2. If cache hit and covers date range → load from Parquet, filter to range
    3. If cache miss or insufficient range → fetch via ccxt (or vectorbt.download)
       → save full result to Parquet cache → return filtered range
    4. Normalize index: DatetimeIndex, no duplicates, sorted

    Returns: pd.DataFrame with columns [open, high, low, close, volume]
             and DatetimeIndex (timezone-naive UTC)
    """

def load_experiment_data(
    experiment: "Experiment",
    start_date: str,
    end_date: str | None = None,
    cache_dir: str | Path = "artifacts/ohlcv",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Convenience: load both trigger and action OHLCV for an experiment.

    Returns: (trigger_ohlcv, action_ohlcv)
    """

def cache_info(cache_dir: str | Path = "artifacts/ohlcv") -> list[dict]:
    """
    List cached OHLCV files with metadata (asset, timeframe, date range, file size).
    Used by control panel for cache management UI.
    """
```

### Parquet Cache File Naming
```
artifacts/ohlcv/binance_BTC-USDT_1h.parquet
artifacts/ohlcv/binance_ETH-USDT_4h.parquet
```
- Asset name: replace `/` with `-` (e.g., `BTC/USDT` → `BTC-USDT`)
- All lowercase for the filename

### Constraints
- Parquet engine: try `pyarrow` first, fall back to `fastparquet`, fail with clear error if neither available
- Do NOT use `vectorbt.download` if `ccxt` is available (prefer direct ccxt for control over pagination)
- Tests must NOT make real API calls — mock the fetch function and test cache hit/miss/merge logic
- Tests must use `tmp_path` for cache_dir
- `load_ohlcv()` must be safe for concurrent calls (file locking or atomic write pattern)

### Verification Commands
```bash
pytest tests/test_autowfo_data_multi.py -v
python -c "from scripts.autowfo.data_multi import load_ohlcv, load_experiment_data, cache_info; print('OK')"
```

### Exit Criteria
- [ ] `load_ohlcv()` returns DataFrame with correct columns and DatetimeIndex
- [ ] Cache hit: loads from Parquet without API call
- [ ] Cache miss: fetches data (mocked in tests), saves Parquet, returns DataFrame
- [ ] `load_experiment_data()` returns `(trigger_ohlcv, action_ohlcv)` tuple
- [ ] `cache_info()` lists cached files with metadata
- [ ] Asset name normalization: `BTC/USDT` → `btc-usdt` in filename
- [ ] Tests use `tmp_path` and mocked fetch — no real API calls
- [ ] All tests pass: N passed, 0 failed

---

## AWF-133 — Dual-Direction Signal Tests

**Phase**: 21 | **Priority**: P1 | **Status**: todo | **Owner**: Codex
**Arch Ref**: [AUTOWFO_ARCHITECTURE_V2.md §2.6](AUTOWFO_ARCHITECTURE_V2.md)
**Depends on**: AWF-130 (signal_composer), AWF-131 (experiment_runner)

### Responsibility
Integration tests that verify the full pipeline: experiment config → expand_grid → signal_composer → experiment_runner, specifically for dual-direction (long + short) scenarios.

### File to create
| File | Purpose |
|------|---------|
| `tests/test_autowfo_dual_direction.py` | Integration tests for long/short signal path |

### Test Scenarios

1. **Both directions produce results**: Given a `direction="both"` experiment, verify that `expand_grid()` produces both long and short combos, and the runner stores both in SQLite with correct `direction` column values.

2. **Long-only experiment**: Given `direction="long"`, verify no short entries are generated and all SQLite rows have `direction="long"`.

3. **Short-only experiment**: Same but for short.

4. **Signal asymmetry**: Create synthetic OHLCV where trigger fires on specific bars. Verify that `entry_long` and `entry_short` are mutually exclusive (one direction per combo).

5. **Cross-timeframe + dual direction**: Trigger on 1h, action on 4h, direction="both". Verify alignment works correctly for both directions.

6. **Empty signals**: If no trigger fires during entire period, all entries should be False, and the combo should still be stored (with `oos_n_trades=0`).

### Synthetic Data Helper
Create a shared test helper (can be in the test file itself):

```python
def _make_ohlcv(n_bars=100, freq="1h", trend="flat"):
    """Generate synthetic OHLCV DataFrame for testing."""
    index = pd.date_range("2025-01-01", periods=n_bars, freq=freq)
    if trend == "flat":
        close = pd.Series(100.0, index=index)
    elif trend == "up":
        close = pd.Series(100.0 + np.arange(n_bars) * 0.5, index=index)
    elif trend == "down":
        close = pd.Series(100.0 - np.arange(n_bars) * 0.3, index=index)
    # ... build open/high/low/volume from close
    return pd.DataFrame({
        "open": close * 0.999,
        "high": close * 1.005,
        "low": close * 0.995,
        "close": close,
        "volume": pd.Series(1000.0, index=index),
    })
```

### Constraints
- All tests must use synthetic data + `tmp_path`
- Must NOT import from `control_panel*.py` or `engine_*.py`
- Must test the integrated pipeline (signal_composer + experiment_runner), not individual units

### Verification Commands
```bash
pytest tests/test_autowfo_dual_direction.py -v
```

### Exit Criteria
- [ ] Both-direction experiment produces long AND short rows in SQLite
- [ ] Long-only experiment produces only long rows
- [ ] Short-only experiment produces only short rows
- [ ] Cross-timeframe alignment works with both directions
- [ ] Zero-signal combo stored correctly (oos_n_trades=0)
- [ ] All tests pass: N passed, 0 failed

---

## Phase 22–24

> Specs will be written by Architect after Phase 21 gate review.
> AWF-134~145 are pending Phase 21 completion.
