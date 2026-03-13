"""Tests for autowfo.benchmark ??baseline benchmark computations."""

import numpy as np
import pandas as pd
import pytest

from autowfo.benchmark import (
    compute_bh_return_pct,
    compute_monte_carlo_return_stats,
    compute_random_entry_return_pct,
)


# ---------------------------------------------------------------------------
# compute_bh_return_pct
# ---------------------------------------------------------------------------

def test_bh_return_simple_single_symbol():
    """100 ??120 should give +20%."""
    close = pd.DataFrame({"SYM": [100.0, 110.0, 120.0]})
    result = compute_bh_return_pct(close)
    assert result == pytest.approx(20.0)


def test_bh_return_multi_symbol_average():
    """Two symbols: +50% and -20% ??average +15%."""
    close = pd.DataFrame({"A": [100.0, 150.0], "B": [100.0, 80.0]})
    result = compute_bh_return_pct(close)
    assert result == pytest.approx(15.0)


def test_bh_return_empty_df():
    close = pd.DataFrame()
    assert compute_bh_return_pct(close) is None


def test_bh_return_single_row():
    close = pd.DataFrame({"SYM": [100.0]})
    assert compute_bh_return_pct(close) is None


def test_bh_return_zero_start_price():
    """All starting prices are zero ??None."""
    close = pd.DataFrame({"A": [0.0, 50.0], "B": [0.0, 100.0]})
    assert compute_bh_return_pct(close) is None


def test_bh_return_partial_zero():
    """One symbol starts at zero, the other at 100 ??only non-zero counted."""
    close = pd.DataFrame({"A": [0.0, 50.0], "B": [100.0, 130.0]})
    result = compute_bh_return_pct(close)
    assert result == pytest.approx(30.0)


# ---------------------------------------------------------------------------
# compute_random_entry_return_pct
# ---------------------------------------------------------------------------

def test_random_entry_insufficient_data():
    """Fewer bars than hold_bars + 1 ??None."""
    close = pd.DataFrame({"SYM": [100.0, 110.0]})
    assert compute_random_entry_return_pct(close, hold_bars=5) is None


def test_random_entry_empty():
    close = pd.DataFrame()
    assert compute_random_entry_return_pct(close) is None


def test_random_entry_deterministic():
    """Same seed ??same result."""
    idx = pd.date_range("2025-01-01", periods=100, freq="h")
    close = pd.DataFrame({"SYM": np.linspace(100, 200, 100)}, index=idx)
    r1 = compute_random_entry_return_pct(close, hold_bars=5, n_trials=50, seed=99)
    r2 = compute_random_entry_return_pct(close, hold_bars=5, n_trials=50, seed=99)
    assert r1 is not None
    assert r1 == pytest.approx(r2)


def test_random_entry_returns_float():
    idx = pd.date_range("2025-01-01", periods=200, freq="h")
    close = pd.DataFrame({"SYM": np.linspace(100, 150, 200)}, index=idx)
    result = compute_random_entry_return_pct(close, hold_bars=10, n_trials=100, seed=42)
    assert isinstance(result, float)


def test_random_entry_flat_price():
    """Constant price ??return should be ~0."""
    idx = pd.date_range("2025-01-01", periods=100, freq="h")
    close = pd.DataFrame({"SYM": [100.0] * 100}, index=idx)
    result = compute_random_entry_return_pct(close, hold_bars=5, n_trials=50, seed=42)
    assert result == pytest.approx(0.0, abs=1e-8)


# ---------------------------------------------------------------------------
# compute_monte_carlo_return_stats
# ---------------------------------------------------------------------------

def test_monte_carlo_return_stats_deterministic():
    values = [1.0, 2.0, -1.0, 0.5, 3.0]
    s1 = compute_monte_carlo_return_stats(values, n_trials=500, sample_size=4, seed=7)
    s2 = compute_monte_carlo_return_stats(values, n_trials=500, sample_size=4, seed=7)
    assert s1 is not None
    assert s1 == s2
    assert s1["n_obs"] == 5
    assert s1["n_trials"] == 500
    assert s1["sample_size"] == 4


def test_monte_carlo_return_stats_empty():
    assert compute_monte_carlo_return_stats([], n_trials=100, seed=1) is None


def test_monte_carlo_return_stats_filters_invalid_values():
    values = [1.0, "bad", None, float("nan"), 2.0]
    stats = compute_monte_carlo_return_stats(values, n_trials=200, sample_size=3, seed=11)
    assert stats is not None
    assert stats["n_obs"] == 2
    assert isinstance(stats["prob_positive_pct"], float)

