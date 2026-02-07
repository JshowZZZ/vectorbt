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
