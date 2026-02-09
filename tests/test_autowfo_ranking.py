import pandas as pd

from scripts.autowfo import ranking as r


def test_sort_by_score_tie_break_behavior():
    df = pd.DataFrame(
        {
            "oos_avg_total_return_pct": [10.0, 10.0, 8.0],
            "avg_hold_hours": [5.0, 2.0, 1.0],
            "name": ["a", "b", "c"],
        }
    )
    sorted_df, score_col = r._sort_by_score(df, tie_break_avg_hold=True)
    assert score_col == "oos_avg_total_return_pct"
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
    sorted_df, score_col = r._sort_by_score(df, tie_break_avg_hold=True)
    assert score_col == "oos_avg_total_return_pct"
    assert sorted_df["name"].tolist() == ["b", "c", "a"]


def test_top_by_score_uses_fallback_and_honors_top_n():
    df = pd.DataFrame(
        {
            "avg_total_return_pct": [3.0, 5.0, 4.0, 1.0],
            "name": ["a", "b", "c", "d"],
        }
    )
    top_df, score_col = r._top_by_score(df, top_n=2)
    assert score_col == "avg_total_return_pct"
    assert top_df["name"].tolist() == ["b", "c"]
