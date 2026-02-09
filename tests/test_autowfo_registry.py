import json

import pandas as pd

from scripts.autowfo import registry as r


def test_update_run_registry_creates_file_and_coverage(tmp_path):
    registry_path = tmp_path / "run_registry.json"
    run_metadata = {
        "run_id": "20260209_010000",
        "timestamp_utc": "2026-02-09T01:00:00Z",
        "search_mode": "combo",
        "config_sha256": "cfg_hash",
        "data_fingerprint": "data_hash",
        "timeframes": [{"timeframe": "1h", "days": 60}],
        "trade_symbols": ["ETH/BTC", "BNB/BTC"],
    }
    best_row = {
        "timeframe": "1h",
        "data_days": 60,
        "avg_total_return_pct": 1.2,
        "oos_avg_total_return_pct": 0.8,
        "report_file": "btc_regime_ETH-BTC_20260209_010000.html",
    }
    per_symbol_df = pd.DataFrame(
        [
            {"timeframe": "1h", "symbol": "ETH/BTC"},
            {"timeframe": "1h", "symbol": "BNB/BTC"},
            {"timeframe": "4h", "symbol": "ETH/BTC"},
        ]
    )

    payload = r._update_run_registry(
        registry_path=str(registry_path),
        run_metadata=run_metadata,
        best_row=best_row,
        per_symbol_df=per_symbol_df,
        updated_utc="2026-02-09T01:00:00Z",
    )
    assert registry_path.exists()
    assert payload["runs"][0]["run_id"] == "20260209_010000"
    tested_pairs = payload["coverage"]["tested_pairs"]
    assert {"timeframe": "1h", "symbol": "ETH/BTC"} in tested_pairs
    assert {"timeframe": "4h", "symbol": "ETH/BTC"} in tested_pairs
    assert {"timeframe": "4h", "symbol": "BNB/BTC"} in payload["coverage"]["untested_pairs"]


def test_update_run_registry_replaces_same_run_id(tmp_path):
    registry_path = tmp_path / "run_registry.json"
    base_metadata = {
        "run_id": "same_id",
        "timestamp_utc": "2026-02-09T01:00:00Z",
        "search_mode": "combo",
        "config_sha256": "a",
        "data_fingerprint": "b",
        "timeframes": [{"timeframe": "1h", "days": 60}],
        "trade_symbols": ["ETH/BTC"],
    }
    best_row = {"timeframe": "1h", "data_days": 60, "report_file": "r1.html"}

    r._update_run_registry(
        registry_path=str(registry_path),
        run_metadata=base_metadata,
        best_row=best_row,
        per_symbol_df=pd.DataFrame([{"timeframe": "1h", "symbol": "ETH/BTC"}]),
        updated_utc="2026-02-09T01:00:00Z",
    )
    newer = dict(base_metadata)
    newer["timestamp_utc"] = "2026-02-09T02:00:00Z"
    r._update_run_registry(
        registry_path=str(registry_path),
        run_metadata=newer,
        best_row={"timeframe": "4h", "data_days": 120, "report_file": "r2.html"},
        per_symbol_df=pd.DataFrame([{"timeframe": "4h", "symbol": "ETH/BTC"}]),
        updated_utc="2026-02-09T02:00:00Z",
    )

    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    assert len(payload["runs"]) == 1
    assert payload["runs"][0]["best_timeframe"] == "4h"
