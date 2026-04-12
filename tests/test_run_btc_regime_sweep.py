import datetime as dt
import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from autowfo import run_btc_regime_sweep as sweep
from autowfo import data as autowfo_data
from autowfo import evaluator as autowfo_evaluator
from autowfo import metrics as autowfo_metrics
from autowfo import portfolio as autowfo_portfolio
from autowfo import run_workspace as autowfo_run_workspace
from autowfo import split as autowfo_split
from autowfo import strategy as autowfo_strategy


def _make_ohlcv(index, base=100.0):
    close = pd.Series(base + np.arange(len(index), dtype=float), index=index)
    return pd.DataFrame(
        {
            "Open": close,
            "High": close * 1.01,
            "Low": close * 0.99,
            "Close": close,
            "Volume": 1000 + np.arange(len(index), dtype=float),
        },
        index=index,
    )


def _common_ctx_kwargs():
    return dict(
        timeframe="3m",
        data_days=10,
        base_symbol="BTC/USDT",
        trade_symbols=["ETH/BTC", "BNB/BTC"],
        exchange="binance",
        cache_dir="artifacts/cache_ccxt",
        cache_format="parquet",
        vol_lookbacks=[3],
        mom_lookbacks=[3],
        trade_mom_lookbacks=[3],
        rsi_window=3,
        bb_window=3,
        bb_alpha=2.0,
        atr_window=3,
        ma_pairs=[(3, 5)],
        obv_lookbacks=[3],
        volume_lookbacks=[3],
        roc_lookbacks=[3],
        cmf_lookbacks=[3],
        mfi_window=3,
        vroc_lookbacks=[3],
        ad_lookbacks=[3],
        cci_lookbacks=[3],
        willr_lookbacks=[3],
        adx_lookbacks=[3],
        trix_lookbacks=[3],
        dpo_lookbacks=[3],
        efi_lookbacks=[3],
        vwma_lookbacks=[3],
        ultosc_periods=(7, 14, 28),
        keltner_lookbacks=[3],
        donchian_lookbacks=[3],
        ppo_fast=12,
        ppo_slow=26,
        ppo_signal=9,
        chop_lookbacks=[3],
        init_cash_usdt=1000,
        capital_mode="shared",
    )


def test_resolve_risk_grid_from_config_overrides_and_fallback():
    got = sweep._resolve_risk_grid_from_config(
        {
            "tp_stops": [0.004, "bad", -1, 0.004, 0.3],
            "sl_stops": [0.009, 0.5],
            "max_holds": ["3", 0, "x", 3, 999],
        }
    )
    assert got["tp_stops"] == [0.004]
    assert got["sl_stops"] == [0.009]
    assert got["max_holds"] == [3]

    fallback = sweep._resolve_risk_grid_from_config(
        {"tp_stops": [], "sl_stops": [None], "max_holds": ["bad"]}
    )
    assert fallback["tp_stops"] == [0.003, 0.005]
    assert fallback["sl_stops"] == [0.006, 0.01]
    assert fallback["max_holds"] == [2, 4]


def test_resolve_risk_grid_from_config_atr_multiple():
    got = sweep._resolve_risk_grid_from_config(
        {
            "risk_mode": "atr_multiple",
            "tp_atr_multipliers": [1.5, "bad", 99],
            "sl_atr_multipliers": [1.0, 0, -1],
            "max_holds": [3],
        }
    )
    assert got["risk_mode"] == "atr_multiple"
    assert got["tp_stops"] == [1.5]
    assert got["sl_stops"] == [1.0]
    assert got["max_holds"] == [3]


def test_select_indicator_param_options_filters_and_freezes():
    options = {
        "mfi": [{"mfi_long": 70, "mfi_short": 30}, {"mfi_long": 80, "mfi_short": 20}],
        "cmf": [{"cmf_lookback": 20, "cmf_threshold": 0.05}],
        "obv_roc": [{"obv_lookback": 12}, {"obv_lookback": 24}],
    }
    filtered, defaults = sweep._select_indicator_param_options(
        options,
        ["obv_roc", "mfi"],
        fixed_params=False,
    )
    assert set(filtered) == {"obv_roc", "mfi"}
    assert defaults["obv_roc"] == {"obv_lookback": 12}

    frozen, frozen_defaults = sweep._select_indicator_param_options(
        options,
        ["obv_roc", "mfi"],
        fixed_params=True,
    )
    assert frozen_defaults == defaults
    assert frozen["obv_roc"] == [{"obv_lookback": 12}]
    assert frozen["mfi"] == [{"mfi_long": 70, "mfi_short": 30}]


def test_prepare_timeframe_context_success():
    index = pd.date_range("2024-01-01", periods=50, freq="h")
    base_df = _make_ohlcv(index, base=100.0)
    trade_df = _make_ohlcv(index, base=1.0)

    def loader(symbol, *_args, **_kwargs):
        return base_df if symbol == "BTC/USDT" else trade_df

    ctx = autowfo_data._prepare_timeframe_context(
        **_common_ctx_kwargs(), load_or_update_symbol_fn=loader
    )

    assert ctx["trade_close"].shape[1] == 2
    assert ctx["trade_atr_ratio"].shape == ctx["trade_close"].shape
    assert ctx["total_days"] >= 1
    assert ctx["init_cash_btc"] > 0
    assert ctx["overlap_diagnostics"]["available_trade_symbol_count"] == 2
    assert ctx["overlap_diagnostics"]["realized_shared_days"] == ctx["total_days"]
    assert "BTC/USDT" in ctx["overlap_diagnostics"]["symbol_data_ranges"]
    assert "ETH/BTC" in ctx["overlap_diagnostics"]["symbol_data_ranges"]


def test_prepare_timeframe_context_builds_htf_trend_filters():
    index = pd.date_range("2024-01-01", periods=24 * 14, freq="h")
    base_df = _make_ohlcv(index, base=100.0)
    trade_df = _make_ohlcv(index, base=1.0)

    def loader(symbol, *_args, **_kwargs):
        return base_df if symbol == "BTC/USDT" else trade_df

    ctx = autowfo_data._prepare_timeframe_context(
        **_common_ctx_kwargs(),
        htf_trend_timeframes=["8h", "1d"],
        htf_trend_windows=[3],
        load_or_update_symbol_fn=loader,
    )

    htf_filters = ctx["htf_trend_filters"]
    assert sorted(htf_filters) == ["htf_trend:1d:3", "htf_trend:8h:3"]
    for value in htf_filters.values():
        assert list(value) == ["long", "short"]
        assert value["long"].index.equals(ctx["trade_close"].index)
        assert value["short"].index.equals(ctx["trade_close"].index)


def test_prepare_timeframe_context_builds_funding_gate_filters():
    index = pd.date_range("2024-01-01", periods=24 * 14, freq="h")
    base_df = _make_ohlcv(index, base=100.0)
    trade_df = _make_ohlcv(index, base=1.0)
    funding_index = pd.date_range("2023-12-31 16:00:00", periods=50, freq="8h")

    def loader(symbol, *_args, **_kwargs):
        return base_df if symbol == "BTC/USDT" else trade_df

    def funding_loader(symbol, *_args, **_kwargs):
        base_rate = 0.00005 if symbol == "ETH/BTC" else 0.00015
        values = [base_rate if idx % 2 == 0 else -base_rate for idx in range(len(funding_index))]
        return pd.DataFrame({"fundingRate": values}, index=funding_index)

    ctx = autowfo_data._prepare_timeframe_context(
        **_common_ctx_kwargs(),
        funding_gate_long_thresholds=[0.0001],
        funding_gate_short_thresholds=[-0.0001],
        load_or_update_symbol_fn=loader,
        load_funding_history_fn=funding_loader,
    )

    funding_filters = ctx["funding_gate_filters"]
    assert list(funding_filters) == ["funding_gate:0.0001:-0.0001"]
    selected = funding_filters["funding_gate:0.0001:-0.0001"]
    assert selected["long"].columns.tolist() == ["ETH/BTC", "BNB/BTC"]
    assert selected["short"].columns.tolist() == ["ETH/BTC", "BNB/BTC"]
    assert selected["long"].index.equals(ctx["trade_close"].index)
    assert selected["short"].index.equals(ctx["trade_close"].index)
    assert selected["long"]["ETH/BTC"].any()
    assert (~selected["long"]["BNB/BTC"]).any()


def test_resolve_pf_stops_atr_multiple_uses_trade_atr_ratio():
    index = pd.date_range("2024-01-01", periods=3, freq="h")
    trade_atr_ratio = pd.DataFrame(
        {
            "ETH/BTC": [0.01, 0.02, 0.03],
            "BNB/BTC": [0.02, 0.03, 0.04],
        },
        index=index,
    )
    sl_stop, tp_stop = autowfo_evaluator._resolve_pf_stops(
        ctx={"trade_atr_ratio": trade_atr_ratio},
        risk_mode="atr_multiple",
        sl_stop=1.0,
        tp_stop=1.5,
    )
    pd.testing.assert_frame_equal(sl_stop, trade_atr_ratio)
    pd.testing.assert_frame_equal(tp_stop, trade_atr_ratio * 1.5)


def test_prepare_timeframe_context_no_overlap():
    base_index = pd.date_range("2024-01-01", periods=10, freq="h")
    trade_index = pd.date_range("2024-02-01", periods=10, freq="h")
    base_df = _make_ohlcv(base_index, base=100.0)
    trade_df = _make_ohlcv(trade_index, base=1.0)

    def loader(symbol, *_args, **_kwargs):
        return base_df if symbol == "BTC/USDT" else trade_df

    with pytest.raises(RuntimeError, match="No overlapping"):
        autowfo_data._prepare_timeframe_context(
            **_common_ctx_kwargs(), load_or_update_symbol_fn=loader
        )


def test_prepare_timeframe_context_clips_to_requested_days():
    index = pd.date_range("2024-01-01", periods=24 * 30, freq="h")
    base_df = _make_ohlcv(index, base=100.0)
    trade_df = _make_ohlcv(index, base=1.0)

    def loader(symbol, *_args, **_kwargs):
        return base_df if symbol == "BTC/USDT" else trade_df

    cfg = _common_ctx_kwargs()
    cfg["data_days"] = 3
    ctx = autowfo_data._prepare_timeframe_context(
        **cfg, load_or_update_symbol_fn=loader
    )

    assert ctx["total_days"] <= 4
    assert (ctx["trade_close"].index[-1] - ctx["trade_close"].index[0]) <= pd.Timedelta(days=4)


def test_run_pf_combo_metrics_group_by():
    index = pd.date_range("2024-01-01", periods=30, freq="h")
    trade_close = pd.DataFrame(
        {
            "ETH/BTC": np.linspace(1.0, 2.0, len(index)),
            "BNB/BTC": np.linspace(1.5, 2.5, len(index)),
        },
        index=index,
    )
    long_regime = pd.Series(True, index=index)
    short_regime = pd.Series(False, index=index)

    pf = autowfo_portfolio._run_pf(
        trade_close,
        long_regime,
        short_regime,
        max_hold=2,
        fees=0.0,
        sl_stop=None,
        tp_stop=None,
        freq="1h",
        slippage=0.0,
        init_cash=1.0,
        size=1.0,
        size_type="percent",
        cash_sharing=True,
        lock_cash=True,
        allow_partial=False,
        max_positions=None,
    )

    metrics = autowfo_metrics._calc_pf_combo_metrics(pf, bar_hours=1.0)
    assert metrics["total_trades"] > 0
    assert np.isfinite(metrics["total_return_pct"])


def test_run_pf_costs_reduce_return():
    index = pd.date_range("2024-01-01", periods=30, freq="h")
    trade_close = pd.DataFrame(
        {
            "ETH/BTC": np.linspace(1.0, 2.0, len(index)),
            "BNB/BTC": np.linspace(1.2, 2.4, len(index)),
        },
        index=index,
    )
    long_regime = pd.Series(True, index=index)
    short_regime = pd.Series(False, index=index)

    pf_no_cost = autowfo_portfolio._run_pf(
        trade_close,
        long_regime,
        short_regime,
        max_hold=2,
        fees=0.0,
        sl_stop=None,
        tp_stop=None,
        freq="1h",
        slippage=0.0,
        init_cash=1.0,
        size=1.0,
        size_type="percent",
        cash_sharing=True,
        lock_cash=True,
        allow_partial=False,
        max_positions=None,
    )

    pf_cost = autowfo_portfolio._run_pf(
        trade_close,
        long_regime,
        short_regime,
        max_hold=2,
        fees=0.001,
        sl_stop=None,
        tp_stop=None,
        freq="1h",
        slippage=0.001,
        init_cash=1.0,
        size=1.0,
        size_type="percent",
        cash_sharing=True,
        lock_cash=True,
        allow_partial=False,
        max_positions=None,
    )

    ret_no = float(pf_no_cost.total_return(group_by=True))
    ret_cost = float(pf_cost.total_return(group_by=True))
    assert np.isfinite(ret_no)
    assert np.isfinite(ret_cost)
    assert ret_cost <= ret_no + 1e-9


def test_main_smoke_integration(tmp_path, monkeypatch):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    cfg = {
        "search_mode": "combo",
        "combo_sizes": [1],
        "combo_seed": 1,
        "combo_segment_start": 0,
        "combo_segment_size": 1,
        "timeframes": [{"timeframe": "1h", "days": 2}],
        "top_n_refine": 1,
        "trade_symbols": ["ETH/BTC"],
        "capital_mode": "per_symbol",
        "init_cash_usdt": 1000,
        "order_size_pct": 0.5,
        "max_concurrent_positions": 1,
        "slippage_bps": 0.0,
        "spread_bps": 0.0,
        "funding_rate_daily": 0.0,
    }
    (artifacts / "sweep_config.json").write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        autowfo_data,
        "_fetch_top_trade_symbols",
        lambda exchange, limit=10, fallback=None: ["ETH/BTC"],
    )

    def loader(symbol, *_args, **_kwargs):
        index = pd.date_range("2024-01-01", periods=48, freq="h")
        base = 100.0 if symbol == "BTC/USDT" else 1.0
        return _make_ohlcv(index, base=base)

    monkeypatch.setattr(autowfo_data, "_load_or_update_symbol", loader)
    monkeypatch.setattr(
        autowfo_strategy,
        "_build_indicator_param_options_coarse",
        lambda: {"volume_z": [{"volume_lookback": 12, "volume_z": 0.1}]},
    )
    monkeypatch.setattr(
        sweep,
        "INDICATOR_META",
        {"volume_z": {"label": "volume_z", "category": "volume"}},
    )
    monkeypatch.setattr(autowfo_split, "_build_walk_forward_slices", lambda index, *_args, **_kwargs: [])

    sweep.main()

    run_dirs = sorted((artifacts / "runs").glob("*"))
    assert len(run_dirs) == 1
    workspace = autowfo_run_workspace.build_run_workspace(Path(tmp_path), run_dirs[0].name)
    assert not (artifacts / "param_sweep_combo_summary.csv").exists()
    assert not (artifacts / "run_registry.json").exists()
    assert workspace.runtime_config_path.exists()
    assert workspace.status_json_path.exists()
    assert workspace.combo_summary_path.exists()
    assert workspace.symbol_summary_path.exists()
    assert workspace.top10_path.exists()
    assert workspace.run_metadata_path.exists()
    assert workspace.registry_path.exists()
    assert workspace.db_path.exists()

    assert json.loads(workspace.runtime_config_path.read_text(encoding="utf-8")) == cfg
    df = pd.read_csv(workspace.combo_summary_path)
    assert len(df) >= 1


def test_main_uses_configured_walk_forward_days(tmp_path, monkeypatch):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    cfg = {
        "search_mode": "combo",
        "combo_sizes": [1],
        "combo_seed": 1,
        "combo_segment_start": 0,
        "combo_segment_size": 1,
        "timeframes": [{"timeframe": "1h", "days": 2}],
        "wf_train_days": 7,
        "wf_test_days": 2,
        "wf_step_days": 2,
        "top_n_refine": 1,
        "trade_symbols": ["ETH/BTC"],
        "capital_mode": "per_symbol",
        "init_cash_usdt": 1000,
        "order_size_pct": 0.5,
        "max_concurrent_positions": 1,
        "slippage_bps": 0.0,
        "spread_bps": 0.0,
        "funding_rate_daily": 0.0,
    }
    (artifacts / "sweep_config.json").write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        autowfo_data,
        "_fetch_top_trade_symbols",
        lambda exchange, limit=10, fallback=None: ["ETH/BTC"],
    )

    def loader(symbol, *_args, **_kwargs):
        index = pd.date_range("2024-01-01", periods=48, freq="h")
        base = 100.0 if symbol == "BTC/USDT" else 1.0
        return _make_ohlcv(index, base=base)

    monkeypatch.setattr(autowfo_data, "_load_or_update_symbol", loader)
    monkeypatch.setattr(
        autowfo_strategy,
        "_build_indicator_param_options_coarse",
        lambda: {"volume_z": [{"volume_lookback": 12, "volume_z": 0.1}]},
    )
    monkeypatch.setattr(
        sweep,
        "INDICATOR_META",
        {"volume_z": {"label": "volume_z", "category": "volume"}},
    )
    seen = {}

    def _capture_wf(index, train_days, test_days, step_days, mode=None, valid_days=0):
        seen["wf"] = (train_days, test_days, step_days, mode)
        return []

    monkeypatch.setattr(autowfo_split, "_build_walk_forward_slices", _capture_wf)

    sweep.main()

    assert seen.get("wf") == (7, 2, 2, "anchored")


def test_main_uses_configured_walk_forward_mode(tmp_path, monkeypatch):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    cfg = {
        "search_mode": "combo",
        "combo_sizes": [1],
        "combo_seed": 1,
        "combo_segment_start": 0,
        "combo_segment_size": 1,
        "timeframes": [{"timeframe": "1h", "days": 2}],
        "wf_train_days": 7,
        "wf_test_days": 2,
        "wf_step_days": 2,
        "wf_mode": "rolling",
        "top_n_refine": 1,
        "trade_symbols": ["ETH/BTC"],
        "capital_mode": "per_symbol",
        "init_cash_usdt": 1000,
        "order_size_pct": 0.5,
        "max_concurrent_positions": 1,
        "slippage_bps": 0.0,
        "spread_bps": 0.0,
        "funding_rate_daily": 0.0,
    }
    (artifacts / "sweep_config.json").write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        autowfo_data,
        "_fetch_top_trade_symbols",
        lambda exchange, limit=10, fallback=None: ["ETH/BTC"],
    )

    def loader(symbol, *_args, **_kwargs):
        index = pd.date_range("2024-01-01", periods=48, freq="h")
        base = 100.0 if symbol == "BTC/USDT" else 1.0
        return _make_ohlcv(index, base=base)

    monkeypatch.setattr(autowfo_data, "_load_or_update_symbol", loader)
    monkeypatch.setattr(
        autowfo_strategy,
        "_build_indicator_param_options_coarse",
        lambda: {"volume_z": [{"volume_lookback": 12, "volume_z": 0.1}]},
    )
    monkeypatch.setattr(
        sweep,
        "INDICATOR_META",
        {"volume_z": {"label": "volume_z", "category": "volume"}},
    )
    seen = {}

    def _capture_wf(index, train_days, test_days, step_days, mode=None, valid_days=0):
        seen["wf"] = (train_days, test_days, step_days, mode)
        return []

    monkeypatch.setattr(autowfo_split, "_build_walk_forward_slices", _capture_wf)

    sweep.main()

    assert seen.get("wf") == (7, 2, 2, "rolling")


def test_main_deterministic_artifacts_bit_identical(tmp_path, monkeypatch):
    run_id_dt = dt.datetime(2026, 2, 7, 12, 34, 56)
    run_id = run_id_dt.strftime("%Y%m%d_%H%M%S")

    class _FrozenDatetime(dt.datetime):
        @classmethod
        def utcnow(cls):
            return cls(
                run_id_dt.year,
                run_id_dt.month,
                run_id_dt.day,
                run_id_dt.hour,
                run_id_dt.minute,
                run_id_dt.second,
            )

    cfg = {
        "search_mode": "combo",
        "combo_sizes": [1],
        "combo_seed": 1,
        "combo_segment_start": 0,
        "combo_segment_size": 1,
        "timeframes": [{"timeframe": "1h", "days": 2}],
        "top_n_refine": 1,
        "trade_symbols": ["ETH/BTC"],
        "capital_mode": "per_symbol",
        "init_cash_usdt": 1000,
        "order_size_pct": 0.5,
        "max_concurrent_positions": 1,
        "slippage_bps": 0.0,
        "spread_bps": 0.0,
        "funding_rate_daily": 0.0,
    }

    monkeypatch.setattr(sweep.dt, "datetime", _FrozenDatetime)
    monkeypatch.setattr(
        autowfo_data,
        "_fetch_top_trade_symbols",
        lambda exchange, limit=10, fallback=None: ["ETH/BTC"],
    )

    def loader(symbol, *_args, **_kwargs):
        index = pd.date_range("2024-01-01", periods=48, freq="h")
        base = 100.0 if symbol == "BTC/USDT" else 1.0
        return _make_ohlcv(index, base=base)

    monkeypatch.setattr(autowfo_data, "_load_or_update_symbol", loader)
    monkeypatch.setattr(
        autowfo_strategy,
        "_build_indicator_param_options_coarse",
        lambda: {"volume_z": [{"volume_lookback": 12, "volume_z": 0.1}]},
    )
    monkeypatch.setattr(
        sweep,
        "INDICATOR_META",
        {"volume_z": {"label": "volume_z", "category": "volume"}},
    )
    monkeypatch.setattr(autowfo_split, "_build_walk_forward_slices", lambda index, *_args, **_kwargs: [])

    run_dirs = [tmp_path / "run_a", tmp_path / "run_b"]
    for run_dir in run_dirs:
        artifacts = run_dir / "artifacts"
        artifacts.mkdir(parents=True, exist_ok=True)
        (artifacts / "sweep_config.json").write_text(
            json.dumps(cfg, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        monkeypatch.chdir(run_dir)
        sweep.main()

    artifacts_a = run_dirs[0] / "artifacts"
    artifacts_b = run_dirs[1] / "artifacts"
    root_legacy_outputs = [
        "param_sweep_combo_summary.csv",
        "param_sweep_symbol_summary.csv",
        f"param_sweep_combo_summary_{run_id}.csv",
        f"param_sweep_symbol_summary_{run_id}.csv",
        f"param_sweep_top10_{run_id}.csv",
        "leaderboard.csv",
        "run_registry.json",
        "run_metadata.json",
        f"run_metadata_{run_id}.json",
        "run_status.json",
        "run_status.html",
        "results.db",
    ]
    for name in root_legacy_outputs:
        assert not (artifacts_a / name).exists()
        assert not (artifacts_b / name).exists()

    workspace_a = autowfo_run_workspace.build_run_workspace(run_dirs[0], run_id)
    workspace_b = autowfo_run_workspace.build_run_workspace(run_dirs[1], run_id)
    workspace_compare_files = [
        workspace_a.runtime_config_path.relative_to(run_dirs[0]),
        workspace_a.combo_summary_path.relative_to(run_dirs[0]),
        workspace_a.symbol_summary_path.relative_to(run_dirs[0]),
        workspace_a.top10_path.relative_to(run_dirs[0]),
        workspace_a.leaderboard_path.relative_to(run_dirs[0]),
        workspace_a.run_metadata_path.relative_to(run_dirs[0]),
        workspace_a.registry_path.relative_to(run_dirs[0]),
    ]
    for rel_path in workspace_compare_files:
        path_a = run_dirs[0] / rel_path
        path_b = run_dirs[1] / rel_path
        assert path_a.exists()
        assert path_b.exists()
        assert path_a.read_bytes() == path_b.read_bytes()

    assert workspace_a.status_json_path.exists()
    assert workspace_b.status_json_path.exists()
    status_a = json.loads(workspace_a.status_json_path.read_text(encoding="utf-8"))
    status_b = json.loads(workspace_b.status_json_path.read_text(encoding="utf-8"))
    for payload in (status_a, status_b):
        payload["elapsed"] = ""
        payload["eta"] = ""
    assert status_a == status_b

    assert workspace_a.db_path.exists()
    assert workspace_b.db_path.exists()
    with sqlite3.connect(workspace_a.db_path) as conn_a, sqlite3.connect(workspace_b.db_path) as conn_b:
        tables_a = pd.read_sql_query(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name",
            conn_a,
        )
        tables_b = pd.read_sql_query(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name",
            conn_b,
        )
        assert tables_a.equals(tables_b)
        for table_name in tables_a["name"].tolist():
            count_a = pd.read_sql_query(f"SELECT COUNT(*) AS row_count FROM {table_name}", conn_a)
            count_b = pd.read_sql_query(f"SELECT COUNT(*) AS row_count FROM {table_name}", conn_b)
            assert count_a.equals(count_b)

