import importlib
import json

import pytest

from autowfo import strategy_schema as ss


def test_default_strategy_schema_contains_expected_inventory():
    schema = ss.load_strategy_schema()
    assert schema["schema_version"] == "1.0.0"
    assert len(schema["indicators"]) == 25
    assert len(schema["regimes"]) == 8
    assert any(item["key"] == "ma_trend" for item in schema["indicators"])
    assert any(item["key"] == "cci" for item in schema["indicators"])
    assert any(item["key"] == "chop" for item in schema["indicators"])
    assert any(item["name"] == "trend_high" for item in schema["regimes"])


def test_validate_strategy_schema_rejects_duplicate_indicator_keys(tmp_path):
    schema = ss.load_strategy_schema()
    schema["indicators"] = [
        {"key": "dup", "label": "A", "category": "volume"},
        {"key": "dup", "label": "B", "category": "volume"},
    ]
    path = tmp_path / "bad_strategy_schema.json"
    path.write_text(json.dumps(schema), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate indicator key"):
        ss.load_strategy_schema(str(path))


def test_validate_strategy_schema_rejects_unknown_regime_type(tmp_path):
    schema = ss.load_strategy_schema()
    schema["regimes"][0]["type"] = "unknown_type"
    path = tmp_path / "bad_strategy_schema.json"
    path.write_text(json.dumps(schema), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown_type"):
        ss.load_strategy_schema(str(path))


def test_constants_fail_fast_when_schema_invalid(monkeypatch, tmp_path):
    schema = ss.load_strategy_schema()
    schema["regimes"][0]["name"] = ""
    bad_path = tmp_path / "invalid_strategy_schema.json"
    bad_path.write_text(json.dumps(schema), encoding="utf-8")

    import autowfo.constants as constants_module
    import autowfo.run_btc_regime_sweep as sweep_module

    monkeypatch.setenv(ss.STRATEGY_SCHEMA_PATH_ENV, str(bad_path))
    try:
        with pytest.raises(ValueError, match="regimes\\[0\\]\\.name"):
            importlib.reload(constants_module)
    finally:
        monkeypatch.delenv(ss.STRATEGY_SCHEMA_PATH_ENV, raising=False)
        importlib.reload(constants_module)
        importlib.reload(sweep_module)

