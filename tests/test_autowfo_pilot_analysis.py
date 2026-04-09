import json

import pandas as pd

from autowfo import pilot_analysis


def _combo_frame(return_pct=0.1, trades=1.0, sharpe=1.0):
    return pd.DataFrame(
        [
            {
                "timeframe": "2h",
                "data_days": 180,
                "indicator_list": "mfi,obv_roc",
                "regime_name": "trend_high",
                "vol_mode": "high",
                "filter_name": "none",
                "vol_lookback": 20,
                "mom_lookback": 14,
                "trade_mom_lookback": 14,
                "tp_stop": 1.5,
                "sl_stop": 1.0,
                "max_hold": 4,
                "oos_avg_total_return_pct": return_pct,
                "oos_avg_total_trades": trades,
                "oos_sharpe_like": sharpe,
            }
        ]
    )


def _symbol_frame(returns, trades=None):
    if trades is None:
        trades = [1.0] * len(returns)
    rows = []
    for symbol, ret, trade_count in zip(["LTC/BTC", "LINK/BTC", "SOL/BTC"], returns, trades):
        rows.append(
            {
                "timeframe": "2h",
                "data_days": 180,
                "indicator_list": "mfi,obv_roc",
                "regime_name": "trend_high",
                "vol_mode": "high",
                "filter_name": "none",
                "vol_lookback": 20,
                "mom_lookback": 14,
                "trade_mom_lookback": 14,
                "tp_stop": 1.5,
                "sl_stop": 1.0,
                "max_hold": 4,
                "symbol": symbol,
                "oos_avg_total_return_pct": ret,
                "oos_avg_total_trades": trade_count,
                "oos_positive_segment_ratio": 0.5 if ret > 0 else 0.0,
                "oos_segments": 2.0,
            }
        )
    return pd.DataFrame(rows)


def test_compare_pilot_runs_marks_gate_passed_for_all_symbol_supported_candidate():
    main_run = {
        "run_id": "main",
        "run_root": "artifacts/runs/main",
        "combo_df": _combo_frame(return_pct=0.12, trades=1.0, sharpe=1.5),
        "symbol_oos_df": _symbol_frame([0.2, 0.1, 0.05]),
        "metadata": {"timeframe_diagnostics": [{"realized_shared_days": 125}]},
    }
    sens_run = {
        "run_id": "sens",
        "run_root": "artifacts/runs/sens",
        "combo_df": _combo_frame(return_pct=0.08, trades=0.75, sharpe=1.1),
        "symbol_oos_df": _symbol_frame([0.1, 0.04, 0.01], trades=[1.0, 0.5, 0.5]),
        "metadata": {"timeframe_diagnostics": [{"realized_shared_days": 125}]},
    }

    payload = pilot_analysis.compare_pilot_runs(
        main_run,
        sens_run,
        min_combo_return=0.0,
        min_combo_trades=0.5,
        top_n=5,
    )

    assert payload["schema_version"] == pilot_analysis.SCHEMA_VERSION
    assert payload["summary"]["compared_combo_rows"] == 1
    assert payload["summary"]["stable_positive_rows"] == 1
    assert payload["summary"]["gate_passed_rows"] == 1
    row = payload["top_gate_passed"][0]
    assert row["passes_overall_gate"] is True
    assert row["both_positive"] is True
    assert row["symbol_support_main"]["all_symbols_nonnegative"] is True
    assert row["symbol_support_sens"]["all_symbols_nonnegative"] is True
    assert row["min_return"] == 0.08


def test_compare_pilot_runs_blocks_gate_when_one_symbol_turns_negative():
    main_run = {
        "run_id": "main",
        "run_root": "artifacts/runs/main",
        "combo_df": _combo_frame(return_pct=0.12, trades=1.0, sharpe=1.5),
        "symbol_oos_df": _symbol_frame([0.2, 0.1, 0.05]),
        "metadata": {},
    }
    sens_run = {
        "run_id": "sens",
        "run_root": "artifacts/runs/sens",
        "combo_df": _combo_frame(return_pct=0.08, trades=0.75, sharpe=1.1),
        "symbol_oos_df": _symbol_frame([0.1, -0.04, 0.01], trades=[1.0, 0.5, 0.5]),
        "metadata": {},
    }

    payload = pilot_analysis.compare_pilot_runs(
        main_run,
        sens_run,
        min_combo_return=0.0,
        min_combo_trades=0.5,
        top_n=5,
    )

    assert payload["summary"]["stable_positive_rows"] == 1
    assert payload["summary"]["gate_passed_rows"] == 0
    row = payload["top_stable_positive"][0]
    assert row["both_positive"] is True
    assert row["passes_symbol_support_gate"] is False
    assert row["passes_overall_gate"] is False
    assert row["symbol_support_sens"]["nonnegative_count"] == 2


def test_load_run_analysis_inputs_resolves_run_id_under_artifacts(tmp_path):
    run_root = tmp_path / "artifacts" / "runs" / "20260409_010000"
    (run_root / "results").mkdir(parents=True)
    (run_root / "metadata").mkdir(parents=True)
    _combo_frame().to_csv(run_root / "results" / "param_sweep_combo_summary.csv", index=False)
    _symbol_frame([0.1, 0.05, 0.01]).to_csv(
        run_root / "results" / "param_sweep_symbol_oos_summary.csv",
        index=False,
    )
    metadata = {"timeframe_diagnostics": [{"realized_shared_days": 125}]}
    (run_root / "metadata" / "run_metadata_20260409_010000.json").write_text(
        json.dumps(metadata),
        encoding="utf-8",
    )

    got = pilot_analysis.load_run_analysis_inputs("20260409_010000", artifacts_dir=tmp_path / "artifacts")

    assert got["run_id"] == "20260409_010000"
    assert len(got["combo_df"]) == 1
    assert len(got["symbol_oos_df"]) == 3
    assert got["metadata"]["timeframe_diagnostics"][0]["realized_shared_days"] == 125
