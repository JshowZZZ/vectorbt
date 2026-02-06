import json

import pandas as pd

from scripts.autowfo import engine as e


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


def test_normalize_trade_symbols():
    got = e._normalize_trade_symbols(
        "ETH/BTC, BTC/USDT, SOL/BTC",
        base_symbol="BTC/USDT",
        default_trade_symbols=["BNB/BTC"],
    )
    assert got == ["ETH/BTC", "SOL/BTC"]


def test_build_regime_variants_characterization():
    variants = e._build_regime_variants([(30, 70), (40, 60), (35, 65)])
    names = [v["regime_name"] for v in variants]
    assert len(variants) == 12
    assert "trend_high" in names
    assert "rsi_revert_low" in names
    assert "bb_breakout_high" in names


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
    assert seen == {"a=1"}


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

    combo_row = e._build_combo_row(
        timeframe="3m",
        data_days=60,
        exchange="binance",
        base_symbol="BTC/USDT",
        trade_symbols_tf=["ETH/BTC"],
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
