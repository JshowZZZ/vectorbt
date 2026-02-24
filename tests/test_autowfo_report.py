import pandas as pd

from scripts import run_btc_regime_sweep as sweep
from scripts.autowfo import engine as e
from scripts.autowfo import report as r
from scripts.autowfo import search as s


def _build_sweep_adapters():
    return e._build_sweep_adapter_functions(
        combo_key_fields=sweep.COMBO_KEY_FIELDS,
        strict_config_fields=sweep.STRICT_CONFIG_FIELDS,
        indicator_meta=sweep.INDICATOR_META,
        filter_name_map=sweep.FILTER_NAME_MAP,
        regime_name_map=sweep.REGIME_NAME_MAP,
        regime_type_map=sweep.REGIME_TYPE_MAP,
        combo_key_from_dict_impl_fn=s._combo_key_from_dict,
        indicator_combo_label_impl_fn=r._indicator_combo_label,
        format_indicator_list_impl_fn=r._format_indicator_list,
        df_to_html_impl_fn=r._df_to_html,
    )


def test_format_indicator_list_adapter_matches_module():
    adapters = _build_sweep_adapters()
    value = "rsi,roc"
    expected = r._format_indicator_list(value, sweep.INDICATOR_META)
    actual = adapters["format_indicator_list_fn"](value)
    assert actual == expected


def test_df_to_html_adapter_matches_module():
    adapters = _build_sweep_adapters()
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
    actual = adapters["df_to_html_fn"](df, columns, sweep.LABELS)
    assert actual == expected


def test_combo_key_and_config_field_adapters_match_module_behavior():
    adapters = _build_sweep_adapters()
    payload = {
        "exchange": "binance",
        "base_symbol": "BTC/USDT",
        "trade_symbols_key": "ETH/BTC",
        "capital_mode": "shared",
        "fees": 0.001,
        "order_size_pct": 0.5,
        "max_concurrent_positions": 2,
        "init_cash_usdt": 1000.0,
        "wf_train_days": 7,
        "wf_test_days": 2,
        "wf_step_days": 2,
        "wf_valid_days": 0,
        "wf_mode": "rolling",
        "data_start": "2024-01-01",
        "data_end": "2024-02-01",
    }
    expected_key = s._combo_key_from_dict(payload, sweep.COMBO_KEY_FIELDS)
    actual_key = adapters["combo_key_from_dict_fn"](payload)
    assert actual_key == expected_key
    assert adapters["has_all_config_fields_fn"](payload)
    assert not adapters["has_all_config_fields_fn"]({**payload, "wf_mode": ""})
