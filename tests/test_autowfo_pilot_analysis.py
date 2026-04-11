import json

import pandas as pd

from autowfo import pilot_analysis


def _combo_frame(return_pct=0.1, trades=1.0, sharpe=1.0, indicator_list="mfi,obv_roc", data_days=180):
    return pd.DataFrame(
        [
            {
                "timeframe": "2h",
                "data_days": data_days,
                "indicator_list": indicator_list,
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


def _symbol_frame(returns, trades=None, indicator_list="mfi,obv_roc", data_days=180):
    if trades is None:
        trades = [1.0] * len(returns)
    rows = []
    for symbol, ret, trade_count in zip(["LTC/BTC", "LINK/BTC", "SOL/BTC"], returns, trades):
        rows.append(
            {
                "timeframe": "2h",
                "data_days": data_days,
                "indicator_list": indicator_list,
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


def test_compare_pilot_runs_excludes_rows_without_symbol_support_from_stable_positive():
    main_run = {
        "run_id": "main",
        "run_root": "artifacts/runs/main",
        "combo_df": _combo_frame(return_pct=0.12, trades=1.0, sharpe=1.5),
        "symbol_oos_df": pd.DataFrame(),
        "metadata": {},
    }
    sens_run = {
        "run_id": "sens",
        "run_root": "artifacts/runs/sens",
        "combo_df": _combo_frame(return_pct=0.08, trades=0.75, sharpe=1.1),
        "symbol_oos_df": pd.DataFrame(),
        "metadata": {},
    }

    payload = pilot_analysis.compare_pilot_runs(main_run, sens_run, top_n=5)

    assert payload["summary"]["compared_combo_rows"] == 1
    assert payload["summary"]["symbol_supported_rows"] == 0
    assert payload["summary"]["stable_positive_rows"] == 0
    assert payload["summary"]["gate_passed_rows"] == 0
    assert payload["top_stable_positive"] == []


def test_compare_pilot_runs_window_aware_trade_gate_relaxes_short_window_floor():
    main_run = {
        "run_id": "main",
        "run_root": "artifacts/runs/main",
        "combo_df": _combo_frame(return_pct=0.12, trades=0.5, sharpe=1.5, data_days=120),
        "symbol_oos_df": _symbol_frame([0.2, 0.1, 0.05], trades=[0.5, 0.5, 0.5], data_days=120),
        "metadata": {"timeframe_diagnostics": [{"requested_data_days": 120, "realized_shared_days": 121}]},
    }
    sens_run = {
        "run_id": "sens",
        "run_root": "artifacts/runs/sens",
        "combo_df": _combo_frame(return_pct=0.08, trades=0.375, sharpe=1.1, data_days=120),
        "symbol_oos_df": _symbol_frame([0.1, 0.04, 0.01], trades=[0.375, 0.375, 0.375], data_days=120),
        "metadata": {"timeframe_diagnostics": [{"requested_data_days": 120, "realized_shared_days": 121}]},
    }

    payload = pilot_analysis.compare_pilot_runs(
        main_run,
        sens_run,
        min_combo_return=0.0,
        min_combo_trades=0.5,
        trade_gate_policy="window_aware",
        trade_gate_reference_days=180,
        trade_gate_min_ratio=0.75,
        top_n=5,
    )

    assert payload["summary"]["gate_passed_rows"] == 1
    assert payload["thresholds"]["trade_gate_policy"] == "window_aware"
    row = payload["top_gate_passed"][0]
    assert row["passes_trade_gate"] is True
    assert row["effective_trade_floor"] == 0.375


def test_compare_pilot_runs_window_aware_trade_gate_keeps_full_window_floor():
    main_run = {
        "run_id": "main",
        "run_root": "artifacts/runs/main",
        "combo_df": _combo_frame(return_pct=0.12, trades=0.5, sharpe=1.5, data_days=180),
        "symbol_oos_df": _symbol_frame([0.2, 0.1, 0.05], trades=[0.5, 0.5, 0.5], data_days=180),
        "metadata": {"timeframe_diagnostics": [{"requested_data_days": 180, "realized_shared_days": 127}]},
    }
    sens_run = {
        "run_id": "sens",
        "run_root": "artifacts/runs/sens",
        "combo_df": _combo_frame(return_pct=0.08, trades=0.375, sharpe=1.1, data_days=180),
        "symbol_oos_df": _symbol_frame([0.1, 0.04, 0.01], trades=[0.375, 0.375, 0.375], data_days=180),
        "metadata": {"timeframe_diagnostics": [{"requested_data_days": 180, "realized_shared_days": 127}]},
    }

    payload = pilot_analysis.compare_pilot_runs(
        main_run,
        sens_run,
        min_combo_return=0.0,
        min_combo_trades=0.5,
        trade_gate_policy="window_aware",
        trade_gate_reference_days=180,
        trade_gate_min_ratio=0.75,
        top_n=5,
    )

    assert payload["summary"]["stable_positive_rows"] == 1
    assert payload["summary"]["gate_passed_rows"] == 0
    row = payload["top_stable_positive"][0]
    assert row["passes_trade_gate"] is False
    assert row["effective_trade_floor"] == 0.5


def test_evaluate_promotion_verdict_promotes_full_window_gate_pass():
    analysis_payload = {
        "main_run": {"timeframe_diagnostics": [{"timeframe": "2h", "data_days": 180, "realized_shared_days": 127}]},
        "summary": {"stable_positive_rows": 30, "gate_passed_rows": 30},
    }
    promotion_policy = {
        "full_window_gate": {
            "policy_kind": "promotive",
            "timeframe": "2h",
            "data_days": 180,
            "trade_gate_policy": "flat",
            "min_combo_trades": 0.5,
        }
    }

    verdict = pilot_analysis.evaluate_promotion_verdict(analysis_payload, promotion_policy)

    assert verdict["matched_policy_name"] == "full_window_gate"
    assert verdict["verdict"] == "promote"
    assert verdict["reason"] == "full_window_gate_passed"


def test_evaluate_promotion_verdict_holds_supporting_window_pass():
    analysis_payload = {
        "main_run": {"timeframe_diagnostics": [{"timeframe": "2h", "data_days": 120, "realized_shared_days": 121}]},
        "summary": {"stable_positive_rows": 24, "gate_passed_rows": 24},
    }
    promotion_policy = {
        "short_window_gate": {
            "policy_kind": "supporting",
            "timeframe": "2h",
            "data_days": 120,
            "trade_gate_policy": "window_aware",
            "min_combo_trades": 0.5,
            "trade_gate_reference_days": 180,
            "trade_gate_min_ratio": 0.75,
        }
    }

    verdict = pilot_analysis.evaluate_promotion_verdict(analysis_payload, promotion_policy)

    assert verdict["matched_policy_name"] == "short_window_gate"
    assert verdict["verdict"] == "hold"
    assert verdict["reason"] == "short_window_gate_passed"


def test_evaluate_promotion_verdict_rejects_density_lane():
    analysis_payload = {
        "main_run": {"timeframe_diagnostics": [{"timeframe": "1h", "data_days": 180, "realized_shared_days": 181}]},
        "summary": {"stable_positive_rows": 0, "gate_passed_rows": 0},
    }
    promotion_policy = {
        "rejected_density_lane": {
            "policy_kind": "rejected",
            "timeframe": "1h",
            "data_days": 180,
            "reason": "awf263_density_follow_up_failed",
        }
    }

    verdict = pilot_analysis.evaluate_promotion_verdict(analysis_payload, promotion_policy)

    assert verdict["matched_policy_name"] == "rejected_density_lane"
    assert verdict["verdict"] == "no_go"
    assert verdict["reason"] == "awf263_density_follow_up_failed"


def test_compare_pilot_runs_marks_evidence_equivalent_superset_as_redundant():
    main_combo = pd.concat(
        [
            _combo_frame(return_pct=0.12, trades=1.0, sharpe=1.5, indicator_list="mfi,obv_roc,atr_ratio"),
            _combo_frame(return_pct=0.12, trades=1.0, sharpe=1.5, indicator_list="mfi,obv_roc,atr_ratio,macd_hist"),
        ],
        ignore_index=True,
    )
    sens_combo = pd.concat(
        [
            _combo_frame(return_pct=0.08, trades=0.75, sharpe=1.1, indicator_list="mfi,obv_roc,atr_ratio"),
            _combo_frame(return_pct=0.08, trades=0.75, sharpe=1.1, indicator_list="mfi,obv_roc,atr_ratio,macd_hist"),
        ],
        ignore_index=True,
    )
    main_symbols = pd.concat(
        [
            _symbol_frame([0.2, 0.1, 0.05], indicator_list="mfi,obv_roc,atr_ratio"),
            _symbol_frame([0.2, 0.1, 0.05], indicator_list="mfi,obv_roc,atr_ratio,macd_hist"),
        ],
        ignore_index=True,
    )
    sens_symbols = pd.concat(
        [
            _symbol_frame([0.1, 0.04, 0.01], trades=[1.0, 0.5, 0.5], indicator_list="mfi,obv_roc,atr_ratio"),
            _symbol_frame([0.1, 0.04, 0.01], trades=[1.0, 0.5, 0.5], indicator_list="mfi,obv_roc,atr_ratio,macd_hist"),
        ],
        ignore_index=True,
    )

    payload = pilot_analysis.compare_pilot_runs(
        {
            "run_id": "main",
            "run_root": "artifacts/runs/main",
            "combo_df": main_combo,
            "symbol_oos_df": main_symbols,
            "metadata": {},
        },
        {
            "run_id": "sens",
            "run_root": "artifacts/runs/sens",
            "combo_df": sens_combo,
            "symbol_oos_df": sens_symbols,
            "metadata": {},
        },
        min_combo_return=0.0,
        min_combo_trades=0.5,
        top_n=5,
    )

    assert payload["summary"]["gate_passed_rows"] == 2
    assert payload["summary"]["canonical_gate_passed_rows"] == 1
    assert payload["summary"]["redundant_gate_passed_rows"] == 1
    assert payload["canonical_gate_passed"][0]["indicator_list"] == "mfi,obv_roc,atr_ratio"
    assert payload["redundant_gate_passed"][0]["indicator_list"] == "mfi,obv_roc,atr_ratio,macd_hist"
    assert payload["redundant_gate_passed"][0]["is_canonical_family"] is False
    assert payload["redundant_gate_passed"][0]["canonical_indicator_list"] == "mfi,obv_roc,atr_ratio"
    assert payload["redundant_gate_passed"][0]["canonical_reason"] == "evidence_equivalent_superset"
    protocol_summary = payload["protocol_summary"]["canonical_gate_passed"]
    assert protocol_summary["row_count"] == 1
    assert protocol_summary["field_values"]["indicator_list"] == ["mfi,obv_roc,atr_ratio"]
    assert protocol_summary["field_values"]["tp_stop"] == [1.5]
    redundant_summary = payload["protocol_summary"]["redundant_gate_passed"]
    assert redundant_summary["row_count"] == 1
    assert redundant_summary["field_values"]["indicator_list"] == ["mfi,obv_roc,atr_ratio,macd_hist"]


def test_compare_pilot_runs_distinguishes_state_trigger_role_variants():
    main_combo = pd.DataFrame(
        [
            {
                "timeframe": "2h",
                "data_days": 180,
                "strategy_mode": "state_trigger_entry",
                "state_indicator_list": "obv_roc,keltner_pos",
                "trigger_indicator_list": "ad",
                "indicator_list": "obv_roc,keltner_pos,ad",
                "regime_name": "trend_any",
                "vol_mode": "any",
                "filter_name": "pair-a",
                "vol_lookback": None,
                "mom_lookback": 6,
                "trade_mom_lookback": 3,
                "tp_stop": 1.5,
                "sl_stop": 1.0,
                "max_hold": 4,
                "state_exit_policy": "state_reversal",
                "oos_avg_total_return_pct": 0.12,
                "oos_avg_total_trades": 1.0,
                "oos_sharpe_like": 1.2,
            },
            {
                "timeframe": "2h",
                "data_days": 180,
                "strategy_mode": "state_trigger_entry",
                "state_indicator_list": "obv_roc,keltner_pos,ad",
                "trigger_indicator_list": "ad",
                "indicator_list": "obv_roc,keltner_pos,ad",
                "regime_name": "trend_any",
                "vol_mode": "any",
                "filter_name": "pair-b",
                "vol_lookback": None,
                "mom_lookback": 6,
                "trade_mom_lookback": 3,
                "tp_stop": 1.5,
                "sl_stop": 1.0,
                "max_hold": 4,
                "state_exit_policy": "state_reversal",
                "oos_avg_total_return_pct": 0.04,
                "oos_avg_total_trades": 0.75,
                "oos_sharpe_like": 0.4,
            },
        ]
    )
    sens_combo = pd.DataFrame(
        [
            {
                "timeframe": "2h",
                "data_days": 180,
                "strategy_mode": "state_trigger_entry",
                "state_indicator_list": "obv_roc,keltner_pos",
                "trigger_indicator_list": "ad",
                "indicator_list": "obv_roc,keltner_pos,ad",
                "regime_name": "trend_any",
                "vol_mode": "any",
                "filter_name": "pair-a",
                "vol_lookback": None,
                "mom_lookback": 6,
                "trade_mom_lookback": 3,
                "tp_stop": 1.5,
                "sl_stop": 1.0,
                "max_hold": 4,
                "state_exit_policy": "state_reversal",
                "oos_avg_total_return_pct": 0.09,
                "oos_avg_total_trades": 0.75,
                "oos_sharpe_like": 0.9,
            },
            {
                "timeframe": "2h",
                "data_days": 180,
                "strategy_mode": "state_trigger_entry",
                "state_indicator_list": "obv_roc,keltner_pos,ad",
                "trigger_indicator_list": "ad",
                "indicator_list": "obv_roc,keltner_pos,ad",
                "regime_name": "trend_any",
                "vol_mode": "any",
                "filter_name": "pair-b",
                "vol_lookback": None,
                "mom_lookback": 6,
                "trade_mom_lookback": 3,
                "tp_stop": 1.5,
                "sl_stop": 1.0,
                "max_hold": 4,
                "state_exit_policy": "state_reversal",
                "oos_avg_total_return_pct": 0.03,
                "oos_avg_total_trades": 0.5,
                "oos_sharpe_like": 0.3,
            },
        ]
    )
    main_symbols = pd.DataFrame(
        [
            {
                "timeframe": "2h",
                "data_days": 180,
                "strategy_mode": "state_trigger_entry",
                "state_indicator_list": state_indicator_list,
                "trigger_indicator_list": trigger_indicator_list,
                "indicator_list": "obv_roc,keltner_pos,ad",
                "regime_name": "trend_any",
                "vol_mode": "any",
                "filter_name": filter_name,
                "vol_lookback": None,
                "mom_lookback": 6,
                "trade_mom_lookback": 3,
                "tp_stop": 1.5,
                "sl_stop": 1.0,
                "max_hold": 4,
                "state_exit_policy": "state_reversal",
                "symbol": symbol,
                "oos_avg_total_return_pct": ret,
                "oos_avg_total_trades": trade_count,
                "oos_positive_segment_ratio": 0.5,
                "oos_segments": 2.0,
            }
            for state_indicator_list, trigger_indicator_list, filter_name, symbol, ret, trade_count in [
                ("obv_roc,keltner_pos", "ad", "pair-a", "LTC/BTC", 0.2, 1.0),
                ("obv_roc,keltner_pos", "ad", "pair-a", "LINK/BTC", 0.1, 1.0),
                ("obv_roc,keltner_pos", "ad", "pair-a", "SOL/BTC", 0.05, 1.0),
                ("obv_roc,keltner_pos,ad", "ad", "pair-b", "LTC/BTC", 0.08, 0.75),
                ("obv_roc,keltner_pos,ad", "ad", "pair-b", "LINK/BTC", 0.04, 0.75),
                ("obv_roc,keltner_pos,ad", "ad", "pair-b", "SOL/BTC", 0.02, 0.75),
            ]
        ]
    )
    sens_symbols = pd.DataFrame(
        [
            {
                "timeframe": "2h",
                "data_days": 180,
                "strategy_mode": "state_trigger_entry",
                "state_indicator_list": state_indicator_list,
                "trigger_indicator_list": trigger_indicator_list,
                "indicator_list": "obv_roc,keltner_pos,ad",
                "regime_name": "trend_any",
                "vol_mode": "any",
                "filter_name": filter_name,
                "vol_lookback": None,
                "mom_lookback": 6,
                "trade_mom_lookback": 3,
                "tp_stop": 1.5,
                "sl_stop": 1.0,
                "max_hold": 4,
                "state_exit_policy": "state_reversal",
                "symbol": symbol,
                "oos_avg_total_return_pct": ret,
                "oos_avg_total_trades": trade_count,
                "oos_positive_segment_ratio": 0.5,
                "oos_segments": 2.0,
            }
            for state_indicator_list, trigger_indicator_list, filter_name, symbol, ret, trade_count in [
                ("obv_roc,keltner_pos", "ad", "pair-a", "LTC/BTC", 0.1, 0.75),
                ("obv_roc,keltner_pos", "ad", "pair-a", "LINK/BTC", 0.04, 0.75),
                ("obv_roc,keltner_pos", "ad", "pair-a", "SOL/BTC", 0.01, 0.75),
                ("obv_roc,keltner_pos,ad", "ad", "pair-b", "LTC/BTC", 0.05, 0.5),
                ("obv_roc,keltner_pos,ad", "ad", "pair-b", "LINK/BTC", 0.03, 0.5),
                ("obv_roc,keltner_pos,ad", "ad", "pair-b", "SOL/BTC", 0.01, 0.5),
            ]
        ]
    )

    payload = pilot_analysis.compare_pilot_runs(
        {
            "run_id": "main",
            "run_root": "artifacts/runs/main",
            "combo_df": main_combo,
            "symbol_oos_df": main_symbols,
            "metadata": {},
        },
        {
            "run_id": "sens",
            "run_root": "artifacts/runs/sens",
            "combo_df": sens_combo,
            "symbol_oos_df": sens_symbols,
            "metadata": {},
        },
        min_combo_return=0.0,
        min_combo_trades=0.5,
        top_n=5,
    )

    assert payload["summary"]["compared_combo_rows"] == 2
    assert payload["summary"]["gate_passed_rows"] == 2
    assert payload["identity_fields"][2:5] == ["strategy_mode", "state_indicator_list", "trigger_indicator_list"]
    state_rows = {
        (row["state_indicator_list"], row["trigger_indicator_list"]): row
        for row in payload["top_gate_passed"]
    }
    assert ("obv_roc,keltner_pos", "ad") in state_rows
    assert ("obv_roc,keltner_pos,ad", "ad") in state_rows


def test_compare_pilot_runs_min_avg_symbol_trades_rejects_low_density():
    """Rows with avg per-symbol trades below the floor fail the gate."""
    main_run = {
        "run_id": "main",
        "run_root": "artifacts/runs/main",
        "combo_df": _combo_frame(return_pct=0.12, trades=0.16, sharpe=1.0),
        "symbol_oos_df": _symbol_frame([0.2, 0.1, 0.05], trades=[0.2, 0.15, 0.13]),
        "metadata": {"timeframe_diagnostics": [{"realized_shared_days": 180}]},
    }
    sens_run = {
        "run_id": "sens",
        "run_root": "artifacts/runs/sens",
        "combo_df": _combo_frame(return_pct=0.08, trades=0.16, sharpe=0.9),
        "symbol_oos_df": _symbol_frame([0.1, 0.04, 0.01], trades=[0.2, 0.15, 0.13]),
        "metadata": {"timeframe_diagnostics": [{"realized_shared_days": 180}]},
    }

    # Without density floor → gate passed
    payload_no_floor = pilot_analysis.compare_pilot_runs(
        main_run, sens_run, min_avg_symbol_trades=0.0, top_n=5
    )
    assert payload_no_floor["summary"]["gate_passed_rows"] == 1

    # With density floor of 1.0 → gate rejected
    payload_with_floor = pilot_analysis.compare_pilot_runs(
        main_run, sens_run, min_avg_symbol_trades=1.0, top_n=5
    )
    assert payload_with_floor["summary"]["gate_passed_rows"] == 0
    row = payload_with_floor["top_stable_positive"][0]
    assert row["passes_symbol_trade_density_gate"] is False
    assert row["passes_overall_gate"] is False
    assert payload_with_floor["thresholds"]["min_avg_symbol_trades"] == 1.0


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


def test_build_replay_config_from_analysis_uses_canonical_protocol_ranges(tmp_path):
    config_path = tmp_path / "artifacts" / "base_config.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps(
            {
                "risk_mode": "atr_multiple",
                "pilot_fixed_indicator_params": True,
                "pilot_single_trend_mom": True,
                "capital_mode": "per_symbol",
            }
        ),
        encoding="utf-8",
    )
    analysis_payload = {
        "main_run": {"run_id": "main"},
        "protocol_summary": {
            "canonical_gate_passed": {
                "row_count": 2,
                "field_values": {
                    "indicator_list": ["mfi,obv_roc,atr_ratio"],
                    "regime_name": ["trend_high"],
                    "tp_stop": [1.0, 1.25],
                    "sl_stop": [0.75, 1.0],
                    "max_hold": [4],
                },
            }
        },
    }
    main_run = {
        "metadata": {
            "config_path": "artifacts/base_config.json",
            "trade_symbols": ["LTC/BTC", "LINK/BTC", "SOL/BTC", "AVAX/BTC"],
            "timeframes": [{"timeframe": "2h", "days": 180}],
            "wf_train_days": 45,
            "wf_test_days": 30,
            "wf_step_days": 30,
            "wf_valid_days": 0,
        }
    }

    replay_config = pilot_analysis.build_replay_config_from_analysis(
        analysis_payload,
        main_run,
        cwd=tmp_path,
    )

    assert replay_config["combo_sizes"] == [3]
    assert replay_config["indicator_subset"] == ["mfi", "obv_roc", "atr_ratio"]
    assert replay_config["regime_name_filter"] == ["trend_high"]
    assert replay_config["tp_atr_multipliers"] == [1.0, 1.25]
    assert replay_config["sl_atr_multipliers"] == [0.75, 1.0]
    assert replay_config["max_holds"] == [4]


def test_build_indicator_clue_map_prefers_supported_singles_and_pairs():
    main_combo = pd.concat(
        [
            _combo_frame(return_pct=0.12, trades=1.0, sharpe=1.5, indicator_list="mfi"),
            _combo_frame(return_pct=0.11, trades=0.8, sharpe=1.2, indicator_list="obv_roc"),
            _combo_frame(return_pct=0.02, trades=0.5, sharpe=0.5, indicator_list="cmf"),
            _combo_frame(return_pct=0.14, trades=1.0, sharpe=1.6, indicator_list="mfi,obv_roc"),
            _combo_frame(return_pct=0.03, trades=0.4, sharpe=0.3, indicator_list="mfi,cmf"),
        ],
        ignore_index=True,
    )
    sens_combo = pd.concat(
        [
            _combo_frame(return_pct=0.09, trades=0.75, sharpe=1.1, indicator_list="mfi"),
            _combo_frame(return_pct=0.08, trades=0.75, sharpe=1.0, indicator_list="obv_roc"),
            _combo_frame(return_pct=0.01, trades=0.5, sharpe=0.2, indicator_list="cmf"),
            _combo_frame(return_pct=0.1, trades=0.75, sharpe=1.2, indicator_list="mfi,obv_roc"),
            _combo_frame(return_pct=0.02, trades=0.4, sharpe=0.1, indicator_list="mfi,cmf"),
        ],
        ignore_index=True,
    )
    main_symbols = pd.concat(
        [
            _symbol_frame([0.2, 0.1, 0.05], indicator_list="mfi"),
            _symbol_frame([0.15, 0.08, 0.03], indicator_list="obv_roc"),
            _symbol_frame([0.03, 0.01, 0.0], indicator_list="cmf"),
            _symbol_frame([0.2, 0.12, 0.06], indicator_list="mfi,obv_roc"),
            _symbol_frame([0.05, -0.02, 0.01], indicator_list="mfi,cmf"),
        ],
        ignore_index=True,
    )
    sens_symbols = pd.concat(
        [
            _symbol_frame([0.1, 0.04, 0.01], trades=[0.75, 0.75, 0.75], indicator_list="mfi"),
            _symbol_frame([0.08, 0.03, 0.01], trades=[0.75, 0.75, 0.75], indicator_list="obv_roc"),
            _symbol_frame([0.02, 0.01, 0.0], trades=[0.5, 0.5, 0.5], indicator_list="cmf"),
            _symbol_frame([0.12, 0.05, 0.02], trades=[0.75, 0.75, 0.75], indicator_list="mfi,obv_roc"),
            _symbol_frame([0.04, -0.01, 0.01], trades=[0.4, 0.4, 0.4], indicator_list="mfi,cmf"),
        ],
        ignore_index=True,
    )

    payload = pilot_analysis.build_indicator_clue_map(
        {
            "run_id": "main",
            "run_root": "artifacts/runs/main",
            "combo_df": main_combo,
            "symbol_oos_df": main_symbols,
            "metadata": {"timeframe_diagnostics": [{"realized_shared_days": 180}]},
        },
        {
            "run_id": "sens",
            "run_root": "artifacts/runs/sens",
            "combo_df": sens_combo,
            "symbol_oos_df": sens_symbols,
            "metadata": {"timeframe_diagnostics": [{"realized_shared_days": 180}]},
        },
        min_combo_return=0.0,
        min_combo_trades=0.5,
        top_k=2,
    )

    assert payload["summary"]["compared_combo_rows"] == 5
    assert payload["summary"]["stable_positive_rows"] == 5
    assert payload["summary"]["gate_passed_rows"] == 4
    assert payload["selected_top_indicators"] == ["mfi", "obv_roc"]
    indicator_rows = {row["indicator"]: row for row in payload["indicator_rows"]}
    assert indicator_rows["mfi"]["single_gate_passed_rows"] == 1
    assert indicator_rows["mfi"]["pair_gate_passed_rows"] == 1
    assert indicator_rows["mfi"]["partner_indicators"] == ["cmf", "obv_roc"]
    assert indicator_rows["obv_roc"]["pair_gate_passed_rows"] == 1
    assert indicator_rows["cmf"]["gate_passed_rows"] == 1
