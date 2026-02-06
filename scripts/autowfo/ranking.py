"""Ranking helpers extracted from run_btc_regime_sweep monolith."""


def _choose_score_col(df, preferred="oos_avg_total_return_pct", fallback="avg_total_return_pct"):
    sort_col = preferred
    if sort_col not in df.columns or not df[sort_col].notna().any():
        sort_col = fallback
    return sort_col


def _sort_by_score(
    df,
    preferred="oos_avg_total_return_pct",
    fallback="avg_total_return_pct",
    tie_break_avg_hold=True,
):
    score_col = _choose_score_col(df, preferred=preferred, fallback=fallback)
    sort_cols = [score_col]
    sort_asc = [False]
    if tie_break_avg_hold and "avg_hold_hours" in df.columns:
        sort_cols.append("avg_hold_hours")
        sort_asc.append(True)
    return df.sort_values(sort_cols, ascending=sort_asc), score_col


def _top_by_score(
    df,
    top_n,
    preferred="oos_avg_total_return_pct",
    fallback="avg_total_return_pct",
    tie_break_avg_hold=True,
):
    sorted_df, score_col = _sort_by_score(
        df,
        preferred=preferred,
        fallback=fallback,
        tie_break_avg_hold=tie_break_avg_hold,
    )
    return sorted_df.head(top_n), score_col
