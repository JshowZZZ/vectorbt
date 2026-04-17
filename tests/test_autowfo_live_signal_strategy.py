import importlib.util
import json
from pathlib import Path

import pandas as pd


def _load_strategy_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "freqtrade_generic_signal_strategy.py"
    spec = importlib.util.spec_from_file_location("autowfo_freqtrade_generic_signal_strategy", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_live_strategy_resolves_source_pair_mapping(tmp_path):
    module = _load_strategy_module()
    signals_path = tmp_path / "current_signals.csv"
    pd.DataFrame(
        [
            {
                "date": "2026-04-13T08:00:00",
                "pair": "LTC/BTC",
                "close": 1.0,
                "signal_long": 1,
                "signal_short": 0,
                "enter_long": 0,
                "enter_short": 0,
                "exit_long": 0,
                "exit_short": 0,
                "explicit_exit_long": 0,
                "explicit_exit_short": 0,
            },
            {
                "date": "2026-04-13T10:00:00",
                "pair": "LTC/BTC",
                "close": 1.1,
                "signal_long": 0,
                "signal_short": 0,
                "enter_long": 1,
                "enter_short": 0,
                "exit_long": 1,
                "exit_short": 0,
                "explicit_exit_long": 0,
                "explicit_exit_short": 0,
            }
        ]
    ).to_csv(signals_path, index=False)
    manifest_path = tmp_path / "live_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "source": {"timeframe": "2h", "data_end": "2026-04-13T10:00:00"},
                "signals": {
                    "csv_path": str(signals_path),
                    "path": "",
                    "last_bar_utc": "2026-04-13T10:00:00",
                },
                "runtime": {"staleness_ttl_bars": 1.5},
            }
        ),
        encoding="utf-8",
    )

    module.AutowfoLiveSignalStrategyLongShort._autowfo_live_cache = None
    strategy = module.AutowfoLiveSignalStrategyLongShort()
    strategy.config = {
        "autowfo_signal_manifest": str(manifest_path),
        "autowfo_pair_mapping": {"LTC/BTC": "LTC/USDT:USDT"},
        "autowfo_staleness_ttl_bars": 1000,
    }
    dataframe = pd.DataFrame(
        {
            "date": ["2026-04-13T08:00:00", "2026-04-13T10:00:00"],
            "close": [100.0, 101.0],
        }
    )

    result = strategy.populate_indicators(dataframe, {"pair": "LTC/USDT:USDT"})
    entry_result = strategy.populate_entry_trend(result.copy(), {"pair": "LTC/USDT:USDT"})
    exit_result = strategy.populate_exit_trend(result.copy(), {"pair": "LTC/USDT:USDT"})

    assert "close" in result.columns
    assert result["signal_long"].astype(int).tolist() == [1, 0]
    assert result["enter_long"].astype(int).tolist() == [0, 1]
    assert entry_result["enter_long"].astype(int).tolist() == [1, 0]
    assert entry_result["enter_short"].astype(int).tolist() == [0, 0]
    assert exit_result["exit_long"].astype(int).tolist() == [1, 0]
    assert exit_result["exit_short"].astype(int).tolist() == [0, 0]


def test_static_strategy_resolves_source_pair_mapping(tmp_path):
    module = _load_strategy_module()
    signals_path = tmp_path / "signals.csv"
    pd.DataFrame(
        [
            {
                "date": "2026-04-13T08:00:00",
                "pair": "LTC/BTC",
                "close": 1.0,
                "signal_long": 1,
                "signal_short": 0,
                "enter_long": 0,
                "enter_short": 0,
                "exit_long": 0,
                "exit_short": 0,
                "explicit_exit_long": 0,
                "explicit_exit_short": 0,
            },
            {
                "date": "2026-04-13T10:00:00",
                "pair": "LTC/BTC",
                "close": 1.1,
                "signal_long": 0,
                "signal_short": 0,
                "enter_long": 1,
                "enter_short": 0,
                "exit_long": 1,
                "exit_short": 0,
                "explicit_exit_long": 0,
                "explicit_exit_short": 0,
            }
        ]
    ).to_csv(signals_path, index=False)
    manifest_path = tmp_path / "signal_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "signals": {
                    "csv_path": str(signals_path),
                    "path": "",
                }
            }
        ),
        encoding="utf-8",
    )

    module.AutowfoGenericSignalStrategyLongShort._autowfo_manifest = None
    module.AutowfoGenericSignalStrategyLongShort._autowfo_signal_frames = None
    strategy = module.AutowfoGenericSignalStrategyLongShort()
    strategy.config = {
        "autowfo_signal_manifest": str(manifest_path),
        "autowfo_pair_mapping": {"LTC/BTC": "LTC/USDT:USDT"},
    }
    strategy.bot_start()
    dataframe = pd.DataFrame(
        {
            "date": ["2026-04-13T08:00:00", "2026-04-13T10:00:00"],
            "close": [100.0, 101.0],
        }
    )

    result = strategy.populate_indicators(dataframe, {"pair": "LTC/USDT:USDT"})
    entry_result = strategy.populate_entry_trend(result.copy(), {"pair": "LTC/USDT:USDT"})
    exit_result = strategy.populate_exit_trend(result.copy(), {"pair": "LTC/USDT:USDT"})

    assert "close" in result.columns
    assert result["signal_long"].astype(int).tolist() == [1, 0]
    assert result["enter_long"].astype(int).tolist() == [0, 1]
    assert entry_result["enter_long"].astype(int).tolist() == [1, 0]
    assert entry_result["enter_short"].astype(int).tolist() == [0, 0]
    assert exit_result["exit_long"].astype(int).tolist() == [1, 0]
    assert exit_result["exit_short"].astype(int).tolist() == [0, 0]


def test_manifest_is_stale_when_last_bar_exceeds_ttl():
    module = _load_strategy_module()
    manifest = {
        "source": {"timeframe": "2h", "data_end": "2026-04-13T00:00:00"},
        "signals": {"last_bar_utc": "2026-04-13T00:00:00"},
        "runtime": {"staleness_ttl_bars": 1.5},
    }
    assert module._manifest_is_stale(manifest, {"autowfo_staleness_ttl_bars": 0}) is True
