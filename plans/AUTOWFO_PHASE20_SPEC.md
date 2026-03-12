# AUTOWFO Phase 20 Implementation Spec
**Author**: Architect (Claude)
**Version**: 1.0 — 2026-02-27
**For**: Codex (implementation AI)

## How to use this document
1. Read `plans/ARCHITECT_PROTOCOL.md` first — understand your role and workflow
2. Find your assigned AWF block below
3. Read the full block before writing any code
4. After completion, copy `plans/reports/AWF-TEMPLATE.md` → `plans/reports/AWF-{ID}-report.md` and fill it in
5. Do NOT modify this spec file — if you find an error, report it as a BLOCKER

---

## AWF-125 — Indicator Plugin System

**Phase**: 20 | **Priority**: P1 | **Status**: todo | **Owner**: Codex
**Arch Ref**: [AUTOWFO_ARCHITECTURE_V2.md §6](AUTOWFO_ARCHITECTURE_V2.md)
**Depends on**: — (first AWF in Phase 20, no dependencies)
**Blocks**: AWF-127 (experiment.py reads PARAMS), AWF-130 (signal_composer calls compute())
**⚠️ Cross-phase interface**: `compute(ohlcv_df, params) -> pd.Series` — Phase 21 (AWF-130, AWF-131) depends on this contract. Architect must review before Phase 21 starts using it.

### Files to create
| File | Purpose |
|------|---------|
| `scripts/autowfo/indicators/__init__.py` | Auto-discovery: glob `*.py` in this dir, import each, build `REGISTRY` dict keyed by `INDICATOR_ID` |
| `scripts/autowfo/indicators/rsi.py` | RSI indicator plugin |
| `scripts/autowfo/indicators/macd.py` | MACD indicator plugin |
| `scripts/autowfo/indicators/bb.py` | Bollinger Bands indicator plugin |
| `scripts/autowfo/indicators/ema.py` | EMA indicator plugin |
| `scripts/autowfo/indicators/volume.py` | Volume-based indicator plugin |
| `tests/test_autowfo_indicators.py` | Unit tests |

### Files NOT to modify
- `scripts/autowfo/strategy.py` — existing indicator logic stays untouched
- `scripts/autowfo/strategy_schema.py` — not replaced yet
- Any `engine_*.py` file
- Any `control_panel*.py` file

### Plugin contract (every plugin must implement exactly this)
```python
# Required module-level attributes
INDICATOR_ID: str          # e.g., "RSI" — used as REGISTRY key
DISPLAY_NAME: str          # e.g., "Relative Strength Index"
PARAMS: dict               # name → {"type": "int"|"float", "default": X, "min": X, "max": X}
CONDITION_OPERATORS: list  # subset of: ["below","above","crossover","crossunder",
                           #   "near_lower","near_upper","above_avg","pct_move"]

def compute(ohlcv_df: pd.DataFrame, params: dict) -> pd.Series:
    """
    Args:
        ohlcv_df: DataFrame with columns ["open","high","low","close","volume"],
                  DatetimeIndex, no NaNs guaranteed at head.
        params: dict matching keys in PARAMS (pre-validated by caller).
    Returns:
        pd.Series with same DatetimeIndex as ohlcv_df.
        Leading NaNs are acceptable (e.g., RSI needs warmup period).
        Must NOT modify ohlcv_df in place.
    """
```

### Auto-discovery implementation (`__init__.py`)
```python
import importlib, pathlib, logging

REGISTRY: dict = {}
_logger = logging.getLogger(__name__)

def _discover():
    pkg_dir = pathlib.Path(__file__).parent
    for path in sorted(pkg_dir.glob("*.py")):
        if path.name.startswith("_"):
            continue
        module_name = f"scripts.autowfo.indicators.{path.stem}"
        try:
            mod = importlib.import_module(module_name)
            indicator_id = getattr(mod, "INDICATOR_ID", None)
            if indicator_id:
                REGISTRY[indicator_id] = mod
        except Exception as e:
            _logger.warning(f"Failed to load indicator plugin {path.name}: {e}")

_discover()
```

### Indicator implementations (guidance per plugin)

**RSI** (`rsi.py`):
- PARAMS: `rsi_period` (int, default=14, min=5, max=50)
- compute: use `pandas_ta` or manual Wilder smoothing; return RSI values 0–100
- CONDITION_OPERATORS: `["below", "above", "crossover", "crossunder"]`

**MACD** (`macd.py`):
- PARAMS: `macd_fast` (int, 12, 5, 30), `macd_slow` (int, 26, 15, 60), `macd_signal` (int, 9, 3, 20)
- compute: return MACD line (not histogram, not signal line)
- CONDITION_OPERATORS: `["above", "below", "crossover", "crossunder"]`

**BB** (`bb.py`):
- PARAMS: `bb_period` (int, 20, 5, 50), `bb_std` (float, 2.0, 1.0, 3.0)
- compute: return `(close - lower_band) / (upper_band - lower_band)` — BB position 0..1
- CONDITION_OPERATORS: `["below", "above", "near_lower", "near_upper"]`

**EMA** (`ema.py`):
- PARAMS: `ema_period` (int, 20, 5, 200)
- compute: return `close / ema - 1` — percentage above/below EMA
- CONDITION_OPERATORS: `["above", "below", "crossover", "crossunder"]`

**Volume** (`volume.py`):
- PARAMS: `vol_period` (int, 20, 5, 60)
- compute: return `volume / volume.rolling(vol_period).mean()` — volume ratio vs N-period average
- CONDITION_OPERATORS: `["above_avg"]`

### Constraints
- Each plugin must be independently importable (`python -c "from scripts.autowfo.indicators.rsi import compute"`)
- Do NOT import from `strategy.py` or `strategy_schema.py` inside plugins
- Use `pandas_ta` if available (it's already a project dependency); fallback to manual pandas math
- Do not add `pandas_ta` if not already installed — check `pyproject.toml` first

### Verification command
```bash
pytest tests/test_autowfo_indicators.py -v
```

### Exit criteria (ALL must pass before submitting report)
- [ ] `from scripts.autowfo.indicators import REGISTRY` succeeds; `len(REGISTRY) == 5`
- [ ] `REGISTRY["RSI"]`, `["MACD"]`, `["BB"]`, `["EMA"]`, `["Volume"]` all accessible
- [ ] Adding a 6th `.py` file with valid `INDICATOR_ID` auto-appears in REGISTRY (test this)
- [ ] Each `compute()` returns `pd.Series` with index identical to input `ohlcv_df.index`
- [ ] Each `compute()` does not modify input `ohlcv_df` in place (test with `.copy()` comparison)
- [ ] Plugin with syntax error in its file is skipped with warning, REGISTRY still loads remaining plugins
- [ ] All tests: N passed, 0 failed

### Report file
`plans/reports/AWF-125-report.md`

---

## AWF-126 — Condition Operator Library

**Phase**: 20 | **Priority**: P1 | **Status**: todo | **Owner**: Codex
**Arch Ref**: [AUTOWFO_ARCHITECTURE_V2.md §2.7](AUTOWFO_ARCHITECTURE_V2.md)
**Depends on**: AWF-125 (uses indicator Series as input)
**Blocks**: AWF-127 (experiment.py validates operator names), AWF-130 (signal_composer applies operators)
**⚠️ Cross-phase interface**: `apply(series, operator, params) -> pd.Series[bool]` — Phase 21 depends on this. Architect review required.

### Files to create
| File | Purpose |
|------|---------|
| `scripts/autowfo/conditions/__init__.py` | Exports `OPERATOR_REGISTRY` and `apply()` dispatcher |
| `scripts/autowfo/conditions/threshold.py` | `below`, `above` operators |
| `scripts/autowfo/conditions/crossover.py` | `crossover`, `crossunder` operators |
| `scripts/autowfo/conditions/band.py` | `near_lower`, `near_upper` operators |
| `scripts/autowfo/conditions/momentum.py` | `above_avg`, `pct_move` operators |
| `tests/test_autowfo_conditions.py` | Unit tests |

### Files NOT to modify
- All existing `scripts/autowfo/` files
- All `control_panel*.py` files

### Operator contract
```python
# Each operator is a function:
def operator_name(series: pd.Series, params: dict) -> pd.Series:
    """
    Args:
        series: indicator values (output of compute()), same DatetimeIndex
        params: operator-specific parameters (pre-validated by caller)
    Returns:
        pd.Series[bool] with same DatetimeIndex as input.
        True = condition is met at that bar.
        NaN positions in input → False in output (not NaN).
    """
```

### `__init__.py` dispatcher
```python
from scripts.autowfo.conditions import threshold, crossover, band, momentum

OPERATOR_REGISTRY = {
    "below":      threshold.below,
    "above":      threshold.above,
    "crossover":  crossover.crossover,
    "crossunder": crossover.crossunder,
    "near_lower": band.near_lower,
    "near_upper": band.near_upper,
    "above_avg":  momentum.above_avg,
    "pct_move":   momentum.pct_move,
}

def apply(series: pd.Series, operator: str, params: dict) -> pd.Series:
    """Main entrypoint for condition evaluation."""
    if operator not in OPERATOR_REGISTRY:
        raise ValueError(f"Unknown operator: {operator!r}. Available: {list(OPERATOR_REGISTRY)}")
    return OPERATOR_REGISTRY[operator](series, params)
```

### Operator specs

**`below(series, params)`**:
- params: `{"threshold": float}`
- returns: `series < params["threshold"]` (NaN → False)

**`above(series, params)`**:
- params: `{"threshold": float}`
- returns: `series > params["threshold"]`

**`crossover(series, params)`**:
- params: `{"threshold": float}` OR `{"reference": pd.Series}`
- returns: True where series crosses above threshold (previous bar below, current bar above)
- Edge: first bar always False

**`crossunder(series, params)`**:
- params: `{"threshold": float}` OR `{"reference": pd.Series}`
- returns: True where series crosses below threshold

**`near_lower(series, params)`**:
- params: `{"pct": float}` — e.g., 0.05 means within 5% of range bottom
- Input series is expected to be BB position (0..1 from AWF-125 bb.py)
- returns: `series <= params["pct"]`

**`near_upper(series, params)`**:
- params: `{"pct": float}`
- returns: `series >= (1 - params["pct"])`

**`above_avg(series, params)`**:
- params: `{"multiplier": float}` — e.g., 1.5
- Input series expected to be volume ratio (from AWF-125 volume.py)
- returns: `series >= params["multiplier"]`

**`pct_move(series, params)`**:
- params: `{"pct": float, "direction": "up"|"down", "lookback": int}`
- returns: True where `(series - series.shift(lookback)) / series.shift(lookback)` exceeds pct in specified direction

### Constraints
- NaN in input series MUST produce False (not NaN) in output — this is critical for signal alignment
- No external dependencies beyond `pandas` and `numpy`
- Each operator independently testable without importing other operators

### Verification command
```bash
pytest tests/test_autowfo_conditions.py -v
```

### Exit criteria
- [ ] `from scripts.autowfo.conditions import apply, OPERATOR_REGISTRY` succeeds
- [ ] All 8 operators present in `OPERATOR_REGISTRY`
- [ ] `apply(series, "below", {"threshold": 30})` returns `pd.Series[bool]`
- [ ] NaN in input → False in output (not NaN, not propagated NaN)
- [ ] `crossover` / `crossunder` first bar always False
- [ ] Unknown operator raises `ValueError` with helpful message
- [ ] All tests: N passed, 0 failed

### Report file
`plans/reports/AWF-126-report.md`

---

## AWF-127 — Experiment Definition Model

**Phase**: 20 | **Priority**: P1 | **Status**: todo | **Owner**: Codex
**Arch Ref**: [AUTOWFO_ARCHITECTURE_V2.md §3](AUTOWFO_ARCHITECTURE_V2.md)
**Depends on**: AWF-125 (validates indicator IDs against REGISTRY), AWF-126 (validates operator names)
**Blocks**: AWF-129 (control_panel_experiments.py uses Experiment class), AWF-131 (experiment_runner.py uses Experiment)

### Files to create
| File | Purpose |
|------|---------|
| `scripts/autowfo/experiment.py` | Experiment class: load, validate, expand grid |
| `tests/test_autowfo_experiment.py` | Unit tests |

### Files NOT to modify
- All existing files

### `Experiment` class spec
```python
class Experiment:
    def __init__(self, config: dict):
        """
        Args:
            config: dict matching Architecture V2 §3.1 JSON schema
        Raises:
            ValueError: on invalid config (with descriptive message)
        """

    @classmethod
    def from_json(cls, path: pathlib.Path) -> "Experiment":
        """Load from config.json file."""

    @classmethod
    def from_dict(cls, config: dict) -> "Experiment":
        """Create from dict (same as __init__ but classmethod for clarity)."""

    def save(self, path: pathlib.Path) -> None:
        """Write config to path as JSON (creates parent dirs)."""

    def expand_grid(self) -> list[dict]:
        """
        Returns all parameter combinations as list of dicts.
        Each dict has flat keys: trigger_*, action_*, risk_*, wf_*.
        Uses itertools.product over all *_values arrays.
        Empty *_values → uses default value only (single point, not skipped).
        """

    def validate(self) -> None:
        """Raises ValueError with specific message if config is invalid."""

    @property
    def experiment_id(self) -> str: ...

    @property
    def artifact_dir(self) -> pathlib.Path:
        """Returns artifacts/experiments/{experiment_id}/"""
```

### Validation rules (implement all)
1. `experiment_id` must be non-empty string, alphanumeric + underscores only
2. `trigger.asset` and `action.asset` must be non-empty strings
3. `trigger.timeframe` and `action.timeframe` must be non-empty strings
4. Every indicator name in `trigger.indicators` must exist in `REGISTRY` (from AWF-125)
5. Every `operator` value in `trigger.conditions` and `action.conditions` must be in `OPERATOR_REGISTRY` (from AWF-126)
6. `wf.train_days >= 7`, `wf.test_days >= 1`, `wf.step_days >= wf.test_days`
7. `risk.stoploss_pct_values` must all be negative
8. `risk.take_profit_pct_values` must all be positive
9. `mode` must be `"hypothesis"` or `"discovery"`

### Grid expansion example
```python
# Given:
# trigger RSI: rsi_period=[14,21], threshold=[25,30]
# action BB: bb_period=[20], pct=[0.02,0.05]
# risk: stoploss=[-3,-5], take_profit=[5], max_hold=[24]
# → expand_grid() returns 2×2×1×2×2×1 = 16 combo dicts

# Each combo dict looks like:
{
    "trigger_indicator": "RSI",
    "trigger_rsi_period": 14,
    "trigger_threshold": 25,
    "action_indicator": "BB",
    "action_bb_period": 20,
    "action_pct": 0.02,
    "direction": "long",  # one entry per direction if direction="both"
    "risk_stoploss_pct": -3,
    "risk_take_profit_pct": 5,
    "risk_max_hold_bars": 24,
}
```

Note: if `action.direction == "both"`, each parameter combination produces TWO grid entries (long + short).

### Artifact directory
```python
# experiment.artifact_dir should resolve to:
pathlib.Path("artifacts") / "experiments" / self.experiment_id
# Do NOT use ROOT or any global path variable — use relative path from CWD
```

### Constraints
- `expand_grid()` must be deterministic (same config → same order always)
- Do NOT validate against live OHLCV data (no API calls in this module)
- Use only stdlib + pandas (no new dependencies)

### Verification command
```bash
pytest tests/test_autowfo_experiment.py -v
```

### Exit criteria
- [ ] `Experiment.from_dict(valid_config)` succeeds without exception
- [ ] `experiment.expand_grid()` returns correct count (product of all `*_values` lengths × 2 for direction="both")
- [ ] Grid order is deterministic (run twice, same order)
- [ ] All 9 validation rules raise `ValueError` with descriptive message
- [ ] `direction="both"` produces long AND short entries
- [ ] `experiment.save(path)` writes valid JSON that can be round-tripped with `from_json()`
- [ ] All tests: N passed, 0 failed

### Report file
`plans/reports/AWF-127-report.md`

---

## AWF-128 — Artifact Directory Structure

**Phase**: 20 | **Priority**: P1 | **Status**: todo | **Owner**: Codex
**Arch Ref**: [AUTOWFO_ARCHITECTURE_V2.md §4.2](AUTOWFO_ARCHITECTURE_V2.md)
**Depends on**: AWF-127 (uses `experiment.artifact_dir`)
**Blocks**: AWF-131 (experiment_runner writes to this structure)

### Files to create
| File | Purpose |
|------|---------|
| `scripts/autowfo/artifact_store.py` | Directory init, SQLite create, run_meta write/read |
| `tests/test_autowfo_artifact_store.py` | Unit tests (use tmp_path fixture) |

### Files NOT to modify
- `scripts/autowfo/artifacts.py` — existing artifact logic stays untouched (different purpose)

### `ArtifactStore` class spec
```python
class ArtifactStore:
    def __init__(self, experiment_id: str, base_dir: pathlib.Path = None):
        """
        base_dir defaults to pathlib.Path("artifacts") if None.
        Does NOT create directories at init time.
        """

    def init_run(self, run_id: str) -> pathlib.Path:
        """
        Creates: artifacts/experiments/{exp_id}/runs/{run_id}/
        Returns the run directory path.
        run_id format: YYYYMMDD_HHMMSS (caller provides)
        """

    def get_run_db_path(self, run_id: str) -> pathlib.Path:
        """Returns path to results.db for this run (not created yet)."""

    def get_run_meta_path(self, run_id: str) -> pathlib.Path:
        """Returns path to run_meta.json for this run."""

    def write_run_meta(self, run_id: str, meta: dict) -> None:
        """Write run_meta.json. Creates file (overwrites if exists)."""

    def read_run_meta(self, run_id: str) -> dict:
        """Read run_meta.json. Raises FileNotFoundError if missing."""

    def list_runs(self) -> list[str]:
        """Return sorted list of run_ids (directory names) for this experiment."""

    def init_results_db(self, run_id: str) -> sqlite3.Connection:
        """
        Creates results.db with WAL mode and combo_results table.
        Returns open connection (caller must close).
        Schema per Architecture V2 §4.3.
        """
```

### SQLite schema (exact)
```sql
CREATE TABLE IF NOT EXISTS combo_results (
    combo_id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    direction TEXT NOT NULL,
    trigger_asset TEXT,
    action_asset TEXT NOT NULL,
    indicator_params TEXT NOT NULL,
    condition_params TEXT NOT NULL,
    risk_params TEXT NOT NULL,
    oos_sharpe REAL,
    oos_win_rate REAL,
    oos_n_trades INTEGER,
    oos_total_return REAL,
    wf_score REAL,
    created_utc TEXT
);
CREATE INDEX IF NOT EXISTS idx_experiment ON combo_results(experiment_id);
CREATE INDEX IF NOT EXISTS idx_wf_score ON combo_results(wf_score DESC);
```

WAL mode: immediately after `CREATE TABLE`, run:
```python
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA synchronous=NORMAL")
```

### Constraints
- `init_run()` must be idempotent (safe to call twice with same run_id)
- `init_results_db()` must be idempotent (safe to call on existing DB)
- All paths use `pathlib.Path` — no string concatenation
- `base_dir` defaults to `pathlib.Path("artifacts")` — NOT an absolute path — so tests can use `tmp_path`

### Verification command
```bash
pytest tests/test_autowfo_artifact_store.py -v
```

### Exit criteria
- [ ] `init_run("20260301_020000")` creates correct directory structure
- [ ] `init_results_db()` creates DB with WAL mode enabled (verify `PRAGMA journal_mode`)
- [ ] `combo_results` table has all columns per schema
- [ ] `init_run()` called twice with same run_id does NOT raise exception
- [ ] `init_results_db()` called twice does NOT duplicate table or indexes
- [ ] `write_run_meta` + `read_run_meta` round-trip correctly
- [ ] All tests use `tmp_path` (no real `artifacts/` directory touched by tests)
- [ ] All tests: N passed, 0 failed

### Report file
`plans/reports/AWF-128-report.md`

---

## AWF-129 — Experiment CRUD API

**Phase**: 20 | **Priority**: P1 | **Status**: todo | **Owner**: Codex
**Arch Ref**: [AUTOWFO_ARCHITECTURE_V2.md §9.2](AUTOWFO_ARCHITECTURE_V2.md)
**Depends on**: AWF-127 (Experiment class), AWF-128 (ArtifactStore)
**Blocks**: AWF-142 (Experiments tab UI)

### Files to create
| File | Purpose |
|------|---------|
| `scripts/control_panel_experiments.py` | HTTP handler functions for experiment CRUD |
| `tests/test_control_panel_experiments.py` | Endpoint regression tests |

### Files to modify
| File | Change |
|------|--------|
| `scripts/control_panel.py` | Import and wire 5 new endpoints from `control_panel_experiments.py` |

### Endpoints to implement

| Method | Path | Handler | Description |
|--------|------|---------|-------------|
| GET | `/experiments.json` | `_handle_experiments_list` | List all experiments with status summary |
| POST | `/experiments/create` | `_handle_experiments_create` | Create new experiment from JSON body |
| GET | `/experiments/{id}/config.json` | `_handle_experiment_config` | Get config for one experiment |
| DELETE | `/experiments/{id}` | `_handle_experiment_delete` | Delete experiment (config only, not run artifacts) |
| POST | `/experiments/{id}/run` | `_handle_experiment_run` | Add experiment to batch queue |

### Response schemas

**`GET /experiments.json`**:
```json
{
  "experiments": [
    {
      "experiment_id": "exp_btc1h_eth4h_rsi_bb_v1",
      "description": "...",
      "mode": "hypothesis",
      "runs": 2,
      "last_run_utc": "2026-03-01T02:00:00Z",
      "best_oos_sharpe": 1.23,
      "status": "idle"
    }
  ],
  "total": 1
}
```

**`POST /experiments/create`** body: experiment config dict (Architecture V2 §3.1 format)
Response on success: `{"ok": true, "experiment_id": "..."}`
Response on validation error: HTTP 400, `{"error": "...", "field": "..."}`

**`POST /experiments/{id}/run`** response:
```json
{"ok": true, "queued": true, "job_id": "..."}
```

### Deferred accessor pattern (REQUIRED)
```python
import sys as _sys

def _cp():
    return _sys.modules.get("scripts.control_panel")
```
Use `_cp().ARTIFACTS`, `_cp().STATUS_JSON`, etc. — same pattern as `control_panel_config.py`.

### Constraints
- `DELETE /experiments/{id}` only deletes `config.json` and the `experiments/{id}/` directory if empty — does NOT delete `runs/` subdirectories with real data. If runs exist, return HTTP 409 with `{"error": "experiment has runs, cannot delete"}`.
- Experiment list builds summary by scanning `artifacts/experiments/*/config.json` — no database query
- `POST /experiments/{id}/run` adds to `artifacts/batch_state.json` queue — reuse existing batch queue mechanism

### Verification command
```bash
pytest tests/test_control_panel_experiments.py -v
```

### Exit criteria
- [ ] `GET /experiments.json` returns correct list shape (test with 0 and 2 experiments)
- [ ] `POST /experiments/create` with valid config creates `config.json` on disk
- [ ] `POST /experiments/create` with invalid config returns HTTP 400 with `error` field
- [ ] `GET /experiments/{id}/config.json` returns config for existing experiment; 404 for missing
- [ ] `DELETE /experiments/{id}` succeeds when no runs exist; returns 409 when runs exist
- [ ] `POST /experiments/{id}/run` adds entry to batch queue
- [ ] All tests: N passed, 0 failed

### Report file
`plans/reports/AWF-129-report.md`

---

## Phase 20 Completion Gate

Before Phase 21 (AWF-130+) starts using Phase 20 interfaces, Architect must review:
- **AWF-125** report — specifically the `compute()` contract (⚠️ cross-phase)
- **AWF-126** report — specifically the `apply()` dispatcher contract (⚠️ cross-phase)

Codex may begin AWF-130 (`signal_composer.py`) structure and non-interface code while awaiting review. Codex must NOT call `compute()` or `apply()` in production code until Architect confirms contracts.

---

## Phase 21 AWFs (AWF-130 ~ AWF-133)

> Detailed specs for Phase 21 will be written by Architect after Phase 20 gate review.
> Placeholder entries below indicate dependencies only.

### AWF-130 — Signal Composer (Cross-Timeframe Alignment)
**Depends on**: AWF-125 (⚠️), AWF-126 (⚠️)
**Spec**: To be written after Phase 20 gate.

### AWF-131 — Experiment Runner (WFO Integration)
**Depends on**: AWF-127, AWF-128, AWF-130, AWF-132
**Spec**: To be written after Phase 20 gate.

### AWF-132 — Multi-Asset Data Layer
**Depends on**: — (can implement in parallel with AWF-130)
**Spec**: To be written after Phase 20 gate.

### AWF-133 — Dual-Direction Signal Generation
**Depends on**: AWF-130, AWF-131
**Spec**: To be written after Phase 20 gate.

---

## Phase 22 AWFs (AWF-134 ~ AWF-137)

> Specs to be written by Architect after Phase 21 gate review.

---

## Phase 23 AWFs (AWF-138 ~ AWF-141)

> Specs to be written by Architect after Phase 22 gate review.

---

## Phase 24 AWFs (AWF-142 ~ AWF-145)

> Specs to be written by Architect after Phase 23 gate review.

---

*Spec version: 1.0 — 2026-02-27. This file is maintained by Architect. Codex does not modify it.*
