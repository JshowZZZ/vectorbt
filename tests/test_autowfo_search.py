from scripts import run_btc_regime_sweep as sweep
from scripts.autowfo import search as s


def test_normalize_key_value_wrapper_matches_module():
    assert sweep._normalize_key_value(None) == s._normalize_key_value(None)
    assert sweep._normalize_key_value(1.23456789) == s._normalize_key_value(1.23456789)
    assert sweep._normalize_key_value(5) == s._normalize_key_value(5)


def test_combo_key_from_dict_wrapper_matches_module():
    values = {
        "timeframe": "3m",
        "data_days": 180,
        "fees": 0.001234567,
        "filter_name": "rsi+roc",
    }
    expected = s._combo_key_from_dict(values, sweep.COMBO_KEY_FIELDS)
    actual = sweep._combo_key_from_dict(values)
    assert actual == expected
