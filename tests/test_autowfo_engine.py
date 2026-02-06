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
