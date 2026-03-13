"""Portfolio execution helpers extracted from run_btc_regime_sweep monolith."""

import numpy as np
import pandas as pd
import vectorbt as vbt


def _run_pf(
    trade_close,
    long_regime,
    short_regime,
    max_hold,
    fees,
    sl_stop,
    tp_stop,
    freq,
    slippage=None,
    long_filter=None,
    short_filter=None,
    init_cash=None,
    size=None,
    size_type=None,
    cash_sharing=None,
    lock_cash=None,
    allow_partial=None,
    max_positions=None,
    long_scores=None,
    short_scores=None,
):
    long_matrix = pd.DataFrame(
        np.broadcast_to(long_regime.to_numpy()[:, None], trade_close.shape),
        index=trade_close.index,
        columns=trade_close.columns,
    )
    short_matrix = pd.DataFrame(
        np.broadcast_to(short_regime.to_numpy()[:, None], trade_close.shape),
        index=trade_close.index,
        columns=trade_close.columns,
    )
    if long_filter is not None:
        long_matrix = long_matrix & long_filter.fillna(False)
    if short_filter is not None:
        short_matrix = short_matrix & short_filter.fillna(False)
    entries = long_matrix.vbt.fshift(1, fill_value=False)
    short_entries = short_matrix.vbt.fshift(1, fill_value=False)
    if max_positions is not None and max_positions > 0:
        if long_scores is not None:
            long_scores = long_scores.reindex_like(entries).where(entries, -np.inf).fillna(-np.inf)
            long_ranks = long_scores.rank(axis=1, method="first", ascending=False)
            entries = entries & (long_ranks <= max_positions)
        if short_scores is not None:
            short_scores = short_scores.reindex_like(short_entries).where(short_entries, -np.inf).fillna(-np.inf)
            short_ranks = short_scores.rank(axis=1, method="first", ascending=False)
            short_entries = short_entries & (short_ranks <= max_positions)
    entries_shifted = entries.vbt.fshift(max_hold, fill_value=False)
    short_entries_shifted = short_entries.vbt.fshift(max_hold, fill_value=False)
    exits = entries_shifted
    short_exits = short_entries_shifted
    group_by_param = True if cash_sharing else None
    return vbt.Portfolio.from_signals(
        trade_close,
        entries=entries,
        exits=exits,
        short_entries=short_entries,
        short_exits=short_exits,
        init_cash=init_cash,
        cash_sharing=cash_sharing,
        group_by=group_by_param,
        size=size,
        size_type=size_type,
        lock_cash=lock_cash,
        allow_partial=allow_partial,
        upon_opposite_entry="close",
        upon_dir_conflict="ignore",
        fees=fees,
        sl_stop=sl_stop,
        tp_stop=tp_stop,
        slippage=slippage,
        freq=freq,
    )

