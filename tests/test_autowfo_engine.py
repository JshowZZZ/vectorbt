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
