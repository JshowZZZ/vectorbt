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


# -- _build_coverage_map target dimensions ----------------------------------

def test_build_coverage_map_without_targets_ignores_unseen_timeframes():
    """Without target args, 1h doesn't appear if no run used it."""
    per_symbol_df = pd.DataFrame([
        {"timeframe": "2h", "symbol": "ETH/USDT"},
        {"timeframe": "4h", "symbol": "ETH/USDT"},
    ])
    run_entries = [
        {"timeframes": [{"timeframe": "2h", "days": 120}, {"timeframe": "4h", "days": 180}],
         "trade_symbols": ["ETH/USDT", "BNB/USDT"]},
    ]
    cov = r._build_coverage_map(per_symbol_df, run_entries)
    assert "1h" not in cov["timeframes"]
    # 2h×BNB and 4h×BNB should be untested
    untested_keys = {(p["timeframe"], p["symbol"]) for p in cov["untested_pairs"]}
    assert ("2h", "BNB/USDT") in untested_keys
    assert ("4h", "BNB/USDT") in untested_keys


def test_build_coverage_map_with_targets_surfaces_unseen_gaps():
    """With target_timeframes=['1h','2h','4h'], 1h gaps become visible."""
    per_symbol_df = pd.DataFrame([
        {"timeframe": "2h", "symbol": "ETH/USDT"},
        {"timeframe": "4h", "symbol": "ETH/USDT"},
    ])
    run_entries = [
        {"timeframes": [{"timeframe": "2h", "days": 120}],
         "trade_symbols": ["ETH/USDT"]},
    ]
    cov = r._build_coverage_map(
        per_symbol_df, run_entries,
        target_timeframes=["1h", "2h", "4h"],
        target_symbols=["ETH/USDT", "BNB/USDT", "SOL/USDT"],
    )
    assert "1h" in cov["timeframes"]
    assert "SOL/USDT" in cov["symbols"]

    untested_keys = {(p["timeframe"], p["symbol"]) for p in cov["untested_pairs"]}
    # All 1h pairs should be untested
    assert ("1h", "ETH/USDT") in untested_keys
    assert ("1h", "BNB/USDT") in untested_keys
    assert ("1h", "SOL/USDT") in untested_keys
    # 2h tested only for ETH
    assert ("2h", "BNB/USDT") in untested_keys
    assert ("2h", "SOL/USDT") in untested_keys
    # 4h tested only for ETH
    assert ("4h", "BNB/USDT") in untested_keys
    assert ("4h", "SOL/USDT") in untested_keys
    # Already tested should NOT be in untested
    assert ("2h", "ETH/USDT") not in untested_keys
    assert ("4h", "ETH/USDT") not in untested_keys
    # Total untested = 9 - 2 = 7
    assert len(cov["untested_pairs"]) == 7


# -- _build_run_entry benchmark fields --------------------------------------

def test_build_run_entry_includes_benchmark_fields():
    """bh_return_pct and random_entry_return_pct should propagate."""
    meta = {
        "run_id": "bench1",
        "timestamp_utc": "2026-02-14T00:00:00Z",
        "search_mode": "combo",
        "config_sha256": "x",
        "data_fingerprint": "y",
        "timeframes": [{"timeframe": "2h", "days": 120}],
        "trade_symbols": ["ETH/USDT"],
    }
    best = {
        "timeframe": "2h",
        "data_days": 120,
        "avg_total_return_pct": 3.5,
        "oos_avg_total_return_pct": 2.8,
        "bh_return_pct": 1.5,
        "random_entry_return_pct": 0.3,
        "report_file": "report.html",
    }
    entry = r._build_run_entry(meta, best)
    assert entry["bh_return_pct"] == 1.5
    assert entry["random_entry_return_pct"] == 0.3


def test_build_run_entry_benchmark_fields_missing():
    """Old best_row without benchmark fields → None."""
    meta = {
        "run_id": "old1",
        "timestamp_utc": "2026-01-01T00:00:00Z",
        "search_mode": "combo",
        "config_sha256": "x",
        "data_fingerprint": "y",
        "timeframes": [],
        "trade_symbols": [],
    }
    best = {
        "timeframe": "4h",
        "data_days": 180,
        "report_file": "old.html",
    }
    entry = r._build_run_entry(meta, best)
    assert entry["bh_return_pct"] is None
    assert entry["random_entry_return_pct"] is None
