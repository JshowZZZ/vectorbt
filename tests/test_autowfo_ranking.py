import pandas as pd

from scripts import run_btc_regime_sweep as sweep
from scripts.autowfo import ranking as r


def test_choose_score_col_wrapper_matches_module():
    df = pd.DataFrame({"avg_total_return_pct": [1.0, 2.0], "oos_avg_total_return_pct": [None, None]})
    assert sweep._choose_score_col(df) == r._choose_score_col(df)
    assert sweep._choose_score_col(df) == "avg_total_return_pct"


def test_sort_by_score_tie_break_behavior():
    df = pd.DataFrame(
        {
            "oos_avg_total_return_pct": [10.0, 10.0, 8.0],
            "avg_hold_hours": [5.0, 2.0, 1.0],
            "name": ["a", "b", "c"],
        }
    )
    sorted_df, score_col = sweep._sort_by_score(df, tie_break_avg_hold=True)
    assert score_col == "oos_avg_total_return_pct"
    assert sorted_df.iloc[0]["name"] == "b"


def test_top_by_score_wrapper_matches_module():
    df = pd.DataFrame(
        {
            "oos_avg_total_return_pct": [1.0, 3.0, 2.0],
            "avg_total_return_pct": [1.0, 3.0, 2.0],
            "name": ["x", "y", "z"],
        }
    )
    expected_df, expected_col = r._top_by_score(df, top_n=2, tie_break_avg_hold=False)
    actual_df, actual_col = sweep._top_by_score(df, top_n=2, tie_break_avg_hold=False)

    pd.testing.assert_frame_equal(actual_df.reset_index(drop=True), expected_df.reset_index(drop=True))
    assert actual_col == expected_col
