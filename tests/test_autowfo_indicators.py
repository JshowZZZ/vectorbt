import importlib
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PLUGIN_MODULES = [
    "scripts.autowfo.indicators.rsi",
    "scripts.autowfo.indicators.macd",
    "scripts.autowfo.indicators.bb",
    "scripts.autowfo.indicators.ema",
    "scripts.autowfo.indicators.volume",
]

EXPECTED_INDICATORS = {"RSI", "MACD", "BB", "EMA", "Volume"}


def _reload_indicators_package():
    import scripts.autowfo.indicators as indicators

    importlib.invalidate_caches()
    return importlib.reload(indicators)


def _default_params(module):
    return {name: meta["default"] for name, meta in module.PARAMS.items()}


@pytest.fixture
def sample_ohlcv() -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=200, freq="h")
    base = np.linspace(100.0, 130.0, len(idx))
    wave = np.sin(np.linspace(0.0, 10.0, len(idx)))
    close = base + wave
    data = pd.DataFrame(
        {
            "open": close - 0.2,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": np.linspace(1000.0, 2500.0, len(idx)),
        },
        index=idx,
    )
    return data


def test_registry_contains_expected_plugins():
    indicators = _reload_indicators_package()
    assert set(indicators.REGISTRY.keys()) == EXPECTED_INDICATORS
    assert len(indicators.REGISTRY) == 5
    assert indicators.REGISTRY["RSI"].INDICATOR_ID == "RSI"
    assert indicators.REGISTRY["MACD"].INDICATOR_ID == "MACD"
    assert indicators.REGISTRY["BB"].INDICATOR_ID == "BB"
    assert indicators.REGISTRY["EMA"].INDICATOR_ID == "EMA"
    assert indicators.REGISTRY["Volume"].INDICATOR_ID == "Volume"


@pytest.mark.parametrize("module_name", PLUGIN_MODULES)
def test_plugin_module_importable(module_name):
    module = importlib.import_module(module_name)
    assert hasattr(module, "compute")
    assert callable(module.compute)


@pytest.mark.parametrize("module_name", PLUGIN_MODULES)
def test_compute_returns_series_with_input_index_and_no_inplace_mutation(module_name, sample_ohlcv):
    module = importlib.import_module(module_name)
    before = sample_ohlcv.copy(deep=True)
    result = module.compute(sample_ohlcv, _default_params(module))
    assert isinstance(result, pd.Series)
    pd.testing.assert_index_equal(result.index, sample_ohlcv.index)
    pd.testing.assert_frame_equal(sample_ohlcv, before)


def test_registry_auto_discovers_new_plugin():
    indicators = _reload_indicators_package()
    pkg_dir = Path(indicators.__file__).resolve().parent
    plugin_name = "zz_awf125_temp_plugin"
    plugin_path = pkg_dir / f"{plugin_name}.py"
    module_name = f"{indicators.__name__}.{plugin_name}"
    plugin_source = """
import pandas as pd

INDICATOR_ID = "AWF125_TEMP"
DISPLAY_NAME = "AWF125 Temp"
PARAMS = {}
CONDITION_OPERATORS = ["above"]

def compute(ohlcv_df: pd.DataFrame, params: dict) -> pd.Series:
    return pd.Series(0.0, index=ohlcv_df.index)
"""
    plugin_path.write_text(plugin_source.strip() + "\n", encoding="utf-8")
    try:
        indicators = _reload_indicators_package()
        assert "AWF125_TEMP" in indicators.REGISTRY
    finally:
        if plugin_path.exists():
            plugin_path.unlink()
        sys.modules.pop(module_name, None)
        _reload_indicators_package()


def test_registry_skips_syntax_error_plugin_with_warning(caplog):
    indicators = _reload_indicators_package()
    pkg_dir = Path(indicators.__file__).resolve().parent
    plugin_name = "zz_awf125_broken_plugin"
    plugin_path = pkg_dir / f"{plugin_name}.py"
    module_name = f"{indicators.__name__}.{plugin_name}"
    plugin_path.write_text("def compute(:\n    return None\n", encoding="utf-8")
    try:
        with caplog.at_level(logging.WARNING):
            indicators = _reload_indicators_package()
        assert plugin_name not in [m.__name__.split(".")[-1] for m in indicators.REGISTRY.values()]
        assert "Failed to load indicator plugin" in caplog.text
        assert f"{plugin_name}.py" in caplog.text
    finally:
        if plugin_path.exists():
            plugin_path.unlink()
        sys.modules.pop(module_name, None)
        _reload_indicators_package()

