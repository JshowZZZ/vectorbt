import json

import pandas as pd

from autowfo import live_signal_producer


def _sample_bundle_manifest(tmp_path):
    return {
        "schema_version": "1.0.0",
        "analysis": {
            "main_run_id": "run_001",
            "selected_row": {
                "timeframe": "2h",
                "data_days": 180,
                "max_hold": 4,
            },
        },
        "source": {
            "run_root": str(tmp_path / "run_001"),
            "timeframe": "2h",
            "pairs": ["LTC/BTC", "ETH/BTC"],
        },
        "replay_contract": {
            "strategy_mode": "combo_entry",
        },
        "freqtrade": {
            "strategy_path": "scripts/freqtrade_generic_signal_strategy.py",
        },
    }


def test_export_live_signal_store_writes_tailed_manifest(tmp_path, monkeypatch):
    bundle_manifest = _sample_bundle_manifest(tmp_path)
    signal_df = pd.DataFrame(
        [
            {
                "date": f"2026-04-13T0{hour}:00:00",
                "pair": pair,
                "close": 1.0 + hour,
                "signal_long": 1 if hour == 3 else 0,
                "signal_short": 0,
                "enter_long": 1 if hour == 4 else 0,
                "enter_short": 0,
                "exit_long": 0,
                "exit_short": 0,
                "explicit_exit_long": 0,
                "explicit_exit_short": 0,
            }
            for pair in ("LTC/BTC", "ETH/BTC")
            for hour in range(1, 6)
        ]
    )

    monkeypatch.setattr(
        live_signal_producer.pilot_analysis,
        "load_run_analysis_inputs",
        lambda path_or_run_id: {"run_id": "run_001", "run_root": tmp_path / "run_001", "metadata": {}},
    )
    monkeypatch.setattr(
        live_signal_producer.freqtrade_bridge,
        "reconstruct_frozen_lane",
        lambda *args, **kwargs: {
            "signal_df": signal_df,
            "summary": {"trade_count": 3},
            "has_short_signals": True,
        },
    )
    monkeypatch.setattr(live_signal_producer.autowfo_data, "_has_parquet_engine", lambda: False)

    out_dir = tmp_path / "live_signal_store"
    payload = live_signal_producer.export_live_signal_store(
        bundle_manifest,
        manifest_path=tmp_path / "signal_manifest.json",
        out_dir=out_dir,
        tail_bars=2,
    )

    assert payload["signals"]["primary_format"] == "csv"
    assert payload["signals"]["rows"] == 6
    assert payload["signals"]["pairs"] == ["ETH/BTC", "LTC/BTC"]
    assert payload["runtime"]["tail_bars_per_pair"] == 3
    assert payload["freqtrade"]["recommended_strategy"] == "AutowfoLiveSignalStrategyLongShort"

    manifest_path = out_dir / "live_manifest.json"
    csv_path = out_dir / "current_signals.csv"
    assert manifest_path.exists()
    assert csv_path.exists()

    stored_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    stored_signal_df = pd.read_csv(csv_path)
    assert stored_manifest["signals"]["last_bar_utc"] == "2026-04-13T05:00:00"
    assert len(stored_signal_df) == 6
