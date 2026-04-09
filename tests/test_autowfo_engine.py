import json
from types import SimpleNamespace

import pandas as pd
import pytest

from autowfo import engine_finalize as _engine_finalize_mod
from autowfo import engine_helpers as _engine_helpers_mod
from autowfo import engine_report as _engine_report_mod
from autowfo import engine_runtime as _engine_runtime_mod
from autowfo import engine_search as _engine_search_mod
from autowfo import engine_search as _e_search
from autowfo import engine_finalize as _e_finalize


def _collect_private_callables(module):
    return {
        name: getattr(module, name)
        for name in dir(module)
        if name.startswith("_") and callable(getattr(module, name))
    }


_symbols = {"DEFAULT_CONFIG": _engine_helpers_mod.DEFAULT_CONFIG}
for _module in (
    _engine_helpers_mod,
    _engine_runtime_mod,
    _engine_report_mod,
    _engine_search_mod,
    _engine_finalize_mod,
):
    _symbols.update(_collect_private_callables(_module))

e = SimpleNamespace(**_symbols)


def test_load_runtime_config_reads_file_and_env_override(tmp_path):
    out_dir = tmp_path
    cfg_path = out_dir / "sweep_config.json"
    cfg_path.write_text(
        json.dumps(
            {
                "search_mode": "refine",
                "combo_seed": 7,
                "trade_symbols": ["ETH/BTC"],
            }
        ),
        encoding="utf-8",
    )

    config = e._load_runtime_config(str(out_dir), env_mode="combo")
    assert config["search_mode"] == "combo"
    assert config["combo_seed"] == 7
    assert config["trade_symbols"] == ["ETH/BTC"]


def test_load_runtime_config_accepts_utf8_bom(tmp_path):
    out_dir = tmp_path
    cfg_path = out_dir / "sweep_config.json"
    cfg_path.write_text(
        json.dumps({"search_mode": "refine", "combo_seed": 9}),
        encoding="utf-8-sig",
    )
    config = e._load_runtime_config(str(out_dir), env_mode=None)
    assert config["search_mode"] == "refine"
    assert config["combo_seed"] == 9


def test_normalize_trade_symbols():
    got = e._normalize_trade_symbols(
        "ETH/BTC, BTC/USDT, SOL/BTC",
        base_symbol="BTC/USDT",
        default_trade_symbols=["BNB/BTC"],
    )
    assert got == ["ETH/BTC", "SOL/BTC"]


def test_safe_int_and_safe_float_defaulting():
    nan_value = float("nan")
    assert e._safe_int(None, 7) == 7
    assert e._safe_int(nan_value, 7) == 7
    assert e._safe_int("9", 7) == 9

    assert e._safe_float(None, 1.5) == 1.5
    assert e._safe_float(nan_value, 1.5) == 1.5
    assert e._safe_float("2.5", 1.5) == 2.5


def test_has_all_config_fields_validates_presence_and_content():
    strict_fields = ["exchange", "base_symbol", "wf_mode"]
    assert e._has_all_config_fields(
        {"exchange": "binance", "base_symbol": "BTC/USDT", "wf_mode": "rolling"},
        strict_fields,
    )
    assert not e._has_all_config_fields(
        {"exchange": "binance", "base_symbol": "BTC/USDT"},
        strict_fields,
    )
    assert not e._has_all_config_fields(
        {"exchange": "binance", "base_symbol": "", "wf_mode": "rolling"},
        strict_fields,
    )
    assert not e._has_all_config_fields(
        {"exchange": float("nan"), "base_symbol": "BTC/USDT", "wf_mode": "rolling"},
        strict_fields,
    )


def test_build_sweep_schema_fields_contract():
    metadata_fields = ["config_sha256", "data_fingerprint"]
    fields = e._build_sweep_schema_fields(
        artifact_row_metadata_fields=metadata_fields,
    )

    combo_key_fields = fields["combo_key_fields"]
    combo_result_fields = fields["combo_result_fields"]
    symbol_result_fields = fields["symbol_result_fields"]
    oos_symbol_result_fields = fields["oos_symbol_result_fields"]
    strict_config_fields = fields["strict_config_fields"]

    assert combo_key_fields[0:4] == ["timeframe", "data_days", "exchange", "base_symbol"]
    assert "risk_mode" in combo_key_fields
    assert combo_key_fields[-4:] == ["cmf_threshold", "vroc_lookback", "vroc_threshold", "ad_lookback"]
    assert combo_result_fields[0 : len(combo_key_fields)] == combo_key_fields
    assert combo_result_fields[len(combo_key_fields) : len(combo_key_fields) + 2] == metadata_fields
    assert "oos_sharpe_like" in combo_result_fields
    assert combo_result_fields[-1] == "oos_segments"

    assert symbol_result_fields[0:4] == ["timeframe", "data_days", "exchange", "base_symbol"]
    assert symbol_result_fields[18:20] == metadata_fields
    assert symbol_result_fields[-4:] == [
        "avg_trade_pct",
        "max_drawdown_pct",
        "position_coverage_pct",
        "avg_hold_hours",
    ]
    assert oos_symbol_result_fields[0:4] == ["timeframe", "data_days", "exchange", "base_symbol"]
    assert oos_symbol_result_fields[18:20] == metadata_fields
    assert oos_symbol_result_fields[-4:] == [
        "oos_sharpe_like",
        "oos_low_trade_segment_ratio",
        "oos_low_trade_penalty",
        "oos_segments",
    ]

    assert strict_config_fields == [
        "exchange",
        "base_symbol",
        "trade_symbols_key",
        "capital_mode",
        "fees",
        "risk_mode",
        "order_size_pct",
        "max_concurrent_positions",
        "init_cash_usdt",
        "wf_train_days",
        "wf_test_days",
        "wf_step_days",
        "wf_valid_days",
        "wf_mode",
        "data_start",
        "data_end",
    ]


def test_resolve_runtime_settings_normalizes_fields():
    config = {
        "search_mode": "refine",
        "timeframes": [{"timeframe": "1h", "days": 30}],
        "combo_sizes": [2],
        "combo_seed": 9,
        "max_workers": 0,
        "combo_segment_start": 3,
        "combo_segment_size": 10,
        "combo_group_fields": ["indicator_list"],
        "trade_symbols": "ETH/BTC,BTC/USDT,SOL/BTC",
        "indicator_subset": "mfi,cmf,missing,mfi",
        "regime_preset": "pilot_trend_3",
        "pilot_fixed_indicator_params": "true",
        "pilot_single_trend_mom": "yes",
        "wf_train_days": 7,
        "wf_test_days": 2,
        "wf_step_days": 2,
        "wf_mode": "rolling",
        "slippage_bps": 1.5,
        "spread_bps": 2.5,
        "funding_rate_daily": 0.001,
        "risk_mode": "atr_multiple",
        "capital_mode": "unknown",
        "init_cash_usdt": 2000,
        "order_size_pct": 25,
        "max_concurrent_positions": 0,
        "min_avg_daily_trades_target": -5,
        "min_oos_trades_target": -1,
        "top_n_refine": 7,
        "ranking": {"mode": "legacy"},
    }

    seen = {}

    def _normalize_mode(mode):
        seen["wf_mode_input"] = mode
        return str(mode)

    got = e._resolve_runtime_settings(
        config,
        base_symbol="BTC/USDT",
        default_trade_symbols=["BNB/BTC"],
        available_indicator_keys=["mfi", "cmf", "macd_hist"],
        normalize_split_mode_fn=_normalize_mode,
        resolve_ranking_config_fn=lambda ranking: {"resolved": ranking.get("mode")},
    )

    assert got["search_mode"] == "refine"
    assert got["combo_seed"] == 9
    assert got["max_workers"] == 1
    assert got["combo_segment_start"] == 3
    assert got["combo_segment_size"] == 10
    assert got["combo_group_fields"] == ["indicator_list"]
    assert got["trade_symbols"] == ["ETH/BTC", "SOL/BTC"]
    assert got["indicator_subset"] == ["mfi", "cmf"]
    assert got["regime_preset"] == "pilot_trend_3"
    assert got["pilot_fixed_indicator_params"] is True
    assert got["pilot_single_trend_mom"] is True
    assert got["wf_train_days"] == 7
    assert got["wf_test_days"] == 2
    assert got["wf_step_days"] == 2
    assert got["wf_mode"] == "rolling"
    assert seen["wf_mode_input"] == "rolling"
    assert got["slippage_bps"] == 1.5
    assert got["spread_bps"] == 2.5
    assert got["funding_rate_daily"] == 0.001
    assert got["risk_mode"] == "atr_multiple"
    assert got["capital_mode"] == "shared"
    assert got["init_cash_usdt"] == 2000.0
    assert got["order_size_pct"] == 0.25
    assert got["max_concurrent_positions"] == 2
    assert got["min_avg_daily_trades_target"] == 0.0
    assert got["min_oos_trades_target"] == 0
    assert got["top_n_fine"] == 7
    assert got["ranking_config"] == {"resolved": "legacy"}


def test_resolve_runtime_settings_uses_default_trade_symbols_when_empty():
    config = {
        "timeframes": [{"timeframe": "1h", "days": 30}],
        "combo_sizes": [2],
        "trade_symbols": "",
    }
    got = e._resolve_runtime_settings(
        config,
        base_symbol="BTC/USDT",
        default_trade_symbols=["BNB/BTC", "SOL/BTC"],
        available_indicator_keys=["mfi", "cmf"],
        normalize_split_mode_fn=lambda mode: "anchored",
        resolve_ranking_config_fn=lambda ranking: {"mode": "composite"},
    )
    assert got["trade_symbols"] == ["BNB/BTC", "SOL/BTC"]
    assert got["indicator_subset"] == ["mfi", "cmf"]


def test_build_regime_variants_characterization():
    variants = e._build_regime_variants([(30, 70), (40, 60), (35, 65)])
    names = [v["regime_name"] for v in variants]
    assert len(variants) == 12
    assert "trend_high" in names
    assert "rsi_revert_low" in names
    assert "bb_breakout_high" in names


def test_build_regime_variants_pilot_trend_3():
    variants = e._build_regime_variants([(30, 70)], preset="pilot_trend_3")
    assert [v["regime_name"] for v in variants] == ["trend_high", "trend_low", "trend_any"]


def test_count_coarse_combos_small_case():
    regime_variants = [{"regime_type": "trend", "vol_mode": "high"}]
    indicator_param_options = {"a": [{"x": 1}, {"x": 2}]}
    combo_keys_all = [("a",)]
    count = e._count_coarse_combos(
        regime_variants=regime_variants,
        indicator_param_options=indicator_param_options,
        combo_keys_all=combo_keys_all,
        mom_lookbacks=[6],
        vol_lookbacks=[24],
        vol_zs=[0.8],
        trade_mom_lookbacks=[3],
        tp_stops=[0.003],
        sl_stops=[0.006],
        max_holds=[2],
    )
    assert count == 2


def test_apply_quality_filters():
    df = pd.DataFrame(
        [
            {
                "avg_daily_trades": 6.0,
                "oos_avg_total_return_pct": 10.0,
                "oos_avg_avg_trade_pct": 0.2,
                "oos_min_total_trades": 2.0,
            },
            {
                "avg_daily_trades": 2.0,
                "oos_avg_total_return_pct": 12.0,
                "oos_avg_avg_trade_pct": 0.3,
                "oos_min_total_trades": 3.0,
            },
        ]
    )
    filtered = e._apply_quality_filters(df, min_avg_daily_trades_target=5, min_oos_trades_target=1)
    assert len(filtered) == 1


def test_should_emit_progress():
    assert e._should_emit_progress(
        done=0,
        force=False,
        last_progress_ts=100.0,
        now=101.0,
        progress_every=25,
        progress_min_seconds=5,
    )
    assert not e._should_emit_progress(
        done=1,
        force=False,
        last_progress_ts=100.0,
        now=101.0,
        progress_every=25,
        progress_min_seconds=5,
    )
    assert e._should_emit_progress(
        done=25,
        force=False,
        last_progress_ts=100.0,
        now=101.0,
        progress_every=25,
        progress_min_seconds=5,
    )


def test_build_progress_payload():
    payload = e._build_progress_payload(
        run_id="r1",
        stage="running",
        total=10,
        done=2,
        skipped=1,
        elapsed_seconds=20.0,
        updated="2026-02-07T00:00:00Z",
        format_duration_fn=lambda x: f"{int(x)}s" if x is not None else "",
    )
    assert payload["run_id"] == "r1"
    assert payload["remaining"] == 8
    assert payload["percent"] == 20.0
    assert payload["elapsed"] == "20s"
    assert payload["eta"] == "80s"


def test_should_checkpoint():
    assert not e._should_checkpoint(
        done=10,
        force=False,
        last_checkpoint_done=5,
        last_checkpoint_ts=100.0,
        now=101.0,
        checkpoint_every=200,
        checkpoint_min_seconds=30,
    )
    assert e._should_checkpoint(
        done=300,
        force=False,
        last_checkpoint_done=5,
        last_checkpoint_ts=100.0,
        now=101.0,
        checkpoint_every=200,
        checkpoint_min_seconds=30,
    )


def test_checkpoint_pending_rows_flushes_and_updates_state():
    append_rows_calls = []
    append_db_calls = []
    warnings = []
    pending_combo_rows = [{"x": 1}]
    pending_symbol_rows = [{"symbol": "ETH/BTC"}]
    pending_oos_symbol_rows = [{"symbol": "ETH/BTC", "oos_avg_total_return_pct": 1.0}]

    def _append_rows(path, rows, fields):
        append_rows_calls.append((path, list(rows), list(fields)))

    def _append_db_rows(db_path, table, rows, fields, normalize_key_value_fn=None):
        append_db_calls.append((db_path, table, list(rows), list(fields), normalize_key_value_fn))

    result = e._checkpoint_pending_rows(
        done=12,
        force=True,
        last_checkpoint_done=5,
        last_checkpoint_ts=100.0,
        now=120.0,
        checkpoint_every=200,
        checkpoint_min_seconds=30,
        pending_combo_rows=pending_combo_rows,
        pending_symbol_rows=pending_symbol_rows,
        pending_oos_symbol_rows=pending_oos_symbol_rows,
        combo_path="combo.csv",
        per_symbol_path="symbol.csv",
        oos_symbol_path="symbol_oos.csv",
        db_path="results.db",
        combo_result_fields=["x"],
        symbol_result_fields=["symbol"],
        oos_symbol_result_fields=["symbol", "oos_avg_total_return_pct"],
        should_checkpoint_fn=e._should_checkpoint,
        append_rows_fn=_append_rows,
        append_db_rows_fn=_append_db_rows,
        normalize_key_value_fn=lambda v: v,
        warn_fn=warnings.append,
    )

    assert result["checkpointed"] is True
    assert result["last_checkpoint_done"] == 12
    assert result["last_checkpoint_ts"] == 120.0
    assert pending_combo_rows == []
    assert pending_symbol_rows == []
    assert pending_oos_symbol_rows == []
    assert [call[0] for call in append_rows_calls] == ["combo.csv", "symbol.csv", "symbol_oos.csv"]
    assert [call[1] for call in append_db_calls] == ["combo_summary", "symbol_summary", "symbol_oos_summary"]
    assert warnings == []


def test_checkpoint_pending_rows_skips_when_not_due():
    append_rows_calls = []
    pending_combo_rows = [{"x": 1}]
    pending_symbol_rows = []

    result = e._checkpoint_pending_rows(
        done=10,
        force=False,
        last_checkpoint_done=9,
        last_checkpoint_ts=100.0,
        now=101.0,
        checkpoint_every=200,
        checkpoint_min_seconds=30,
        pending_combo_rows=pending_combo_rows,
        pending_symbol_rows=pending_symbol_rows,
        combo_path="combo.csv",
        per_symbol_path="symbol.csv",
        db_path="results.db",
        combo_result_fields=["x"],
        symbol_result_fields=["symbol"],
        should_checkpoint_fn=e._should_checkpoint,
        append_rows_fn=lambda *args, **kwargs: append_rows_calls.append((args, kwargs)),
        append_db_rows_fn=lambda *args, **kwargs: append_rows_calls.append((args, kwargs)),
        normalize_key_value_fn=lambda v: v,
    )

    assert result["checkpointed"] is False
    assert result["last_checkpoint_done"] == 9
    assert result["last_checkpoint_ts"] == 100.0
    assert pending_combo_rows == [{"x": 1}]
    assert append_rows_calls == []


def test_build_run_lifecycle_callbacks_progress_and_counters():
    writes = []
    prints = []
    now_values = iter([100.0, 100.0, 101.0, 102.0])

    lifecycle = e._build_run_lifecycle_callbacks(
        total_combos=10,
        run_id="r1",
        status_json_path="status.json",
        status_html_path="status.html",
        labels={"running": "Running"},
        control_path="control.json",
        combo_path="combo.csv",
        per_symbol_path="symbol.csv",
        db_path="results.db",
        combo_result_fields=["x"],
        symbol_result_fields=["symbol"],
        pending_combo_rows=[],
        pending_symbol_rows=[],
        pending_oos_symbol_rows=[],
        format_duration_fn=lambda x: f"{int(x)}s" if x is not None else "",
        write_status_fn=lambda json_path, html_path, payload, labels: writes.append(
            {
                "json_path": json_path,
                "html_path": html_path,
                "payload": payload,
                "labels": labels,
            }
        ),
        append_rows_fn=lambda *args, **kwargs: None,
        append_db_rows_fn=lambda *args, **kwargs: None,
        normalize_key_value_fn=lambda value: value,
        now_fn=lambda: next(now_values),
        sleep_fn=lambda seconds: None,
        build_updated_timestamp_fn=lambda: "2026-02-13T00:00:00Z",
        print_fn=lambda *args, **kwargs: prints.append((args, kwargs)),
    )

    lifecycle["emit_progress_fn"](stage="running", force=True)
    lifecycle["advance_progress_counts_fn"](done_delta=3, skipped_delta=1)
    lifecycle["set_total_combos_fn"](12)
    lifecycle["emit_progress_fn"](stage="combo", force=True)

    assert lifecycle["get_done_fn"]() == 3
    assert lifecycle["get_total_combos_fn"]() == 12
    assert writes[0]["payload"]["stage"] == "running"
    assert writes[0]["payload"]["done"] == 0
    assert writes[1]["payload"]["stage"] == "combo"
    assert writes[1]["payload"]["done"] == 3
    assert writes[1]["payload"]["skipped"] == 1
    assert writes[1]["payload"]["total"] == 12
    assert len(prints) == 2


def test_build_run_lifecycle_callbacks_wait_if_paused_emits_and_sleeps():
    writes = []
    sleeps = []
    controls = iter([{"paused": True}, {"paused": False}])
    now_values = iter([200.0, 200.0, 201.0])

    lifecycle = e._build_run_lifecycle_callbacks(
        total_combos=10,
        run_id="r1",
        status_json_path="status.json",
        status_html_path="status.html",
        labels={},
        control_path="control.json",
        combo_path="combo.csv",
        per_symbol_path="symbol.csv",
        oos_symbol_path="symbol_oos.csv",
        db_path="results.db",
        combo_result_fields=["x"],
        symbol_result_fields=["symbol"],
        oos_symbol_result_fields=["symbol", "oos_avg_total_return_pct"],
        pending_combo_rows=[],
        pending_symbol_rows=[],
        pending_oos_symbol_rows=[],
        format_duration_fn=lambda x: f"{int(x)}s" if x is not None else "",
        write_status_fn=lambda _json_path, _html_path, payload, _labels: writes.append(payload),
        append_rows_fn=lambda *args, **kwargs: None,
        append_db_rows_fn=lambda *args, **kwargs: None,
        normalize_key_value_fn=lambda value: value,
        now_fn=lambda: next(now_values),
        sleep_fn=lambda seconds: sleeps.append(seconds),
        build_updated_timestamp_fn=lambda: "2026-02-13T00:00:00Z",
        read_control_fn=lambda _path: next(controls),
        print_fn=lambda *args, **kwargs: None,
    )

    lifecycle["wait_if_paused_fn"]("1h combo")

    assert sleeps == [2]
    assert len(writes) == 1
    assert writes[0]["stage"] == "1h combo paused"


def test_build_run_lifecycle_callbacks_checkpoint_tracks_state():
    checkpoint_calls = []
    now_values = iter([300.0, 300.0, 301.0, 302.0])
    pending_combo_rows = [{"x": 1}]
    pending_symbol_rows = [{"symbol": "ETH/BTC"}]
    pending_oos_symbol_rows = [{"symbol": "ETH/BTC", "oos_avg_total_return_pct": 1.0}]

    def _checkpoint_pending_rows_fn(**kwargs):
        checkpoint_calls.append(kwargs)
        return {
            "checkpointed": True,
            "last_checkpoint_done": kwargs["done"],
            "last_checkpoint_ts": kwargs["now"],
        }

    lifecycle = e._build_run_lifecycle_callbacks(
        total_combos=10,
        run_id="r1",
        status_json_path="status.json",
        status_html_path="status.html",
        labels={},
        control_path="control.json",
        combo_path="combo.csv",
        per_symbol_path="symbol.csv",
        oos_symbol_path="symbol_oos.csv",
        db_path="results.db",
        combo_result_fields=["x"],
        symbol_result_fields=["symbol"],
        oos_symbol_result_fields=["symbol", "oos_avg_total_return_pct"],
        pending_combo_rows=pending_combo_rows,
        pending_symbol_rows=pending_symbol_rows,
        pending_oos_symbol_rows=pending_oos_symbol_rows,
        format_duration_fn=lambda x: f"{int(x)}s" if x is not None else "",
        write_status_fn=lambda *args, **kwargs: None,
        append_rows_fn=lambda *args, **kwargs: None,
        append_db_rows_fn=lambda *args, **kwargs: None,
        normalize_key_value_fn=lambda value: value,
        now_fn=lambda: next(now_values),
        sleep_fn=lambda seconds: None,
        build_updated_timestamp_fn=lambda: "2026-02-13T00:00:00Z",
        checkpoint_pending_rows_fn=_checkpoint_pending_rows_fn,
        print_fn=lambda *args, **kwargs: None,
    )

    lifecycle["advance_progress_counts_fn"](done_delta=5, skipped_delta=0)
    lifecycle["checkpoint_fn"](force=True)
    lifecycle["checkpoint_fn"](force=False)

    assert len(checkpoint_calls) == 2
    assert checkpoint_calls[0]["done"] == 5
    assert checkpoint_calls[0]["force"] is True
    assert checkpoint_calls[0]["last_checkpoint_done"] == 0
    assert checkpoint_calls[0]["pending_combo_rows"] is pending_combo_rows
    assert checkpoint_calls[0]["pending_symbol_rows"] is pending_symbol_rows
    assert checkpoint_calls[0]["pending_oos_symbol_rows"] is pending_oos_symbol_rows
    assert checkpoint_calls[1]["force"] is False
    assert checkpoint_calls[1]["last_checkpoint_done"] == 5
    assert checkpoint_calls[1]["last_checkpoint_ts"] == 301.0


def test_build_combo_keys_segment_and_seed():
    keys = e._build_combo_keys(
        indicator_keys=["a", "b", "c"],
        combo_sizes=[1, 2],
        combo_seed=1,
        combo_segment_start=1,
        combo_segment_size=3,
    )
    assert len(keys) == 3
    assert all(isinstance(k, tuple) for k in keys)


def test_normalize_existing_results_adds_columns():
    combo_df = pd.DataFrame([{"x": 1}])
    symbol_df = pd.DataFrame([{"y": 1}])
    combo_norm, symbol_norm = e._normalize_existing_results(combo_df, symbol_df, ["field_a"])
    assert "timeframe" in combo_norm.columns
    assert "data_days" in combo_norm.columns
    assert "field_a" in combo_norm.columns
    assert "timeframe" in symbol_norm.columns
    assert "data_days" in symbol_norm.columns


def test_build_seen_keys_filters_invalid_rows():
    df = pd.DataFrame([{"a": 1, "ok": True}, {"a": 2, "ok": False}])
    seen = e._build_seen_keys(
        df,
        has_all_config_fields_fn=lambda row: bool(row.get("ok")),
        combo_key_from_dict_fn=lambda row: f"a={row['a']}",
    )
    # Returns dict with 'full' and 'stripped' sets;
    # no data_start/data_end in this key so stripped == full.
    assert seen["full"] == {"a=1"}
    assert seen["stripped"] == {"a=1"}


def test_build_seen_keys_strips_data_range():
    # Verify stripped set removes data_start/data_end so cross-run OHLCV
    # refresh (data_end advances) does not invalidate seen_keys.
    key_v1 = "timeframe=1h|data_start=2024-01-01|data_end=2024-03-01|indicator_list=RSI"
    key_v2 = "timeframe=1h|data_start=2024-01-01|data_end=2024-03-10|indicator_list=RSI"
    expected_stripped = "timeframe=1h|indicator_list=RSI"
    df = pd.DataFrame([{"combo_key": key_v1, "ok": True}])
    seen = e._build_seen_keys(
        df,
        has_all_config_fields_fn=lambda row: bool(row.get("ok")),
        combo_key_from_dict_fn=lambda row: row["combo_key"],
    )
    assert key_v1 in seen["full"]
    assert expected_stripped in seen["stripped"]
    # A new run with updated data_end strips to the same key -> would be skipped
    stripped_new = e._strip_data_range_from_combo_key(key_v2)
    assert stripped_new == expected_stripped
    assert stripped_new in seen["stripped"]


def test_build_seen_keys_fills_null_fields_with_defaults():
    """AWF-106b: rows with None/NaN strict fields get DEFAULT_CONFIG fills so
    they pass has_all_config_fields and produce matchable seen keys.
    Regression: old CSV rows written before capital_mode/wf_valid_days/wf_mode
    were added caused ALL rows to fail has_all_config_fields ??seen_keys always
    empty ??0 cross-run skips ??same speed on every re-run."""
    import numpy as np
    from autowfo.engine_helpers import _SEEN_KEY_NULL_FIELD_DEFAULTS

    # Simulate an old CSV row: has combo fields but capital_mode/wf_mode are NaN
    old_row = {
        "capital_mode": float("nan"),   # was not tracked in old runs
        "wf_mode": float("nan"),        # ditto
        "wf_valid_days": float("nan"),  # ditto
        "indicator_list": "RSI",
        "timeframe": "15m",
        "ok": True,
    }
    df = pd.DataFrame([old_row])

    # With the old behavior (no fill), has_all_config_fields would fail for
    # capital_mode=NaN ??seen_keys is empty.
    strict_fields = ["capital_mode", "wf_mode", "indicator_list"]

    def has_all_config_fields(row):
        for f in strict_fields:
            v = row.get(f)
            if v is None or (isinstance(v, float) and np.isnan(v)) or (isinstance(v, str) and not v):
                return False
        return True

    def combo_key(row):
        return f"capital_mode={row.get('capital_mode')}|wf_mode={row.get('wf_mode')}|indicator_list={row.get('indicator_list')}"

    seen = e._build_seen_keys(
        df,
        has_all_config_fields_fn=has_all_config_fields,
        combo_key_from_dict_fn=combo_key,
    )

    # After AWF-106b, capital_mode/wf_mode should be filled with defaults so
    # the row passes the filter and contributes a valid key.
    default_capital_mode = _SEEN_KEY_NULL_FIELD_DEFAULTS.get("capital_mode", "shared")
    default_wf_mode = _SEEN_KEY_NULL_FIELD_DEFAULTS.get("wf_mode", "anchored")
    expected_key = f"capital_mode={default_capital_mode}|wf_mode={default_wf_mode}|indicator_list=RSI"

    assert len(seen["full"]) == 1, (
        f"Expected 1 seen key after null-fill, got {len(seen['full'])}. "
        "Old rows with NaN capital_mode/wf_mode must be included in seen_keys."
    )
    assert expected_key in seen["full"], f"Expected key '{expected_key}' in seen['full'], got {seen['full']}"


def test_normalize_key_value_int_float_consistency():
    """AWF-106c: When pandas reads a CSV column that has NaN in some rows, it
    upcasts the entire column to float64. Integer values like wf_valid_days=0
    become 0.0 (np.float64). Before AWF-106c, _normalize_key_value(0.0) produced
    the string '0.0' while _normalize_key_value(0) produced '0', so CSV-sourced
    keys never matched config-sourced keys even after AWF-106b null-fill.
    After AWF-106c, integer-valued floats are converted to int for consistent
    key representation regardless of how the value was sourced."""
    import numpy as np
    from autowfo.search import _normalize_key_value, _combo_key_from_dict

    # Core correctness: integer-valued floats -> int
    assert _normalize_key_value(0.0) == 0
    assert _normalize_key_value(10.0) == 10
    assert _normalize_key_value(np.float64(30.0)) == 30
    # Types should match
    assert type(_normalize_key_value(0.0)) is int
    assert type(_normalize_key_value(0)) is int
    # Non-integer floats must NOT be converted
    assert _normalize_key_value(0.001) == 0.001
    assert _normalize_key_value(2.5) == 2.5
    assert isinstance(_normalize_key_value(0.001), float)

    # End-to-end: CSV row (float64 from pandas) vs config row (int) must produce same key
    fields = ["wf_valid_days", "wf_train_days", "indicator_list"]
    csv_row = {"wf_valid_days": np.float64(0.0), "wf_train_days": np.int64(10), "indicator_list": "RSI"}
    cfg_row = {"wf_valid_days": 0, "wf_train_days": 10, "indicator_list": "RSI"}
    csv_key = _combo_key_from_dict(csv_row, fields)
    cfg_key = _combo_key_from_dict(cfg_row, fields)
    assert csv_key == cfg_key, (
        f"CSV key {csv_key!r} != config key {cfg_key!r}. "
        "Float-upcast integer columns from pandas must produce identical keys to int config values."
    )


def test_build_seen_keys_int_float_csv_roundtrip():
    """AWF-106c regression: simulates the CSV roundtrip where wf_valid_days=0 is written
    to CSV and read back as 0.0 (float64 due to NaN rows), then must still match the
    current-run combo key built with wf_valid_days=0 (int from config)."""
    import numpy as np

    # Simulate a CSV row where wf_valid_days was stored as 0 but pandas reads as 0.0
    csv_row = {
        "wf_valid_days": np.float64(0.0),  # pandas float64 upcast
        "indicator_list": "RSI",
        "ok": True,
    }
    df = pd.DataFrame([csv_row])

    def has_all(row):
        return bool(row.get("ok"))

    def key_fn(row):
        # wf_valid_days must come out as "0" not "0.0"
        from autowfo.search import _combo_key_from_dict
        return _combo_key_from_dict(row, ["wf_valid_days", "indicator_list"])

    seen = e._build_seen_keys(df, has_all_config_fields_fn=has_all, combo_key_from_dict_fn=key_fn)

    # Current-run key uses int 0 from config
    current_key = "wf_valid_days=0|indicator_list=RSI"
    assert current_key in seen["full"], (
        f"Expected '{current_key}' in seen_keys. "
        "CSV float64 0.0 must normalize identically to config int 0."
    )


def test_build_seen_keys_null_fill_overrides_capital_mode():
    """AWF-106d regression: _build_combo_row did not persist capital_mode to CSV,
    so every CSV row had capital_mode=NaN.  _build_seen_keys filled NaN with
    DEFAULT_CONFIG['capital_mode']='shared' regardless of the actual runtime
    value.  When the user's config used capital_mode='per_symbol', the
    runtime-generated key (capital_mode=per_symbol) never matched the seen key
    (capital_mode=shared) ??zero cross-run skips.

    After AWF-106d:
    - _build_combo_row writes capital_mode to CSV (prevents future NaN).
    - _build_seen_keys accepts null_fill_overrides so that legacy NaN rows
      are filled with the *current* runtime value, not the hardcoded default.
    """
    import numpy as np

    csv_row = {
        "capital_mode": float("nan"),  # OLD CSV row: capital_mode never written
        "indicator_list": "RSI",
        "ok": True,
    }
    df = pd.DataFrame([csv_row])

    def has_all(row):
        for f in ["capital_mode", "indicator_list"]:
            v = row.get(f)
            if v is None or (isinstance(v, float) and np.isnan(v)):
                return False
        return True

    def key_fn(row):
        from autowfo.search import _combo_key_from_dict
        return _combo_key_from_dict(row, ["capital_mode", "indicator_list"])

    # Without override: NaN is filled with DEFAULT_CONFIG's 'shared'
    seen_default = e._build_seen_keys(df, has_all, key_fn)
    assert "capital_mode=shared|indicator_list=RSI" in seen_default["full"]

    # With override: NaN is filled with the current runtime value 'per_symbol'
    seen_override = e._build_seen_keys(
        df, has_all, key_fn, null_fill_overrides={"capital_mode": "per_symbol"}
    )
    assert "capital_mode=per_symbol|indicator_list=RSI" in seen_override["full"], (
        "null_fill_overrides must take precedence over _SEEN_KEY_NULL_FIELD_DEFAULTS "
        "so that legacy NaN rows match the current runtime's capital_mode."
    )
    assert "capital_mode=shared|indicator_list=RSI" not in seen_override["full"], (
        "When null_fill_overrides provides capital_mode, the default fill must "
        "NOT be used."
    )


def test_build_combo_row_includes_capital_mode():
    """AWF-106d: _build_combo_row must include capital_mode in the returned dict
    so that future CSV rows have a non-NaN capital_mode column."""
    variant_params = {
        "rsi_long": None, "rsi_short": None, "bb_width": None, "atr_ratio": None,
        "ma_fast": None, "ma_slow": None, "macd_hist_ratio": None,
        "stoch_long": None, "stoch_short": None, "obv_lookback": None,
        "volume_lookback": None, "volume_z": None, "roc_lookback": None,
        "roc_threshold": None, "mfi_long": None, "mfi_short": None,
        "cmf_lookback": None, "cmf_threshold": None, "vroc_lookback": None,
        "vroc_threshold": None, "ad_lookback": None,
    }
    metrics = {
        "total_return_pct": pd.Series([10.0], index=["ETH/BTC"]),
        "total_profit": pd.Series([100.0], index=["ETH/BTC"]),
        "total_trades": pd.Series([5.0], index=["ETH/BTC"]),
        "win_rate_pct": pd.Series([60.0], index=["ETH/BTC"]),
        "avg_trade_pct": pd.Series([1.5], index=["ETH/BTC"]),
        "max_drawdown_pct": pd.Series([-5.0], index=["ETH/BTC"]),
        "position_coverage_pct": pd.Series([30.0], index=["ETH/BTC"]),
        "avg_hold_hours": pd.Series([2.0], index=["ETH/BTC"]),
    }

    for cm in ("shared", "per_symbol"):
        row = e._build_combo_row(
            timeframe="5m",
            data_days=30,
            exchange="binance",
            base_symbol="BTC/USDT",
            trade_symbols_tf=["ETH/BTC"],
            capital_mode=cm,
            fees=0.001,
            slippage_bps=2.0,
            spread_bps=2.0,
            funding_rate_daily=0.0,
            order_size_pct=0.5,
            max_concurrent_positions=2,
            init_cash_usdt=1000.0,
            wf_train_days=10,
            wf_test_days=10,
            wf_step_days=10,
            data_start="2024-01-01",
            data_end="2024-01-31",
            regime={"regime_name": "trend_high", "regime_type": "trend", "vol_mode": "high"},
            regime_rsi_long=None,
            regime_rsi_short=None,
            filter_name="none",
            indicator_list="rsi",
            indicator_combo=("rsi",),
            vol_lookback=24,
            vol_z=0.8,
            mom_lookback=6,
            trade_mom_lookback=3,
            tp_stop=0.003,
            sl_stop=0.006,
            max_hold=2,
            rsi_window=14,
            variant_params=variant_params,
            combo_metrics={
                "total_return_pct": 8.0, "win_rate_pct": 55.0, "avg_trade_pct": 1.2,
                "max_drawdown_pct": -4.0, "position_coverage_pct": 40.0,
                "total_trades": 5.0, "avg_hold_hours": 2.0,
            },
            sym_metrics={
                "avg_total_return_pct": 10.0, "avg_win_rate_pct": 60.0,
                "avg_avg_trade_pct": 1.5, "avg_max_drawdown_pct": -5.0,
                "avg_position_coverage_pct": 30.0, "avg_total_trades": 5.0,
                "min_total_trades": 5.0, "avg_hold_hours": 2.0,
            },
            metrics=metrics,
            ctx_total_days=10,
            oos_metrics={"oos_avg_total_return_pct": 7.0},
        )
        assert "capital_mode" in row, "combo_row must include capital_mode"
        assert row["capital_mode"] == cm, (
            f"combo_row['capital_mode'] should be '{cm}', got {row['capital_mode']!r}"
        )


def test_control_file_helpers(tmp_path):
    control_path = tmp_path / "run_control.json"
    e._ensure_control_file(str(control_path))
    control = e._read_control(str(control_path))
    assert control.get("paused") is False

    bad_path = tmp_path / "missing.json"
    fallback = e._read_control(str(bad_path))
    assert fallback == {"paused": False}


def test_iter_coarse_plan_count():
    def _iter_indicator(combo_keys, param_options):
        for item in param_options.get(combo_keys[0], [{}]):
            yield item

    plan = list(
        e._iter_coarse_plan(
            regime_variants=[{"regime_type": "trend", "vol_mode": "high"}],
            mom_lookbacks=[6],
            vol_lookbacks=[24],
            vol_zs=[0.8],
            trade_mom_lookbacks=[3],
            tp_stops=[0.003],
            sl_stops=[0.006],
            max_holds=[2],
            combo_keys_all=[("a",)],
            iter_indicator_param_combos_fn=_iter_indicator,
            indicator_param_options={"a": [{"x": 1}, {"x": 2}]},
        )
    )
    assert len(plan) == 2


def test_build_refine_targets():
    top_candidates = pd.DataFrame([{"indicator_list": "rsi", "tp_stop": 0.003, "sl_stop": 0.006}])
    fine_total, fine_targets = e._build_refine_targets(
        top_candidates=top_candidates,
        tp_stops=[0.003],
        sl_stops=[0.006],
        indicator_defaults={"rsi": {"rsi_long": 60, "rsi_short": 40}},
        refine_steps={"tp_stop": 0.001, "sl_stop": 0.002, "threshold_pair": 5},
        expand_float_fn=lambda base, step, min_value=None: [base - step, base, base + step],
        safe_float_fn=lambda v, d: d if v is None else float(v),
        refine_indicator_params_fn=lambda key, row, steps, defaults: [defaults[key]],
    )
    assert fine_total == 9
    assert len(fine_targets) == 1


def test_resolve_refine_risk_steps_switches_for_atr_multiple():
    refine_steps = _e_search._default_refine_steps()
    assert _e_search._resolve_refine_risk_steps(refine_steps, "fixed_pct") == (0.001, 0.002)
    assert _e_search._resolve_refine_risk_steps(refine_steps, "atr_multiple") == (0.25, 0.25)


def test_build_refine_targets_uses_atr_specific_risk_steps():
    top_candidates = pd.DataFrame(
        [
            {
                "indicator_list": "mfi",
                "risk_mode": "atr_multiple",
                "tp_stop": 1.5,
                "sl_stop": 1.0,
                "mfi_long": 60,
                "mfi_short": 40,
            }
        ]
    )
    expand_calls = []

    def _expand(base, step, min_value=None):
        expand_calls.append((base, step, min_value))
        return [base - step, base, base + step]

    fine_total, fine_targets = _e_search._build_refine_targets(
        top_candidates=top_candidates,
        tp_stops=[1.5],
        sl_stops=[1.0],
        indicator_defaults={"mfi": {"mfi_long": 60, "mfi_short": 40}},
        refine_steps=_e_search._default_refine_steps(),
        expand_float_fn=_expand,
        safe_float_fn=lambda v, d: d if v is None else float(v),
        refine_indicator_params_fn=lambda key, row, steps, defaults: [defaults[key]],
    )
    assert fine_total == 9
    assert len(fine_targets) == 1
    assert expand_calls[0] == (1.5, 0.25, 0.0001)
    assert expand_calls[1] == (1.0, 0.25, 0.0001)


def test_build_combo_key_values_characterization():
    values = e._build_combo_key_values(
        timeframe="3m",
        data_days=60,
        exchange="binance",
        base_symbol="BTC/USDT",
        trade_symbols_tf=["ETH/BTC"],
        capital_mode="shared",
        fees=0.001,
        slippage_bps=2.0,
        spread_bps=2.0,
        funding_rate_daily=0.0,
        order_size_pct=0.5,
        max_concurrent_positions=2,
        init_cash_usdt=1000.0,
        wf_train_days=120,
        wf_test_days=30,
        wf_step_days=30,
        data_start="2024-01-01",
        data_end="2024-01-31",
        regime={"regime_name": "trend_high", "regime_type": "trend", "vol_mode": "high"},
        filter_name="rsi+roc",
        indicator_list="rsi,roc",
        indicator_combo=("rsi", "roc"),
        vol_lookback=24,
        vol_z=0.8,
        mom_lookback=6,
        trade_mom_lookback=3,
        tp_stop=0.003,
        sl_stop=0.006,
        max_hold=2,
        rsi_window=14,
        param_payload={k: None for k in [
            "rsi_long",
            "rsi_short",
            "bb_width",
            "atr_ratio",
            "ma_fast",
            "ma_slow",
            "macd_hist_ratio",
            "stoch_long",
            "stoch_short",
            "obv_lookback",
            "volume_lookback",
            "volume_z",
            "roc_lookback",
            "roc_threshold",
            "mfi_long",
            "mfi_short",
            "cmf_lookback",
            "cmf_threshold",
            "vroc_lookback",
            "vroc_threshold",
            "ad_lookback",
        ]},
    )
    assert values["trade_symbols_key"] == "ETH/BTC"
    assert values["indicator_count"] == 2
    assert values["mom_lookback"] == 6


def test_build_combo_task_payload_characterization():
    combo_key, task_payload = e._build_combo_task_payload(
        timeframe="1h",
        data_days=30,
        exchange="binance",
        base_symbol="BTC/USDT",
        trade_symbols_tf=["ETH/BTC"],
        capital_mode="shared",
        fees=0.001,
        slippage_bps=2.0,
        spread_bps=2.0,
        funding_rate_daily=0.0,
        order_size_pct=0.5,
        max_concurrent_positions=2,
        init_cash_usdt=1000.0,
        wf_train_days=7,
        wf_test_days=2,
        wf_step_days=2,
        wf_mode="rolling",
        data_start="2024-01-01",
        data_end="2024-01-31",
        regime={"regime_name": "trend_high", "regime_type": "trend", "vol_mode": "high"},
        indicator_combo=("rsi", "roc"),
        combo_params={"rsi_long": 60, "rsi_short": 40, "roc_lookback": 6},
        vol_lookback=24,
        vol_z=0.8,
        mom_lookback=6,
        trade_mom_lookback=3,
        tp_stop=0.003,
        sl_stop=0.006,
        max_hold=2,
        rsi_window=14,
        indicator_param_fields=[
            "rsi_long",
            "rsi_short",
            "bb_width",
            "atr_ratio",
            "ma_fast",
            "ma_slow",
            "macd_hist_ratio",
            "stoch_long",
            "stoch_short",
            "obv_lookback",
            "volume_lookback",
            "volume_z",
            "roc_lookback",
            "roc_threshold",
            "mfi_long",
            "mfi_short",
            "cmf_lookback",
            "cmf_threshold",
            "vroc_lookback",
            "vroc_threshold",
            "ad_lookback",
        ],
        combo_key_from_dict_fn=lambda row: f"{row['timeframe']}:{row['indicator_list']}",
        indicator_combo_label_fn=lambda combo: "+".join(combo),
    )
    assert combo_key == "1h:rsi,roc"
    assert task_payload["combo_key"] == combo_key
    assert task_payload["filter_name"] == "rsi+roc"
    assert task_payload["indicator_list"] == "rsi,roc"
    assert task_payload["mom_lookback"] == 6


def test_resolve_regime_signals():
    idx = pd.date_range("2024-01-01", periods=3, freq="h")
    vol_cond = pd.Series([True, False, True], index=idx)
    ctx = {
        "mom_by_lb": {6: pd.Series([1.0, -1.0, 0.5], index=idx)},
        "rsi_series": pd.Series([20.0, 60.0, 80.0], index=idx),
        "btc_close": pd.Series([10.0, 11.0, 9.0], index=idx),
        "bb_lower": pd.Series([10.5, 10.5, 10.5], index=idx),
        "bb_upper": pd.Series([10.8, 10.8, 10.8], index=idx),
    }
    long_trend, short_trend, _, _ = e._resolve_regime_signals(
        {"regime_type": "trend"}, vol_cond, ctx, mom_lookback=6
    )
    assert bool(long_trend.iloc[0]) is True
    assert bool(short_trend.iloc[0]) is False


def test_build_symbol_and_combo_rows():
    metrics = {
        "total_return_pct": pd.Series({"ETH/BTC": 10.0}),
        "total_profit": pd.Series({"ETH/BTC": 1.0}),
        "total_trades": pd.Series({"ETH/BTC": 5.0}),
        "win_rate_pct": pd.Series({"ETH/BTC": 60.0}),
        "avg_trade_pct": pd.Series({"ETH/BTC": 1.5}),
        "max_drawdown_pct": pd.Series({"ETH/BTC": -5.0}),
        "position_coverage_pct": pd.Series({"ETH/BTC": 30.0}),
        "avg_hold_hours": pd.Series({"ETH/BTC": 2.0}),
    }
    variant_params = {
        "rsi_long": None,
        "rsi_short": None,
        "bb_width": None,
        "atr_ratio": None,
        "ma_fast": None,
        "ma_slow": None,
        "macd_hist_ratio": None,
        "stoch_long": None,
        "stoch_short": None,
        "obv_lookback": None,
        "volume_lookback": None,
        "volume_z": None,
        "roc_lookback": None,
        "roc_threshold": None,
        "mfi_long": None,
        "mfi_short": None,
        "cmf_lookback": None,
        "cmf_threshold": None,
        "vroc_lookback": None,
        "vroc_threshold": None,
        "ad_lookback": None,
    }
    symbol_row = e._build_symbol_row(
        timeframe="3m",
        data_days=60,
        exchange="binance",
        base_symbol="BTC/USDT",
        trade_symbols_tf=["ETH/BTC"],
        capital_mode="shared",
        fees=0.001,
        order_size_pct=0.5,
        max_concurrent_positions=2,
        init_cash_usdt=1000.0,
        wf_train_days=120,
        wf_test_days=30,
        wf_step_days=30,
        data_start="2024-01-01",
        data_end="2024-01-31",
        symbol="ETH/BTC",
        regime={"regime_name": "trend_high", "regime_type": "trend", "vol_mode": "high"},
        regime_rsi_long=None,
        regime_rsi_short=None,
        filter_name="none",
        indicator_list="rsi",
        indicator_combo=("rsi",),
        vol_lookback=24,
        vol_z=0.8,
        mom_lookback=6,
        trade_mom_lookback=3,
        tp_stop=0.003,
        sl_stop=0.006,
        max_hold=2,
        rsi_window=14,
        variant_params=variant_params,
        metrics=metrics,
    )
    assert symbol_row["symbol"] == "ETH/BTC"
    assert symbol_row["total_return_pct"] == 10.0

    oos_symbol_row = e._build_oos_symbol_row(
        timeframe="3m",
        data_days=60,
        exchange="binance",
        base_symbol="BTC/USDT",
        trade_symbols_tf=["ETH/BTC"],
        capital_mode="shared",
        fees=0.001,
        order_size_pct=0.5,
        max_concurrent_positions=2,
        init_cash_usdt=1000.0,
        wf_train_days=120,
        wf_test_days=30,
        wf_step_days=30,
        data_start="2024-01-01",
        data_end="2024-01-31",
        symbol="ETH/BTC",
        regime={"regime_name": "trend_high", "regime_type": "trend", "vol_mode": "high"},
        regime_rsi_long=None,
        regime_rsi_short=None,
        filter_name="none",
        indicator_list="rsi",
        indicator_combo=("rsi",),
        vol_lookback=24,
        vol_z=0.8,
        mom_lookback=6,
        trade_mom_lookback=3,
        tp_stop=0.003,
        sl_stop=0.006,
        max_hold=2,
        rsi_window=14,
        variant_params=variant_params,
        oos_metrics={
            "oos_avg_total_return_pct": pd.Series({"ETH/BTC": 0.5}),
            "oos_avg_win_rate_pct": pd.Series({"ETH/BTC": 60.0}),
            "oos_avg_avg_trade_pct": pd.Series({"ETH/BTC": 1.0}),
            "oos_avg_max_drawdown_pct": pd.Series({"ETH/BTC": -2.0}),
            "oos_avg_position_coverage_pct": pd.Series({"ETH/BTC": 30.0}),
            "oos_avg_total_trades": pd.Series({"ETH/BTC": 4.0}),
            "oos_min_total_trades": pd.Series({"ETH/BTC": 2.0}),
            "oos_avg_daily_trades": pd.Series({"ETH/BTC": 0.5}),
            "oos_avg_hold_hours": pd.Series({"ETH/BTC": 2.0}),
            "oos_return_std": pd.Series({"ETH/BTC": 0.1}),
            "oos_positive_segment_ratio": pd.Series({"ETH/BTC": 0.5}),
            "oos_sharpe_like": pd.Series({"ETH/BTC": 5.0}),
            "oos_low_trade_segment_ratio": pd.Series({"ETH/BTC": 0.0}),
            "oos_low_trade_penalty": pd.Series({"ETH/BTC": 0.0}),
            "oos_segments": pd.Series({"ETH/BTC": 2.0}),
        },
    )
    assert oos_symbol_row["symbol"] == "ETH/BTC"
    assert oos_symbol_row["oos_avg_total_return_pct"] == 0.5

    combo_row = e._build_combo_row(
        timeframe="3m",
        data_days=60,
        exchange="binance",
        base_symbol="BTC/USDT",
        trade_symbols_tf=["ETH/BTC"],
        capital_mode="shared",
        fees=0.001,
        slippage_bps=2.0,
        spread_bps=2.0,
        funding_rate_daily=0.0,
        order_size_pct=0.5,
        max_concurrent_positions=2,
        init_cash_usdt=1000.0,
        wf_train_days=120,
        wf_test_days=30,
        wf_step_days=30,
        data_start="2024-01-01",
        data_end="2024-01-31",
        regime={"regime_name": "trend_high", "regime_type": "trend", "vol_mode": "high"},
        regime_rsi_long=None,
        regime_rsi_short=None,
        filter_name="none",
        indicator_list="rsi",
        indicator_combo=("rsi",),
        vol_lookback=24,
        vol_z=0.8,
        mom_lookback=6,
        trade_mom_lookback=3,
        tp_stop=0.003,
        sl_stop=0.006,
        max_hold=2,
        rsi_window=14,
        variant_params=variant_params,
        combo_metrics={
            "total_return_pct": 8.0,
            "win_rate_pct": 55.0,
            "avg_trade_pct": 1.2,
            "max_drawdown_pct": -4.0,
            "position_coverage_pct": 40.0,
            "total_trades": 5.0,
            "avg_hold_hours": 2.0,
        },
        sym_metrics={
            "avg_total_return_pct": 10.0,
            "avg_win_rate_pct": 60.0,
            "avg_avg_trade_pct": 1.5,
            "avg_max_drawdown_pct": -5.0,
            "avg_position_coverage_pct": 30.0,
            "avg_total_trades": 5.0,
            "min_total_trades": 5.0,
            "avg_hold_hours": 2.0,
        },
        metrics=metrics,
        ctx_total_days=10,
        oos_metrics={"oos_avg_total_return_pct": 7.0},
    )
    assert combo_row["avg_total_return_pct"] == 8.0
    assert combo_row["capital_mode"] == "shared"
    assert combo_row["oos_avg_total_return_pct"] == 7.0


def test_compute_effective_costs_and_trade_mom_filters():
    effective_fees, effective_slippage = e._compute_effective_costs(
        fees=0.001,
        slippage_bps=2.0,
        spread_bps=2.0,
        funding_rate_daily=0.0001,
        max_hold=24,
        bar_hours=1.0,
    )
    assert effective_fees > 0.001
    assert effective_slippage == 0.0003

    trade_mom = pd.Series([1.0, -1.0, 0.0])
    long_filter, short_filter = e._build_trade_mom_filters(trade_mom)
    assert list(long_filter.astype(int)) == [1, 0, 0]
    assert list(short_filter.astype(int)) == [0, 1, 0]


def test_run_search_for_timeframe_combo():
    calls = []

    def _eval(*args, **kwargs):
        calls.append((args, kwargs))

    e._run_search_for_timeframe(
        search_mode="combo",
        stage_prefix="3m",
        timeframe="3m",
        regime_variants=[{"regime_type": "trend", "vol_mode": "high", "regime_name": "trend_high"}],
        regime_lookup={"trend_high": {"regime_type": "trend", "vol_mode": "high", "regime_name": "trend_high"}},
        mom_lookbacks=[6],
        vol_lookbacks=[24],
        vol_zs=[0.8],
        trade_mom_lookbacks=[3],
        tp_stops=[0.003],
        sl_stops=[0.006],
        max_holds=[2],
        combo_keys_all=[("rsi",)],
        iter_indicator_param_combos_fn=lambda combo, opts: [{}],
        indicator_param_options={"rsi": [{}]},
        eval_combo_fn=_eval,
        existing_combo_df=pd.DataFrame(),
        apply_quality_filters_fn=lambda df: df,
        sort_by_score_fn=lambda df, tie_break_avg_hold=True: (df, "x"),
        combo_group_fields=[],
        top_n_fine=10,
        min_avg_daily_trades_target=5.0,
        indicator_defaults={},
        expand_float_fn=lambda base, step, min_value=None: [base],
        safe_float_fn=lambda v, d: d if v is None else float(v),
        refine_indicator_params_fn=lambda key, row, steps, defaults: [{}],
        safe_int_fn=lambda v, d: d if v is None else int(v),
        on_refine_plan_fn=None,
    )
    assert len(calls) == 1


def test_run_search_for_timeframe_refine():
    calls = []
    refine_notice = {}

    def _eval(*args, **kwargs):
        calls.append((args, kwargs))

    existing = pd.DataFrame(
        [
            {
                "timeframe": "3m",
                "indicator_list": "rsi",
                "regime_name": "trend_high",
                "tp_stop": 0.003,
                "sl_stop": 0.006,
                "vol_lookback": 24,
                "vol_z": 0.8,
                "mom_lookback": 6,
                "trade_mom_lookback": 3,
                "max_hold": 2,
                "avg_daily_trades": 6.0,
            }
        ]
    )

    e._run_search_for_timeframe(
        search_mode="refine",
        stage_prefix="3m",
        timeframe="3m",
        regime_variants=[{"regime_type": "trend", "vol_mode": "high", "regime_name": "trend_high"}],
        regime_lookup={"trend_high": {"regime_type": "trend", "vol_mode": "high", "regime_name": "trend_high"}},
        mom_lookbacks=[6],
        vol_lookbacks=[24],
        vol_zs=[0.8],
        trade_mom_lookbacks=[3],
        tp_stops=[0.003],
        sl_stops=[0.006],
        max_holds=[2],
        combo_keys_all=[("rsi",)],
        iter_indicator_param_combos_fn=lambda combo, opts: [{}],
        indicator_param_options={"rsi": [{}]},
        eval_combo_fn=_eval,
        existing_combo_df=existing,
        apply_quality_filters_fn=lambda df: df,
        sort_by_score_fn=lambda df, tie_break_avg_hold=True: (df, "x"),
        combo_group_fields=[],
        top_n_fine=10,
        min_avg_daily_trades_target=5.0,
        indicator_defaults={"rsi": {}},
        expand_float_fn=lambda base, step, min_value=None: [base],
        safe_float_fn=lambda v, d: d if v is None else float(v),
        refine_indicator_params_fn=lambda key, row, steps, defaults: [defaults.get(key, {})],
        safe_int_fn=lambda v, d: d if v is None else int(v),
        on_refine_plan_fn=lambda fine_total, stage: refine_notice.update(
            {"fine_total": fine_total, "stage": stage}
        ),
    )
    assert len(calls) == 1
    assert refine_notice["fine_total"] == 1


def test_run_search_for_timeframe_refine_activity_fallback_keeps_candidates():
    calls = []

    def _eval(*args, **kwargs):
        calls.append((args, kwargs))

    existing = pd.DataFrame(
        [
            {
                "timeframe": "1h",
                "indicator_list": "rsi",
                "regime_name": "trend_high",
                "tp_stop": 0.003,
                "sl_stop": 0.006,
                "vol_lookback": 24,
                "vol_z": 0.8,
                "mom_lookback": 6,
                "trade_mom_lookback": 3,
                "max_hold": 2,
                "avg_daily_trades": 0.2,
            }
        ]
    )

    e._run_search_for_timeframe(
        search_mode="refine",
        stage_prefix="1h",
        timeframe="1h",
        regime_variants=[{"regime_type": "trend", "vol_mode": "high", "regime_name": "trend_high"}],
        regime_lookup={"trend_high": {"regime_type": "trend", "vol_mode": "high", "regime_name": "trend_high"}},
        mom_lookbacks=[6],
        vol_lookbacks=[24],
        vol_zs=[0.8],
        trade_mom_lookbacks=[3],
        tp_stops=[0.003],
        sl_stops=[0.006],
        max_holds=[2],
        combo_keys_all=[("rsi",)],
        iter_indicator_param_combos_fn=lambda combo, opts: [{}],
        indicator_param_options={"rsi": [{}]},
        eval_combo_fn=_eval,
        existing_combo_df=existing,
        apply_quality_filters_fn=lambda df: df[df["avg_daily_trades"] >= 5.0],
        sort_by_score_fn=lambda df, tie_break_avg_hold=True: (df, "x"),
        combo_group_fields=[],
        top_n_fine=10,
        min_avg_daily_trades_target=5.0,
        indicator_defaults={"rsi": {}},
        expand_float_fn=lambda base, step, min_value=None: [base],
        safe_float_fn=lambda v, d: d if v is None else float(v),
        refine_indicator_params_fn=lambda key, row, steps, defaults: [defaults.get(key, {})],
        safe_int_fn=lambda v, d: d if v is None else int(v),
        on_refine_plan_fn=None,
    )
    assert len(calls) == 1


def test_run_parallel_combo_search_for_timeframe_counts_done_and_skipped():
    progress_calls = []
    checkpoint_calls = []
    append_calls = []
    counter = {"done": 0, "skipped": 0}
    seen_keys = {"k1"}

    def _build_combo_task(
        regime,
        indicator_combo,
        combo_params,
        vol_lookback,
        vol_z,
        mom_lookback,
        trade_mom_lookback,
        tp_stop,
        sl_stop,
        max_hold,
    ):
        key = combo_params["key"]
        payload = {"combo_key": key, "regime": regime["regime_name"]}
        return key, payload

    def _run_combo_tasks(combo_tasks, runtime_eval, max_workers):
        assert runtime_eval == {"ctx": "runtime"}
        assert max_workers == 3
        return [{"metrics_values": {"total_return_pct": [1.0]}} for _ in combo_tasks]

    result = e._run_parallel_combo_search_for_timeframe(
        stage="1h combo",
        regime_variants=[{"regime_type": "trend", "vol_mode": "high", "regime_name": "trend_high"}],
        mom_lookbacks=[6],
        vol_lookbacks=[24],
        vol_zs=[0.8],
        trade_mom_lookbacks=[3],
        tp_stops=[0.003],
        sl_stops=[0.006],
        max_holds=[2],
        combo_keys_all=[("rsi",)],
        iter_indicator_param_combos_fn=lambda combo, options: options["rsi"],
        indicator_param_options={"rsi": [{"key": "k1"}, {"key": "k2"}]},
        build_combo_task_fn=_build_combo_task,
        seen_keys=seen_keys,
        runtime_eval={"ctx": "runtime"},
        max_workers=3,
        run_combo_tasks_fn=_run_combo_tasks,
        append_eval_result_fn=lambda result_payload, task_meta: append_calls.append(
            (result_payload, task_meta)
        ),
        emit_progress_fn=lambda stage: progress_calls.append(stage),
        checkpoint_fn=lambda: checkpoint_calls.append(True),
        on_progress_tick_fn=lambda done_delta, skipped_delta: counter.update(
            {
                "done": counter["done"] + done_delta,
                "skipped": counter["skipped"] + skipped_delta,
            }
        ),
    )

    assert result == {"done": 2, "skipped": 1}
    assert counter == {"done": 2, "skipped": 1}
    assert seen_keys == {"k1", "k2"}
    # AWF-108(a): skip emit is throttled every 200 consecutive skips; only 1 skip here ??no skip emit
    assert progress_calls == ["1h combo"]
    assert len(append_calls) == 1
    assert append_calls[0][1]["combo_key"] == "k2"
    assert len(checkpoint_calls) == 1


def test_run_timeframe_ready_search_parallel_branch(monkeypatch):
    index = pd.date_range("2024-01-01", periods=2, freq="h")
    captured = {}

    def _capture_parallel(**kwargs):
        captured.update(kwargs)

    def _unexpected_search(**_kwargs):
        raise AssertionError("search branch should not be called")

    monkeypatch.setattr(_e_search, "_run_parallel_combo_search_for_timeframe", _capture_parallel)
    monkeypatch.setattr(_e_search, "_run_search_for_timeframe", _unexpected_search)

    e._run_timeframe_ready_search(
        timeframe="1h",
        data_days=30,
        stage_prefix="1h",
        timeframe_runtime={
            "ctx": {
                "trade_close": pd.DataFrame({"ETH/BTC": [1.0, 1.1]}, index=index),
                "total_days": 1,
            },
            "trade_symbols_tf": ["ETH/BTC"],
            "timeframe_data_fingerprint": "fp-1h",
            "runtime_eval": {"runtime": True},
        },
        search_mode="combo",
        max_workers=2,
        regime_variants=[{"regime_type": "trend", "vol_mode": "high", "regime_name": "trend_high"}],
        regime_lookup={"trend_high": {"regime_type": "trend", "vol_mode": "high", "regime_name": "trend_high"}},
        mom_lookbacks=[6],
        vol_lookbacks=[24],
        vol_zs=[0.8],
        trade_mom_lookbacks=[3],
        tp_stops=[0.003],
        sl_stops=[0.006],
        max_holds=[2],
        combo_keys_all=[("rsi",)],
        indicator_param_options={"rsi": [{}]},
        existing_combo_df=pd.DataFrame(),
        combo_group_fields=[],
        top_n_fine=10,
        min_avg_daily_trades_target=5.0,
        indicator_defaults={},
        indicator_param_fields=[
            "rsi_long",
            "rsi_short",
            "bb_width",
            "atr_ratio",
            "ma_fast",
            "ma_slow",
            "macd_hist_ratio",
            "stoch_long",
            "stoch_short",
            "obv_lookback",
            "volume_lookback",
            "volume_z",
            "roc_lookback",
            "roc_threshold",
            "mfi_long",
            "mfi_short",
            "cmf_lookback",
            "cmf_threshold",
            "vroc_lookback",
            "vroc_threshold",
            "ad_lookback",
        ],
        exchange="binance",
        base_symbol="BTC/USDT",
        capital_mode="shared",
        fees=0.001,
        slippage_bps=2.0,
        spread_bps=2.0,
        funding_rate_daily=0.0,
        order_size_pct=0.5,
        max_concurrent_positions=2,
        init_cash_usdt=1000.0,
        wf_train_days=7,
        wf_test_days=2,
        wf_step_days=2,
        wf_mode="rolling",
        rsi_window=14,
        config_sha256="cfg123",
        seen_keys=set(),
        pending_symbol_rows=[],
        pending_combo_rows=[],
        combo_key_from_dict_fn=lambda row: str(row),
        indicator_combo_label_fn=lambda combo: "+".join(combo),
        iter_indicator_param_combos_fn=lambda combo, options: options.get(combo[0], [{}]),
        run_combo_tasks_fn=lambda *args, **kwargs: [],
        evaluate_combo_task_fn=lambda *args, **kwargs: {},
        wait_if_paused_fn=lambda stage: None,
        emit_progress_fn=lambda stage, force=False: None,
        checkpoint_fn=lambda: None,
        on_progress_tick_fn=lambda done_delta, skipped_delta: None,
        on_refine_plan_fn=lambda fine_total, stage: None,
        apply_quality_filters_fn=lambda df: df,
        sort_by_score_fn=lambda df, tie_break_avg_hold=True: (df, None),
        expand_float_fn=lambda base, step, min_value=None: [base],
        safe_float_fn=lambda v, d: d if v is None else float(v),
        refine_indicator_params_fn=lambda key, row, steps, defaults: [defaults.get(key, {})],
        safe_int_fn=lambda v, d: d if v is None else int(v),
    )

    assert captured["stage"] == "1h combo"
    assert captured["max_workers"] == 2
    assert captured["runtime_eval"] == {"runtime": True}
    assert callable(captured["build_combo_task_fn"])
    assert callable(captured["append_eval_result_fn"])


def test_run_timeframe_ready_search_refine_branch_invokes_refine_plan(monkeypatch):
    index = pd.date_range("2024-01-01", periods=2, freq="h")
    captured = {}
    refine_notice = {}

    def _capture_search(**kwargs):
        captured.update(kwargs)
        kwargs["on_refine_plan_fn"](3, "1h refine")

    def _unexpected_parallel(**_kwargs):
        raise AssertionError("parallel branch should not be called")

    monkeypatch.setattr(_e_search, "_run_search_for_timeframe", _capture_search)
    monkeypatch.setattr(_e_search, "_run_parallel_combo_search_for_timeframe", _unexpected_parallel)

    e._run_timeframe_ready_search(
        timeframe="1h",
        data_days=30,
        stage_prefix="1h",
        timeframe_runtime={
            "ctx": {
                "trade_close": pd.DataFrame({"ETH/BTC": [1.0, 1.1]}, index=index),
                "total_days": 1,
            },
            "trade_symbols_tf": ["ETH/BTC"],
            "timeframe_data_fingerprint": "fp-1h",
            "runtime_eval": {"runtime": True},
        },
        search_mode="refine",
        max_workers=1,
        regime_variants=[{"regime_type": "trend", "vol_mode": "high", "regime_name": "trend_high"}],
        regime_lookup={"trend_high": {"regime_type": "trend", "vol_mode": "high", "regime_name": "trend_high"}},
        mom_lookbacks=[6],
        vol_lookbacks=[24],
        vol_zs=[0.8],
        trade_mom_lookbacks=[3],
        tp_stops=[0.003],
        sl_stops=[0.006],
        max_holds=[2],
        combo_keys_all=[("rsi",)],
        indicator_param_options={"rsi": [{}]},
        existing_combo_df=pd.DataFrame(),
        combo_group_fields=[],
        top_n_fine=10,
        min_avg_daily_trades_target=5.0,
        indicator_defaults={},
        indicator_param_fields=[
            "rsi_long",
            "rsi_short",
            "bb_width",
            "atr_ratio",
            "ma_fast",
            "ma_slow",
            "macd_hist_ratio",
            "stoch_long",
            "stoch_short",
            "obv_lookback",
            "volume_lookback",
            "volume_z",
            "roc_lookback",
            "roc_threshold",
            "mfi_long",
            "mfi_short",
            "cmf_lookback",
            "cmf_threshold",
            "vroc_lookback",
            "vroc_threshold",
            "ad_lookback",
        ],
        exchange="binance",
        base_symbol="BTC/USDT",
        capital_mode="shared",
        fees=0.001,
        slippage_bps=2.0,
        spread_bps=2.0,
        funding_rate_daily=0.0,
        order_size_pct=0.5,
        max_concurrent_positions=2,
        init_cash_usdt=1000.0,
        wf_train_days=7,
        wf_test_days=2,
        wf_step_days=2,
        wf_mode="rolling",
        rsi_window=14,
        config_sha256="cfg123",
        seen_keys=set(),
        pending_symbol_rows=[],
        pending_combo_rows=[],
        combo_key_from_dict_fn=lambda row: str(row),
        indicator_combo_label_fn=lambda combo: "+".join(combo),
        iter_indicator_param_combos_fn=lambda combo, options: options.get(combo[0], [{}]),
        run_combo_tasks_fn=lambda *args, **kwargs: [],
        evaluate_combo_task_fn=lambda *args, **kwargs: {},
        wait_if_paused_fn=lambda stage: None,
        emit_progress_fn=lambda stage, force=False: None,
        checkpoint_fn=lambda: None,
        on_progress_tick_fn=lambda done_delta, skipped_delta: None,
        on_refine_plan_fn=lambda fine_total, stage: refine_notice.update(
            {"fine_total": fine_total, "stage": stage}
        ),
        apply_quality_filters_fn=lambda df: df,
        sort_by_score_fn=lambda df, tie_break_avg_hold=True: (df, None),
        expand_float_fn=lambda base, step, min_value=None: [base],
        safe_float_fn=lambda v, d: d if v is None else float(v),
        refine_indicator_params_fn=lambda key, row, steps, defaults: [defaults.get(key, {})],
        safe_int_fn=lambda v, d: d if v is None else int(v),
    )

    assert captured["search_mode"] == "refine"
    assert captured["stage_prefix"] == "1h"
    assert callable(captured["eval_combo_fn"])
    assert refine_notice == {"fine_total": 3, "stage": "1h refine"}


def test_run_combo_eval_step_skip_existing_key():
    waits = []
    progress = []
    checkpoints = []
    append_calls = []
    eval_calls = []
    counter = {"done": 0, "skipped": 0}
    seen_keys = {"k1"}

    result = e._run_combo_eval_step(
        regime={"regime_name": "trend_high"},
        indicator_combo=("rsi",),
        combo_params={"a": 1},
        vol_lookback=24,
        vol_z=0.8,
        mom_lookback=6,
        trade_mom_lookback=3,
        tp_stop=0.003,
        sl_stop=0.006,
        max_hold=2,
        stage="1h combo",
        wait_if_paused_fn=lambda stage: waits.append(stage),
        build_combo_task_fn=lambda **kwargs: ("k1", {"combo_key": "k1", "kwargs": kwargs}),
        seen_keys=seen_keys,
        evaluate_combo_task_fn=lambda task, runtime: eval_calls.append((task, runtime)),
        runtime_eval={"ctx": "runtime"},
        append_eval_result_fn=lambda result_payload, task_payload: append_calls.append(
            (result_payload, task_payload)
        ),
        emit_progress_fn=lambda stage: progress.append(stage),
        checkpoint_fn=lambda: checkpoints.append(True),
        on_progress_tick_fn=lambda done_delta, skipped_delta: counter.update(
            {
                "done": counter["done"] + done_delta,
                "skipped": counter["skipped"] + skipped_delta,
            }
        ),
    )

    assert result == {"skipped": True, "evaluated": False}
    assert waits == ["1h combo"]
    assert progress == ["1h combo"]
    assert checkpoints == []
    assert eval_calls == []
    assert append_calls == []
    assert counter == {"done": 1, "skipped": 1}
    assert seen_keys == {"k1"}


def test_run_combo_eval_step_evaluate_path():
    waits = []
    progress = []
    checkpoints = []
    append_calls = []
    eval_calls = []
    counter = {"done": 0, "skipped": 0}
    seen_keys = set()

    result = e._run_combo_eval_step(
        regime={"regime_name": "trend_high"},
        indicator_combo=("rsi",),
        combo_params={"a": 1},
        vol_lookback=24,
        vol_z=0.8,
        mom_lookback=6,
        trade_mom_lookback=3,
        tp_stop=0.003,
        sl_stop=0.006,
        max_hold=2,
        stage="1h combo",
        wait_if_paused_fn=lambda stage: waits.append(stage),
        build_combo_task_fn=lambda **kwargs: ("k2", {"combo_key": "k2", "kwargs": kwargs}),
        seen_keys=seen_keys,
        evaluate_combo_task_fn=lambda task, runtime: eval_calls.append((task, runtime)) or {"ok": True},
        runtime_eval={"ctx": "runtime"},
        append_eval_result_fn=lambda result_payload, task_payload: append_calls.append(
            (result_payload, task_payload)
        ),
        emit_progress_fn=lambda stage: progress.append(stage),
        checkpoint_fn=lambda: checkpoints.append(True),
        on_progress_tick_fn=lambda done_delta, skipped_delta: counter.update(
            {
                "done": counter["done"] + done_delta,
                "skipped": counter["skipped"] + skipped_delta,
            }
        ),
    )

    assert result == {"skipped": False, "evaluated": True}
    assert waits == ["1h combo"]
    assert progress == ["1h combo"]
    assert checkpoints == [True]
    assert len(eval_calls) == 1
    assert eval_calls[0][0]["combo_key"] == "k2"
    assert eval_calls[0][1] == {"ctx": "runtime"}
    assert len(append_calls) == 1
    assert append_calls[0][0] == {"ok": True}
    assert append_calls[0][1]["combo_key"] == "k2"
    assert counter == {"done": 1, "skipped": 0}
    assert seen_keys == {"k2"}


def test_prepare_timeframe_runtime_or_skip_success_and_skip_paths():
    progress_calls = []
    warnings = []

    success = e._prepare_timeframe_runtime_or_skip(
        prepare_timeframe_runtime_fn=lambda **kwargs: {"ctx": kwargs["timeframe"]},
        prepare_kwargs={"timeframe": "1h"},
        search_mode="combo",
        total_combos=100,
        done=20,
        count_coarse_combos_fn=lambda: 10,
        stage_prefix="1h",
        timeframe="1h",
        emit_progress_fn=lambda **kwargs: progress_calls.append(kwargs),
        warn_fn=warnings.append,
    )
    assert success["ok"] is True
    assert success["timeframe_runtime"] == {"ctx": "1h"}
    assert success["total_combos"] == 100
    assert progress_calls == []
    assert warnings == []

    def _raise(**_kwargs):
        raise RuntimeError("boom")

    skipped = e._prepare_timeframe_runtime_or_skip(
        prepare_timeframe_runtime_fn=_raise,
        prepare_kwargs={"timeframe": "1h"},
        search_mode="combo",
        total_combos=100,
        done=95,
        count_coarse_combos_fn=lambda: 10,
        stage_prefix="1h",
        timeframe="1h",
        emit_progress_fn=lambda **kwargs: progress_calls.append(kwargs),
        warn_fn=warnings.append,
    )
    assert skipped["ok"] is False
    assert skipped["timeframe_runtime"] is None
    assert skipped["total_combos"] == 95
    assert progress_calls[-1] == {"stage": "1h skipped", "force": True}
    assert warnings[-1] == "[warn] timeframe 1h skipped: boom"


def test_build_prepare_timeframe_runtime_kwargs_maps_runtime_inputs():
    def _prepare_ctx(**kwargs):
        return kwargs

    def _build_windows(*_args, **_kwargs):
        return []

    def _fingerprint(payload):
        return payload

    got = e._build_prepare_timeframe_runtime_kwargs(
        timeframe="1h",
        data_days=30,
        base_symbol="BTC/USDT",
        trade_symbols=["ETH/BTC"],
        exchange="binance",
        cache_dir="artifacts/cache",
        cache_format="parquet",
        vol_lookbacks=[24],
        mom_lookbacks=[6],
        trade_mom_lookbacks=[3],
        rsi_window=14,
        bb_window=20,
        bb_alpha=2.0,
        atr_window=14,
        ma_pairs=[(10, 30)],
        obv_lookbacks=[12],
        volume_lookbacks=[12],
        roc_lookbacks=[6],
        cmf_lookbacks=[20],
        mfi_window=14,
        vroc_lookbacks=[12],
        ad_lookbacks=[20],
        cci_lookbacks=[14],
        willr_lookbacks=[14],
        adx_lookbacks=[14],
        trix_lookbacks=[12],
        dpo_lookbacks=[14],
        efi_lookbacks=[13],
        vwma_lookbacks=[20],
        ultosc_periods=(7, 14, 28),
        keltner_lookbacks=[14],
        donchian_lookbacks=[14],
        ppo_fast=12,
        ppo_slow=26,
        ppo_signal=9,
        chop_lookbacks=[14],
        init_cash_usdt=1000.0,
        capital_mode="shared",
        wf_train_days=7,
        wf_test_days=2,
        wf_step_days=2,
        wf_mode="rolling",
        fees=0.001,
        slippage_bps=2.0,
        spread_bps=2.0,
        funding_rate_daily=0.0,
        order_size_pct=0.5,
        max_concurrent_positions=2,
        config_sha256="cfg123",
        bar_hours=1.0,
        prepare_timeframe_context_fn=_prepare_ctx,
        build_walk_forward_windows_fn=_build_windows,
        compute_data_fingerprint_fn=_fingerprint,
    )

    assert got["timeframe"] == "1h"
    assert got["data_days"] == 30
    assert got["trade_symbols"] == ["ETH/BTC"]
    assert got["wf_mode"] == "rolling"
    assert got["bar_hours"] == 1.0
    assert got["prepare_timeframe_context_fn"] is _prepare_ctx
    assert got["build_walk_forward_windows_fn"] is _build_windows
    assert got["compute_data_fingerprint_fn"] is _fingerprint


def test_prepare_timeframe_runtime_context_and_from_context_builder():
    context = e._build_prepare_timeframe_runtime_context(
        base_symbol="BTC/USDT",
        trade_symbols=["ETH/BTC"],
        exchange="binance",
        cache_dir="artifacts/cache",
        cache_format="parquet",
        vol_lookbacks=[24],
        mom_lookbacks=[6],
        trade_mom_lookbacks=[3],
        rsi_window=14,
        bb_window=20,
        bb_alpha=2.0,
        atr_window=14,
        ma_pairs=[(10, 30)],
        obv_lookbacks=[12],
        volume_lookbacks=[12],
        roc_lookbacks=[6],
        cmf_lookbacks=[20],
        mfi_window=14,
        vroc_lookbacks=[12],
        ad_lookbacks=[20],
        cci_lookbacks=[14],
        willr_lookbacks=[14],
        adx_lookbacks=[14],
        trix_lookbacks=[12],
        dpo_lookbacks=[14],
        efi_lookbacks=[13],
        vwma_lookbacks=[20],
        ultosc_periods=(7, 14, 28),
        keltner_lookbacks=[14],
        donchian_lookbacks=[14],
        ppo_fast=12,
        ppo_slow=26,
        ppo_signal=9,
        chop_lookbacks=[14],
        init_cash_usdt=1000.0,
        capital_mode="shared",
        wf_train_days=7,
        wf_test_days=2,
        wf_step_days=2,
        wf_mode="rolling",
        fees=0.001,
        slippage_bps=2.0,
        spread_bps=2.0,
        funding_rate_daily=0.0,
        order_size_pct=0.5,
        max_concurrent_positions=2,
        config_sha256="cfg123",
        prepare_timeframe_context_fn=lambda **kwargs: kwargs,
        build_walk_forward_windows_fn=lambda *args, **kwargs: [],
        compute_data_fingerprint_fn=lambda payload: payload,
    )
    got = e._build_prepare_timeframe_runtime_kwargs_from_context(
        timeframe="1h",
        data_days=30,
        bar_hours=1.0,
        prepare_timeframe_runtime_context=context,
    )
    assert got["timeframe"] == "1h"
    assert got["data_days"] == 30
    assert got["bar_hours"] == 1.0
    assert got["base_symbol"] == "BTC/USDT"
    assert got["trade_symbols"] == ["ETH/BTC"]


def _sample_shared_pipeline_runtime_context():
    return e._build_shared_pipeline_runtime_context(
        base_symbol="BTC/USDT",
        trade_symbols=["ETH/BTC"],
        exchange="binance",
        cache_dir="artifacts/cache",
        cache_format="parquet",
        vol_lookbacks=[24],
        vol_zs=[0.8],
        mom_lookbacks=[6],
        trade_mom_lookbacks=[3],
        rsi_window=14,
        bb_window=20,
        bb_alpha=2.0,
        atr_window=14,
        ma_pairs=[(10, 30)],
        obv_lookbacks=[12],
        volume_lookbacks=[12],
        roc_lookbacks=[6],
        cmf_lookbacks=[20],
        mfi_window=14,
        vroc_lookbacks=[12],
        ad_lookbacks=[20],
        cci_lookbacks=[14],
        willr_lookbacks=[14],
        adx_lookbacks=[14],
        trix_lookbacks=[12],
        dpo_lookbacks=[14],
        efi_lookbacks=[13],
        vwma_lookbacks=[20],
        ultosc_periods=(7, 14, 28),
        keltner_lookbacks=[14],
        donchian_lookbacks=[14],
        ppo_fast=12,
        ppo_slow=26,
        ppo_signal=9,
        chop_lookbacks=[14],
        init_cash_usdt=1000.0,
        capital_mode="shared",
        wf_train_days=7,
        wf_test_days=2,
        wf_step_days=2,
        wf_mode="rolling",
        indicator_param_fields=["rsi_long"],
        fees=0.001,
        slippage_bps=2.0,
        spread_bps=2.0,
        funding_rate_daily=0.0,
        order_size_pct=0.5,
        max_concurrent_positions=2,
        config_sha256="cfg123",
        combo_seed=42,
    )


def test_prepare_timeframe_runtime_context_from_shared_builder():
    shared = _sample_shared_pipeline_runtime_context()
    context = e._build_prepare_timeframe_runtime_context_from_shared(
        shared_pipeline_runtime_context=shared,
        prepare_timeframe_context_fn=lambda **kwargs: kwargs,
        build_walk_forward_windows_fn=lambda *args, **kwargs: [],
        compute_data_fingerprint_fn=lambda payload: payload,
    )

    got = e._build_prepare_timeframe_runtime_kwargs_from_context(
        timeframe="1h",
        data_days=30,
        bar_hours=1.0,
        prepare_timeframe_runtime_context=context,
    )

    assert got["base_symbol"] == "BTC/USDT"
    assert got["trade_symbols"] == ["ETH/BTC"]
    assert got["capital_mode"] == "shared"
    assert got["fees"] == 0.001
    assert got["config_sha256"] == "cfg123"


def test_build_timeframe_ready_search_kwargs_maps_inputs_and_sort_wiring():
    sort_calls = []

    def _sort_impl(df, tie_break_avg_hold=True, ranking_config=None):
        sort_calls.append(
            {
                "rows": len(df),
                "tie_break_avg_hold": tie_break_avg_hold,
                "ranking_config": ranking_config,
            }
        )
        return (df.copy(), None)

    got = e._build_timeframe_ready_search_kwargs(
        timeframe="1h",
        data_days=30,
        stage_prefix="1h",
        timeframe_runtime={"ctx": "runtime"},
        search_mode="combo",
        max_workers=2,
        regime_variants=[{"regime_name": "trend_high"}],
        regime_lookup={"trend_high": {"regime_name": "trend_high"}},
        mom_lookbacks=[6],
        vol_lookbacks=[24],
        vol_zs=[0.8],
        trade_mom_lookbacks=[3],
        tp_stops=[0.003],
        sl_stops=[0.006],
        max_holds=[2],
        combo_keys_all=[("rsi",)],
        indicator_param_options={"rsi": [{"rsi_long": 60.0}]},
        existing_combo_df=pd.DataFrame(),
        combo_group_fields=["indicator_list", "regime_name", "vol_mode"],
        top_n_fine=5,
        min_avg_daily_trades_target=5.0,
        indicator_defaults={"rsi_long": None},
        indicator_param_fields=["rsi_long"],
        exchange="binance",
        base_symbol="BTC/USDT",
        capital_mode="shared",
        fees=0.001,
        slippage_bps=1.0,
        spread_bps=2.0,
        funding_rate_daily=0.0,
        order_size_pct=0.5,
        max_concurrent_positions=2,
        init_cash_usdt=1000.0,
        wf_train_days=7,
        wf_test_days=2,
        wf_step_days=2,
        wf_mode="rolling",
        rsi_window=14,
        config_sha256="cfg123",
        seen_keys={"k1"},
        pending_symbol_rows=[],
        pending_combo_rows=[],
        combo_key_from_dict_fn=lambda payload: payload["combo_key"],
        indicator_combo_label_fn=lambda combo: "+".join(combo),
        iter_indicator_param_combos_fn=lambda **kwargs: [],
        run_combo_tasks_fn=lambda **kwargs: [],
        evaluate_combo_task_fn=lambda task, runtime: {"ok": True},
        wait_if_paused_fn=lambda stage: None,
        emit_progress_fn=lambda **kwargs: None,
        checkpoint_fn=lambda **kwargs: None,
        on_progress_tick_fn=lambda done_delta, skipped_delta: None,
        apply_quality_filters_fn=lambda df: df,
        sort_by_score_impl_fn=_sort_impl,
        ranking_config={"mode": "composite"},
        expand_float_fn=lambda value: [value],
        safe_float_fn=lambda value, default: default if pd.isna(value) else float(value),
        refine_indicator_params_fn=lambda *args, **kwargs: {},
        safe_int_fn=lambda value, default: int(default if pd.isna(value) else value),
    )

    assert got["timeframe"] == "1h"
    assert got["timeframe_runtime"] == {"ctx": "runtime"}
    assert got["search_mode"] == "combo"
    assert got["max_workers"] == 2
    assert got["wf_mode"] == "rolling"
    assert got["config_sha256"] == "cfg123"
    assert got["seen_keys"] == {"k1"}
    assert "on_refine_plan_fn" not in got

    sort_result = got["sort_by_score_fn"](
        pd.DataFrame([{"score": 1.0}]),
        tie_break_avg_hold=False,
    )
    assert len(sort_result[0]) == 1
    assert sort_calls == [
        {
            "rows": 1,
            "tie_break_avg_hold": False,
            "ranking_config": {"mode": "composite"},
        }
    ]


def test_timeframe_ready_search_context_and_from_context_builder():
    sort_calls = []

    def _sort_impl(df, tie_break_avg_hold=True, ranking_config=None):
        sort_calls.append((tie_break_avg_hold, ranking_config))
        return (df.copy(), None)

    context = e._build_timeframe_ready_search_context(
        search_mode="combo",
        max_workers=2,
        regime_variants=[{"regime_name": "trend_high"}],
        regime_lookup={"trend_high": {"regime_name": "trend_high"}},
        mom_lookbacks=[6],
        vol_lookbacks=[24],
        vol_zs=[0.8],
        trade_mom_lookbacks=[3],
        tp_stops=[0.003],
        sl_stops=[0.006],
        max_holds=[2],
        combo_keys_all=[("rsi",)],
        indicator_param_options={"rsi": [{"rsi_long": 60.0}]},
        existing_combo_df=pd.DataFrame(),
        combo_group_fields=["indicator_list", "regime_name", "vol_mode"],
        top_n_fine=5,
        min_avg_daily_trades_target=5.0,
        indicator_defaults={"rsi_long": None},
        indicator_param_fields=["rsi_long"],
        exchange="binance",
        base_symbol="BTC/USDT",
        capital_mode="shared",
        fees=0.001,
        slippage_bps=1.0,
        spread_bps=2.0,
        funding_rate_daily=0.0,
        order_size_pct=0.5,
        max_concurrent_positions=2,
        init_cash_usdt=1000.0,
        wf_train_days=7,
        wf_test_days=2,
        wf_step_days=2,
        wf_mode="rolling",
        rsi_window=14,
        config_sha256="cfg123",
        ranking_config={"mode": "composite"},
        seen_keys={"k1"},
        pending_symbol_rows=[],
        pending_combo_rows=[],
        combo_key_from_dict_fn=lambda payload: payload["combo_key"],
        indicator_combo_label_fn=lambda combo: "+".join(combo),
        iter_indicator_param_combos_fn=lambda **kwargs: [],
        run_combo_tasks_fn=lambda **kwargs: [],
        evaluate_combo_task_fn=lambda task, runtime: {"ok": True},
        wait_if_paused_fn=lambda stage: None,
        emit_progress_fn=lambda **kwargs: None,
        checkpoint_fn=lambda **kwargs: None,
        on_progress_tick_fn=lambda done_delta, skipped_delta: None,
        apply_quality_filters_fn=lambda df: df,
        sort_by_score_impl_fn=_sort_impl,
        expand_float_fn=lambda value: [value],
        safe_float_fn=lambda value, default: default if pd.isna(value) else float(value),
        refine_indicator_params_fn=lambda *args, **kwargs: {},
        safe_int_fn=lambda value, default: int(default if pd.isna(value) else value),
    )
    got = e._build_timeframe_ready_search_kwargs_from_context(
        timeframe="1h",
        data_days=30,
        stage_prefix="1h",
        timeframe_runtime={"ctx": "runtime"},
        timeframe_ready_search_context=context,
    )
    assert got["timeframe"] == "1h"
    assert got["stage_prefix"] == "1h"
    assert got["timeframe_runtime"] == {"ctx": "runtime"}
    assert got["search_mode"] == "combo"
    assert got["seen_keys"] == {"k1"}
    _ = got["sort_by_score_fn"](pd.DataFrame([{"score": 1.0}]), tie_break_avg_hold=False)
    assert sort_calls == [(False, {"mode": "composite"})]


def test_timeframe_ready_search_context_from_shared_builder():
    sort_calls = []
    shared = _sample_shared_pipeline_runtime_context()

    def _sort_impl(df, tie_break_avg_hold=True, ranking_config=None):
        sort_calls.append((tie_break_avg_hold, ranking_config))
        return (df.copy(), None)

    context = e._build_timeframe_ready_search_context_from_shared(
        shared_pipeline_runtime_context=shared,
        search_mode="combo",
        max_workers=2,
        regime_variants=[{"regime_name": "trend_high"}],
        regime_lookup={"trend_high": {"regime_name": "trend_high"}},
        tp_stops=[0.003],
        sl_stops=[0.006],
        max_holds=[2],
        combo_keys_all=[("rsi",)],
        indicator_param_options={"rsi": [{"rsi_long": 60.0}]},
        existing_combo_df=pd.DataFrame(),
        combo_group_fields=["indicator_list", "regime_name", "vol_mode"],
        top_n_fine=5,
        min_avg_daily_trades_target=5.0,
        indicator_defaults={"rsi_long": None},
        ranking_config={"mode": "composite"},
        seen_keys={"k1"},
        pending_symbol_rows=[],
        pending_combo_rows=[],
        combo_key_from_dict_fn=lambda payload: payload["combo_key"],
        indicator_combo_label_fn=lambda combo: "+".join(combo),
        iter_indicator_param_combos_fn=lambda **kwargs: [],
        run_combo_tasks_fn=lambda **kwargs: [],
        evaluate_combo_task_fn=lambda task, runtime: {"ok": True},
        wait_if_paused_fn=lambda stage: None,
        emit_progress_fn=lambda **kwargs: None,
        checkpoint_fn=lambda **kwargs: None,
        on_progress_tick_fn=lambda done_delta, skipped_delta: None,
        apply_quality_filters_fn=lambda df: df,
        sort_by_score_impl_fn=_sort_impl,
        expand_float_fn=lambda value: [value],
        safe_float_fn=lambda value, default: default if pd.isna(value) else float(value),
        refine_indicator_params_fn=lambda *args, **kwargs: {},
        safe_int_fn=lambda value, default: int(default if pd.isna(value) else value),
    )
    got = e._build_timeframe_ready_search_kwargs_from_context(
        timeframe="1h",
        data_days=30,
        stage_prefix="1h",
        timeframe_runtime={"ctx": "runtime"},
        timeframe_ready_search_context=context,
    )

    assert got["base_symbol"] == "BTC/USDT"
    assert got["exchange"] == "binance"
    assert got["indicator_param_fields"] == ["rsi_long"]
    assert got["vol_zs"] == [0.8]
    _ = got["sort_by_score_fn"](pd.DataFrame([{"score": 1.0}]), tie_break_avg_hold=False)
    assert sort_calls == [(False, {"mode": "composite"})]


def test_run_timeframe_ready_search_with_refine_tracking_updates_total_and_progress():
    total_state = {"value": 100}
    progress_calls = []
    captured = {}

    def _run_ready(**kwargs):
        captured.update(kwargs)
        kwargs["on_refine_plan_fn"](7, "1h refine")

    e._run_timeframe_ready_search_with_refine_tracking(
        run_timeframe_ready_search_fn=_run_ready,
        run_timeframe_ready_search_kwargs={"timeframe": "1h"},
        get_total_combos_fn=lambda: total_state["value"],
        set_total_combos_fn=lambda value: total_state.update({"value": value}),
        emit_progress_fn=lambda **kwargs: progress_calls.append(kwargs),
    )

    assert captured["timeframe"] == "1h"
    assert callable(captured["on_refine_plan_fn"])
    assert total_state["value"] == 107
    assert progress_calls == [{"stage": "1h refine", "force": True}]


def test_build_timeframe_execution_callbacks_wires_prepare_and_ready_paths():
    calls = {
        "build_prepare": [],
        "prepare_or_skip": [],
        "build_ready": [],
        "run_ready": [],
    }
    progress_calls = []
    total_state = {"value": 100}

    def _build_prepare(**kwargs):
        calls["build_prepare"].append(kwargs)
        return {"prepared": kwargs["timeframe"]}

    def _prepare_or_skip(**kwargs):
        calls["prepare_or_skip"].append(kwargs)
        return {"ok": True, "timeframe_runtime": {"ctx": "runtime"}, "total_combos": kwargs["total_combos"]}

    def _build_ready(**kwargs):
        calls["build_ready"].append(kwargs)
        return {"timeframe": kwargs["timeframe"], "ready": True}

    def _run_ready_with_refine(**kwargs):
        calls["run_ready"].append(kwargs)
        kwargs["set_total_combos_fn"](kwargs["get_total_combos_fn"]() + 3)
        kwargs["emit_progress_fn"](stage="1h refine", force=True)

    callbacks = e._build_timeframe_execution_callbacks(
        search_mode="combo",
        count_coarse_combos_fn=lambda: 5,
        emit_progress_fn=lambda **kwargs: progress_calls.append(kwargs),
        get_total_combos_fn=lambda: total_state["value"],
        set_total_combos_fn=lambda value: total_state.update({"value": value}),
        prepare_timeframe_runtime_context={"prepare": "ctx"},
        prepare_timeframe_runtime_fn=lambda **kwargs: {"ctx": kwargs},
        timeframe_ready_search_context={"ready": "ctx"},
        run_timeframe_ready_search_fn=lambda **kwargs: None,
        run_timeframe_ready_search_with_refine_tracking_fn=_run_ready_with_refine,
        build_prepare_kwargs_from_context_fn=_build_prepare,
        prepare_runtime_or_skip_fn=_prepare_or_skip,
        build_ready_kwargs_from_context_fn=_build_ready,
    )

    prepare_result = callbacks["prepare_runtime_attempt_fn"](
        timeframe="1h",
        data_days=30,
        stage_prefix="1h",
        bar_hours=1.0,
        done=20,
        total_combos=100,
    )
    assert prepare_result["ok"] is True
    assert calls["build_prepare"][0]["timeframe"] == "1h"
    assert calls["build_prepare"][0]["prepare_timeframe_runtime_context"] == {"prepare": "ctx"}
    assert calls["prepare_or_skip"][0]["search_mode"] == "combo"
    assert calls["prepare_or_skip"][0]["stage_prefix"] == "1h"
    assert calls["prepare_or_skip"][0]["count_coarse_combos_fn"]() == 5

    callbacks["on_timeframe_ready_fn"](
        timeframe="1h",
        data_days=30,
        stage_prefix="1h",
        bar_hours=1.0,
        timeframe_runtime={"ctx": "runtime"},
    )
    assert calls["build_ready"][0]["timeframe"] == "1h"
    assert calls["build_ready"][0]["timeframe_ready_search_context"] == {"ready": "ctx"}
    assert calls["run_ready"][0]["run_timeframe_ready_search_kwargs"] == {"timeframe": "1h", "ready": True}
    assert total_state["value"] == 103
    assert progress_calls == [{"stage": "1h refine", "force": True}]


def test_run_timeframe_search_and_finalize_wires_loop_and_finalize_paths():
    calls = {}

    def _run_loop(**kwargs):
        calls["loop"] = kwargs
        return {
            "timeframe_ranges": ["1h (30d): A to B"],
            "timeframe_fingerprints": ["fp-1h"],
        }

    def _build_finalize_kwargs(**kwargs):
        calls["build_finalize_kwargs"] = kwargs
        return {"combo_path": "artifacts/combo.csv"}

    def _run_finalize(**kwargs):
        calls["run_finalize"] = kwargs
        return {"ok": True, "completion_outputs": {"combo_summary": "artifacts/combo.csv"}}

    result = e._run_timeframe_search_and_finalize(
        timeframe_configs=[{"timeframe": "1h", "days": 30}],
        wf_train_days=7,
        wf_test_days=2,
        prepare_runtime_attempt_fn=lambda **kwargs: {
            "ok": False,
            "total_combos": kwargs["total_combos"],
            "timeframe_runtime": None,
        },
        on_timeframe_ready_fn=lambda **kwargs: None,
        get_done_fn=lambda: 20,
        get_total_combos_fn=lambda: 100,
        set_total_combos_fn=lambda value: None,
        timeframe_to_hours_fn=lambda tf: 1.0,
        finalize_pipeline_context={"ctx": "finalize"},
        checkpoint_fn=lambda **kwargs: None,
        run_finalize_pipeline_fn=lambda **kwargs: {"ok": True},
        run_timeframe_search_loop_fn=_run_loop,
        build_finalize_pipeline_kwargs_from_context_fn=_build_finalize_kwargs,
        run_finalize_after_timeframe_loop_fn=_run_finalize,
    )

    assert calls["loop"]["timeframe_configs"] == [{"timeframe": "1h", "days": 30}]
    assert calls["loop"]["wf_train_days"] == 7
    assert calls["loop"]["wf_test_days"] == 2
    assert callable(calls["loop"]["prepare_runtime_attempt_fn"])
    assert callable(calls["loop"]["on_timeframe_ready_fn"])
    assert calls["build_finalize_kwargs"] == {"finalize_pipeline_context": {"ctx": "finalize"}}
    assert calls["run_finalize"]["timeframe_loop_result"] == {
        "timeframe_ranges": ["1h (30d): A to B"],
        "timeframe_fingerprints": ["fp-1h"],
    }
    assert calls["run_finalize"]["finalize_kwargs"] == {"combo_path": "artifacts/combo.csv"}
    assert result == {"ok": True, "completion_outputs": {"combo_summary": "artifacts/combo.csv"}}


def test_run_timeframe_pipeline_wires_callback_builder_and_runner():
    calls = {}
    prepare_cb = lambda **kwargs: {"ok": True}
    ready_cb = lambda **kwargs: None

    def _build_callbacks(**kwargs):
        calls["build_callbacks"] = kwargs
        return {
            "prepare_runtime_attempt_fn": prepare_cb,
            "on_timeframe_ready_fn": ready_cb,
        }

    def _run_pipeline(**kwargs):
        calls["run_pipeline"] = kwargs
        return {"ok": True, "completion_outputs": {"combo_summary": "artifacts/combo.csv"}}

    result = e._run_timeframe_pipeline(
        timeframe_configs=[{"timeframe": "1h", "days": 30}],
        wf_train_days=7,
        wf_test_days=2,
        search_mode="combo",
        count_coarse_combos_fn=lambda: 12,
        emit_progress_fn=lambda **kwargs: None,
        get_done_fn=lambda: 3,
        get_total_combos_fn=lambda: 100,
        set_total_combos_fn=lambda value: None,
        prepare_timeframe_runtime_context={"prepare": "ctx"},
        prepare_timeframe_runtime_fn=lambda **kwargs: {"ctx": "runtime"},
        timeframe_ready_search_context={"ready": "ctx"},
        run_timeframe_ready_search_fn=lambda **kwargs: None,
        run_timeframe_ready_search_with_refine_tracking_fn=lambda **kwargs: None,
        timeframe_to_hours_fn=lambda timeframe: 1.0,
        finalize_pipeline_context={"finalize": "ctx"},
        checkpoint_fn=lambda **kwargs: None,
        run_finalize_pipeline_fn=lambda **kwargs: {"ok": True},
        build_timeframe_execution_callbacks_fn=_build_callbacks,
        run_timeframe_search_and_finalize_fn=_run_pipeline,
    )

    assert calls["build_callbacks"]["search_mode"] == "combo"
    assert calls["build_callbacks"]["prepare_timeframe_runtime_context"] == {"prepare": "ctx"}
    assert calls["build_callbacks"]["timeframe_ready_search_context"] == {"ready": "ctx"}
    assert calls["run_pipeline"]["timeframe_configs"] == [{"timeframe": "1h", "days": 30}]
    assert calls["run_pipeline"]["wf_train_days"] == 7
    assert calls["run_pipeline"]["wf_test_days"] == 2
    assert calls["run_pipeline"]["prepare_runtime_attempt_fn"] is prepare_cb
    assert calls["run_pipeline"]["on_timeframe_ready_fn"] is ready_cb
    assert calls["run_pipeline"]["finalize_pipeline_context"] == {"finalize": "ctx"}
    assert result == {"ok": True, "completion_outputs": {"combo_summary": "artifacts/combo.csv"}}


def test_handle_finalize_result_warn_path():
    print_calls = []
    progress_calls = []
    handled = e._handle_finalize_result(
        finalize_result={"ok": False, "warning": "[warn] skip finalize"},
        emit_progress_fn=lambda **kwargs: progress_calls.append(kwargs),
        print_fn=lambda *args: print_calls.append(args),
    )

    assert handled is False
    assert progress_calls == []
    assert print_calls == [("[warn] skip finalize",)]


def test_handle_finalize_result_completion_path():
    print_calls = []
    progress_calls = []
    handled = e._handle_finalize_result(
        finalize_result={
            "ok": True,
            "completion_outputs": {
                "combo_summary": "artifacts/combo.csv",
                "report_run": "artifacts/report.html",
            },
        },
        emit_progress_fn=lambda **kwargs: progress_calls.append(kwargs),
        print_fn=lambda *args: print_calls.append(args),
    )

    assert handled is True
    assert progress_calls == [{"stage": "complete", "force": True}]
    assert print_calls == [
        ("combo_summary", "artifacts/combo.csv"),
        ("report_run", "artifacts/report.html"),
    ]


def test_build_finalize_pipeline_kwargs_maps_inputs_and_top_score_wiring(tmp_path):
    top_score_calls = []

    def _top_by_score_impl(df, top_n, tie_break_avg_hold, ranking_config):
        top_score_calls.append(
            {
                "rows": len(df),
                "top_n": top_n,
                "tie_break_avg_hold": tie_break_avg_hold,
                "ranking_config": ranking_config,
            }
        )
        return (df.head(top_n).copy(), None)

    got = e._build_finalize_pipeline_kwargs(
        combo_path="artifacts/combo.csv",
        per_symbol_path="artifacts/symbol.csv",
        out_dir=str(tmp_path),
        run_id="r1",
        timeframe_configs=[{"timeframe": "1h", "days": 30}],
        timeframe_days_map={"1h": 30},
        safe_int_fn=lambda value, default: int(default if pd.isna(value) else value),
        min_avg_daily_trades_target=5.0,
        apply_quality_filters_fn=lambda df: df.copy(),
        top_by_score_impl_fn=_top_by_score_impl,
        ranking_config={"mode": "composite"},
        history_rows=10,
        base_symbol="BTC/USDT",
        trade_symbols=["ETH/BTC"],
        exchange="binance",
        cache_dir=str(tmp_path / "cache"),
        cache_format="parquet",
        vol_lookbacks=[24],
        vol_zs=[0.8],
        mom_lookbacks=[6],
        trade_mom_lookbacks=[3],
        rsi_window=14,
        bb_window=20,
        bb_alpha=2.0,
        atr_window=14,
        ma_pairs=[(10, 30)],
        obv_lookbacks=[12],
        volume_lookbacks=[12],
        roc_lookbacks=[6],
        cmf_lookbacks=[20],
        mfi_window=14,
        vroc_lookbacks=[12],
        ad_lookbacks=[20],
        cci_lookbacks=[14],
        willr_lookbacks=[14],
        adx_lookbacks=[14],
        trix_lookbacks=[12],
        dpo_lookbacks=[14],
        efi_lookbacks=[13],
        vwma_lookbacks=[20],
        ultosc_periods=(7, 14, 28),
        keltner_lookbacks=[14],
        donchian_lookbacks=[14],
        ppo_fast=12,
        ppo_slow=26,
        ppo_signal=9,
        chop_lookbacks=[14],
        init_cash_usdt=1000.0,
        capital_mode="shared",
        wf_train_days=7,
        wf_test_days=2,
        wf_step_days=2,
        wf_mode="rolling",
        indicator_param_fields=["rsi_long"],
        fees=0.001,
        slippage_bps=1.0,
        spread_bps=2.0,
        funding_rate_daily=0.0,
        order_size_pct=0.5,
        max_concurrent_positions=2,
        labels={"report_title": "Report"},
        config_sha256="cfg123",
        timestamp_utc="2026-02-13T00:00:00Z",
        leaderboard_path=str(tmp_path / "leaderboard.csv"),
        run_metadata_path=str(tmp_path / "run_metadata.json"),
        run_metadata_path_run=str(tmp_path / "run_metadata_r1.json"),
        registry_path=str(tmp_path / "run_registry.json"),
        search_mode="combo",
        config_path="artifacts/sweep_config.json",
        prepare_timeframe_context_fn=lambda **kwargs: {"ctx": kwargs["timeframe"]},
        indicator_combo_label_fn=lambda combo: "+".join(combo),
        coerce_indicator_params_fn=lambda combo, params, ctx: params,
        pick_series_from_map_fn=lambda series_map, lookback, default_key: (series_map[default_key], default_key),
        apply_indicator_combo_fn=lambda long_regime, short_regime, combo, params, ctx: (
            long_regime,
            short_regime,
            params,
        ),
        timeframe_to_hours_fn=lambda timeframe: 1.0,
        run_pf_fn=lambda *args, **kwargs: None,
        plot_portfolio_fn=lambda pf, symbol: None,
        calc_pf_series_fn=lambda pf, symbols, bar_hours: {},
        build_walk_forward_slices_fn=lambda index, train_days, test_days, step_days, mode=None: [],
        df_to_html_fn=lambda df, columns, label_map: "",
        combine_data_fingerprints_fn=lambda fingerprints: "fp-run",
        write_run_metadata_fn=lambda path, payload: None,
        update_run_registry_fn=lambda **kwargs: None,
    )

    assert got["combo_path"] == "artifacts/combo.csv"
    assert got["run_id"] == "r1"
    assert got["ranking_config"] == {"mode": "composite"}
    assert got["history_rows"] == 10
    assert got["search_mode"] == "combo"

    top_df = pd.DataFrame([{"score": 1.0}, {"score": 2.0}])
    result_main = got["top_by_score_fn"](top_df, top_n=1, tie_break_avg_hold=False)
    result_lb = got["top_by_score_leaderboard_fn"](top_df, top_n=2, tie_break_avg_hold=True)
    assert len(result_main[0]) == 1
    assert len(result_lb[0]) == 2
    assert top_score_calls == [
        {
            "rows": 2,
            "top_n": 1,
            "tie_break_avg_hold": False,
            "ranking_config": {"mode": "composite"},
        },
        {
            "rows": 2,
            "top_n": 2,
            "tie_break_avg_hold": True,
            "ranking_config": {"mode": "composite"},
        },
    ]


def test_finalize_pipeline_context_and_from_context_builder(tmp_path):
    top_score_calls = []

    def _top_by_score_impl(df, top_n, tie_break_avg_hold, ranking_config):
        top_score_calls.append((top_n, tie_break_avg_hold, ranking_config))
        return (df.head(top_n).copy(), None)

    context = e._build_finalize_pipeline_context(
        combo_path="artifacts/combo.csv",
        per_symbol_path="artifacts/symbol.csv",
        out_dir=str(tmp_path),
        run_id="r1",
        timeframe_configs=[{"timeframe": "1h", "days": 30}],
        timeframe_days_map={"1h": 30},
        safe_int_fn=lambda value, default: int(default if pd.isna(value) else value),
        min_avg_daily_trades_target=5.0,
        apply_quality_filters_fn=lambda df: df.copy(),
        top_by_score_impl_fn=_top_by_score_impl,
        ranking_config={"mode": "composite"},
        history_rows=10,
        base_symbol="BTC/USDT",
        trade_symbols=["ETH/BTC"],
        exchange="binance",
        cache_dir=str(tmp_path / "cache"),
        cache_format="parquet",
        vol_lookbacks=[24],
        vol_zs=[0.8],
        mom_lookbacks=[6],
        trade_mom_lookbacks=[3],
        rsi_window=14,
        bb_window=20,
        bb_alpha=2.0,
        atr_window=14,
        ma_pairs=[(10, 30)],
        obv_lookbacks=[12],
        volume_lookbacks=[12],
        roc_lookbacks=[6],
        cmf_lookbacks=[20],
        mfi_window=14,
        vroc_lookbacks=[12],
        ad_lookbacks=[20],
        cci_lookbacks=[14],
        willr_lookbacks=[14],
        adx_lookbacks=[14],
        trix_lookbacks=[12],
        dpo_lookbacks=[14],
        efi_lookbacks=[13],
        vwma_lookbacks=[20],
        ultosc_periods=(7, 14, 28),
        keltner_lookbacks=[14],
        donchian_lookbacks=[14],
        ppo_fast=12,
        ppo_slow=26,
        ppo_signal=9,
        chop_lookbacks=[14],
        init_cash_usdt=1000.0,
        capital_mode="shared",
        wf_train_days=7,
        wf_test_days=2,
        wf_step_days=2,
        wf_mode="rolling",
        indicator_param_fields=["rsi_long"],
        fees=0.001,
        slippage_bps=1.0,
        spread_bps=2.0,
        funding_rate_daily=0.0,
        order_size_pct=0.5,
        max_concurrent_positions=2,
        labels={"report_title": "Report"},
        config_sha256="cfg123",
        timestamp_utc="2026-02-13T00:00:00Z",
        leaderboard_path=str(tmp_path / "leaderboard.csv"),
        run_metadata_path=str(tmp_path / "run_metadata.json"),
        run_metadata_path_run=str(tmp_path / "run_metadata_r1.json"),
        registry_path=str(tmp_path / "run_registry.json"),
        search_mode="combo",
        config_path="artifacts/sweep_config.json",
        prepare_timeframe_context_fn=lambda **kwargs: {"ctx": kwargs["timeframe"]},
        indicator_combo_label_fn=lambda combo: "+".join(combo),
        coerce_indicator_params_fn=lambda combo, params, ctx: params,
        pick_series_from_map_fn=lambda series_map, lookback, default_key: (series_map[default_key], default_key),
        apply_indicator_combo_fn=lambda long_regime, short_regime, combo, params, ctx: (
            long_regime,
            short_regime,
            params,
        ),
        timeframe_to_hours_fn=lambda timeframe: 1.0,
        run_pf_fn=lambda *args, **kwargs: None,
        plot_portfolio_fn=lambda pf, symbol: None,
        calc_pf_series_fn=lambda pf, symbols, bar_hours: {},
        build_walk_forward_slices_fn=lambda index, train_days, test_days, step_days, mode=None: [],
        df_to_html_fn=lambda df, columns, label_map: "",
        combine_data_fingerprints_fn=lambda fingerprints: "fp-run",
        write_run_metadata_fn=lambda path, payload: None,
        update_run_registry_fn=lambda **kwargs: None,
    )
    got = e._build_finalize_pipeline_kwargs_from_context(finalize_pipeline_context=context)
    assert got["run_id"] == "r1"
    assert got["history_rows"] == 10
    assert got["search_mode"] == "combo"
    top_df = pd.DataFrame([{"score": 1.0}, {"score": 2.0}])
    _ = got["top_by_score_fn"](top_df, top_n=1, tie_break_avg_hold=False)
    _ = got["top_by_score_leaderboard_fn"](top_df, top_n=2, tie_break_avg_hold=True)
    assert top_score_calls == [
        (1, False, {"mode": "composite"}),
        (2, True, {"mode": "composite"}),
    ]


def test_finalize_pipeline_context_from_shared_builder(tmp_path):
    top_score_calls = []
    shared = _sample_shared_pipeline_runtime_context()

    def _top_by_score_impl(df, top_n, tie_break_avg_hold, ranking_config):
        top_score_calls.append((top_n, tie_break_avg_hold, ranking_config))
        return (df.head(top_n).copy(), None)

    context = e._build_finalize_pipeline_context_from_shared(
        shared_pipeline_runtime_context=shared,
        combo_path="artifacts/combo.csv",
        per_symbol_path="artifacts/symbol.csv",
        out_dir=str(tmp_path),
        run_id="r1",
        timeframe_configs=[{"timeframe": "1h", "days": 30}],
        timeframe_days_map={"1h": 30},
        safe_int_fn=lambda value, default: int(default if pd.isna(value) else value),
        min_avg_daily_trades_target=5.0,
        apply_quality_filters_fn=lambda df: df.copy(),
        top_by_score_impl_fn=_top_by_score_impl,
        ranking_config={"mode": "composite"},
        history_rows=10,
        labels={"report_title": "Report"},
        timestamp_utc="2026-02-13T00:00:00Z",
        leaderboard_path=str(tmp_path / "leaderboard.csv"),
        run_metadata_path=str(tmp_path / "run_metadata.json"),
        run_metadata_path_run=str(tmp_path / "run_metadata_r1.json"),
        registry_path=str(tmp_path / "run_registry.json"),
        search_mode="combo",
        config_path="artifacts/sweep_config.json",
        prepare_timeframe_context_fn=lambda **kwargs: {"ctx": kwargs["timeframe"]},
        indicator_combo_label_fn=lambda combo: "+".join(combo),
        coerce_indicator_params_fn=lambda combo, params, ctx: params,
        pick_series_from_map_fn=lambda series_map, lookback, default_key: (series_map[default_key], default_key),
        apply_indicator_combo_fn=lambda long_regime, short_regime, combo, params, ctx: (
            long_regime,
            short_regime,
            params,
        ),
        timeframe_to_hours_fn=lambda timeframe: 1.0,
        run_pf_fn=lambda *args, **kwargs: None,
        plot_portfolio_fn=lambda pf, symbol: None,
        calc_pf_series_fn=lambda pf, symbols, bar_hours: {},
        build_walk_forward_slices_fn=lambda index, train_days, test_days, step_days, mode=None: [],
        df_to_html_fn=lambda df, columns, label_map: "",
        combine_data_fingerprints_fn=lambda fingerprints: "fp-run",
        write_run_metadata_fn=lambda path, payload: None,
        update_run_registry_fn=lambda **kwargs: None,
    )
    got = e._build_finalize_pipeline_kwargs_from_context(finalize_pipeline_context=context)

    assert got["base_symbol"] == "BTC/USDT"
    assert got["trade_symbols"] == ["ETH/BTC"]
    assert got["indicator_param_fields"] == ["rsi_long"]
    assert got["vol_zs"] == [0.8]
    assert got["combo_seed"] == 42
    top_df = pd.DataFrame([{"score": 1.0}, {"score": 2.0}])
    _ = got["top_by_score_fn"](top_df, top_n=1, tie_break_avg_hold=False)
    _ = got["top_by_score_leaderboard_fn"](top_df, top_n=2, tie_break_avg_hold=True)
    assert top_score_calls == [
        (1, False, {"mode": "composite"}),
        (2, True, {"mode": "composite"}),
    ]


def test_run_finalize_after_timeframe_loop_injects_loop_outputs_and_forces_checkpoint():
    checkpoint_calls = []
    finalize_calls = []

    def _checkpoint(**kwargs):
        checkpoint_calls.append(kwargs)

    def _run_finalize_pipeline(**kwargs):
        finalize_calls.append(kwargs)
        return {"ok": True, "timeframe_ranges": kwargs["timeframe_ranges"]}

    result = e._run_finalize_after_timeframe_loop(
        timeframe_loop_result={
            "timeframe_ranges": ["1h (30d): A to B"],
            "timeframe_fingerprints": ["fp-1h"],
            "timeframe_diagnostics": [{"timeframe": "1h"}],
        },
        checkpoint_fn=_checkpoint,
        run_finalize_pipeline_fn=_run_finalize_pipeline,
        finalize_kwargs={
            "combo_path": "artifacts/combo.csv",
            "timeframe_ranges": ["stale"],
            "timeframe_fingerprints": ["stale"],
        },
    )

    assert checkpoint_calls == [{"force": True}]
    assert len(finalize_calls) == 1
    assert finalize_calls[0]["combo_path"] == "artifacts/combo.csv"
    assert finalize_calls[0]["timeframe_ranges"] == ["1h (30d): A to B"]
    assert finalize_calls[0]["timeframe_fingerprints"] == ["fp-1h"]
    assert finalize_calls[0]["timeframe_diagnostics"] == [{"timeframe": "1h"}]
    assert result["ok"] is True


def test_append_eval_result_rows_appends_and_skips_invalid_metrics():
    pending_symbol_rows = []
    pending_combo_rows = []
    pending_oos_symbol_rows = []
    symbol_calls = []
    combo_calls = []
    oos_symbol_calls = []

    result = e._append_eval_result_rows(
        result={"metrics_values": None},
        task_meta={},
        timeframe="1h",
        data_days=30,
        exchange="binance",
        base_symbol="BTC/USDT",
        trade_symbols_tf=["ETH/BTC"],
        capital_mode="shared",
        fees=0.001,
        slippage_bps=2.0,
        spread_bps=2.0,
        funding_rate_daily=0.0,
        order_size_pct=0.5,
        max_concurrent_positions=2,
        init_cash_usdt=1000.0,
        wf_train_days=7,
        wf_test_days=2,
        wf_step_days=2,
        wf_mode="rolling",
        data_start="2024-01-01",
        data_end="2024-01-31",
        rsi_window=14,
        config_sha256="cfg123",
        timeframe_data_fingerprint="fp1",
        ctx_total_days=10,
        pending_symbol_rows=pending_symbol_rows,
        pending_combo_rows=pending_combo_rows,
        pending_oos_symbol_rows=pending_oos_symbol_rows,
        build_symbol_row_fn=lambda **kwargs: symbol_calls.append(kwargs),
        build_combo_row_fn=lambda **kwargs: combo_calls.append(kwargs),
        build_oos_symbol_row_fn=lambda **kwargs: oos_symbol_calls.append(kwargs),
    )
    assert result is False
    assert pending_symbol_rows == []
    assert pending_combo_rows == []
    assert pending_oos_symbol_rows == []

    task_meta = {
        "regime": {"regime_name": "trend_high", "regime_type": "trend", "vol_mode": "high"},
        "indicator_combo": ("rsi",),
        "filter_name": "rsi",
        "indicator_list": "rsi",
        "vol_lookback": 24,
        "vol_z": 0.8,
        "mom_lookback": 6,
        "trade_mom_lookback": 3,
        "tp_stop": 0.003,
        "sl_stop": 0.006,
        "max_hold": 2,
    }
    eval_result = {
        "metrics_values": {
            "total_return_pct": {"ETH/BTC": 1.0},
            "total_profit": {"ETH/BTC": 0.1},
            "total_trades": {"ETH/BTC": 4.0},
            "win_rate_pct": {"ETH/BTC": 50.0},
            "avg_trade_pct": {"ETH/BTC": 1.0},
            "max_drawdown_pct": {"ETH/BTC": -2.0},
            "position_coverage_pct": {"ETH/BTC": 30.0},
            "avg_hold_hours": {"ETH/BTC": 2.0},
        },
        "variant_params": {
            "rsi_long": 60.0,
            "rsi_short": 40.0,
            "bb_width": None,
            "atr_ratio": None,
            "ma_fast": None,
            "ma_slow": None,
            "macd_hist_ratio": None,
            "stoch_long": None,
            "stoch_short": None,
            "obv_lookback": None,
            "volume_lookback": None,
            "volume_z": None,
            "roc_lookback": None,
            "roc_threshold": None,
            "mfi_long": None,
            "mfi_short": None,
            "cmf_lookback": None,
            "cmf_threshold": None,
            "vroc_lookback": None,
            "vroc_threshold": None,
            "ad_lookback": None,
        },
        "regime_rsi_long": None,
        "regime_rsi_short": None,
        "combo_metrics": {
            "total_return_pct": 1.0,
            "win_rate_pct": 50.0,
            "avg_trade_pct": 1.0,
            "max_drawdown_pct": -2.0,
            "position_coverage_pct": 30.0,
            "total_trades": 4.0,
            "avg_hold_hours": 2.0,
        },
        "sym_metrics": {
            "avg_total_return_pct": 1.0,
            "avg_win_rate_pct": 50.0,
            "avg_avg_trade_pct": 1.0,
            "avg_max_drawdown_pct": -2.0,
            "avg_position_coverage_pct": 30.0,
            "avg_total_trades": 4.0,
            "min_total_trades": 4.0,
            "avg_hold_hours": 2.0,
        },
        "oos_metrics": {"oos_avg_total_return_pct": 0.5},
        "oos_symbol_metrics_values": {
            "oos_avg_total_return_pct": {"ETH/BTC": 0.5},
            "oos_avg_win_rate_pct": {"ETH/BTC": 50.0},
            "oos_avg_avg_trade_pct": {"ETH/BTC": 1.0},
            "oos_avg_max_drawdown_pct": {"ETH/BTC": -2.0},
            "oos_avg_position_coverage_pct": {"ETH/BTC": 30.0},
            "oos_avg_total_trades": {"ETH/BTC": 4.0},
            "oos_min_total_trades": {"ETH/BTC": 2.0},
            "oos_avg_daily_trades": {"ETH/BTC": 0.5},
            "oos_avg_hold_hours": {"ETH/BTC": 2.0},
            "oos_return_std": {"ETH/BTC": 0.1},
            "oos_positive_segment_ratio": {"ETH/BTC": 0.5},
            "oos_sharpe_like": {"ETH/BTC": 5.0},
            "oos_low_trade_segment_ratio": {"ETH/BTC": 0.0},
            "oos_low_trade_penalty": {"ETH/BTC": 0.0},
            "oos_segments": {"ETH/BTC": 2.0},
        },
    }

    def _build_symbol_row(**kwargs):
        symbol_calls.append(kwargs)
        return {"symbol": kwargs["symbol"]}

    def _build_combo_row(**kwargs):
        combo_calls.append(kwargs)
        return {"timeframe": kwargs["timeframe"]}

    def _build_oos_symbol_row(**kwargs):
        oos_symbol_calls.append(kwargs)
        return {"symbol": kwargs["symbol"], "oos_avg_total_return_pct": kwargs["oos_metrics"]["oos_avg_total_return_pct"][kwargs["symbol"]]}

    result = e._append_eval_result_rows(
        result=eval_result,
        task_meta=task_meta,
        timeframe="1h",
        data_days=30,
        exchange="binance",
        base_symbol="BTC/USDT",
        trade_symbols_tf=["ETH/BTC"],
        capital_mode="shared",
        fees=0.001,
        slippage_bps=2.0,
        spread_bps=2.0,
        funding_rate_daily=0.0,
        order_size_pct=0.5,
        max_concurrent_positions=2,
        init_cash_usdt=1000.0,
        wf_train_days=7,
        wf_test_days=2,
        wf_step_days=2,
        wf_mode="rolling",
        data_start="2024-01-01",
        data_end="2024-01-31",
        rsi_window=14,
        config_sha256="cfg123",
        timeframe_data_fingerprint="fp1",
        ctx_total_days=10,
        pending_symbol_rows=pending_symbol_rows,
        pending_combo_rows=pending_combo_rows,
        pending_oos_symbol_rows=pending_oos_symbol_rows,
        build_symbol_row_fn=_build_symbol_row,
        build_combo_row_fn=_build_combo_row,
        build_oos_symbol_row_fn=_build_oos_symbol_row,
    )

    assert result is True
    assert pending_symbol_rows == [{"symbol": "ETH/BTC"}]
    assert pending_combo_rows == [{"timeframe": "1h"}]
    assert pending_oos_symbol_rows == [{"symbol": "ETH/BTC", "oos_avg_total_return_pct": 0.5}]
    assert symbol_calls[-1]["symbol"] == "ETH/BTC"
    assert combo_calls[-1]["timeframe"] == "1h"
    assert oos_symbol_calls[-1]["symbol"] == "ETH/BTC"
    # AWF-106d: capital_mode must be forwarded to build_combo_row_fn
    assert combo_calls[-1]["capital_mode"] == "shared"


def test_run_timeframe_search_loop_tracks_state_and_warnings():
    done_state = {"value": 20}
    total_state = {"value": 100}
    prepare_calls = []
    ready_calls = []
    warnings = []
    set_total_calls = []

    timeframe_configs = [
        {"timeframe": "1h", "days": 30},
        {"timeframe": "4h", "days": 60},
        {"timeframe": "1d", "days": 90},
    ]

    def _prepare_runtime_attempt(**kwargs):
        prepare_calls.append(kwargs)
        tf = kwargs["timeframe"]
        if tf == "1h":
            return {
                "ok": True,
                "total_combos": 100,
                "timeframe_runtime": {
                    "ctx": {"total_days": 5},
                    "timeframe_range": "1h (30d): A to B",
                    "timeframe_data_fingerprint": "fp-1h",
                    "timeframe_diagnostics": {"timeframe": "1h"},
                    "wf_windows": [],
                },
            }
        if tf == "4h":
            return {"ok": False, "total_combos": 90, "timeframe_runtime": None}
        return {
            "ok": True,
            "total_combos": 90,
            "timeframe_runtime": {
                "ctx": {"total_days": 20},
                "timeframe_range": "1d (90d): C to D",
                "timeframe_data_fingerprint": "fp-1d",
                "timeframe_diagnostics": {"timeframe": "1d"},
                "wf_windows": [("x", "y")],
            },
        }

    def _on_ready(**kwargs):
        ready_calls.append(kwargs)
        done_state["value"] += 5

    def _set_total(value):
        total_state["value"] = value
        set_total_calls.append(value)

    result = e._run_timeframe_search_loop(
        timeframe_configs=timeframe_configs,
        wf_train_days=7,
        wf_test_days=2,
        prepare_runtime_attempt_fn=_prepare_runtime_attempt,
        on_timeframe_ready_fn=_on_ready,
        get_done_fn=lambda: done_state["value"],
        get_total_combos_fn=lambda: total_state["value"],
        set_total_combos_fn=_set_total,
        timeframe_to_hours_fn=lambda tf: {"1h": 1.0, "4h": 4.0, "1d": 24.0}[tf],
        warn_fn=warnings.append,
    )

    assert [call["timeframe"] for call in prepare_calls] == ["1h", "4h", "1d"]
    assert [call["done"] for call in prepare_calls] == [20, 25, 25]
    assert [call["total_combos"] for call in prepare_calls] == [100, 100, 90]
    assert set_total_calls == [100, 90, 90]
    assert total_state["value"] == 90

    assert [call["timeframe"] for call in ready_calls] == ["1h", "1d"]
    assert [call["bar_hours"] for call in ready_calls] == [1.0, 24.0]
    assert done_state["value"] == 30

    assert result["timeframe_ranges"] == ["1h (30d): A to B", "1d (90d): C to D"]
    assert result["timeframe_fingerprints"] == ["fp-1h", "fp-1d"]
    assert result["timeframe_diagnostics"] == [{"timeframe": "1h"}, {"timeframe": "1d"}]
    assert len(warnings) == 1
    assert "timeframe 1h has no walk-forward segments" in warnings[0]


def test_fallback_activity_filter_without_avg_daily_trades_column():
    combo_df = pd.DataFrame([{"timeframe": "1h", "indicator_list": "rsi"}])
    filtered, min_avg = e._fallback_activity_filter(
        combo_df_current=combo_df,
        min_avg_daily_trades_target=5.0,
        apply_quality_filters_fn=lambda df: pd.DataFrame(),
    )
    assert min_avg == 0
    assert len(filtered) == 1


def test_load_result_frames_and_write_run_snapshot_files(tmp_path):
    combo_src = tmp_path / "combo.csv"
    symbol_src = tmp_path / "symbol.csv"
    combo_df = pd.DataFrame([{"timeframe": "3m", "x": 1}])
    symbol_df = pd.DataFrame([{"timeframe": "3m", "symbol": "ETH/BTC"}])
    combo_df.to_csv(combo_src, index=False)
    symbol_df.to_csv(symbol_src, index=False)

    combo_loaded, symbol_loaded = e._load_result_frames(str(combo_src), str(symbol_src))
    assert len(combo_loaded) == 1
    assert len(symbol_loaded) == 1

    combo_run_path, symbol_run_path = e._write_run_snapshot_files(
        combo_df=combo_loaded,
        per_symbol_df=symbol_loaded,
        out_dir=str(tmp_path),
        run_id="r1",
    )
    assert (tmp_path / "param_sweep_combo_summary_r1.csv").exists()
    assert (tmp_path / "param_sweep_symbol_summary_r1.csv").exists()
    assert combo_run_path.endswith("param_sweep_combo_summary_r1.csv")
    assert symbol_run_path.endswith("param_sweep_symbol_summary_r1.csv")


def test_select_current_combo_df_prefers_valid_timeframes():
    combo_df = pd.DataFrame(
        [
            {"timeframe": "3m", "x": 1},
            {"timeframe": "1h", "x": 2},
        ]
    )
    filtered = e._select_current_combo_df(combo_df, [{"timeframe": "3m"}, {"timeframe": "5m"}])
    assert list(filtered["timeframe"]) == ["3m"]

    unchanged = e._select_current_combo_df(combo_df, [{"timeframe": "15m"}])
    assert len(unchanged) == 2


def test_fallback_activity_filter_tiers():
    combo_df = pd.DataFrame([{"avg_daily_trades": 1.0}, {"avg_daily_trades": 3.0}])
    filtered, min_filter = e._fallback_activity_filter(
        combo_df_current=combo_df,
        min_avg_daily_trades_target=5,
        apply_quality_filters_fn=lambda df: df.iloc[0:0],
    )
    assert min_filter == 2
    assert len(filtered) == 1

    low_df = pd.DataFrame([{"avg_daily_trades": 1.0}])
    filtered_low, min_filter_low = e._fallback_activity_filter(
        combo_df_current=low_df,
        min_avg_daily_trades_target=5,
        apply_quality_filters_fn=lambda df: df.iloc[0:0],
    )
    assert min_filter_low == 0
    assert len(filtered_low) == 1


def test_pick_best_from_top_defaults():
    top_df = pd.DataFrame([{"timeframe": float("nan"), "data_days": float("nan")}])

    def _safe_int(v, default):
        return default if v is None or pd.isna(v) else int(v)

    best, best_timeframe, best_data_days = e._pick_best_from_top(
        top_df=top_df,
        timeframe_configs=[{"timeframe": "3m", "days": 60}],
        timeframe_days_map={"3m": 60},
        safe_int_fn=_safe_int,
    )
    assert isinstance(best, dict)
    assert best_timeframe == "3m"
    assert best_data_days == 60


def test_prepare_timeframe_runtime_builds_payload():
    index = pd.date_range("2024-01-01", periods=6, freq="h")
    seen = {}

    def _prepare_timeframe_context_fn(**kwargs):
        seen["prepare_kwargs"] = kwargs
        return {
            "trade_symbols": ["ETH/BTC", "BNB/BTC"],
            "trade_close": pd.DataFrame(
                {
                    "ETH/BTC": [1, 2, 3, 4, 5, 6],
                    "BNB/BTC": [2, 3, 4, 5, 6, 7],
                },
                index=index,
            ),
            "data_range": "2024-01-01 to 2024-01-01",
            "total_days": 1,
            "overlap_diagnostics": {"realized_shared_days": 1, "requested_data_days": 5},
        }

    def _build_walk_forward_windows_fn(idx, train_days, test_days, step_days, mode=None, valid_days=0):
        seen["wf_args"] = (len(idx), train_days, test_days, step_days, mode)
        return [(idx[0], idx[2], idx[2], idx[2], idx[2], idx[3])]

    def _compute_data_fingerprint_fn(payload):
        seen["fingerprint_payload"] = payload
        return "fp-123"

    got = e._prepare_timeframe_runtime(
        timeframe="1h",
        data_days=5,
        base_symbol="BTC/USDT",
        trade_symbols=["ETH/BTC", "BNB/BTC"],
        exchange="binance",
        cache_dir="artifacts/cache",
        cache_format="parquet",
        vol_lookbacks=[24],
        mom_lookbacks=[6],
        trade_mom_lookbacks=[3],
        rsi_window=14,
        bb_window=20,
        bb_alpha=2.0,
        atr_window=14,
        ma_pairs=[(10, 30)],
        obv_lookbacks=[12],
        volume_lookbacks=[12],
        roc_lookbacks=[6],
        cmf_lookbacks=[20],
        mfi_window=14,
        vroc_lookbacks=[12],
        ad_lookbacks=[20],
        cci_lookbacks=[14],
        willr_lookbacks=[14],
        adx_lookbacks=[14],
        trix_lookbacks=[12],
        dpo_lookbacks=[14],
        efi_lookbacks=[13],
        vwma_lookbacks=[20],
        ultosc_periods=(7, 14, 28),
        keltner_lookbacks=[14],
        donchian_lookbacks=[14],
        ppo_fast=12,
        ppo_slow=26,
        ppo_signal=9,
        chop_lookbacks=[14],
        init_cash_usdt=1000.0,
        capital_mode="shared",
        wf_train_days=7,
        wf_test_days=2,
        wf_step_days=2,
        wf_mode="rolling",
        fees=0.001,
        slippage_bps=2.0,
        spread_bps=2.0,
        funding_rate_daily=0.0,
        order_size_pct=0.5,
        max_concurrent_positions=2,
        config_sha256="cfg123",
        bar_hours=1.0,
        prepare_timeframe_context_fn=_prepare_timeframe_context_fn,
        build_walk_forward_windows_fn=_build_walk_forward_windows_fn,
        compute_data_fingerprint_fn=_compute_data_fingerprint_fn,
    )

    assert seen["prepare_kwargs"]["timeframe"] == "1h"
    assert seen["wf_args"] == (6, 7, 2, 2, "rolling")
    assert seen["fingerprint_payload"]["timeframe"] == "1h"
    assert got["timeframe_range"] == "1h (5d): 2024-01-01 to 2024-01-01"
    assert got["timeframe_data_fingerprint"] == "fp-123"
    assert len(got["wf_windows"]) == 1
    assert len(got["wf_slices"]) == 1
    assert got["timeframe_diagnostics"]["realized_shared_days"] == 1
    assert got["timeframe_diagnostics"]["requested_data_days"] == 5
    assert got["runtime_eval"]["wf_mode"] == "rolling"
    assert got["runtime_eval"]["config_sha256"] == "cfg123"
    assert got["runtime_eval"]["data_fingerprint"] == "fp-123"


def test_build_leaderboard_row_payload():
    row = e._build_leaderboard_row_payload(
        run_id="r1",
        timestamp_utc="2026-02-11T00:00:00Z",
        config_sha256="cfg123",
        ranking_mode="composite",
        plot_symbol="ETH/BTC",
        best_timeframe="1h",
        best_data_days=30,
        min_avg_daily_trades_target=5.0,
        min_avg_daily_trades_filter=2.0,
        capital_mode="shared",
        init_cash_usdt=1000.0,
        order_size_pct=0.5,
        max_concurrent_positions=2,
        slippage_bps=2.0,
        spread_bps=2.0,
        funding_rate_daily=0.0,
        wf_train_days=7,
        wf_test_days=2,
        wf_step_days=2,
        wf_mode="rolling",
        wf_segments=3,
        best={
            "data_fingerprint": "fp-best",
            "regime_name": "trend_high",
            "avg_total_return_pct": 10.0,
            "oos_sharpe_like": 1.25,
            "oos_segments": 3,
        },
        report_file="report_r1.html",
    )

    assert row["run_id"] == "r1"
    assert row["data_fingerprint"] == "fp-best"
    assert row["wf_mode"] == "rolling"
    assert row["wf_segments"] == 3
    assert row["regime_name"] == "trend_high"
    assert row["avg_total_return_pct"] == 10.0
    assert row["oos_sharpe_like"] == 1.25
    assert row["report_file"] == "report_r1.html"


def test_build_run_metadata_payload():
    payload = e._build_run_metadata_payload(
        run_id="r1",
        timestamp_utc="2026-02-11T00:00:00Z",
        search_mode="combo",
        config_sha256="cfg123",
        combo_seed=42,
        data_fingerprint="fp-run",
        config_path="artifacts/sweep_config.json",
        exchange="binance",
        base_symbol="BTC/USDT",
        trade_symbols=["ETH/BTC"],
        timeframe_configs=[{"timeframe": "1h", "days": 30}],
        timeframe_diagnostics=[{"timeframe": "1h", "realized_shared_days": 24}],
        wf_train_days=7,
        wf_test_days=2,
        wf_step_days=2,
        wf_mode="rolling",
        capital_mode="shared",
        init_cash_usdt=1000.0,
        ranking_config={"mode": "composite"},
    )

    assert payload["run_id"] == "r1"
    assert payload["data_fingerprint"] == "fp-run"
    assert payload["combo_seed"] == 42
    assert payload["timeframes"] == [{"timeframe": "1h", "days": 30}]
    assert payload["timeframe_diagnostics"] == [{"timeframe": "1h", "realized_shared_days": 24}]
    assert payload["wf_mode"] == "rolling"
    assert payload["ranking"]["mode"] == "composite"


def test_prepare_best_timeframe_context_success_and_error():
    seen = {}

    def _prepare(**kwargs):
        seen["kwargs"] = kwargs
        return {"ctx": "ok"}

    ok = e._prepare_best_timeframe_context(
        best_timeframe="1h",
        best_data_days=30,
        base_symbol="BTC/USDT",
        trade_symbols=["ETH/BTC"],
        exchange="binance",
        cache_dir="artifacts/cache",
        cache_format="parquet",
        vol_lookbacks=[24],
        mom_lookbacks=[6],
        trade_mom_lookbacks=[3],
        rsi_window=14,
        bb_window=20,
        bb_alpha=2.0,
        atr_window=14,
        ma_pairs=[(10, 30)],
        obv_lookbacks=[12],
        volume_lookbacks=[12],
        roc_lookbacks=[6],
        cmf_lookbacks=[20],
        mfi_window=14,
        vroc_lookbacks=[12],
        ad_lookbacks=[20],
        cci_lookbacks=[14],
        willr_lookbacks=[14],
        adx_lookbacks=[14],
        trix_lookbacks=[12],
        dpo_lookbacks=[14],
        efi_lookbacks=[13],
        vwma_lookbacks=[20],
        ultosc_periods=(7, 14, 28),
        keltner_lookbacks=[14],
        donchian_lookbacks=[14],
        ppo_fast=12,
        ppo_slow=26,
        ppo_signal=9,
        chop_lookbacks=[14],
        init_cash_usdt=1000.0,
        capital_mode="shared",
        prepare_timeframe_context_fn=_prepare,
    )
    assert ok["ctx"] == {"ctx": "ok"}
    assert ok["error"] is None
    assert seen["kwargs"]["timeframe"] == "1h"
    assert seen["kwargs"]["data_days"] == 30

    def _raise(**_kwargs):
        raise RuntimeError("boom")

    err = e._prepare_best_timeframe_context(
        best_timeframe="1h",
        best_data_days=30,
        base_symbol="BTC/USDT",
        trade_symbols=["ETH/BTC"],
        exchange="binance",
        cache_dir="artifacts/cache",
        cache_format="parquet",
        vol_lookbacks=[24],
        mom_lookbacks=[6],
        trade_mom_lookbacks=[3],
        rsi_window=14,
        bb_window=20,
        bb_alpha=2.0,
        atr_window=14,
        ma_pairs=[(10, 30)],
        obv_lookbacks=[12],
        volume_lookbacks=[12],
        roc_lookbacks=[6],
        cmf_lookbacks=[20],
        mfi_window=14,
        vroc_lookbacks=[12],
        ad_lookbacks=[20],
        cci_lookbacks=[14],
        willr_lookbacks=[14],
        adx_lookbacks=[14],
        trix_lookbacks=[12],
        dpo_lookbacks=[14],
        efi_lookbacks=[13],
        vwma_lookbacks=[20],
        ultosc_periods=(7, 14, 28),
        keltner_lookbacks=[14],
        donchian_lookbacks=[14],
        ppo_fast=12,
        ppo_slow=26,
        ppo_signal=9,
        chop_lookbacks=[14],
        init_cash_usdt=1000.0,
        capital_mode="shared",
        prepare_timeframe_context_fn=_raise,
    )
    assert err["ctx"] is None
    assert isinstance(err["error"], RuntimeError)


def test_persist_run_metadata_and_registry_calls_dependencies():
    write_calls = []
    registry_calls = []

    def _combine(fingerprints):
        assert fingerprints == ["fp1", "fp2"]
        return "run-fp"

    def _write(path, payload):
        write_calls.append((path, payload))

    def _update(**kwargs):
        registry_calls.append(kwargs)

    per_symbol_df = pd.DataFrame([{"symbol": "ETH/BTC"}])
    result = e._persist_run_metadata_and_registry(
        timeframe_fingerprints=["fp1", "fp2"],
        run_id="r1",
        timestamp_utc="2026-02-11T00:00:00Z",
        search_mode="combo",
        config_sha256="cfg123",
        combo_seed=42,
        config_path="artifacts/sweep_config.json",
        exchange="binance",
        base_symbol="BTC/USDT",
        trade_symbols=["ETH/BTC"],
        timeframe_configs=[{"timeframe": "1h", "days": 30}],
        wf_train_days=7,
        wf_test_days=2,
        wf_step_days=2,
        wf_mode="rolling",
        capital_mode="shared",
        init_cash_usdt=1000.0,
        ranking_config={"mode": "composite"},
        run_metadata_path="artifacts/run_metadata.json",
        run_metadata_path_run="artifacts/run_metadata_r1.json",
        registry_path="artifacts/run_registry.json",
        leaderboard_row={"run_id": "r1"},
        per_symbol_df=per_symbol_df,
        combine_data_fingerprints_fn=_combine,
        write_run_metadata_fn=_write,
        update_run_registry_fn=_update,
    )

    assert result["run_data_fingerprint"] == "run-fp"
    assert result["run_metadata_payload"]["wf_mode"] == "rolling"
    assert result["run_metadata_payload"]["combo_seed"] == 42
    assert len(write_calls) == 2
    assert write_calls[0][0] == "artifacts/run_metadata.json"
    assert write_calls[1][0] == "artifacts/run_metadata_r1.json"
    assert write_calls[0][1] == write_calls[1][1]
    assert len(registry_calls) == 1
    assert registry_calls[0]["registry_path"] == "artifacts/run_registry.json"
    assert registry_calls[0]["best_row"] == {"run_id": "r1"}
    assert registry_calls[0]["per_symbol_df"] is per_symbol_df


def test_build_completion_output_map_order():
    outputs = e._build_completion_output_map(
        combo_path="a.csv",
        per_symbol_path="b.csv",
        top10_path="c.csv",
        leaderboard_path="d.csv",
        registry_path="e.json",
        run_metadata_path="f.json",
        run_metadata_path_run="g.json",
        report_path_latest="h.html",
        report_path_run="i.html",
    )
    assert list(outputs.keys()) == [
        "combo_summary",
        "per_symbol_summary",
        "top10",
        "leaderboard",
        "run_registry",
        "run_metadata",
        "run_metadata_run",
        "report_latest",
        "report_run",
    ]
    assert outputs["report_run"] == "i.html"

def _base_finalize_kwargs(tmp_path, *, combo_path, per_symbol_path):
    out_dir = tmp_path / "artifacts"
    out_dir.mkdir(parents=True, exist_ok=True)
    return {
        "combo_path": str(combo_path),
        "per_symbol_path": str(per_symbol_path),
        "out_dir": str(out_dir),
        "run_id": "r1",
        "timeframe_configs": [{"timeframe": "1h", "days": 30}],
        "timeframe_days_map": {"1h": 30},
        "safe_int_fn": lambda value, default: int(default if pd.isna(value) else value),
        "min_avg_daily_trades_target": 5.0,
        "apply_quality_filters_fn": lambda df: df.copy(),
        "top_by_score_fn": lambda df, top_n, tie_break_avg_hold: (df.head(top_n).copy(), None),
        "history_rows": 10,
        "top_by_score_leaderboard_fn": (
            lambda df, top_n, tie_break_avg_hold: (df.head(top_n).copy(), None)
        ),
        "base_symbol": "BTC/USDT",
        "trade_symbols": ["ETH/BTC"],
        "exchange": "binance",
        "cache_dir": str(tmp_path / "cache"),
        "cache_format": "parquet",
        "vol_lookbacks": [24],
        "vol_zs": [0.8],
        "mom_lookbacks": [6],
        "trade_mom_lookbacks": [3],
        "rsi_window": 14,
        "bb_window": 20,
        "bb_alpha": 2.0,
        "atr_window": 14,
        "ma_pairs": [(10, 30)],
        "obv_lookbacks": [12],
        "volume_lookbacks": [12],
        "roc_lookbacks": [6],
        "cmf_lookbacks": [20],
        "mfi_window": 14,
        "vroc_lookbacks": [12],
        "ad_lookbacks": [20],
        "cci_lookbacks": [14],
        "willr_lookbacks": [14],
        "adx_lookbacks": [14],
        "trix_lookbacks": [12],
        "dpo_lookbacks": [14],
        "efi_lookbacks": [13],
        "vwma_lookbacks": [20],
        "ultosc_periods": (7, 14, 28),
        "keltner_lookbacks": [14],
        "donchian_lookbacks": [14],
        "ppo_fast": 12,
        "ppo_slow": 26,
        "ppo_signal": 9,
        "chop_lookbacks": [14],
        "init_cash_usdt": 1000.0,
        "capital_mode": "shared",
        "timeframe_ranges": {"1h": "2024-01-01 to 2024-02-01"},
        "wf_train_days": 7,
        "wf_test_days": 2,
        "wf_step_days": 2,
        "wf_mode": "rolling",
        "indicator_param_fields": ["rsi_long"],
        "fees": 0.001,
        "slippage_bps": 1.0,
        "spread_bps": 2.0,
        "funding_rate_daily": 0.0,
        "order_size_pct": 0.5,
        "max_concurrent_positions": 2,
        "labels": {"report_title": "Report"},
        "config_sha256": "cfg123",
        "timestamp_utc": "2026-02-11T00:00:00Z",
        "ranking_config": {"mode": "composite"},
        "leaderboard_path": str(tmp_path / "leaderboard.csv"),
        "run_metadata_path": str(tmp_path / "run_metadata.json"),
        "run_metadata_path_run": str(tmp_path / "run_metadata_r1.json"),
        "registry_path": str(tmp_path / "run_registry.json"),
        "timeframe_fingerprints": ["fp1"],
        "search_mode": "combo",
        "config_path": "artifacts/sweep_config.json",
        "prepare_timeframe_context_fn": lambda **kwargs: {"ctx": kwargs["timeframe"]},
    }


def test_run_finalize_pipeline_warns_when_combo_empty(tmp_path):
    kwargs = _base_finalize_kwargs(
        tmp_path,
        combo_path=tmp_path / "missing_combo.csv",
        per_symbol_path=tmp_path / "missing_symbol.csv",
    )
    result = e._run_finalize_pipeline(**kwargs)
    assert result == {
        "ok": False,
        "warning": "[warn] No valid combinations evaluated; check data download and filters.",
    }


def test_run_finalize_pipeline_warns_on_best_context_error(tmp_path):
    combo_path = tmp_path / "combo.csv"
    pd.DataFrame(
        [
            {
                "timeframe": "1h",
                "data_days": 30,
                "avg_daily_trades": 6.0,
            }
        ]
    ).to_csv(combo_path, index=False)
    kwargs = _base_finalize_kwargs(
        tmp_path,
        combo_path=combo_path,
        per_symbol_path=tmp_path / "missing_symbol.csv",
    )

    def _raise_context(**_kwargs):
        raise RuntimeError("context boom")

    kwargs["prepare_timeframe_context_fn"] = _raise_context
    result = e._run_finalize_pipeline(**kwargs)
    assert result["ok"] is False
    assert result["warning"] == "[warn] best report skipped: context boom"


def test_run_finalize_pipeline_forwards_vol_zs(tmp_path, monkeypatch):
    combo_path = tmp_path / "combo.csv"
    pd.DataFrame(
        [
            {
                "timeframe": "1h",
                "data_days": 30,
                "avg_daily_trades": 6.0,
            }
        ]
    ).to_csv(combo_path, index=False)
    kwargs = _base_finalize_kwargs(
        tmp_path,
        combo_path=combo_path,
        per_symbol_path=tmp_path / "missing_symbol.csv",
    )
    kwargs["vol_zs"] = [0.8, 1.1]

    seen = {}

    class _StopPipeline(Exception):
        pass

    def _capture_prepare_best_replay_payload(**payload_kwargs):
        seen["vol_zs"] = payload_kwargs["vol_zs"]
        raise _StopPipeline

    monkeypatch.setattr(_e_finalize, "_prepare_best_replay_payload", _capture_prepare_best_replay_payload)

    with pytest.raises(_StopPipeline):
        e._run_finalize_pipeline(**kwargs)

    assert seen["vol_zs"] == [0.8, 1.1]


def test_build_report_file_paths():
    paths = e._build_report_file_paths(
        out_dir="artifacts",
        plot_symbol="ETH/BTC",
        run_id="20260211_000000",
    )
    assert paths["report_file_latest"] == "btc_regime_ETH-BTC.html"
    assert paths["report_file_run"] == "btc_regime_ETH-BTC_20260211_000000.html"
    assert paths["report_path_latest"].endswith("btc_regime_ETH-BTC.html")
    assert paths["report_path_run"].endswith("btc_regime_ETH-BTC_20260211_000000.html")


def test_build_report_html_scan_timeframes_toggle():
    labels = {
        "report_title": "Report",
        "data_range": "Data Range",
        "timeframe": "Timeframe",
        "data_days": "Data Days",
        "scan_timeframes": "Scan Timeframes",
        "run_id": "Run ID",
        "timestamp_utc": "Timestamp UTC",
        "min_avg_daily_trades_target": "Min Avg Trades Target",
        "min_avg_daily_trades_filter": "Min Avg Trades Filter",
        "capital_mode": "Capital Mode",
        "init_cash_usdt": "Init Cash USDT",
        "order_size_pct": "Order Size %",
        "max_concurrent_positions": "Max Positions",
        "wf_train_days": "WF Train Days",
        "wf_test_days": "WF Test Days",
        "wf_step_days": "WF Step Days",
        "wf_valid_days": "WF Valid Days",
        "wf_mode": "WF Mode",
        "wf_segments": "WF Segments",
        "base_symbol": "Base Symbol",
        "trade_symbols": "Trade Symbols",
        "summary_title": "Summary",
        "params_title": "Params",
        "oos_summary_title": "OOS Summary",
        "top_title": "Top",
        "history_title": "History",
        "leaderboard_title": "Leaderboard",
        "recent_runs_title": "Recent",
        "chart_title": "Chart",
    }
    html = e._build_report_html(
        labels=labels,
        data_range="2024-01-01 to 2024-02-01",
        best_timeframe="1h",
        best_data_days=30,
        scan_timeframes="1h (30d): 2024-01-01 to 2024-02-01",
        run_id="r1",
        timestamp_utc="2026-02-11T00:00:00Z",
        min_avg_daily_trades_target=5.0,
        min_avg_daily_trades_filter=2.0,
        capital_mode="shared",
        init_cash_usdt=1000.0,
        order_size_pct=0.5,
        max_concurrent_positions=2,
        wf_train_days=7,
        wf_test_days=2,
        wf_step_days=2,
        wf_mode="rolling",
        wf_segments=3,
        base_symbol="BTC/USDT",
        trade_symbols=["ETH/BTC", "BNB/BTC"],
        summary_html="<table id='summary'></table>",
        report_params_html="<table id='params'></table>",
        oos_summary_html="<table id='oos'></table>",
        top10_html="<table id='top'></table>",
        lb_best_html="<table id='lb-best'></table>",
        lb_recent_html="<table id='lb-recent'></table>",
        plot_symbol="ETH/BTC",
        plot_html="<div id='plot'></div>",
    )
    assert "<!doctype html>" in html
    assert "<h1>Report</h1>" in html
    assert "Scan Timeframes" in html
    assert "<table id='summary'></table>" in html
    assert "<div id='plot'></div>" in html

    html_no_scan = e._build_report_html(
        labels=labels,
        data_range="2024-01-01 to 2024-02-01",
        best_timeframe="1h",
        best_data_days=30,
        scan_timeframes="",
        run_id="r1",
        timestamp_utc="2026-02-11T00:00:00Z",
        min_avg_daily_trades_target=5.0,
        min_avg_daily_trades_filter=2.0,
        capital_mode="shared",
        init_cash_usdt=1000.0,
        order_size_pct=0.5,
        max_concurrent_positions=2,
        wf_train_days=7,
        wf_test_days=2,
        wf_step_days=2,
        wf_mode="rolling",
        wf_segments=3,
        base_symbol="BTC/USDT",
        trade_symbols=["ETH/BTC", "BNB/BTC"],
        summary_html="<table id='summary'></table>",
        report_params_html="<table id='params'></table>",
        oos_summary_html="<table id='oos'></table>",
        top10_html="<table id='top'></table>",
        lb_best_html="<table id='lb-best'></table>",
        lb_recent_html="<table id='lb-recent'></table>",
        plot_symbol="ETH/BTC",
        plot_html="<div id='plot'></div>",
    )
    assert "Scan Timeframes" not in html_no_scan


def test_write_report_files(tmp_path):
    latest = tmp_path / "latest.html"
    run = tmp_path / "run.html"
    html = "<html><body>ok</body></html>"
    e._write_report_files(str(latest), str(run), html)
    assert latest.exists()
    assert run.exists()
    assert latest.read_text(encoding="utf-8") == html
    assert run.read_text(encoding="utf-8") == html


def test_prepare_best_replay_payload():
    index = pd.date_range("2024-01-01", periods=4, freq="h")
    best_ctx = {
        "trade_close": pd.DataFrame({"ETH/BTC": [1.0, 1.1, 1.2, 1.3]}, index=index),
        "trade_symbols": ["ETH/BTC"],
        "data_range": "2024-01-01 to 2024-01-01",
        "init_cash_btc": 1.0,
        "vol_zscore_by_lb": {24: pd.Series([1.0, 1.2, 0.9, 1.1], index=index)},
        "mom_by_lb": {6: pd.Series([1.0, 1.0, -1.0, 1.0], index=index)},
        "trade_mom_by_lb": {3: pd.Series([0.5, -0.2, 0.3, -0.1], index=index)},
        "rsi_series": pd.Series([50.0, 50.0, 50.0, 50.0], index=index),
        "btc_close": pd.Series([10.0, 10.0, 10.0, 10.0], index=index),
        "bb_lower": pd.Series([9.0, 9.0, 9.0, 9.0], index=index),
        "bb_upper": pd.Series([11.0, 11.0, 11.0, 11.0], index=index),
    }
    best = {
        "regime_name": "trend_high",
        "regime_type": "trend",
        "vol_mode": "high",
        "regime_rsi_long": None,
        "regime_rsi_short": None,
        "indicator_list": "rsi",
        "filter_name": None,
        "rsi_long": 60.0,
        "rsi_short": 40.0,
        "vol_lookback": 24.0,
        "vol_z": 0.8,
        "mom_lookback": 6.0,
        "trade_mom_lookback": 3.0,
        "tp_stop": 0.003,
        "sl_stop": 0.006,
        "max_hold": 2.0,
    }
    seen = {}

    def _coerce(combo, params, ctx):
        seen["coerce_combo"] = combo
        assert ctx is best_ctx
        return params

    def _pick_series(series_map, key, default_key):
        seen.setdefault("pick_series_calls", []).append((key, default_key))
        return series_map[key], key

    def _apply_combo(long_regime, short_regime, combo, params, ctx):
        seen["apply_combo"] = combo
        assert ctx is best_ctx
        return long_regime, short_regime, params

    def _run_pf(*args, **kwargs):
        seen["run_pf_kwargs"] = kwargs
        return "pf_obj"

    class _Figure:
        def to_html(self, full_html=False, include_plotlyjs=None):
            seen["to_html_args"] = (full_html, include_plotlyjs)
            return "<div>plot</div>"

    def _plot_portfolio(pf_obj, plot_symbol):
        assert pf_obj == "pf_obj"
        seen["plot_symbol"] = plot_symbol
        return _Figure()

    def _calc_pf_series(pf_obj, trade_symbols, bar_hours):
        seen["calc_pf_series_args"] = (pf_obj, tuple(trade_symbols), bar_hours)
        return {
            "total_return_pct": pd.Series({"ETH/BTC": 12.0}),
            "total_profit": pd.Series({"ETH/BTC": 0.12}),
            "total_trades": pd.Series({"ETH/BTC": 4.0}),
            "win_rate_pct": pd.Series({"ETH/BTC": 50.0}),
            "avg_trade_pct": pd.Series({"ETH/BTC": 1.0}),
            "max_drawdown_pct": pd.Series({"ETH/BTC": -2.0}),
            "position_coverage_pct": pd.Series({"ETH/BTC": 30.0}),
            "avg_hold_hours": pd.Series({"ETH/BTC": 2.0}),
        }

    def _build_wf_slices(idx, train_days, test_days, step_days, mode=None, valid_days=0):
        seen["wf_slice_args"] = (len(idx), train_days, test_days, step_days, mode)
        return [(idx[0], idx[1])]

    got = e._prepare_best_replay_payload(
        best=best,
        best_timeframe="1h",
        best_ctx=best_ctx,
        timeframe_ranges=["1h (10d): 2024-01-01 to 2024-01-01"],
        wf_train_days=7,
        wf_test_days=2,
        wf_step_days=2,
        wf_mode="rolling",
        indicator_param_fields=["rsi_long", "rsi_short"],
        vol_lookbacks=[24],
        vol_zs=[0.8],
        mom_lookbacks=[6],
        trade_mom_lookbacks=[3],
        fees=0.001,
        slippage_bps=2.0,
        spread_bps=2.0,
        funding_rate_daily=0.0,
        order_size_pct=0.5,
        capital_mode="shared",
        max_concurrent_positions=2,
        indicator_combo_label_fn=lambda combo: "+".join(combo),
        coerce_indicator_params_fn=_coerce,
        pick_series_from_map_fn=_pick_series,
        apply_indicator_combo_fn=_apply_combo,
        timeframe_to_hours_fn=lambda tf: 1.0,
        run_pf_fn=_run_pf,
        plot_portfolio_fn=_plot_portfolio,
        calc_pf_series_fn=_calc_pf_series,
        build_walk_forward_slices_fn=_build_wf_slices,
    )

    assert got["plot_symbol"] == "ETH/BTC"
    assert got["scan_timeframes"] == "1h (10d): 2024-01-01 to 2024-01-01"
    assert got["best_filter_name"] == "rsi"
    assert got["best_trade_mom_lookback"] == 3
    assert got["best_tp_stop"] == 0.003
    assert got["best_sl_stop"] == 0.006
    assert got["best_max_hold"] == 2
    assert len(got["wf_slices"]) == 1
    assert float(got["best_summary"]["total_return_pct"].iloc[0]) == 12.0
    assert seen["coerce_combo"] == ("rsi",)
    assert seen["apply_combo"] == ("rsi",)
    assert seen["wf_slice_args"] == (4, 7, 2, 2, "rolling")
    assert seen["run_pf_kwargs"]["freq"] == "1h"
    assert list(seen["run_pf_kwargs"]["long_filter"].astype(int)) == [1, 0, 1, 0]
    assert list(seen["run_pf_kwargs"]["short_filter"].astype(int)) == [0, 1, 0, 1]
    assert seen["plot_symbol"] == "ETH/BTC"
    assert seen["to_html_args"] == (False, "cdn")
    assert seen["calc_pf_series_args"] == ("pf_obj", ("ETH/BTC",), 1.0)
    assert got["plot_html"] == "<div>plot</div>"


def test_build_best_report_frames():
    best_params = {
        "rsi_long": 60.0,
        "rsi_short": 40.0,
        "bb_width": None,
        "atr_ratio": None,
        "ma_fast": None,
        "ma_slow": None,
        "macd_hist_ratio": None,
        "stoch_long": None,
        "stoch_short": None,
        "obv_lookback": None,
        "volume_lookback": None,
        "volume_z": None,
        "roc_lookback": None,
        "roc_threshold": None,
        "mfi_long": None,
        "mfi_short": None,
        "cmf_lookback": None,
        "cmf_threshold": None,
        "vroc_lookback": None,
        "vroc_threshold": None,
        "ad_lookback": None,
    }
    best = {
        "vol_lookback": 24.0,
        "vol_z": 0.8,
        "mom_lookback": 6.0,
        "oos_segments": 3.0,
        "oos_avg_total_return_pct": 5.0,
        "oos_avg_win_rate_pct": 55.0,
    }
    report_params, oos_summary = e._build_best_report_frames(
        best=best,
        best_timeframe="1h",
        best_data_days=30,
        capital_mode="shared",
        wf_mode="rolling",
        best_regime={
            "regime_name": "trend_high",
            "regime_type": "trend",
            "vol_mode": "high",
            "regime_rsi_long": None,
            "regime_rsi_short": None,
        },
        best_filter_name="rsi",
        indicator_list="rsi",
        best_indicator_combo=("rsi",),
        best_trade_mom_lookback=3,
        best_tp_stop=0.003,
        best_sl_stop=0.006,
        best_max_hold=2,
        rsi_window=14,
        best_params=best_params,
    )

    assert list(report_params["timeframe"]) == ["1h"]
    assert list(report_params["wf_mode"]) == ["rolling"]
    assert list(report_params["filter_name"]) == ["rsi"]
    assert float(report_params["tp_stop"].iloc[0]) == 0.003
    assert list(oos_summary["oos_segments"]) == [3.0]
    assert list(oos_summary["oos_avg_total_return_pct"]) == [5.0]


def test_top_and_summary_report_columns_contract():
    top_cols = e._top_report_columns()
    summary_cols = e._summary_report_columns()

    assert top_cols[0:3] == ["timeframe", "data_days", "regime_name"]
    assert top_cols[-3:] == ["avg_position_coverage_pct", "avg_total_trades", "min_total_trades"]
    assert "oos_sharpe_like" in top_cols
    assert "oos_low_trade_penalty" in top_cols

    assert summary_cols == [
        "symbol",
        "total_return_pct",
        "total_profit",
        "total_trades",
        "position_coverage_pct",
        "win_rate_pct",
        "avg_trade_pct",
        "max_drawdown_pct",
        "avg_hold_hours",
    ]


def test_build_report_table_html_sections_default_and_custom_columns():
    calls = []

    def _df_to_html(df, columns, label_map):
        calls.append((df, list(columns), dict(label_map)))
        return f"html{len(calls)}"

    report_params = pd.DataFrame([{"timeframe": "1h"}])
    oos_summary = pd.DataFrame([{"oos_segments": 3}])
    top10 = pd.DataFrame([{"timeframe": "1h", "avg_total_return_pct": 10.0}])
    best_summary = pd.DataFrame([{"symbol": "ETH/BTC", "total_return_pct": 12.0}])

    got = e._build_report_table_html_sections(
        report_params=report_params,
        oos_summary=oos_summary,
        top10=top10,
        best_summary=best_summary,
        label_map={"timeframe": "Timeframe"},
        df_to_html_fn=_df_to_html,
    )

    assert got["top_columns"] == e._top_report_columns()
    assert got["summary_columns"] == e._summary_report_columns()
    assert got["report_params_html"] == "html1"
    assert got["oos_summary_html"] == "html2"
    assert got["top10_html"] == "html3"
    assert got["summary_html"] == "html4"
    assert calls[0][1] == ["timeframe"]
    assert calls[1][1] == ["oos_segments"]
    assert calls[2][1] == e._top_report_columns()
    assert calls[3][1] == e._summary_report_columns()

    calls.clear()
    got_custom = e._build_report_table_html_sections(
        report_params=report_params,
        oos_summary=oos_summary,
        top10=top10,
        best_summary=best_summary,
        label_map={},
        df_to_html_fn=_df_to_html,
        top_columns=["timeframe"],
        summary_columns=["symbol"],
    )
    assert got_custom["top_columns"] == ["timeframe"]
    assert got_custom["summary_columns"] == ["symbol"]
    assert calls[2][1] == ["timeframe"]
    assert calls[3][1] == ["symbol"]


def test_build_leaderboard_report_html_uses_default_columns():
    lb_recent = pd.DataFrame([{"run_id": "r2"}])
    lb_best = pd.DataFrame([{"run_id": "r1"}])
    seen = {"calls": []}

    def _df_to_html(df, columns, label_map):
        seen["calls"].append((list(df.columns), list(columns), dict(label_map)))
        return f"html{len(seen['calls'])}"

    result = e._build_leaderboard_report_html(
        lb_recent=lb_recent,
        lb_best=lb_best,
        label_map={"run_id": "Run ID"},
        df_to_html_fn=_df_to_html,
    )

    expected_columns = e._leaderboard_report_columns()
    assert result["columns"] == expected_columns
    assert result["lb_recent_html"] == "html1"
    assert result["lb_best_html"] == "html2"
    assert seen["calls"][0][1] == expected_columns
    assert seen["calls"][1][1] == expected_columns


def test_append_leaderboard_row_and_build_views(tmp_path):
    leaderboard_path = tmp_path / "leaderboard.csv"
    first = {
        "run_id": "r1",
        "timestamp_utc": "2026-02-07T00:00:00Z",
        "report_file": "r1.html",
        "score": 10.0,
    }
    second = {
        "run_id": "r2",
        "timestamp_utc": "2026-02-07T01:00:00Z",
        "report_file": "r2.html",
        "score": 20.0,
    }
    e._append_leaderboard_row(str(leaderboard_path), first)
    lb_df = e._append_leaderboard_row(str(leaderboard_path), second)
    assert len(lb_df) == 2

    lb_view, lb_recent, lb_best = e._build_leaderboard_views(
        lb_df=lb_df,
        history_rows=1,
        top_by_score_fn=lambda df, top_n, tie_break_avg_hold: (
            df.sort_values("score", ascending=False).head(top_n),
            "score",
        ),
    )
    assert "report" in lb_view.columns
    assert "href=" in lb_view.iloc[0]["report"]
    assert lb_recent.iloc[0]["run_id"] == "r2"
    assert lb_best.iloc[0]["run_id"] == "r2"


# ---------------------------------------------------------------------------
#  AWF-231: Leaderboard is_latest marking
# ---------------------------------------------------------------------------


def test_append_leaderboard_marks_is_latest(tmp_path):
    """is_latest should be True only for the newest run per (plot_symbol, timeframe)."""
    lb_path = tmp_path / "leaderboard.csv"
    row1 = {"run_id": "r1", "timestamp_utc": "2026-01-01T00:00:00Z", "plot_symbol": "BNB/BTC", "timeframe": "2h"}
    row2 = {"run_id": "r2", "timestamp_utc": "2026-01-02T00:00:00Z", "plot_symbol": "BNB/BTC", "timeframe": "2h"}
    row3 = {"run_id": "r3", "timestamp_utc": "2026-01-01T12:00:00Z", "plot_symbol": "SOL/BTC", "timeframe": "4h"}

    e._append_leaderboard_row(str(lb_path), row1)
    e._append_leaderboard_row(str(lb_path), row2)
    lb_df = e._append_leaderboard_row(str(lb_path), row3)

    assert "is_latest" in lb_df.columns
    # BNB/BTC 2h: r2 is latest (newer timestamp)
    bnb_rows = lb_df[lb_df["plot_symbol"] == "BNB/BTC"]
    assert bnb_rows[bnb_rows["is_latest"] == True]["run_id"].iloc[0] == "r2"
    assert not bnb_rows[bnb_rows["run_id"] == "r1"]["is_latest"].iloc[0]
    # SOL/BTC 4h: r3 is the only row → is_latest
    sol_rows = lb_df[lb_df["plot_symbol"] == "SOL/BTC"]
    assert sol_rows["is_latest"].iloc[0] == True


def test_mark_leaderboard_is_latest_empty():
    """Empty DataFrame returns empty without error."""
    result = e._mark_leaderboard_is_latest(pd.DataFrame())
    assert result.empty

