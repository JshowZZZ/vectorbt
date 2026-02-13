import pandas as pd

from scripts.autowfo import ranking as r


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
