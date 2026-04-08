import numpy as np
import pandas as pd

from autowfo import ranking as r


def test_sort_by_score_tie_break_behavior_in_legacy_mode():
    df = pd.DataFrame(
        {
            "oos_avg_total_return_pct": [10.0, 10.0, 8.0],
            "avg_hold_hours": [5.0, 2.0, 1.0],
            "name": ["a", "b", "c"],
        }
    )
    sorted_df, score_col = r._sort_by_score(
        df,
        tie_break_avg_hold=True,
        ranking_config={"mode": "legacy"},
    )
    assert score_col == "oos_avg_total_return_pct"
    assert sorted_df.iloc[0]["name"] == "b"


def test_sort_by_score_default_mode_uses_composite_score():
    df = pd.DataFrame(
        {
            "oos_avg_total_return_pct": [10.0, 10.0],
            "oos_positive_segment_ratio": [0.2, 0.8],
            "oos_return_std": [5.0, 1.0],
            "oos_sharpe_like": [0.1, 0.8],
            "oos_avg_max_drawdown_pct": [-15.0, -8.0],
            "oos_low_trade_penalty": [0.5, 0.0],
            "name": ["a", "b"],
        }
    )
    sorted_df, score_col = r._sort_by_score(df, tie_break_avg_hold=False)
    assert score_col == "composite_score"
    assert sorted_df.iloc[0]["name"] == "b"


def test_choose_score_col_falls_back_when_preferred_missing():
    df = pd.DataFrame({"avg_total_return_pct": [1.0, 2.0]})
    assert r._choose_score_col(df) == "avg_total_return_pct"


def test_choose_score_col_falls_back_when_preferred_all_nan():
    df = pd.DataFrame(
        {
            "oos_avg_total_return_pct": [float("nan"), float("nan")],
            "avg_total_return_pct": [1.0, 2.0],
        }
    )
    assert r._choose_score_col(df) == "avg_total_return_pct"


def test_sort_by_score_without_avg_hold_column():
    df = pd.DataFrame(
        {
            "oos_avg_total_return_pct": [1.0, 3.0, 2.0],
            "name": ["a", "b", "c"],
        }
    )
    sorted_df, score_col = r._sort_by_score(
        df,
        tie_break_avg_hold=True,
        ranking_config={"mode": "legacy"},
    )
    assert score_col == "oos_avg_total_return_pct"
    assert sorted_df["name"].tolist() == ["b", "c", "a"]


def test_top_by_score_uses_fallback_and_honors_top_n():
    df = pd.DataFrame(
        {
            "avg_total_return_pct": [3.0, 5.0, 4.0, 1.0],
            "name": ["a", "b", "c", "d"],
        }
    )
    top_df, score_col = r._top_by_score(
        df,
        top_n=2,
        ranking_config={"mode": "legacy"},
    )
    assert score_col == "avg_total_return_pct"
    assert top_df["name"].tolist() == ["b", "c"]


def test_sort_by_score_gracefully_handles_missing_score_columns():
    df = pd.DataFrame(
        {
            "name": ["a", "b"],
            "avg_hold_hours": [4.0, 2.0],
        }
    )
    sorted_df, score_col = r._sort_by_score(
        df,
        tie_break_avg_hold=True,
        ranking_config={"mode": "legacy"},
    )
    assert score_col == "avg_total_return_pct"
    assert "avg_total_return_pct" in sorted_df.columns
    assert sorted_df["name"].tolist() == ["b", "a"]


def test_resolve_ranking_config_merges_partial_weights():
    cfg = r._resolve_ranking_config(
        {
            "mode": "composite",
            "weights": {"return": 2.5},
        }
    )
    assert cfg["mode"] == "composite"
    assert cfg["weights"]["return"] == 2.5
    assert cfg["weights"]["stability"] == r.DEFAULT_RANKING_CONFIG["weights"]["stability"]


# ---------------------------------------------------------------------------
#  AWF-026: Regime-aware ranking tests
# ---------------------------------------------------------------------------


def _make_regime_df():
    """Build a small DataFrame with two regimes and composite_score."""
    return pd.DataFrame({
        "regime_name": ["trend_high", "trend_high", "rsi_revert_low", "rsi_revert_low", "trend_high"],
        "oos_avg_total_return_pct": [10.0, 6.0, 8.0, 3.0, 12.0],
        "avg_total_return_pct": [9.0, 5.0, 7.0, 2.0, 11.0],
        "composite_score": [1.5, 0.8, 1.2, 0.3, 1.8],
        "name": ["a", "b", "c", "d", "e"],
    })


def test_default_ranking_config_has_regime_weights():
    assert "regime_weights" in r.DEFAULT_RANKING_CONFIG
    assert r.DEFAULT_RANKING_CONFIG["regime_weights"] == {}


def test_apply_regime_weight_no_weights():
    """Empty regime_weights ??no change to composite_score."""
    df = _make_regime_df()
    original_scores = df["composite_score"].tolist()
    result = r._apply_regime_weight(df, ranking_config=None)
    assert result["composite_score"].tolist() == original_scores


def test_apply_regime_weight_with_weights():
    """Per-regime weight multiplies composite_score."""
    df = _make_regime_df()
    cfg = {"regime_weights": {"trend_high": 2.0, "rsi_revert_low": 0.5}}
    result = r._apply_regime_weight(df, ranking_config=cfg)
    # trend_high rows: 1.5*2=3.0, 0.8*2=1.6, 1.8*2=3.6
    # rsi_revert_low: 1.2*0.5=0.6, 0.3*0.5=0.15
    assert result.iloc[0]["composite_score"] == 3.0
    assert result.iloc[1]["composite_score"] == 1.6
    assert result.iloc[2]["composite_score"] == 0.6
    assert abs(result.iloc[3]["composite_score"] - 0.15) < 1e-9
    assert result.iloc[4]["composite_score"] == 3.6


def test_apply_regime_weight_default_for_unknown():
    """Unknown regime_name defaults to weight 1.0."""
    df = _make_regime_df()
    cfg = {"regime_weights": {"trend_high": 1.5}}  # rsi_revert_low not listed ??1.0
    result = r._apply_regime_weight(df, ranking_config=cfg)
    assert result.iloc[2]["composite_score"] == 1.2  # unchanged


def test_apply_regime_weight_no_regime_column():
    """DataFrame without regime_name ??no change."""
    df = pd.DataFrame({"composite_score": [1.0, 2.0]})
    cfg = {"regime_weights": {"trend_high": 2.0}}
    result = r._apply_regime_weight(df, ranking_config=cfg)
    assert result["composite_score"].tolist() == [1.0, 2.0]


def test_top_by_score_per_regime_grouping():
    """_top_by_score_per_regime groups by regime_name and returns top-N per group."""
    df = _make_regime_df()
    result = r._top_by_score_per_regime(df, top_n=2, ranking_config={"mode": "legacy"})
    assert "trend_high" in result
    assert "rsi_revert_low" in result
    # trend_high: top 2 by oos_avg_total_return_pct ??e(12), a(10)
    th_df, _ = result["trend_high"]
    assert len(th_df) == 2
    assert th_df.iloc[0]["name"] == "e"
    assert th_df.iloc[1]["name"] == "a"
    # rsi_revert_low: top 2 ??c(8), d(3)
    rr_df, _ = result["rsi_revert_low"]
    assert len(rr_df) == 2
    assert rr_df.iloc[0]["name"] == "c"


def test_top_by_score_per_regime_empty_when_no_column():
    """No regime_name column ??empty dict."""
    df = pd.DataFrame({"oos_avg_total_return_pct": [1.0]})
    assert r._top_by_score_per_regime(df, top_n=5) == {}


def test_regime_summary_basic():
    """_regime_summary produces per-regime aggregates."""
    df = _make_regime_df()
    # Need composite_score for avg_composite_score
    summary = r._regime_summary(df)
    assert len(summary) == 2
    by_name = {row["regime_name"]: row for row in summary}
    assert by_name["trend_high"]["combo_count"] == 3
    assert by_name["rsi_revert_low"]["combo_count"] == 2
    # avg return for trend_high: (10+6+12)/3 ??9.3333
    assert abs(by_name["trend_high"]["avg_return_pct"] - 9.3333) < 0.01
    # avg composite for rsi_revert_low: (1.2+0.3)/2 = 0.75
    assert abs(by_name["rsi_revert_low"]["avg_composite_score"] - 0.75) < 0.01


def test_regime_summary_empty_without_regime_column():
    df = pd.DataFrame({"oos_avg_total_return_pct": [1.0]})
    assert r._regime_summary(df) == []


# ---------------------------------------------------------------------------
#  AWF-225: Combo deduplication tests
# ---------------------------------------------------------------------------


def test_dedup_by_combo_group_keeps_best_per_combo():
    """Same indicator_list + regime should keep only the highest-score row."""
    df = pd.DataFrame({
        "indicator_list": ["A,B", "A,B", "C,D", "C,D", "A,B"],
        "regime_name": ["trend", "trend", "trend", "trend", "revert"],
        "vol_mode": ["high", "high", "high", "high", "high"],
        "composite_score": [0.5, 0.8, 0.3, 0.9, 0.4],
        "name": ["a1", "a2", "c1", "c2", "a3"],
    })
    # Sort descending by score first (as _sort_by_score would)
    df = df.sort_values("composite_score", ascending=False)
    result = r._dedup_by_combo_group(df)
    assert len(result) == 3
    names = result["name"].tolist()
    assert "c2" in names  # best C,D/trend
    assert "a2" in names  # best A,B/trend
    assert "a3" in names  # best A,B/revert (different regime)


def test_dedup_by_combo_group_no_fields_present():
    """If none of the dedup fields exist, return unchanged."""
    df = pd.DataFrame({"score": [1.0, 2.0], "name": ["a", "b"]})
    result = r._dedup_by_combo_group(df)
    assert len(result) == 2


def test_dedup_by_combo_group_custom_fields():
    """Operator can override dedup fields via ranking_config."""
    df = pd.DataFrame({
        "indicator_list": ["A,B", "A,B", "C,D"],
        "composite_score": [0.5, 0.8, 0.3],
    })
    df = df.sort_values("composite_score", ascending=False)
    # Dedup only by indicator_list (ignoring regime/vol_mode)
    cfg = {"top10_dedup_fields": ["indicator_list"]}
    result = r._dedup_by_combo_group(df, ranking_config=cfg)
    assert len(result) == 2


def test_dedup_preserves_order():
    """After dedup, rows should remain in score-descending order."""
    df = pd.DataFrame({
        "indicator_list": ["X", "Y", "X", "Z"],
        "regime_name": ["t", "t", "t", "t"],
        "vol_mode": ["h", "h", "h", "h"],
        "composite_score": [0.9, 0.7, 0.5, 0.3],
    })
    df = df.sort_values("composite_score", ascending=False)
    result = r._dedup_by_combo_group(df)
    scores = result["composite_score"].tolist()
    assert scores == sorted(scores, reverse=True)
    assert len(result) == 3


# ---------------------------------------------------------------------------
#  AWF-226: Relative low-trade penalty tests
# ---------------------------------------------------------------------------


def test_relative_low_trade_penalty_differentiates():
    """In relative mode, combos above P75 get zero penalty."""
    df = pd.DataFrame({
        "oos_avg_total_return_pct": [10.0, 10.0, 10.0, 10.0],
        "oos_avg_daily_trades": [1.0, 2.0, 5.0, 8.0],
        "oos_positive_segment_ratio": [0.6, 0.6, 0.6, 0.6],
        "oos_return_std": [1.0, 1.0, 1.0, 1.0],
        "oos_sharpe_like": [0.5, 0.5, 0.5, 0.5],
        "oos_avg_max_drawdown_pct": [-5.0, -5.0, -5.0, -5.0],
    })
    cfg_abs = {"mode": "composite", "low_trade_mode": "absolute", "low_trade_threshold": 30.0}
    cfg_rel = {"mode": "composite", "low_trade_mode": "relative", "low_trade_threshold": 30.0}

    resolved_abs = r._resolve_ranking_config(cfg_abs)
    resolved_rel = r._resolve_ranking_config(cfg_rel)

    scores_abs = r._build_composite_score(df, resolved_abs)
    scores_rel = r._build_composite_score(df, resolved_rel)

    # Absolute mode: all combos have low trades → all penalized equally
    assert scores_abs.nunique() == 1  # all same score

    # Relative mode: combo with 8 trades (P75) gets zero penalty,
    # combo with 1 trade gets higher penalty → scores differ
    assert scores_rel.nunique() > 1
    # Higher daily trades → higher score
    assert scores_rel.iloc[3] > scores_rel.iloc[0]


def test_relative_penalty_all_zero_trades():
    """When all combos have zero trades, relative penalty is 0 for all."""
    df = pd.DataFrame({
        "oos_avg_total_return_pct": [5.0, 10.0],
        "oos_avg_daily_trades": [0.0, 0.0],
        "oos_positive_segment_ratio": [0.5, 0.8],
        "oos_return_std": [1.0, 1.0],
        "oos_sharpe_like": [0.3, 0.6],
        "oos_avg_max_drawdown_pct": [-3.0, -3.0],
    })
    cfg = {"mode": "composite", "low_trade_mode": "relative"}
    resolved = r._resolve_ranking_config(cfg)
    scores = r._build_composite_score(df, resolved)
    # Scores should differ only by return/stability/risk, not by penalty
    assert scores.iloc[1] > scores.iloc[0]


def test_relative_penalty_uses_avg_daily_trades_fallback():
    """When oos_avg_daily_trades missing, falls back to avg_daily_trades."""
    df = pd.DataFrame({
        "oos_avg_total_return_pct": [10.0, 10.0],
        "avg_daily_trades": [2.0, 8.0],
        "oos_positive_segment_ratio": [0.6, 0.6],
        "oos_return_std": [1.0, 1.0],
        "oos_sharpe_like": [0.5, 0.5],
        "oos_avg_max_drawdown_pct": [-5.0, -5.0],
    })
    cfg = {"mode": "composite", "low_trade_mode": "relative"}
    resolved = r._resolve_ranking_config(cfg)
    scores = r._build_composite_score(df, resolved)
    assert scores.iloc[1] > scores.iloc[0]


def test_absolute_mode_unchanged_behavior():
    """Absolute mode behavior is identical to pre-Phase-45."""
    df = pd.DataFrame({
        "oos_avg_total_return_pct": [10.0, 10.0],
        "oos_positive_segment_ratio": [0.6, 0.6],
        "oos_return_std": [1.0, 1.0],
        "oos_sharpe_like": [0.5, 0.5],
        "oos_avg_max_drawdown_pct": [-5.0, -5.0],
        "oos_low_trade_penalty": [0.3, 0.7],
    })
    cfg_default = {"mode": "composite"}
    cfg_explicit = {"mode": "composite", "low_trade_mode": "absolute"}
    resolved_default = r._resolve_ranking_config(cfg_default)
    resolved_explicit = r._resolve_ranking_config(cfg_explicit)
    scores_default = r._build_composite_score(df, resolved_default)
    scores_explicit = r._build_composite_score(df, resolved_explicit)
    pd.testing.assert_series_equal(scores_default, scores_explicit)


def test_resolve_ranking_config_new_keys():
    """New config keys resolve with defaults and overrides."""
    cfg = r._resolve_ranking_config(None)
    assert cfg["low_trade_mode"] == "absolute"
    assert cfg["top10_dedup_fields"] == ["indicator_list", "regime_name", "vol_mode"]

    cfg2 = r._resolve_ranking_config({"low_trade_mode": "relative"})
    assert cfg2["low_trade_mode"] == "relative"

    cfg3 = r._resolve_ranking_config({"low_trade_mode": "invalid"})
    assert cfg3["low_trade_mode"] == "absolute"

    cfg4 = r._resolve_ranking_config({"top10_dedup_fields": ["indicator_list"]})
    assert cfg4["top10_dedup_fields"] == ["indicator_list"]

