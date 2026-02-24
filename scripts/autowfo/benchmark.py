"""Benchmark computations for AUTOWFO.

Provides buy-and-hold / random-entry reference returns plus Monte Carlo
sampling helpers for risk-oriented advanced analysis.

All functions are **pure** — they take data in and return results with
no side-effects — so they are easy to unit-test.
"""

from __future__ import annotations

from typing import Iterable, Optional

import numpy as np
import pandas as pd


def compute_bh_return_pct(trade_close: pd.DataFrame) -> Optional[float]:
    """Buy-and-hold return over the full *trade_close* range.

    Computes ``(last / first - 1) * 100`` per symbol column, then
    averages across all trade symbols.  Returns ``None`` when the
    DataFrame is empty or contains no valid (> 0) starting prices.
    """
    if trade_close.empty or len(trade_close) < 2:
        return None
    first = trade_close.iloc[0]
    last = trade_close.iloc[-1]
    mask = first > 0
    if not mask.any():
        return None
    returns_pct = ((last[mask] / first[mask]) - 1.0) * 100.0
    return float(returns_pct.mean())


def compute_random_entry_return_pct(
    trade_close: pd.DataFrame,
    *,
    hold_bars: int = 24,
    n_trials: int = 200,
    seed: int = 42,
) -> Optional[float]:
    """Average return of randomly-timed entries.

    For each trial a random entry bar is chosen, the position is held
    for *hold_bars* bars, and the simple return is computed.  The
    result is the mean across all trials and all symbols.  Returns
    ``None`` when there is insufficient data.
    """
    if trade_close.empty:
        return None
    n_bars = len(trade_close)
    max_entry = n_bars - hold_bars - 1
    if max_entry < 1:
        return None

    rng = np.random.default_rng(seed)
    entries = rng.integers(0, max_entry, size=n_trials)
    values = trade_close.values  # shape (n_bars, n_symbols)

    trial_returns: list[float] = []
    for entry_idx in entries:
        exit_idx = entry_idx + hold_bars
        entry_prices = values[entry_idx]
        exit_prices = values[exit_idx]
        pos_mask = entry_prices > 0
        if pos_mask.any():
            ret_pct = ((exit_prices[pos_mask] / entry_prices[pos_mask]) - 1.0) * 100.0
            trial_returns.append(float(np.mean(ret_pct)))

    if not trial_returns:
        return None
    return float(np.mean(trial_returns))


def _coerce_numeric_series(values: Iterable[object]) -> np.ndarray:
    """Convert an iterable into a finite float numpy array."""
    if values is None:
        return np.array([], dtype=float)
    output: list[float] = []
    for value in values:
        try:
            num = float(value)
        except (TypeError, ValueError):
            continue
        if np.isfinite(num):
            output.append(num)
    if not output:
        return np.array([], dtype=float)
    return np.asarray(output, dtype=float)


def compute_monte_carlo_return_stats(
    returns_pct: Iterable[object],
    *,
    n_trials: int = 2000,
    sample_size: Optional[int] = None,
    seed: int = 42,
) -> Optional[dict]:
    """Bootstrap Monte Carlo stats from a return series (in percent units).

    Parameters
    ----------
    returns_pct
        Iterable of historical return observations (already in percent).
    n_trials
        Number of bootstrap trials.
    sample_size
        Number of observations sampled per trial. Defaults to the input
        series length.
    seed
        RNG seed for deterministic output.
    """
    obs = _coerce_numeric_series(returns_pct)
    if obs.size == 0:
        return None

    try:
        n_trials_i = max(1, int(n_trials))
    except (TypeError, ValueError):
        n_trials_i = 2000
    if sample_size is None:
        sample_size_i = int(obs.size)
    else:
        try:
            sample_size_i = max(1, int(sample_size))
        except (TypeError, ValueError):
            sample_size_i = int(obs.size)

    rng = np.random.default_rng(seed)
    indices = rng.integers(0, obs.size, size=(n_trials_i, sample_size_i))
    sampled = obs[indices]
    trial_means = sampled.mean(axis=1)

    p05 = float(np.quantile(trial_means, 0.05))
    p50 = float(np.quantile(trial_means, 0.50))
    p95 = float(np.quantile(trial_means, 0.95))
    tail = trial_means[trial_means <= p05]
    cvar5 = float(tail.mean()) if tail.size else p05

    std = float(np.std(trial_means, ddof=1)) if trial_means.size > 1 else 0.0
    prob_pos = float(np.mean(trial_means > 0.0) * 100.0)

    return {
        "method": "bootstrap_mean_return_pct",
        "n_obs": int(obs.size),
        "n_trials": int(n_trials_i),
        "sample_size": int(sample_size_i),
        "base_mean_return_pct": float(obs.mean()),
        "base_median_return_pct": float(np.median(obs)),
        "mean_return_pct": float(trial_means.mean()),
        "std_return_pct": std,
        "p05_return_pct": p05,
        "p50_return_pct": p50,
        "p95_return_pct": p95,
        "cvar5_return_pct": cvar5,
        "prob_positive_pct": prob_pos,
    }
