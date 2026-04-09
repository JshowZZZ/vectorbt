import json
from pathlib import Path

import pandas as pd
import pytest

from autowfo import cli
from autowfo import artifact_contract as ac


def test_cli_run_writes_runtime_config_and_invokes_sweep(tmp_path, monkeypatch):
    cfg_path = tmp_path / "experiment.json"
    cfg_path.write_text(
        json.dumps(
            {
                "search_mode": "combo",
                "timeframes": [{"timeframe": "1h", "days": 2}],
                "combo_sizes": [1],
            }
        ),
        encoding="utf-8",
    )

    calls = []

    def _fake_run(cmd, cwd, env, check):
        calls.append({"cmd": cmd, "cwd": cwd, "env": env, "check": check})
        return 0

    monkeypatch.setattr(cli.subprocess, "run", _fake_run)
    code = cli.main(
        [
            "run",
            "--config",
            str(cfg_path),
            "--mode",
            "refine",
            "--workers",
            "3",
            "--cwd",
            str(tmp_path),
        ]
    )
    assert code == 0
    run_id = calls[0]["env"]["VBT_RUN_ID"]
    runtime_cfg = tmp_path / "artifacts" / "runs" / run_id / "runtime" / "sweep_config.json"
    payload = json.loads(runtime_cfg.read_text(encoding="utf-8"))
    assert payload["search_mode"] == "refine"
    assert payload["max_workers"] == 3
    assert calls[0]["cmd"] == [cli.sys.executable, "-m", "autowfo.run_btc_regime_sweep"]
    assert calls[0]["env"]["VBT_SWEEP_MODE"] == "refine"
    assert calls[0]["env"]["VBT_RUNTIME_CONFIG_PATH"] == str(runtime_cfg)


def test_cli_baseline_writes_runtime_config_and_invokes_baseline(tmp_path, monkeypatch):
    cfg_path = tmp_path / "experiment.json"
    cfg_path.write_text(
        json.dumps({"timeframes": [{"timeframe": "1h", "days": 2}], "combo_sizes": [1]}),
        encoding="utf-8",
    )
    calls = []

    def _fake_run(cmd, cwd, env, check):
        calls.append({"cmd": cmd, "cwd": cwd, "env": env, "check": check})
        return 0

    monkeypatch.setattr(cli.subprocess, "run", _fake_run)
    code = cli.main(
        [
            "baseline",
            "--config",
            str(cfg_path),
            "--workers",
            "2",
            "--cwd",
            str(tmp_path),
        ]
    )
    assert code == 0
    runtime_cfg = Path(calls[0]["env"]["VBT_RUNTIME_CONFIG_PATH"])
    payload = json.loads(runtime_cfg.read_text(encoding="utf-8"))
    assert payload["max_workers"] == 2
    assert calls[0]["cmd"] == [cli.sys.executable, "-m", "autowfo.run_autowfo_baseline"]
    assert runtime_cfg.parent == tmp_path / "artifacts" / "baseline_runtime"


def test_cli_batch_runs_jobs_and_writes_state(tmp_path, monkeypatch):
    cfg_a = tmp_path / "cfg_a.json"
    cfg_b = tmp_path / "cfg_b.json"
    cfg_a.write_text(json.dumps({"combo_sizes": [1]}), encoding="utf-8")
    cfg_b.write_text(json.dumps({"combo_sizes": [2]}), encoding="utf-8")

    plan_path = tmp_path / "batch_plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "jobs": [
                    {
                        "name": "combo-a",
                        "workflow": "run",
                        "mode": "combo",
                        "workers": 2,
                        "config": "cfg_a.json",
                    },
                    {
                        "name": "baseline-b",
                        "workflow": "baseline",
                        "workers": 1,
                        "config": "cfg_b.json",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    calls = []
    rebuild_calls = []

    def _fake_run_workflow(cwd, config_path, workflow, mode, workers):
        calls.append(
            {
                "cwd": cwd,
                "config_path": config_path,
                "workflow": workflow,
                "mode": mode,
                "workers": workers,
            }
        )

    def _fake_rebuild_shared_views(artifacts_dir):
        rebuild_calls.append(str(artifacts_dir))
        return {"trusted_runs": 2, "leaderboard_rows": 2}

    monkeypatch.setattr(cli, "_run_workflow", _fake_run_workflow)
    monkeypatch.setattr(cli, "_rebuild_shared_views", _fake_rebuild_shared_views)

    code = cli.main(
        [
            "batch",
            "--plan",
            str(plan_path),
            "--cwd",
            str(tmp_path),
            "--state",
            "artifacts/batch_state.json",
            "--workers",
            "7",
            "--min-free-gb",
            "0",
        ]
    )
    assert code == 0
    assert [call["workflow"] for call in calls] == ["run", "baseline"]
    assert all(call["workers"] == 7 for call in calls)
    assert rebuild_calls == [str(tmp_path / "artifacts")]

    state_path = tmp_path / "artifacts" / "batch_state.json"
    state_payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert len(state_payload["seen_keys"]) == 2
    assert [item["status"] for item in state_payload["history"]] == [
        "running",
        "done",
        "running",
        "done",
    ]


def test_cli_batch_second_run_skips_seen_jobs(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({"combo_sizes": [1]}), encoding="utf-8")
    plan_path = tmp_path / "batch_plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "jobs": [
                    {"name": "combo", "workflow": "run", "mode": "refine", "config": "cfg.json"},
                ]
            }
        ),
        encoding="utf-8",
    )

    calls = []

    def _fake_run_workflow(cwd, config_path, workflow, mode, workers):
        calls.append((str(cwd), str(config_path), workflow, mode, workers))

    monkeypatch.setattr(cli, "_run_workflow", _fake_run_workflow)

    argv = [
        "batch",
        "--plan",
        str(plan_path),
        "--cwd",
        str(tmp_path),
        "--state",
        "artifacts/batch_state.json",
        "--min-free-gb",
        "0",
    ]
    assert cli.main(argv) == 0
    assert cli.main(argv) == 0
    assert len(calls) == 1

    state_payload = json.loads((tmp_path / "artifacts" / "batch_state.json").read_text(encoding="utf-8"))
    assert len(state_payload["seen_keys"]) == 1
    assert any(item["status"] == "skipped_seen_key" for item in state_payload["history"])


def test_cli_batch_preflight_missing_config_fails(tmp_path):
    plan_path = tmp_path / "batch_plan.json"
    plan_path.write_text(
        json.dumps({"jobs": [{"name": "missing", "workflow": "baseline", "config": "missing.json"}]}),
        encoding="utf-8",
    )

    with pytest.raises(FileNotFoundError, match="missing config files"):
        cli.main(
            [
                "batch",
                "--plan",
                str(plan_path),
                "--cwd",
                str(tmp_path),
                "--min-free-gb",
                "0",
            ]
        )


def test_cli_pilot_analyze_writes_machine_readable_report(tmp_path):
    def _combo_frame(return_pct, trades):
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
                    "oos_sharpe_like": 1.0,
                }
            ]
        )

    def _symbol_frame(values):
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
                    "symbol": symbol,
                    "oos_avg_total_return_pct": ret,
                    "oos_avg_total_trades": trades,
                    "oos_positive_segment_ratio": 0.5 if ret > 0 else 0.0,
                    "oos_segments": 2.0,
                }
                for symbol, ret, trades in values
            ]
        )

    artifacts = tmp_path / "artifacts" / "runs"
    main_root = artifacts / "run-main"
    sens_root = artifacts / "run-sens"
    for root in [main_root, sens_root]:
        (root / "results").mkdir(parents=True)
        (root / "metadata").mkdir(parents=True)
    _combo_frame(0.12, 1.0).to_csv(main_root / "results" / "param_sweep_combo_summary.csv", index=False)
    _combo_frame(0.08, 0.5).to_csv(sens_root / "results" / "param_sweep_combo_summary.csv", index=False)
    _symbol_frame(
        [("LTC/BTC", 0.2, 1.0), ("LINK/BTC", 0.1, 1.0), ("SOL/BTC", 0.05, 1.0)]
    ).to_csv(main_root / "results" / "param_sweep_symbol_oos_summary.csv", index=False)
    _symbol_frame(
        [("LTC/BTC", 0.1, 0.5), ("LINK/BTC", 0.04, 0.5), ("SOL/BTC", 0.01, 0.5)]
    ).to_csv(sens_root / "results" / "param_sweep_symbol_oos_summary.csv", index=False)
    (main_root / "metadata" / "run_metadata_run-main.json").write_text(
        json.dumps({"timeframe_diagnostics": [{"realized_shared_days": 125}]}),
        encoding="utf-8",
    )
    (sens_root / "metadata" / "run_metadata_run-sens.json").write_text(
        json.dumps({"timeframe_diagnostics": [{"realized_shared_days": 125}]}),
        encoding="utf-8",
    )

    out_json = tmp_path / "artifacts" / "pilot_report.json"
    code = cli.main(
        [
            "pilot-analyze",
            "--main-run",
            "run-main",
            "--sensitivity-run",
            "run-sens",
            "--artifacts-dir",
            "artifacts",
            "--out-json",
            str(out_json.relative_to(tmp_path)),
            "--min-combo-trades",
            "0.5",
            "--cwd",
            str(tmp_path),
        ]
    )
    assert code == 0
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["summary"]["compared_combo_rows"] == 1
    assert payload["summary"]["gate_passed_rows"] == 1
    assert payload["top_gate_passed"][0]["indicator_list"] == "mfi,obv_roc"


def test_cli_pilot_export_config_writes_replay_config(tmp_path):
    artifacts_dir = tmp_path / "artifacts"
    run_root = artifacts_dir / "runs" / "20260410_010000"
    (run_root / "results").mkdir(parents=True)
    (run_root / "metadata").mkdir(parents=True)
    base_config = artifacts_dir / "base_config.json"
    base_config.write_text(
        json.dumps(
            {
                "risk_mode": "atr_multiple",
                "pilot_fixed_indicator_params": True,
                "pilot_single_trend_mom": True,
            }
        ),
        encoding="utf-8",
    )
    pd.DataFrame(
        [
            {
                "timeframe": "2h",
                "data_days": 180,
                "indicator_list": "mfi,obv_roc,atr_ratio",
                "regime_name": "trend_high",
                "vol_mode": "high",
                "filter_name": "none",
                "vol_lookback": 24,
                "mom_lookback": 6,
                "trade_mom_lookback": 3,
                "tp_stop": 1.25,
                "sl_stop": 0.75,
                "max_hold": 4,
                "oos_avg_total_return_pct": 0.1,
                "oos_avg_total_trades": 0.5,
                "oos_sharpe_like": 1.0,
            }
        ]
    ).to_csv(run_root / "results" / "param_sweep_combo_summary.csv", index=False)
    pd.DataFrame(
        [
            {
                "timeframe": "2h",
                "data_days": 180,
                "indicator_list": "mfi,obv_roc,atr_ratio",
                "regime_name": "trend_high",
                "vol_mode": "high",
                "filter_name": "none",
                "vol_lookback": 24,
                "mom_lookback": 6,
                "trade_mom_lookback": 3,
                "tp_stop": 1.25,
                "sl_stop": 0.75,
                "max_hold": 4,
                "symbol": "LTC/BTC",
                "oos_avg_total_return_pct": 0.1,
                "oos_avg_total_trades": 0.5,
                "oos_positive_segment_ratio": 0.5,
                "oos_segments": 2.0,
            }
        ]
    ).to_csv(run_root / "results" / "param_sweep_symbol_oos_summary.csv", index=False)
    (run_root / "metadata" / "run_metadata_20260410_010000.json").write_text(
        json.dumps(
            {
                "config_path": "artifacts/base_config.json",
                "trade_symbols": ["LTC/BTC", "LINK/BTC", "SOL/BTC", "AVAX/BTC"],
                "timeframes": [{"timeframe": "2h", "days": 180}],
                "wf_train_days": 45,
                "wf_test_days": 30,
                "wf_step_days": 30,
                "wf_valid_days": 0,
            }
        ),
        encoding="utf-8",
    )
    analysis_path = artifacts_dir / "pilot_analysis.json"
    analysis_path.write_text(
        json.dumps(
            {
                "main_run": {"run_id": "20260410_010000"},
                "protocol_summary": {
                    "canonical_gate_passed": {
                        "row_count": 1,
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
        ),
        encoding="utf-8",
    )

    out_config = artifacts_dir / "replay_config.json"
    code = cli.main(
        [
            "pilot-export-config",
            "--analysis-json",
            str(analysis_path),
            "--artifacts-dir",
            "artifacts",
            "--out-config",
            str(out_config.relative_to(tmp_path)),
            "--cwd",
            str(tmp_path),
        ]
    )
    assert code == 0
    payload = json.loads(out_config.read_text(encoding="utf-8"))
    assert payload["indicator_subset"] == ["mfi", "obv_roc", "atr_ratio"]
    assert payload["combo_sizes"] == [3]
    assert payload["regime_name_filter"] == ["trend_high"]
    assert payload["tp_atr_multipliers"] == [1.0, 1.25]
    assert payload["sl_atr_multipliers"] == [0.75, 1.0]
    assert payload["max_holds"] == [4]


def test_cli_batch_continue_on_error_runs_remaining_jobs(tmp_path, monkeypatch):
    good_cfg = tmp_path / "good.json"
    bad_cfg = tmp_path / "bad.json"
    good_cfg.write_text(json.dumps({"combo_sizes": [1]}), encoding="utf-8")
    bad_cfg.write_text(json.dumps({"combo_sizes": [2]}), encoding="utf-8")

    plan_path = tmp_path / "batch_plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "jobs": [
                    {"name": "bad", "workflow": "run", "mode": "combo", "config": "bad.json"},
                    {"name": "good", "workflow": "baseline", "config": "good.json"},
                ]
            }
        ),
        encoding="utf-8",
    )

    calls = []
    rebuild_calls = []

    def _fake_run_workflow(cwd, config_path, workflow, mode, workers):
        calls.append((str(config_path), workflow))
        if config_path.name == "bad.json":
            raise RuntimeError("boom")

    def _fake_rebuild_shared_views(artifacts_dir):
        rebuild_calls.append(str(artifacts_dir))
        return {"trusted_runs": 1, "leaderboard_rows": 1}

    monkeypatch.setattr(cli, "_run_workflow", _fake_run_workflow)
    monkeypatch.setattr(cli, "_rebuild_shared_views", _fake_rebuild_shared_views)

    code = cli.main(
        [
            "batch",
            "--plan",
            str(plan_path),
            "--cwd",
            str(tmp_path),
            "--state",
            "artifacts/batch_state.json",
            "--min-free-gb",
            "0",
            "--continue-on-error",
        ]
    )
    assert code == 0
    assert calls == [
        (str(bad_cfg), "run"),
        (str(good_cfg), "baseline"),
    ]
    assert rebuild_calls == [str(tmp_path / "artifacts")]

    state_payload = json.loads((tmp_path / "artifacts" / "batch_state.json").read_text(encoding="utf-8"))
    assert len(state_payload["seen_keys"]) == 1
    statuses = [item["status"] for item in state_payload["history"]]
    assert "failed" in statuses
    assert "done" in statuses


def test_cli_plan_generates_batch_plan_from_untested_pairs(tmp_path):
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    registry_path = artifacts_dir / "run_registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "runs": [
                    {
                        "run_id": "r1",
                        "timeframes": [
                            {"timeframe": "1h", "days": 120},
                            {"timeframe": "4h", "days": 240},
                        ],
                    }
                ],
                "coverage": {
                    "untested_pairs": [
                        {"timeframe": "1h", "symbol": "ETH/USDT"},
                        {"timeframe": "4h", "symbol": "BNB/USDT"},
                        {"timeframe": "1h", "symbol": "SOL/USDT"},
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    template_path = artifacts_dir / "sweep_config.json"
    template_path.write_text(
        json.dumps(
            {
                "search_mode": "combo",
                "timeframes": [{"timeframe": "15m", "days": 60}],
                "trade_symbols": ["ETH/USDT", "BNB/USDT"],
                "combo_sizes": [2, 3],
            }
        ),
        encoding="utf-8",
    )

    out_plan = artifacts_dir / "batch_plan.auto.json"
    out_cfg_dir = artifacts_dir / "planned_configs"
    code = cli.main(
        [
            "plan",
            "--registry",
            str(registry_path),
            "--template-config",
            str(template_path),
            "--out-plan",
            str(out_plan),
            "--out-config-dir",
            str(out_cfg_dir),
            "--max-jobs",
            "2",
            "--workflow",
            "run",
            "--mode",
            "combo",
            "--workers",
            "3",
            "--cwd",
            str(tmp_path),
        ]
    )
    assert code == 0
    assert out_plan.exists()

    plan_payload = json.loads(out_plan.read_text(encoding="utf-8"))
    assert plan_payload["job_count"] == 2
    assert len(plan_payload["jobs"]) == 2
    assert all(job["workflow"] == "run" for job in plan_payload["jobs"])
    assert all(job["mode"] == "combo" for job in plan_payload["jobs"])
    assert all(job["workers"] == 3 for job in plan_payload["jobs"])

    for job in plan_payload["jobs"]:
        cfg_path = Path(job["config"])
        assert cfg_path.exists()
        payload = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert len(payload["timeframes"]) == 1
        assert len(payload["trade_symbols"]) == 1


def test_cli_plan_generates_empty_jobs_when_no_gaps(tmp_path):
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    registry_path = artifacts_dir / "run_registry.json"
    registry_path.write_text(json.dumps({"coverage": {"untested_pairs": []}}), encoding="utf-8")
    template_path = artifacts_dir / "sweep_config.json"
    template_path.write_text(
        json.dumps({"timeframes": [{"timeframe": "1h", "days": 60}], "trade_symbols": ["ETH/USDT"]}),
        encoding="utf-8",
    )

    out_plan = artifacts_dir / "batch_plan.auto.json"
    code = cli.main(
        [
            "plan",
            "--registry",
            str(registry_path),
            "--template-config",
            str(template_path),
            "--out-plan",
            str(out_plan),
            "--cwd",
            str(tmp_path),
        ]
    )
    assert code == 0
    payload = json.loads(out_plan.read_text(encoding="utf-8"))
    assert payload["job_count"] == 0
    assert payload["jobs"] == []


def test_cli_plan_target_timeframes_surfaces_unseen_gaps(tmp_path):
    """--target-timeframes/--target-symbols detect gaps for never-run dimensions."""
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # Registry has only 2h?ETH and 4h?ETH as tested.  1h never appeared.
    registry_path = artifacts_dir / "run_registry.json"
    registry_path.write_text(
        json.dumps({
            "runs": [
                {"timeframes": [{"timeframe": "2h", "days": 120}], "trade_symbols": ["ETH/USDT"]},
                {"timeframes": [{"timeframe": "4h", "days": 180}], "trade_symbols": ["ETH/USDT"]},
            ],
            "coverage": {
                "tested_pairs": [
                    {"timeframe": "2h", "symbol": "ETH/USDT"},
                    {"timeframe": "4h", "symbol": "ETH/USDT"},
                ],
                "untested_pairs": [],
            },
        }),
        encoding="utf-8",
    )

    template_path = artifacts_dir / "sweep_config.json"
    template_path.write_text(
        json.dumps({
            "search_mode": "combo",
            "timeframes": [{"timeframe": "4h", "days": 180}],
            "trade_symbols": ["ETH/USDT"],
            "combo_sizes": [2],
        }),
        encoding="utf-8",
    )

    out_plan = artifacts_dir / "batch_plan.auto.json"
    out_cfg_dir = artifacts_dir / "planned_configs"
    code = cli.main([
        "plan",
        "--registry", str(registry_path),
        "--template-config", str(template_path),
        "--out-plan", str(out_plan),
        "--out-config-dir", str(out_cfg_dir),
        "--workflow", "run",
        "--mode", "combo",
        "--target-timeframes", "1h,2h,4h",
        "--target-symbols", "ETH/USDT,BNB/USDT,SOL/USDT",
        "--timeframe-days", "1h:90,2h:120,4h:180",
        "--cwd", str(tmp_path),
    ])
    assert code == 0

    plan_payload = json.loads(out_plan.read_text(encoding="utf-8"))
    # 9 total pairs - 2 tested = 7 gaps
    assert plan_payload["job_count"] == 7
    assert len(plan_payload["jobs"]) == 7

    # Verify all gap jobs reference correct single-pair configs
    generated_pairs = set()
    for job in plan_payload["jobs"]:
        cfg_path = Path(job["config"])
        assert cfg_path.exists()
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert len(cfg["timeframes"]) == 1
        assert len(cfg["trade_symbols"]) == 1
        tf = cfg["timeframes"][0]["timeframe"]
        sym = cfg["trade_symbols"][0]
        generated_pairs.add((tf, sym))

    # Already-tested pairs should NOT appear
    assert ("2h", "ETH/USDT") not in generated_pairs
    assert ("4h", "ETH/USDT") not in generated_pairs
    # 1h pairs should be present
    assert ("1h", "ETH/USDT") in generated_pairs
    assert ("1h", "BNB/USDT") in generated_pairs
    assert ("1h", "SOL/USDT") in generated_pairs


def test_cli_plan_timeframe_days_override(tmp_path):
    """--timeframe-days injects days values for new timeframes."""
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    registry_path = artifacts_dir / "run_registry.json"
    registry_path.write_text(
        json.dumps({
            "runs": [],
            "coverage": {"tested_pairs": [], "untested_pairs": []},
        }),
        encoding="utf-8",
    )

    template_path = artifacts_dir / "sweep_config.json"
    template_path.write_text(
        json.dumps({
            "search_mode": "combo",
            "timeframes": [{"timeframe": "4h", "days": 180}],
            "trade_symbols": ["ETH/USDT"],
        }),
        encoding="utf-8",
    )

    out_plan = artifacts_dir / "batch_plan.auto.json"
    out_cfg_dir = artifacts_dir / "planned_configs"
    code = cli.main([
        "plan",
        "--registry", str(registry_path),
        "--template-config", str(template_path),
        "--out-plan", str(out_plan),
        "--out-config-dir", str(out_cfg_dir),
        "--target-timeframes", "1h",
        "--target-symbols", "ETH/USDT",
        "--timeframe-days", "1h:90",
        "--cwd", str(tmp_path),
    ])
    assert code == 0

    plan_payload = json.loads(out_plan.read_text(encoding="utf-8"))
    assert plan_payload["job_count"] == 1
    cfg_path = Path(plan_payload["jobs"][0]["config"])
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert cfg["timeframes"][0]["timeframe"] == "1h"
    assert cfg["timeframes"][0]["days"] == 90


def test_cli_plan_target_requires_both_dimensions(tmp_path):
    """Providing only one of --target-timeframes/--target-symbols raises."""
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    registry_path = artifacts_dir / "run_registry.json"
    registry_path.write_text(json.dumps({"runs": [], "coverage": {}}), encoding="utf-8")
    template_path = artifacts_dir / "sweep_config.json"
    template_path.write_text(json.dumps({"timeframes": [], "trade_symbols": []}), encoding="utf-8")

    with pytest.raises(ValueError, match="both be provided"):
        cli.main([
            "plan",
            "--registry", str(registry_path),
            "--template-config", str(template_path),
            "--target-timeframes", "1h,2h",
            "--cwd", str(tmp_path),
        ])


def test_cli_report_generates_cross_run_outputs(tmp_path):
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    registry_path = artifacts_dir / "run_registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "runs": [
                    {
                        "run_id": "r1",
                        "timestamp_utc": "2026-02-10T01:00:00Z",
                        "search_mode": "combo",
                        "timeframes": [{"timeframe": "1h", "days": 60}],
                        "trade_symbols": ["ETH/USDT"],
                        "oos_avg_total_return_pct": 1.1,
                        "avg_total_return_pct": 0.8,
                    }
                ],
                "coverage": {
                    "tested_pairs": [{"timeframe": "1h", "symbol": "ETH/USDT"}],
                    "untested_pairs": [],
                },
            }
        ),
        encoding="utf-8",
    )
    run_dir = artifacts_dir / "runs" / "run_a" / "refine"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "param_sweep_top10_r1.csv").write_text(
        "indicator_list,regime_name,vol_mode,oos_avg_total_return_pct\n"
        "rsi,trend,normal,1.1\n",
        encoding="utf-8",
    )

    out_html = artifacts_dir / "cross_run_report.html"
    out_json = artifacts_dir / "cross_run_report.json"
    code = cli.main(
        [
            "report",
            "--registry",
            str(registry_path),
            "--artifacts-dir",
            str(artifacts_dir),
            "--out-html",
            str(out_html),
            "--out-json",
            str(out_json),
            "--cwd",
            str(tmp_path),
        ]
    )
    assert code == 0
    assert out_html.exists()
    assert out_json.exists()
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["summary"]["total_runs"] == 1


def test_cli_repro_generates_reproducibility_report(tmp_path):
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    reference_top = artifacts_dir / "top_ref.csv"
    candidate_top = artifacts_dir / "top_new.csv"
    reference_top.write_text(
        "combo_id,oos_avg_total_return_pct,oos_sharpe_like\n"
        "A,5.0,1.2\n"
        "B,4.0,1.1\n",
        encoding="utf-8",
    )
    candidate_top.write_text(
        "combo_id,oos_avg_total_return_pct,oos_sharpe_like\n"
        "A,5.0,1.2\n"
        "B,4.0,1.1\n",
        encoding="utf-8",
    )
    out_json = artifacts_dir / "repro.json"

    code = cli.main(
        [
            "repro",
            "--reference-top",
            str(reference_top),
            "--candidate-top",
            str(candidate_top),
            "--out-json",
            str(out_json),
            "--top-n",
            "2",
            "--identity-fields",
            "combo_id",
            "--metric-fields",
            "oos_avg_total_return_pct,oos_sharpe_like",
            "--cwd",
            str(tmp_path),
        ]
    )

    assert code == 0
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["stable"] is True
    assert payload["overlap_rows"] == 2
    assert payload["identity_fields"] == ["combo_id"]


def test_cli_repro_missing_reference_fails(tmp_path):
    missing_ref = tmp_path / "missing.csv"
    candidate_top = tmp_path / "candidate.csv"
    candidate_top.write_text("combo_id,oos_avg_total_return_pct\nA,5.0\n", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="reference top csv not found"):
        cli.main(
            [
                "repro",
                "--reference-top",
                str(missing_ref),
                "--candidate-top",
                str(candidate_top),
                "--cwd",
                str(tmp_path),
            ]
        )


def test_cli_gate_c_runs_dual_workflow_and_writes_report(tmp_path, monkeypatch):
    cfg_path = tmp_path / "experiment.json"
    cfg_path.write_text(
        json.dumps(
            {
                "search_mode": "combo",
                "combo_seed": 42,
                "timeframes": [{"timeframe": "4h", "days": 10}],
                "combo_sizes": [1],
            }
        ),
        encoding="utf-8",
    )
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    contract = ac.load_artifact_contract()
    call_index = {"value": 0}

    def _fake_run_workflow(cwd, config_path, workflow, mode, workers):
        call_index["value"] += 1
        idx = call_index["value"]
        run_id = f"20260213_13000{idx}"
        run_dir = cwd / "artifacts"
        run_dir.mkdir(parents=True, exist_ok=True)

        metadata = {field: "ok" for field in contract["run_metadata_fields"]}
        metadata["run_id"] = run_id
        metadata["combo_seed"] = 42
        metadata["timeframes"] = [{"timeframe": "4h", "days": 10}]
        metadata["trade_symbols"] = ["ETH/USDT"]
        metadata["init_cash_usdt"] = 1000.0
        (run_dir / "run_metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

        for filename in contract["required_files"]:
            path = run_dir / filename
            if filename in {"param_sweep_combo_summary.csv", "param_sweep_symbol_summary.csv", "leaderboard.csv"}:
                path.write_text("config_sha256,data_fingerprint\nabc,def\n", encoding="utf-8")
            elif filename == "run_metadata.json":
                continue
            else:
                path.write_text("ok", encoding="utf-8")

        top_csv = run_dir / f"param_sweep_top10_{run_id}.csv"
        top_csv.write_text(
            "combo_id,oos_avg_total_return_pct,oos_sharpe_like\n"
            "A,5.0,1.2\n"
            "B,4.0,1.1\n",
            encoding="utf-8",
        )

    monkeypatch.setattr(cli, "_run_workflow", _fake_run_workflow)

    out_json = tmp_path / "artifacts" / "reproducibility" / "gate_c_report.json"
    code = cli.main(
        [
            "gate-c",
            "--config",
            str(cfg_path),
            "--workflow",
            "run",
            "--mode",
            "combo",
            "--target-mode",
            "combo",
            "--out-json",
            str(out_json),
            "--top-n",
            "2",
            "--identity-fields",
            "combo_id",
            "--metric-fields",
            "oos_avg_total_return_pct,oos_sharpe_like",
            "--cwd",
            str(tmp_path),
        ]
    )

    assert code == 0
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["schema_valid"] is True
    assert payload["reproducibility"]["stable"] is True
    assert payload["gate_c_passed"] is True
    assert [entry["run_label"] for entry in payload["runs"]] == ["", ""]
    assert [entry["run_id"] for entry in payload["runs"]] == ["20260213_130001", "20260213_130002"]


def test_cli_gate_c_rejects_mode_override_for_baseline(tmp_path):
    cfg_path = tmp_path / "experiment.json"
    cfg_path.write_text(json.dumps({"search_mode": "combo"}), encoding="utf-8")

    with pytest.raises(ValueError, match="mode override is only valid for workflow=run"):
        cli.main(
            [
                "gate-c",
                "--config",
                str(cfg_path),
                "--workflow",
                "baseline",
                "--mode",
                "combo",
                "--cwd",
                str(tmp_path),
            ]
        )


# -- _compute_coverage_gaps unit tests --------------------------------------

def test_compute_coverage_gaps_full_cartesian_minus_tested():
    """Gaps = target cartesian minus tested."""
    registry_payload = {
        "coverage": {
            "tested_pairs": [
                {"timeframe": "2h", "symbol": "ETH/USDT"},
                {"timeframe": "4h", "symbol": "ETH/USDT"},
                {"timeframe": "4h", "symbol": "BNB/USDT"},
            ],
        }
    }
    gaps = cli._compute_coverage_gaps(
        registry_payload,
        target_timeframes=["1h", "2h", "4h"],
        target_symbols=["ETH/USDT", "BNB/USDT"],
    )
    gap_keys = {(g["timeframe"], g["symbol"]) for g in gaps}
    # 6 total - 3 tested = 3 gaps
    assert len(gaps) == 3
    assert ("1h", "ETH/USDT") in gap_keys
    assert ("1h", "BNB/USDT") in gap_keys
    assert ("2h", "BNB/USDT") in gap_keys


def test_compute_coverage_gaps_empty_registry():
    gaps = cli._compute_coverage_gaps(
        {"coverage": {}},
        target_timeframes=["1h", "2h"],
        target_symbols=["ETH/USDT"],
    )
    assert len(gaps) == 2


def test_compute_coverage_gaps_sorted_output():
    gaps = cli._compute_coverage_gaps(
        {"coverage": {"tested_pairs": []}},
        target_timeframes=["4h", "1h"],
        target_symbols=["SOL/USDT", "BNB/USDT"],
    )
    # Should be sorted by timeframe then symbol
    assert gaps[0] == {"timeframe": "1h", "symbol": "BNB/USDT"}
    assert gaps[1] == {"timeframe": "1h", "symbol": "SOL/USDT"}
    assert gaps[2] == {"timeframe": "4h", "symbol": "BNB/USDT"}
    assert gaps[3] == {"timeframe": "4h", "symbol": "SOL/USDT"}


# ---------------------------------------------------------------------------
#  AWF-023: Parallel batch execution tests
# ---------------------------------------------------------------------------


def _make_batch_plan(tmp_path, jobs):
    """Helper: write a batch plan JSON and per-job config stubs."""
    for job in jobs:
        cfg = tmp_path / job["config"]
        if not cfg.exists():
            cfg.write_text(json.dumps({"combo_sizes": [1]}), encoding="utf-8")
    plan_path = tmp_path / "batch_plan.json"
    plan_path.write_text(json.dumps({"jobs": jobs}), encoding="utf-8")
    return plan_path


def test_cli_batch_parallel_runs_all_jobs(tmp_path, monkeypatch):
    """--parallel-jobs 2 should run all jobs and write state."""
    plan_path = _make_batch_plan(
        tmp_path,
        [
            {"name": "a", "workflow": "run", "mode": "combo", "config": "a.json"},
            {"name": "b", "workflow": "baseline", "config": "b.json"},
            {"name": "c", "workflow": "run", "mode": "refine", "config": "c.json"},
        ],
    )
    calls = []

    def _fake(cwd, config_path, workflow, mode, workers):
        calls.append(workflow)

    monkeypatch.setattr(cli, "_run_workflow", _fake)

    code = cli.main([
        "batch", "--plan", str(plan_path),
        "--cwd", str(tmp_path),
        "--min-free-gb", "0",
        "--parallel-jobs", "2",
    ])
    assert code == 0
    assert sorted(calls) == sorted(["run", "baseline", "run"])

    state = json.loads(
        (tmp_path / "artifacts" / "batch_state.json").read_text(encoding="utf-8")
    )
    assert len(state["seen_keys"]) == 3


def test_cli_batch_parallel_skips_seen_keys(tmp_path, monkeypatch):
    """Parallel mode should skip jobs already registered in seen_keys."""
    plan_path = _make_batch_plan(
        tmp_path,
        [
            {"name": "x", "workflow": "run", "mode": "combo", "config": "x.json"},
        ],
    )
    calls = []

    def _fake(cwd, config_path, workflow, mode, workers):
        calls.append(workflow)

    monkeypatch.setattr(cli, "_run_workflow", _fake)

    base_argv = [
        "batch", "--plan", str(plan_path),
        "--cwd", str(tmp_path),
        "--min-free-gb", "0",
        "--parallel-jobs", "2",
    ]
    assert cli.main(base_argv) == 0
    assert len(calls) == 1

    # Second run ??job already seen
    assert cli.main(base_argv) == 0
    assert len(calls) == 1  # no new calls

    state = json.loads(
        (tmp_path / "artifacts" / "batch_state.json").read_text(encoding="utf-8")
    )
    assert any(h["status"] == "skipped_seen_key" for h in state["history"])


def test_cli_batch_parallel_continue_on_error(tmp_path, monkeypatch):
    """With --continue-on-error --parallel-jobs 2, remaining jobs still run."""
    plan_path = _make_batch_plan(
        tmp_path,
        [
            {"name": "fail-job", "workflow": "run", "mode": "combo", "config": "fail.json"},
            {"name": "ok-job", "workflow": "baseline", "config": "ok.json"},
        ],
    )
    calls = []

    def _fake(cwd, config_path, workflow, mode, workers):
        calls.append(config_path.name)
        if config_path.name == "fail.json":
            raise RuntimeError("deliberate")

    monkeypatch.setattr(cli, "_run_workflow", _fake)

    code = cli.main([
        "batch", "--plan", str(plan_path),
        "--cwd", str(tmp_path),
        "--min-free-gb", "0",
        "--parallel-jobs", "2",
        "--continue-on-error",
    ])
    # With continue_on_error, return code is 1 (has failures) but does not raise
    assert code == 1
    # Both jobs were attempted
    assert sorted(calls) == ["fail.json", "ok.json"]

    state = json.loads(
        (tmp_path / "artifacts" / "batch_state.json").read_text(encoding="utf-8")
    )
    statuses = [h["status"] for h in state["history"]]
    assert "failed" in statuses
    assert "done" in statuses


def test_cli_batch_parallel_fail_fast_raises(tmp_path, monkeypatch):
    """Without --continue-on-error, a failure raises RuntimeError."""
    plan_path = _make_batch_plan(
        tmp_path,
        [
            {"name": "fail-first", "workflow": "run", "mode": "combo", "config": "f.json"},
        ],
    )

    def _fake(cwd, config_path, workflow, mode, workers):
        raise RuntimeError("boom")

    monkeypatch.setattr(cli, "_run_workflow", _fake)

    with pytest.raises(RuntimeError, match="batch job failed"):
        cli.main([
            "batch", "--plan", str(plan_path),
            "--cwd", str(tmp_path),
            "--min-free-gb", "0",
            "--parallel-jobs", "2",
        ])


def test_cli_batch_parallel_jobs_1_uses_sequential(tmp_path, monkeypatch):
    """--parallel-jobs 1 (default) should use the sequential path."""
    plan_path = _make_batch_plan(
        tmp_path,
        [
            {"name": "s1", "workflow": "run", "mode": "combo", "config": "s1.json"},
            {"name": "s2", "workflow": "baseline", "config": "s2.json"},
        ],
    )
    order = []

    def _fake(cwd, config_path, workflow, mode, workers):
        order.append(config_path.name)

    monkeypatch.setattr(cli, "_run_workflow", _fake)

    code = cli.main([
        "batch", "--plan", str(plan_path),
        "--cwd", str(tmp_path),
        "--min-free-gb", "0",
        "--parallel-jobs", "1",
    ])
    assert code == 0
    # Sequential guarantees order
    assert order == ["s1.json", "s2.json"]

    state = json.loads(
        (tmp_path / "artifacts" / "batch_state.json").read_text(encoding="utf-8")
    )
    assert len(state["seen_keys"]) == 2


def test_run_batch_job_single_done(tmp_path, monkeypatch):
    """Unit test: _run_batch_job_single records done in state."""
    import threading

    cfg = tmp_path / "unit.json"
    cfg.write_text(json.dumps({}), encoding="utf-8")
    state_path = tmp_path / "state.json"
    state = {"seen_keys": {}, "history": []}

    called = []

    def _fake(cwd, config_path, workflow, mode, workers):
        called.append(True)

    monkeypatch.setattr(cli, "_run_workflow", _fake)

    result = cli._run_batch_job_single(
        idx=1,
        total=1,
        job={
            "name": "u1",
            "workflow": "run",
            "mode": "combo",
            "workers": None,
            "config_path": cfg,
            "cwd": tmp_path,
        },
        state=state,
        state_path=state_path,
        lock=threading.Lock(),
    )
    assert result["status"] == "done"
    assert len(called) == 1
    assert len(state["seen_keys"]) == 1


def test_run_batch_job_single_skip_seen(tmp_path, monkeypatch):
    """Unit test: _run_batch_job_single skips seen keys."""
    import threading

    cfg = tmp_path / "seen.json"
    cfg.write_text(json.dumps({}), encoding="utf-8")
    state_path = tmp_path / "state.json"

    job = {
        "name": "s",
        "workflow": "run",
        "mode": "combo",
        "workers": None,
        "config_path": cfg,
        "cwd": tmp_path,
    }
    job_key = cli._compute_job_key(job)
    state = {"seen_keys": {job_key: {"status": "done"}}, "history": []}

    called = []

    def _fake(cwd, config_path, workflow, mode, workers):
        called.append(True)

    monkeypatch.setattr(cli, "_run_workflow", _fake)

    result = cli._run_batch_job_single(
        idx=1, total=1, job=job,
        state=state, state_path=state_path,
        lock=threading.Lock(),
    )
    assert result["status"] == "skipped"
    assert len(called) == 0


def test_run_batch_job_single_allow_seen_key_reuse_runs_anyway(tmp_path, monkeypatch):
    import threading

    cfg = tmp_path / "rerun.json"
    cfg.write_text(json.dumps({}), encoding="utf-8")
    state_path = tmp_path / "state.json"

    job = {
        "name": "rerun",
        "workflow": "run",
        "mode": "combo",
        "workers": None,
        "config_path": cfg,
        "cwd": tmp_path,
        "allow_seen_key_reuse": True,
    }
    job_key = cli._compute_job_key(job)
    state = {"seen_keys": {job_key: {"status": "done"}}, "history": []}

    called = []

    def _fake(cwd, config_path, workflow, mode, workers):
        called.append((cwd, config_path, workflow, mode, workers))

    monkeypatch.setattr(cli, "_run_workflow", _fake)

    result = cli._run_batch_job_single(
        idx=1,
        total=1,
        job=job,
        state=state,
        state_path=state_path,
        lock=threading.Lock(),
    )
    assert result["status"] == "done"
    assert len(called) == 1
    assert state["seen_keys"][job_key]["status"] == "done"


def test_run_batch_job_single_failed(tmp_path, monkeypatch):
    """Unit test: _run_batch_job_single records failure."""
    import threading

    cfg = tmp_path / "fail.json"
    cfg.write_text(json.dumps({}), encoding="utf-8")
    state_path = tmp_path / "state.json"
    state = {"seen_keys": {}, "history": []}

    def _fake(cwd, config_path, workflow, mode, workers):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(cli, "_run_workflow", _fake)

    result = cli._run_batch_job_single(
        idx=1, total=1,
        job={
            "name": "f",
            "workflow": "baseline",
            "mode": None,
            "workers": None,
            "config_path": cfg,
            "cwd": tmp_path,
        },
        state=state, state_path=state_path,
        lock=threading.Lock(),
    )
    assert result["status"] == "failed"
    assert "kaboom" in result["error"]
    assert len(state["seen_keys"]) == 0
    assert any(h["status"] == "failed" for h in state["history"])


# ---------------------------------------------------------------------------
#  AWF-027: Cron patrol cycle tests
# ---------------------------------------------------------------------------


def test_run_patrol_cycle_no_gaps_produces_report(tmp_path, monkeypatch):
    """With no untested pairs, cycle should skip batch and still generate report."""
    artifacts = tmp_path / "artifacts"
    registry_path = artifacts / "run_registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps({
            "runs": [
                {"run_id": "r1", "timestamp_utc": "2026-01-01T00:00:00Z",
                 "oos_avg_total_return_pct": 1.0, "trade_symbols": ["ETH/USDT"],
                 "timeframes": [{"timeframe": "1h", "days": 90}]},
            ],
            "coverage": {"tested_pairs": [], "untested_pairs": []},
        }),
        encoding="utf-8",
    )

    template_cfg = tmp_path / "template.json"
    template_cfg.write_text(json.dumps({
        "timeframes": [{"timeframe": "1h", "days": 90}],
        "trade_symbols": ["ETH/USDT"],
    }), encoding="utf-8")

    report_html = artifacts / "cron_report.html"
    result = cli._run_patrol_cycle(
        cwd=tmp_path,
        registry_path=registry_path,
        template_config_path=template_cfg,
        plan_out=artifacts / "cron_plan.json",
        plan_config_dir=artifacts / "cron_configs",
        batch_state_path=artifacts / "batch_state.json",
        report_html_path=report_html,
        report_json_path=None,
        workflow="run",
        mode="combo",
    )
    assert result["plan_jobs"] == 0
    assert result["batch_ok"] is True
    assert result["report_ok"] is True
    assert result["error"] is None
    assert report_html.exists()


def test_run_patrol_cycle_with_gaps_runs_batch(tmp_path, monkeypatch):
    """With untested pairs, cycle should plan jobs, run batch, then report."""
    artifacts = tmp_path / "artifacts"
    registry_path = artifacts / "run_registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps({
            "runs": [],
            "coverage": {
                "tested_pairs": [],
                "untested_pairs": [
                    {"timeframe": "1h", "symbol": "ETH/USDT"},
                ],
            },
        }),
        encoding="utf-8",
    )

    template_cfg = tmp_path / "template.json"
    template_cfg.write_text(json.dumps({
        "timeframes": [{"timeframe": "1h", "days": 90}],
        "trade_symbols": ["ETH/USDT"],
    }), encoding="utf-8")

    # Mock _run_workflow to avoid actual sweep
    batch_calls = []

    def _fake_run_workflow(cwd, config_path, workflow, mode=None, workers=None):
        batch_calls.append({"workflow": workflow, "config_path": str(config_path)})

    monkeypatch.setattr(cli, "_run_workflow", _fake_run_workflow)

    report_html = artifacts / "cron_report.html"
    result = cli._run_patrol_cycle(
        cwd=tmp_path,
        registry_path=registry_path,
        template_config_path=template_cfg,
        plan_out=artifacts / "cron_plan.json",
        plan_config_dir=artifacts / "cron_configs",
        batch_state_path=artifacts / "batch_state.json",
        report_html_path=report_html,
        report_json_path=None,
        workflow="run",
        mode="combo",
    )
    assert result["plan_jobs"] == 1
    assert result["batch_ok"] is True
    assert result["report_ok"] is True
    assert len(batch_calls) == 1
    assert report_html.exists()


def test_cmd_cron_single_cycle(tmp_path, monkeypatch):
    """autowfo cron --max-cycles 1 should run exactly one cycle."""
    artifacts = tmp_path / "artifacts"
    registry_path = artifacts / "run_registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps({
            "runs": [],
            "coverage": {"tested_pairs": [], "untested_pairs": []},
        }),
        encoding="utf-8",
    )

    template_cfg = tmp_path / "template.json"
    template_cfg.write_text(json.dumps({
        "timeframes": [{"timeframe": "1h", "days": 90}],
    }), encoding="utf-8")

    args = cli.build_parser().parse_args([
        "cron",
        "--template-config", str(template_cfg),
        "--registry", str(registry_path),
        "--max-cycles", "1",
        "--interval", "0",
        "--cwd", str(tmp_path),
    ])
    result = args.handler(args)
    assert result == 0

    # Cycle log should exist with 1 entry
    log_path = artifacts / "cron_cycle_log.json"
    assert log_path.exists()
    log = json.loads(log_path.read_text(encoding="utf-8"))
    assert len(log) == 1
    assert log[0]["cycle_number"] == 1


def test_cmd_cron_parser_defaults():
    """Verify cron subcommand parser defaults."""
    parser = cli.build_parser()
    args = parser.parse_args(["cron", "--template-config", "sweep.json"])
    assert args.command == "cron"
    assert args.interval == 0
    assert args.max_cycles == 1
    assert args.max_jobs == 0
    assert args.parallel_jobs == 1
    assert args.workflow == "run"
    assert args.mode == "combo"
    assert args.scheduler_mode is False
    assert args.max_runs is None
    assert args.max_cycle_seconds == 3600


def test_cli_version_outputs_version(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    out = capsys.readouterr().out.strip()
    assert out == f"autowfo {cli.AUTOWFO_VERSION}"


def test_cli_help_lists_all_subcommands():
    parser = cli.build_parser()
    help_text = parser.format_help()
    for command_name in (
        "run",
        "baseline",
        "batch",
        "plan",
        "discover",
        "export-signal",
        "export-report",
        "schedule-signals",
        "report",
        "repro",
        "gate-c",
        "cron",
    ):
        assert command_name in help_text


def test_cli_export_signal_writes_live_signal_config(tmp_path):
    pytest.importorskip("duckdb")
    from autowfo.analytics import AnalyticsStore
    from autowfo.artifact_store import ArtifactStore

    experiment_id = "exp_cli_signal"
    run_id = "20260301_010000"
    store = ArtifactStore(experiment_id, base_dir=tmp_path / "artifacts")
    conn = store.init_results_db(run_id)
    try:
        conn.execute(
            """
            INSERT INTO combo_results (
                combo_id, experiment_id, run_id, direction,
                trigger_asset, action_asset,
                indicator_params, condition_params, risk_params,
                oos_sharpe, oos_win_rate, oos_n_trades, oos_total_return,
                wf_score, created_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "combo_top",
                experiment_id,
                run_id,
                "long",
                "BTC/USDT",
                "ETH/USDT",
                json.dumps({"trigger_indicators": ["RSI"], "action_indicators": ["BB"]}),
                "{}",
                "{}",
                1.2,
                0.56,
                12,
                0.2,
                0.93,
                "2026-03-01T00:00:00+00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    analytics = AnalyticsStore(tmp_path / "artifacts" / "analytics.duckdb")
    analytics.update_from_run(experiment_id, run_id, store)

    out_path = tmp_path / "artifacts" / "live_signal_config.json"
    ret = cli.main(
        [
            "export-signal",
            "--top",
            "3",
            "--out",
            str(out_path),
            "--cwd",
            str(tmp_path),
        ]
    )
    assert ret == 0
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["experiment_id"] == experiment_id
    assert payload["trigger_indicator"] == "RSI"
    assert payload["action_indicator"] == "BB"
    assert payload["wf_params"]["wf_score"] == 0.93


def test_cli_export_report_writes_html_file(tmp_path, monkeypatch):
    from autowfo import report_export as report_export_mod

    captured = {}

    def _fake_export_html_report(analytics_store, output_path):
        _ = analytics_store
        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("<html><body><h1>AUTOWFO Research Report</h1></body></html>", encoding="utf-8")
        captured["output_path"] = str(out_path)
        return {"ok": True, "output_path": str(out_path)}

    monkeypatch.setattr(report_export_mod, "export_html_report", _fake_export_html_report)

    out_path = tmp_path / "artifacts" / "research_report.html"
    ret = cli.main(
        [
            "export-report",
            "--out",
            str(out_path),
            "--cwd",
            str(tmp_path),
        ]
    )
    assert ret == 0
    assert out_path.exists()
    assert "AUTOWFO Research Report" in out_path.read_text(encoding="utf-8")
    assert captured["output_path"] == str(out_path)


def test_cli_schedule_signals_runs_daemon_with_interval_and_max_ticks(tmp_path, monkeypatch):
    from autowfo import signal_scheduler as signal_scheduler_mod

    calls = {}

    class _DummySignalScheduler:
        def __init__(
            self,
            analytics_store,
            state_path,
            export_path,
            positions_path,
            schedule_interval_seconds,
            now_func=None,
        ):
            calls["analytics_store"] = analytics_store
            calls["state_path"] = state_path
            calls["export_path"] = export_path
            calls["positions_path"] = positions_path
            calls["schedule_interval_seconds"] = schedule_interval_seconds
            calls["now_func"] = now_func

        def run_forever(self, max_ticks=None, sleep_func=None):
            calls["max_ticks"] = max_ticks
            calls["sleep_func"] = sleep_func
            return 1

    monkeypatch.setattr(signal_scheduler_mod, "SignalScheduler", _DummySignalScheduler)

    ret = cli.main(
        [
            "schedule-signals",
            "--interval",
            "120",
            "--max-ticks",
            "1",
            "--cwd",
            str(tmp_path),
        ]
    )
    assert ret == 0
    assert calls["schedule_interval_seconds"] == 120
    assert calls["max_ticks"] == 1
    assert str(calls["state_path"]).replace("\\", "/").endswith("artifacts/signal_schedule_state.json")
    assert str(calls["export_path"]).replace("\\", "/").endswith("artifacts/live_signal_config.json")
    assert str(calls["positions_path"]).replace("\\", "/").endswith("artifacts/paper_positions.json")


def test_append_patrol_log_roundtrip(tmp_path):
    row_a = {
        "cycle_end_utc": "2026-03-01T00:00:00+00:00",
        "discovery_tick": {"generated": 10, "enqueued": 4},
        "scheduler_runs_processed": 2,
        "scheduler_run_outcomes": [
            {"processed": True, "ok": True},
            {"processed": True, "ok": False},
        ],
        "queue_remaining": 5,
    }
    row_b = {
        "cycle_end_utc": "2026-03-01T00:10:00+00:00",
        "discovery_tick": {"generated": 10, "enqueued": 0},
        "scheduler_runs_processed": 1,
        "scheduler_run_outcomes": [{"processed": True, "ok": True}],
        "queue_remaining": 4,
    }

    cli._append_patrol_log(tmp_path, row_a)
    cli._append_patrol_log(tmp_path, row_b)

    log_path = tmp_path / "artifacts" / "patrol_log.ndjson"
    assert log_path.exists()
    lines = [line for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 2
    parsed_a = json.loads(lines[0])
    parsed_b = json.loads(lines[1])
    assert parsed_a["tick_generated"] == 10
    assert parsed_a["tick_enqueued"] == 4
    assert parsed_a["runs_executed"] == 2
    assert parsed_a["runs_errors"] == 1
    assert parsed_b["tick_enqueued"] == 0
    assert parsed_b["queue_remaining"] == 4


def test_append_patrol_log_rotation_keeps_latest_lines(tmp_path):
    for idx in range(6):
        cli._append_patrol_log(
            tmp_path,
            {
                "cycle_end_utc": f"2026-03-01T00:{idx:02d}:00+00:00",
                "discovery_tick": {"generated": idx + 1, "enqueued": 1},
                "scheduler_runs_processed": 1,
                "scheduler_run_outcomes": [{"processed": True, "ok": True}],
                "queue_remaining": 0,
            },
            max_lines=5,
            keep_lines=2,
        )

    log_path = tmp_path / "artifacts" / "patrol_log.ndjson"
    lines = [line for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 2
    rows = [json.loads(line) for line in lines]
    assert rows[0]["utc"] == "2026-03-01T00:04:00+00:00"
    assert rows[1]["utc"] == "2026-03-01T00:05:00+00:00"


def test_cmd_cron_scheduler_mode_runs_discovery_then_run_once(tmp_path, monkeypatch):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    registry_path = artifacts / "run_registry.json"
    registry_path.write_text(json.dumps({"runs": [], "coverage": {"tested_pairs": [], "untested_pairs": []}}), encoding="utf-8")
    template_cfg = tmp_path / "template.json"
    template_cfg.write_text(json.dumps({"timeframes": [{"timeframe": "1h", "days": 90}]}), encoding="utf-8")

    (artifacts / "scheduler.json").write_text(
        json.dumps(
            {
                "priority_order": ["user_submitted", "discovery", "refine"],
                "max_concurrent": 1,
                "schedule_cron": "0 0 * * *",
                "max_runs_per_patrol": 1,
            }
        ),
        encoding="utf-8",
    )
    (artifacts / "pool_config.json").write_text(
        json.dumps(
            {
                "indicator_ids": ["RSI", "BB", "EMA"],
                "combo_size_range": [2, 2],
            }
        ),
        encoding="utf-8",
    )

    from autowfo.commands import cron as cron_cmd
    from autowfo import discovery_loop as discovery_loop_mod

    tick_calls = []
    run_once_calls = []

    class _DummyDiscoveryLoop:
        def __init__(self, pool_config, scheduler, analytics_store, experiments_root):
            _ = (pool_config, scheduler, analytics_store, experiments_root)

        def tick(self):
            tick_calls.append("tick")
            return {"generated": 3, "enqueued": 2, "skipped_existing": 1, "queue_depth": 2}

    def _fake_run_once(cwd, cli_impl):
        run_once_calls.append((cwd, cli_impl))
        return {"processed": True, "ok": True, "result": {"run_id": "run_001"}}

    monkeypatch.setattr(discovery_loop_mod, "DiscoveryLoop", _DummyDiscoveryLoop)
    monkeypatch.setattr(cron_cmd, "_run_scheduler_queue_once", _fake_run_once)

    ret = cli.main(
        [
            "cron",
            "--template-config",
            str(template_cfg),
            "--registry",
            str(registry_path),
            "--max-cycles",
            "1",
            "--interval",
            "0",
            "--cwd",
            str(tmp_path),
        ]
    )
    assert ret == 0
    assert len(tick_calls) == 1
    assert len(run_once_calls) == 1

    log_path = artifacts / "cron_cycle_log.json"
    assert log_path.exists()
    payload = json.loads(log_path.read_text(encoding="utf-8"))
    assert len(payload) == 1
    assert payload[0]["scheduler_mode"] is True
    assert payload[0]["schedule_cron"] == "0 0 * * *"
    assert payload[0]["max_runs_per_patrol"] == 1
    assert payload[0]["scheduler_runs_processed"] == 1


def test_cmd_cron_scheduler_mode_respects_max_runs_override(tmp_path, monkeypatch):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    registry_path = artifacts / "run_registry.json"
    registry_path.write_text(json.dumps({"runs": [], "coverage": {"tested_pairs": [], "untested_pairs": []}}), encoding="utf-8")
    template_cfg = tmp_path / "template.json"
    template_cfg.write_text(json.dumps({"timeframes": [{"timeframe": "1h", "days": 90}]}), encoding="utf-8")

    (artifacts / "scheduler.json").write_text(
        json.dumps(
            {
                "priority_order": ["user_submitted", "discovery", "refine"],
                "max_concurrent": 1,
                "schedule_cron": "0 0 * * *",
                "max_runs_per_patrol": 5,
            }
        ),
        encoding="utf-8",
    )

    from autowfo.commands import cron as cron_cmd

    run_once_calls = []

    def _fake_run_once(cwd, cli_impl):
        run_once_calls.append((cwd, cli_impl))
        return {"processed": True, "ok": True, "result": {"run_id": f"run_{len(run_once_calls):03d}"}}

    monkeypatch.setattr(cron_cmd, "_run_scheduler_queue_once", _fake_run_once)

    ret = cli.main(
        [
            "cron",
            "--template-config",
            str(template_cfg),
            "--registry",
            str(registry_path),
            "--scheduler-mode",
            "--max-runs",
            "2",
            "--max-cycles",
            "1",
            "--interval",
            "0",
            "--cwd",
            str(tmp_path),
        ]
    )
    assert ret == 0
    assert len(run_once_calls) == 2

    log_path = artifacts / "cron_cycle_log.json"
    payload = json.loads(log_path.read_text(encoding="utf-8"))
    assert payload[0]["scheduler_mode"] is True
    assert payload[0]["max_runs_per_patrol"] == 2
    assert payload[0]["scheduler_runs_processed"] == 2


def test_cmd_cron_scheduler_mode_opt_in_signal_scheduling_tick(tmp_path, monkeypatch):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    registry_path = artifacts / "run_registry.json"
    registry_path.write_text(json.dumps({"runs": [], "coverage": {"tested_pairs": [], "untested_pairs": []}}), encoding="utf-8")
    template_cfg = tmp_path / "template.json"
    template_cfg.write_text(json.dumps({"timeframes": [{"timeframe": "1h", "days": 90}]}), encoding="utf-8")

    (artifacts / "scheduler.json").write_text(
        json.dumps(
            {
                "priority_order": ["user_submitted", "discovery", "refine"],
                "max_concurrent": 1,
                "schedule_cron": "0 0 * * *",
                "max_runs_per_patrol": 1,
                "enable_signal_scheduling": True,
            }
        ),
        encoding="utf-8",
    )

    from autowfo.commands import cron as cron_cmd
    from autowfo import signal_scheduler as signal_scheduler_mod

    run_once_calls = []
    signal_tick_calls = []

    def _fake_run_once(cwd, cli_impl):
        run_once_calls.append((cwd, cli_impl))
        return {"processed": False, "ok": True, "item": None}

    class _DummySignalScheduler:
        def __init__(self, *args, **kwargs):
            _ = (args, kwargs)

        def tick(self):
            signal_tick_calls.append("tick")
            return {"ok": True, "action": "skip_no_strategy", "changed": False}

    monkeypatch.setattr(cron_cmd, "_run_scheduler_queue_once", _fake_run_once)
    monkeypatch.setattr(signal_scheduler_mod, "SignalScheduler", _DummySignalScheduler)

    ret = cli.main(
        [
            "cron",
            "--template-config",
            str(template_cfg),
            "--registry",
            str(registry_path),
            "--scheduler-mode",
            "--max-cycles",
            "1",
            "--interval",
            "0",
            "--cwd",
            str(tmp_path),
        ]
    )
    assert ret == 0
    assert len(run_once_calls) == 1
    assert len(signal_tick_calls) == 1

    payload = json.loads((artifacts / "cron_cycle_log.json").read_text(encoding="utf-8"))
    assert payload[0]["signal_scheduling"]["enabled"] is True
    assert payload[0]["signal_scheduling"]["tick"]["ok"] is True


def test_cmd_cron_timeout_guard_triggers_break(tmp_path, monkeypatch):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    registry_path = artifacts / "run_registry.json"
    registry_path.write_text(json.dumps({"runs": [], "coverage": {"tested_pairs": [], "untested_pairs": []}}), encoding="utf-8")
    template_cfg = tmp_path / "template.json"
    template_cfg.write_text(json.dumps({"timeframes": [{"timeframe": "1h", "days": 90}]}), encoding="utf-8")

    cycle_calls = []

    def _fake_patrol_cycle(**kwargs):
        cycle_calls.append(kwargs)
        return {
            "cycle_start_utc": "2026-03-01T00:00:00Z",
            "cycle_end_utc": "2026-03-01T00:00:10Z",
            "plan_jobs": 0,
            "batch_ok": True,
            "report_ok": True,
            "error": None,
            "top_entities": [],
        }

    perf_values = iter([0.0, 5.0])

    def _fake_perf_counter():
        try:
            return next(perf_values)
        except StopIteration:
            return 5.0

    monkeypatch.setattr(cli, "_run_patrol_cycle", _fake_patrol_cycle)
    monkeypatch.setattr(cli.time, "perf_counter", _fake_perf_counter)
    monkeypatch.setattr(cli.time, "sleep", lambda _: None)

    ret = cli.main(
        [
            "cron",
            "--template-config",
            str(template_cfg),
            "--registry",
            str(registry_path),
            "--max-cycles",
            "5",
            "--interval",
            "1",
            "--max-cycle-seconds",
            "1",
            "--cwd",
            str(tmp_path),
        ]
    )
    assert ret == 0
    assert len(cycle_calls) == 1

    log_path = artifacts / "cron_cycle_log.json"
    payload = json.loads(log_path.read_text(encoding="utf-8"))
    assert len(payload) == 1
    assert payload[0]["timeout_guard_triggered"] is True


def test_run_patrol_cycle_plan_error_returns_early(tmp_path):
    """If registry doesn't exist, plan should fail and cycle returns error."""
    missing_registry = tmp_path / "no_such_file.json"
    template_cfg = tmp_path / "template.json"
    template_cfg.write_text(json.dumps({}), encoding="utf-8")

    result = cli._run_patrol_cycle(
        cwd=tmp_path,
        registry_path=missing_registry,
        template_config_path=template_cfg,
        plan_out=tmp_path / "plan.json",
        plan_config_dir=tmp_path / "cfgs",
        batch_state_path=tmp_path / "state.json",
        report_html_path=tmp_path / "report.html",
        report_json_path=None,
    )
    assert result["error"] is not None
    assert "plan failed" in result["error"]
    assert result["batch_ok"] is False
    assert result["report_ok"] is False


# ---------------------------------------------------------------------------
#  AWF-032: Cron patrol validation ??deeper cycle state tracking tests
# ---------------------------------------------------------------------------


def test_patrol_cycle_state_timestamps(tmp_path, monkeypatch):
    """Cycle result dict must have ISO cycle_start_utc and cycle_end_utc."""
    artifacts = tmp_path / "artifacts"
    registry_path = artifacts / "run_registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps({
        "runs": [], "coverage": {"tested_pairs": [], "untested_pairs": []},
    }), encoding="utf-8")

    template_cfg = tmp_path / "template.json"
    template_cfg.write_text(json.dumps({
        "timeframes": [{"timeframe": "1h", "days": 90}],
    }), encoding="utf-8")

    result = cli._run_patrol_cycle(
        cwd=tmp_path,
        registry_path=registry_path,
        template_config_path=template_cfg,
        plan_out=artifacts / "plan.json",
        plan_config_dir=artifacts / "cfgs",
        batch_state_path=artifacts / "state.json",
        report_html_path=artifacts / "report.html",
        report_json_path=None,
    )
    assert result["cycle_start_utc"] is not None
    assert result["cycle_end_utc"] is not None
    # Both should parse as ISO timestamps
    from datetime import datetime
    datetime.fromisoformat(result["cycle_start_utc"].replace("Z", "+00:00"))
    datetime.fromisoformat(result["cycle_end_utc"].replace("Z", "+00:00"))


def test_patrol_cycle_target_filtering(tmp_path):
    """With target_timeframes/target_symbols, cycle should use
    _compute_coverage_gaps instead of registry untested list."""
    artifacts = tmp_path / "artifacts"
    registry_path = artifacts / "run_registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps({
        "runs": [],
        "coverage": {
            "tested_pairs": [{"timeframe": "1h", "symbol": "ETH/USDT"}],
            "untested_pairs": [],
        },
    }), encoding="utf-8")

    template_cfg = tmp_path / "template.json"
    template_cfg.write_text(json.dumps({
        "timeframes": [{"timeframe": "1h", "days": 90}],
    }), encoding="utf-8")

    # Mock _run_workflow to capture planned jobs
    batch_calls = []
    import autowfo.cli as cli_mod
    orig_run_workflow = getattr(cli_mod, "_run_workflow", None)

    def _fake_run_workflow(cwd, config_path, workflow, mode=None, workers=None):
        batch_calls.append(str(config_path))

    cli_mod._run_workflow = _fake_run_workflow
    try:
        result = cli._run_patrol_cycle(
            cwd=tmp_path,
            registry_path=registry_path,
            template_config_path=template_cfg,
            plan_out=artifacts / "plan.json",
            plan_config_dir=artifacts / "cfgs",
            batch_state_path=artifacts / "state.json",
            report_html_path=artifacts / "report.html",
            report_json_path=None,
            target_timeframes=["1h"],
            target_symbols=["ETH/USDT", "BNB/USDT"],
        )
    finally:
        if orig_run_workflow is not None:
            cli_mod._run_workflow = orig_run_workflow

    # ETH/USDT is already tested; only BNB/USDT should be a gap
    assert result["plan_jobs"] == 1
    plan = json.loads((artifacts / "plan.json").read_text(encoding="utf-8"))
    assert any("BNB" in j.get("config", "") for j in plan["jobs"])


def test_cmd_cron_multi_cycle_log(tmp_path, monkeypatch):
    """Multiple cycles should accumulate entries in cron_cycle_log.json."""
    artifacts = tmp_path / "artifacts"
    registry_path = artifacts / "run_registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps({
        "runs": [], "coverage": {"tested_pairs": [], "untested_pairs": []},
    }), encoding="utf-8")

    template_cfg = tmp_path / "template.json"
    template_cfg.write_text(json.dumps({
        "timeframes": [{"timeframe": "1h", "days": 90}],
    }), encoding="utf-8")

    # interval must be > 0 for multi-cycle; mock time.sleep to skip waiting
    import autowfo.cli as cli_mod
    monkeypatch.setattr(cli_mod.time, "sleep", lambda _: None)

    args = cli.build_parser().parse_args([
        "cron",
        "--template-config", str(template_cfg),
        "--registry", str(registry_path),
        "--max-cycles", "3",
        "--interval", "1",
        "--cwd", str(tmp_path),
    ])
    ret = args.handler(args)
    assert ret == 0

    log_path = artifacts / "cron_cycle_log.json"
    assert log_path.exists()
    log = json.loads(log_path.read_text(encoding="utf-8"))
    assert len(log) == 3
    for i, entry in enumerate(log, start=1):
        assert entry["cycle_number"] == i
        assert "cycle_start_utc" in entry
        assert "cycle_end_utc" in entry
        assert "plan_jobs" in entry


def test_patrol_cycle_max_jobs_limits(tmp_path, monkeypatch):
    """max_jobs should cap the number of planned jobs."""
    artifacts = tmp_path / "artifacts"
    registry_path = artifacts / "run_registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps({
        "runs": [],
        "coverage": {
            "tested_pairs": [],
            "untested_pairs": [
                {"timeframe": "1h", "symbol": "ETH/USDT"},
                {"timeframe": "1h", "symbol": "BNB/USDT"},
                {"timeframe": "1h", "symbol": "SOL/USDT"},
            ],
        },
    }), encoding="utf-8")

    template_cfg = tmp_path / "template.json"
    template_cfg.write_text(json.dumps({
        "timeframes": [{"timeframe": "1h", "days": 90}],
    }), encoding="utf-8")

    import autowfo.cli as cli_mod
    orig_run_workflow = getattr(cli_mod, "_run_workflow", None)
    cli_mod._run_workflow = lambda *a, **kw: None
    try:
        result = cli._run_patrol_cycle(
            cwd=tmp_path,
            registry_path=registry_path,
            template_config_path=template_cfg,
            plan_out=artifacts / "plan.json",
            plan_config_dir=artifacts / "cfgs",
            batch_state_path=artifacts / "state.json",
            report_html_path=artifacts / "report.html",
            report_json_path=None,
            max_jobs=2,
        )
    finally:
        if orig_run_workflow is not None:
            cli_mod._run_workflow = orig_run_workflow

    # max_jobs=2 should limit to 2 jobs even though 3 untested pairs exist
    assert result["plan_jobs"] == 2


def test_patrol_cycle_batch_failure_continue_on_error(tmp_path, monkeypatch):
    """When a batch job fails with continue_on_error, cycle should still
    attempt report and return batch_ok=False."""
    artifacts = tmp_path / "artifacts"
    registry_path = artifacts / "run_registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps({
        "runs": [],
        "coverage": {
            "tested_pairs": [],
            "untested_pairs": [
                {"timeframe": "1h", "symbol": "ETH/USDT"},
            ],
        },
    }), encoding="utf-8")

    template_cfg = tmp_path / "template.json"
    template_cfg.write_text(json.dumps({
        "timeframes": [{"timeframe": "1h", "days": 90}],
    }), encoding="utf-8")

    # Mock _run_workflow to raise an error
    import autowfo.cli as cli_mod
    orig_run_workflow = getattr(cli_mod, "_run_workflow", None)

    def _failing_workflow(*args, **kwargs):
        raise RuntimeError("simulated batch failure")

    cli_mod._run_workflow = _failing_workflow
    try:
        result = cli._run_patrol_cycle(
            cwd=tmp_path,
            registry_path=registry_path,
            template_config_path=template_cfg,
            plan_out=artifacts / "plan.json",
            plan_config_dir=artifacts / "cfgs",
            batch_state_path=artifacts / "state.json",
            report_html_path=artifacts / "report.html",
            report_json_path=None,
            continue_on_error=True,
        )
    finally:
        if orig_run_workflow is not None:
            cli_mod._run_workflow = orig_run_workflow

    assert result["plan_jobs"] == 1
    assert result["batch_ok"] is False
    # Report should still be attempted even after batch failure
    assert result.get("report_ok") is not None


def test_build_top_change_lines_reports_rank_movements():
    previous_top = [
        {"key": "combo-A", "label": "combo-A", "value": 10.0},
        {"key": "combo-B", "label": "combo-B", "value": 9.0},
        {"key": "combo-C", "label": "combo-C", "value": 8.0},
    ]
    current_top = [
        {"key": "combo-B", "label": "combo-B", "value": 9.5},
        {"key": "combo-D", "label": "combo-D", "value": 9.2},
        {"key": "combo-A", "label": "combo-A", "value": 9.0},
    ]

    lines = cli._build_top_change_lines(previous_top, current_top, limit=3)
    assert len(lines) == 3
    assert "[UP 2->1]" in lines[0]
    assert "[NEW]" in lines[1]
    assert "[DOWN 1->3]" in lines[2]


def test_build_freshness_alert_flags_stale_timeframes(tmp_path):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "data_refresh_state.json").write_text(
        json.dumps(
            {
                "timeframe_data_end": {
                    "1h": "2020-01-01 00:00:00",
                    "4h": "2020-01-02 00:00:00",
                }
            }
        ),
        encoding="utf-8",
    )

    freshness_alert = cli._build_freshness_alert(artifacts, threshold_days=7)
    assert freshness_alert["checked"] is True
    assert freshness_alert["alert"] is True
    assert any(row.get("timeframe") == "1h" for row in freshness_alert["stale"])
    assert "ALERT" in cli._format_freshness_line(freshness_alert)


def test_cmd_cron_notifications_and_state_update(tmp_path, monkeypatch):
    artifacts = tmp_path / "artifacts"
    registry_path = artifacts / "run_registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps({"runs": [], "coverage": {"tested_pairs": [], "untested_pairs": []}}),
        encoding="utf-8",
    )
    template_cfg = tmp_path / "template.json"
    template_cfg.write_text(json.dumps({"timeframes": [{"timeframe": "1h", "days": 90}]}), encoding="utf-8")

    cycle_results = [
        {
            "cycle_start_utc": "2026-02-19T00:00:00Z",
            "cycle_end_utc": "2026-02-19T00:00:30Z",
            "plan_jobs": 0,
            "batch_ok": True,
            "report_ok": True,
            "error": None,
            "top_entities": [
                {"key": "combo-A", "label": "combo-A", "value": 10.0, "kind": "combo"},
                {"key": "combo-B", "label": "combo-B", "value": 9.0, "kind": "combo"},
                {"key": "combo-C", "label": "combo-C", "value": 8.0, "kind": "combo"},
            ],
        },
        {
            "cycle_start_utc": "2026-02-19T00:01:00Z",
            "cycle_end_utc": "2026-02-19T00:01:30Z",
            "plan_jobs": 0,
            "batch_ok": True,
            "report_ok": True,
            "error": None,
            "top_entities": [
                {"key": "combo-B", "label": "combo-B", "value": 9.6, "kind": "combo"},
                {"key": "combo-A", "label": "combo-A", "value": 9.4, "kind": "combo"},
                {"key": "combo-C", "label": "combo-C", "value": 8.1, "kind": "combo"},
            ],
        },
    ]

    def _fake_run_patrol_cycle(**kwargs):
        return dict(cycle_results.pop(0))

    notify_calls = []

    def _fake_dispatch(**kwargs):
        notify_calls.append(kwargs)
        return []

    monkeypatch.setattr(cli, "_run_patrol_cycle", _fake_run_patrol_cycle)
    monkeypatch.setattr(cli, "_dispatch_cron_notifications", _fake_dispatch)
    monkeypatch.setattr(cli.time, "sleep", lambda _: None)

    code = cli.main(
        [
            "cron",
            "--template-config",
            str(template_cfg),
            "--registry",
            str(registry_path),
            "--max-cycles",
            "2",
            "--interval",
            "1",
            "--notify-webhook",
            "https://example.com/hook",
            "--cwd",
            str(tmp_path),
        ]
    )
    assert code == 0
    assert len(notify_calls) == 2
    assert any("NEW" in line for line in notify_calls[0]["payload"]["top_changes"])
    assert any("UP 2->1" in line for line in notify_calls[1]["payload"]["top_changes"])

    notify_state_path = artifacts / "cron_notify_state.json"
    assert notify_state_path.exists()
    notify_state = json.loads(notify_state_path.read_text(encoding="utf-8"))
    assert notify_state["last_top"][0]["key"] == "combo-B"


def test_cli_doctor_returns_nonzero_on_storage_error(tmp_path, capsys):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "scheduler_queue.json").write_text("{invalid json", encoding="utf-8")

    code = cli.main(["doctor", "--artifacts-dir", str(artifacts), "--cwd", str(tmp_path)])

    captured = capsys.readouterr()
    assert code == 1
    assert "[doctor]" in captured.out
    assert "scheduler_queue" in captured.out


def test_cli_storage_migrate_dry_run_preserves_legacy_payload(tmp_path):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    legacy_path = artifacts / "paper_positions.json"
    legacy_path.write_text(
        json.dumps(
            [
                {
                    "signal_id": "signal::exp_cli",
                    "experiment_id": "exp_cli",
                    "open_ts": "2026-03-13T00:00:00Z",
                    "open_price": 1.0,
                    "close_ts": None,
                    "close_price": None,
                    "pnl_pct": None,
                    "status": "open",
                }
            ]
        ),
        encoding="utf-8",
    )

    code = cli.main(["storage", "migrate", "--dry-run", "--artifacts-dir", str(artifacts), "--cwd", str(tmp_path)])

    payload = json.loads(legacy_path.read_text(encoding="utf-8"))
    assert code == 0
    assert isinstance(payload, list)


def test_cli_storage_rebuild_analytics_builds_duckdb(tmp_path):
    pytest.importorskip("duckdb")
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    artifact_store = cli.importlib.import_module("autowfo.artifact_store").ArtifactStore(
        "exp_cli_rebuild",
        base_dir=artifacts,
    )
    run_id = "20260313_040000"
    conn = artifact_store.init_results_db(run_id)
    try:
        conn.execute(
            """
            INSERT INTO combo_results (
                combo_id, experiment_id, run_id, direction,
                trigger_asset, action_asset,
                indicator_params, condition_params, risk_params,
                oos_sharpe, oos_win_rate, oos_n_trades, oos_total_return,
                wf_score, created_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "combo_cli",
                "exp_cli_rebuild",
                run_id,
                "long",
                "BTC/USDT",
                "ETH/USDT",
                "{\"trigger_indicators\": [\"RSI\"], \"action_indicators\": [\"BB\"]}",
                "{}",
                "{}",
                1.1,
                0.5,
                12,
                0.2,
                0.8,
                "2026-03-13T00:00:00+00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    code = cli.main(["storage", "rebuild-analytics", "--artifacts-dir", str(artifacts), "--cwd", str(tmp_path)])

    assert code == 0
    assert (artifacts / "analytics.duckdb").exists()


def test_cli_storage_rebuild_shared_views_builds_root_compatibility_outputs(tmp_path):
    artifacts = tmp_path / "artifacts"
    workspace = cli.importlib.import_module("autowfo.run_workspace").build_run_workspace(tmp_path, "20260314_050000")
    workspace.ensure_directories()
    (workspace.combo_summary_path).write_text("timeframe,symbol\n1h,ETH/BTC\n", encoding="utf-8")
    (workspace.symbol_summary_path).write_text("timeframe,symbol\n1h,ETH/BTC\n", encoding="utf-8")
    (workspace.leaderboard_path).write_text(
        "run_id,timestamp_utc,timeframe,data_days,avg_total_return_pct,oos_avg_total_return_pct,report_file\n"
        "20260314_050000,2026-03-14T05:00:00Z,1h,30,1.0,0.5,btc_regime_ETH-BTC.html\n",
        encoding="utf-8",
    )
    metadata = {
        "run_id": "20260314_050000",
        "timestamp_utc": "2026-03-14T05:00:00Z",
        "search_mode": "combo",
        "config_sha256": "cfg-cli",
        "data_fingerprint": "fp-cli",
        "trade_symbols": ["ETH/BTC"],
        "timeframes": [{"timeframe": "1h", "days": 30}],
    }
    workspace.run_metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    workspace.run_metadata_run_path.write_text(json.dumps(metadata), encoding="utf-8")
    workspace.top10_path.write_text("timeframe,symbol\n1h,ETH/BTC\n", encoding="utf-8")
    (workspace.reports_dir / "btc_regime_ETH-BTC.html").write_text("<html>latest</html>", encoding="utf-8")
    (workspace.reports_dir / "btc_regime_ETH-BTC_20260314_050000.html").write_text(
        "<html>run</html>",
        encoding="utf-8",
    )

    code = cli.main(["storage", "rebuild-shared-views", "--artifacts-dir", str(artifacts), "--cwd", str(tmp_path)])

    assert code == 0
    assert (artifacts / "run_registry.json").exists()
    assert (artifacts / "leaderboard.csv").exists()
    assert (artifacts / "param_sweep_combo_summary.csv").exists()


def test_cli_storage_purge_legacy_dry_run_preserves_files(tmp_path):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    legacy_path = artifacts / "param_sweep_top10_legacy.csv"
    legacy_path.write_text("timeframe\n1h\n", encoding="utf-8")

    code = cli.main(["storage", "purge-legacy", "--dry-run", "--artifacts-dir", str(artifacts), "--cwd", str(tmp_path)])

    assert code == 0
    assert legacy_path.exists()


def test_cli_storage_compare_ranking_parses_config_and_resolves_outputs(tmp_path, monkeypatch):
    candidate_cfg = tmp_path / "candidate.json"
    candidate_cfg.write_text(json.dumps({"mode": "composite"}), encoding="utf-8")
    baseline_cfg = tmp_path / "baseline.json"
    baseline_cfg.write_text(json.dumps({"mode": "legacy"}), encoding="utf-8")

    captured = {}

    def _fake_compare(artifacts_dir, *, candidate_config, baseline_config=None, top_n=10, output_json=None, output_html=None):
        captured["artifacts_dir"] = artifacts_dir
        captured["candidate_config"] = candidate_config
        captured["baseline_config"] = baseline_config
        captured["top_n"] = top_n
        captured["output_json"] = output_json
        captured["output_html"] = output_html
        return {"ok": True}

    import autowfo.storage_ops as storage_ops

    monkeypatch.setattr(storage_ops, "compare_ranking_configs", _fake_compare)

    code = cli.main(
        [
            "storage",
            "compare-ranking",
            "--candidate-config",
            str(candidate_cfg),
            "--baseline-config",
            str(baseline_cfg),
            "--top-n",
            "7",
            "--output-json",
            "reports/cmp.json",
            "--output-html",
            "reports/cmp.html",
            "--cwd",
            str(tmp_path),
        ]
    )

    assert code == 0
    assert captured["candidate_config"] == {"mode": "composite"}
    assert captured["baseline_config"] == {"mode": "legacy"}
    assert captured["top_n"] == 7
    assert captured["output_json"] == tmp_path / "reports" / "cmp.json"
    assert captured["output_html"] == tmp_path / "reports" / "cmp.html"

