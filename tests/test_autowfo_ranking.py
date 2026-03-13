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

