import json
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pandas as pd

from autowfo import freqtrade_bridge


def _sample_analysis_payload():
    return {
        "canonical_gate_passed": [
            {
                "timeframe": "2h",
                "data_days": 180,
                "indicator_list": "obv_roc,keltner_pos",
                "regime_name": "trend_any",
                "vol_mode": "any",
                "filter_name": "OBV ROC + Keltner Position",
                "vol_lookback": 24,
                "vol_z": 0.8,
                "mom_lookback": 6,
                "trade_mom_lookback": 3,
                "tp_stop": 1.5,
                "sl_stop": 1.0,
                "max_hold": 4,
            }
        ],
        "top_gate_passed": [],
        "top_stable_positive": [],
        "main_run": {"run_id": "run_001"},
    }


def _sample_manifest(tmp_path, *, has_short_signals=False):
    autowfo_trades_path = tmp_path / "autowfo_trades.csv"
    pd.DataFrame(
        [
            {
                "pair": "ETH/BTC",
                "entry_timestamp": "2026-04-01T00:00:00",
                "exit_timestamp": "2026-04-01T02:00:00",
                "direction": "Long",
                "return_ratio": 0.02,
                "return_pct": 2.0,
                "pnl": 0.01,
                "status": "Closed",
            }
        ]
    ).to_csv(autowfo_trades_path, index=False)
    return {
        "schema_version": freqtrade_bridge.SIGNAL_BUNDLE_MANIFEST_VERSION,
        "signal_store_schema_version": freqtrade_bridge.SIGNAL_STORE_SCHEMA_VERSION,
        "analysis": {
            "selection": "canonical_gate_passed",
            "rank": 1,
            "main_run_id": "run_001",
            "selected_row": {"timeframe": "2h", "data_days": 180},
        },
        "source": {
            "run_root": str(tmp_path / "run_001"),
            "exchange": "binance",
            "base_symbol": "BTC/USDT",
            "quote_currency": "BTC",
            "timeframe": "2h",
            "data_days": 180,
            "pairs": ["ETH/BTC", "ADA/BTC"],
        },
        "signals": {
            "primary_format": "parquet",
            "path": str(tmp_path / "signals.parquet"),
            "csv_path": str(tmp_path / "signals.csv"),
            "columns": [
                "date",
                "pair",
                "close",
                "signal_long",
                "signal_short",
                "enter_long",
                "enter_short",
                "exit_long",
                "exit_short",
                "explicit_exit_long",
                "explicit_exit_short",
            ],
            "has_short_signals": has_short_signals,
        },
        "autowfo_replay": {
            "summary": {"trade_count": 1, "total_return_pct": 2.0},
            "trades_path": str(autowfo_trades_path),
        },
        "freqtrade": {
            "strategy_path": str(tmp_path / "freqtrade_generic_signal_strategy.py"),
            "recommended_strategy": (
                "AutowfoGenericSignalStrategyLongShort"
                if has_short_signals
                else "AutowfoGenericSignalStrategyLongOnly"
            ),
            "recommended_trading_mode": "futures" if has_short_signals else "spot",
        },
    }


def test_select_analysis_candidate_resolves_alias():
    selected = freqtrade_bridge.select_analysis_candidate(_sample_analysis_payload(), selection="canonical", rank=1)

    assert selected["analysis_bucket"] == "canonical_gate_passed"
    assert selected["analysis_rank"] == 1
    assert selected["indicator_list"] == "obv_roc,keltner_pos"


def test_build_freqtrade_backtest_config_uses_long_only_defaults(tmp_path):
    manifest = _sample_manifest(tmp_path, has_short_signals=False)
    datadir = tmp_path / "user_data" / "data" / "binance"
    datadir.mkdir(parents=True)

    payload = freqtrade_bridge.build_freqtrade_backtest_config(
        manifest,
        manifest_path=tmp_path / "signal_manifest.json",
        datadir=datadir,
    )

    assert payload["strategy"] == "AutowfoGenericSignalStrategyLongOnly"
    assert payload["trading_mode"] == "spot"
    assert payload["exchange"]["pair_whitelist"] == ["ETH/BTC", "ADA/BTC"]
    assert payload["stake_currency"] == "BTC"
    assert payload["user_data_dir"] == str((tmp_path / "user_data").resolve())
    assert payload["entry_pricing"]["price_side"] == "same"
    assert payload["exit_pricing"]["price_side"] == "same"
    assert payload["entry_pricing"]["use_order_book"] is True
    assert payload["exit_pricing"]["use_order_book"] is True


def test_build_freqtrade_backtest_config_rejects_short_signals_in_spot_mode(tmp_path):
    manifest = _sample_manifest(tmp_path, has_short_signals=True)
    datadir = tmp_path / "user_data" / "data" / "binance"
    datadir.mkdir(parents=True)

    try:
        freqtrade_bridge.build_freqtrade_backtest_config(
            manifest,
            manifest_path=tmp_path / "signal_manifest.json",
            datadir=datadir,
            trading_mode="spot",
        )
    except ValueError as exc:
        assert "requires trading_mode=futures" in str(exc)
    else:
        raise AssertionError("expected short-signal bundle to reject spot mode")


def test_build_freqtrade_backtest_config_maps_futures_pairs_to_route_b(tmp_path):
    manifest = _sample_manifest(tmp_path, has_short_signals=True)
    datadir = tmp_path / "user_data" / "data" / "binance"
    datadir.mkdir(parents=True)

    payload = freqtrade_bridge.build_freqtrade_backtest_config(
        manifest,
        manifest_path=tmp_path / "signal_manifest.json",
        datadir=datadir,
    )

    assert payload["trading_mode"] == "futures"
    assert payload["stake_currency"] == "USDT"
    assert payload["exchange"]["pair_whitelist"] == ["ETH/USDT:USDT", "ADA/USDT:USDT"]
    assert payload["autowfo_pair_mapping"] == {
        "ETH/BTC": "ETH/USDT:USDT",
        "ADA/BTC": "ADA/USDT:USDT",
    }
    assert payload["exchange"]["ccxt_config"] == {"options": {"defaultType": "future"}}
    assert payload["exchange"]["ccxt_async_config"] == {"options": {"defaultType": "future"}}


def test_build_freqtrade_backtest_command_uses_strategy_directory(tmp_path):
    strategy_file = tmp_path / "strategies" / "freqtrade_generic_signal_strategy.py"
    strategy_file.parent.mkdir(parents=True)
    strategy_file.write_text("# stub\n", encoding="utf-8")

    command = freqtrade_bridge.build_freqtrade_backtest_command(
        freqtrade_exe=tmp_path / "freqtrade.exe",
        config_path=tmp_path / "config.json",
        strategy_name="AutowfoGenericSignalStrategyLongOnly",
        strategy_path=strategy_file,
        datadir=tmp_path / "user_data" / "data" / "binance",
        backtest_directory=tmp_path / "backtest-results",
        fee=0.001,
    )

    assert "--strategy-path" in command
    strategy_index = command.index("--strategy-path") + 1
    assert command[strategy_index] == str(strategy_file.parent.resolve())
    assert "--backtest-directory" in command
    backtest_dir_index = command.index("--backtest-directory") + 1
    assert command[backtest_dir_index] == str((tmp_path / "backtest-results").resolve())


def test_load_freqtrade_backtest_result_parses_trades(tmp_path):
    payload = {
        "strategy": {
            "AutowfoGenericSignalStrategyLongOnly": {
                "trades": [
                    {
                        "pair": "ETH/BTC",
                        "open_date": "2026-04-01T00:00:00+00:00",
                        "close_date": "2026-04-01T02:00:00+00:00",
                        "profit_ratio": 0.02,
                        "exit_reason": "exit_signal",
                        "is_short": False,
                    }
                ],
                "total_trades": 1,
                "profit_total": 0.02,
            }
        }
    }
    result_path = tmp_path / "backtest-result.json"
    result_path.write_text(json.dumps(payload), encoding="utf-8")

    result = freqtrade_bridge.load_freqtrade_backtest_result(result_path)

    assert result["strategy_name"] == "AutowfoGenericSignalStrategyLongOnly"
    assert result["summary"]["total_trades"] == 1
    assert result["trades_df"].iloc[0]["pair"] == "ETH/BTC"
    assert result["trades_df"].iloc[0]["direction"] == "Long"


def test_load_freqtrade_backtest_result_reads_zip_payload(tmp_path):
    payload = {
        "strategy": {
            "AutowfoGenericSignalStrategyLongOnly": {
                "trades": [
                    {
                        "pair": "ETH/BTC",
                        "open_date": "2026-04-01T00:00:00+00:00",
                        "close_date": "2026-04-01T02:00:00+00:00",
                        "profit_ratio": 0.02,
                        "exit_reason": "exit_signal",
                        "is_short": False,
                    }
                ],
                "total_trades": 1,
            }
        }
    }
    result_zip = tmp_path / "backtest-result.zip"
    with zipfile.ZipFile(result_zip, mode="w") as archive:
        archive.writestr("backtest-result.json", json.dumps(payload))
        archive.writestr("backtest-result_config.json", json.dumps({"strategy": "ignored"}))

    result = freqtrade_bridge.load_freqtrade_backtest_result(result_zip)

    assert result["strategy_name"] == "AutowfoGenericSignalStrategyLongOnly"
    assert result["trades_df"].iloc[0]["pair"] == "ETH/BTC"


def test_resolve_backtest_result_path_uses_last_result_pointer(tmp_path):
    result_zip = tmp_path / "backtest-result.zip"
    result_zip.write_bytes(b"zip-bytes-placeholder")
    (tmp_path / ".last_result.json").write_text(
        json.dumps({"latest_backtest": result_zip.name}),
        encoding="utf-8",
    )

    resolved = freqtrade_bridge._resolve_backtest_result_path(tmp_path)

    assert resolved == result_zip.resolve()


def test_compare_trade_sets_reports_exact_matches():
    autowfo_trades = pd.DataFrame(
        [
            {
                "pair": "ETH/BTC",
                "entry_timestamp": "2026-04-01T00:00:00",
                "exit_timestamp": "2026-04-01T02:00:00",
                "direction": "Long",
                "return_ratio": 0.02,
            }
        ]
    )
    freqtrade_trades = pd.DataFrame(
        [
            {
                "pair": "ETH/BTC",
                "entry_timestamp": "2026-04-01T00:00:00",
                "exit_timestamp": "2026-04-01T02:00:00",
                "direction": "Long",
                "profit_ratio": 0.021,
            }
        ]
    )

    comparison = freqtrade_bridge.compare_trade_sets(autowfo_trades, freqtrade_trades)

    assert comparison["verdict"] == "passed"
    assert comparison["exact_match_count"] == 1
    assert comparison["trade_count_delta"] == 0
    assert comparison["profit_ratio_abs_delta_mean"] == 0.0010000000000000009


def test_build_parity_report_includes_trade_comparison(tmp_path):
    manifest = _sample_manifest(tmp_path, has_short_signals=True)
    freqtrade_result = {
        "strategy_name": "AutowfoGenericSignalStrategyLongShort",
        "summary": {"total_trades": 1, "profit_total": 0.02},
        "trades_df": pd.DataFrame(
            [
                {
                    "pair": "ETH/USDT:USDT",
                    "entry_timestamp": "2026-04-01T00:00:00",
                    "exit_timestamp": "2026-04-01T02:00:00",
                    "direction": "Long",
                    "profit_ratio": 0.02,
                    "exit_reason": "exit_signal",
                }
            ]
        ),
    }

    report = freqtrade_bridge.build_parity_report(manifest, freqtrade_result=freqtrade_result)

    assert report["freqtrade"]["strategy_name"] == "AutowfoGenericSignalStrategyLongShort"
    assert report["freqtrade"]["autowfo_pair_mapping"]["ETH/BTC"] == "ETH/USDT:USDT"
    assert report["trade_comparison"]["exact_match_count"] == 1
    assert report["trade_comparison"]["verdict"] == "passed"


def test_run_freqtrade_cross_check_passes_timeout_to_subprocess(tmp_path, monkeypatch):
    manifest = _sample_manifest(tmp_path, has_short_signals=False)
    manifest_path = tmp_path / "signal_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    captured = {}

    monkeypatch.setattr(
        freqtrade_bridge,
        "build_freqtrade_backtest_config",
        lambda *args, **kwargs: {
            "strategy": "AutowfoGenericSignalStrategyLongOnly",
            "exchange": {"pair_whitelist": ["ETH/BTC"]},
        },
    )
    monkeypatch.setattr(
        freqtrade_bridge,
        "build_freqtrade_backtest_command",
        lambda **kwargs: ["freqtrade", "backtesting"],
    )

    def fake_run(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(freqtrade_bridge.subprocess, "run", fake_run)
    monkeypatch.setattr(freqtrade_bridge, "_resolve_backtest_result_path", lambda out_dir: Path(out_dir) / "backtest-result.json")
    monkeypatch.setattr(
        freqtrade_bridge,
        "load_freqtrade_backtest_result",
        lambda result_path, strategy_name=None: {
            "strategy_name": strategy_name or "AutowfoGenericSignalStrategyLongOnly",
            "summary": {"total_trades": 0},
            "trades_df": pd.DataFrame(),
        },
    )
    monkeypatch.setattr(
        freqtrade_bridge,
        "build_parity_report",
        lambda manifest, *, freqtrade_result: {"trade_comparison": {"verdict": "passed"}},
    )

    payload = freqtrade_bridge.run_freqtrade_cross_check(
        manifest,
        manifest_path=manifest_path,
        out_dir=tmp_path / "cross_check",
        datadir=tmp_path / "user_data" / "data" / "binance",
        execute=True,
    )

    assert payload["executed"] is True
    assert captured["args"][0] == ["freqtrade", "backtesting"]
    assert captured["kwargs"]["timeout"] == 900
