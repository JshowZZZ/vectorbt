import pandas as pd

from scripts import run_btc_regime_sweep as sweep
from scripts.autowfo import report as r


def test_format_duration_wrapper_matches_module():
    assert sweep._format_duration(3661) == r._format_duration(3661)
    assert sweep._format_duration(None) == r._format_duration(None)


def test_format_indicator_list_wrapper_matches_module():
    value = "rsi,roc"
    expected = r._format_indicator_list(value, sweep.INDICATOR_META)
    actual = sweep._format_indicator_list(value)
    assert actual == expected


def test_df_to_html_wrapper_matches_module():
    df = pd.DataFrame(
        [
            {
                "filter_name": "none",
                "indicator_list": "rsi,roc",
                "regime_name": "trend_high",
                "regime_type": "trend",
                "avg_total_return_pct": 12.34567,
            }
        ]
    )
    columns = [
        "filter_name",
        "indicator_list",
        "regime_name",
        "regime_type",
        "avg_total_return_pct",
    ]
    expected = r._df_to_html(
        df,
        columns,
        sweep.LABELS,
        sweep.FILTER_NAME_MAP,
        sweep.REGIME_NAME_MAP,
        sweep.REGIME_TYPE_MAP,
        format_indicator_list_fn=lambda value: r._format_indicator_list(value, sweep.INDICATOR_META),
    )
    actual = sweep._df_to_html(df, columns, sweep.LABELS)
    assert actual == expected
