import json
from pathlib import Path

import pytest

from autowfo import cli


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
    runtime_cfg = tmp_path / "artifacts" / "sweep_config.json"
    payload = json.loads(runtime_cfg.read_text(encoding="utf-8"))
    assert payload["search_mode"] == "refine"
    assert payload["max_workers"] == 3
    assert calls[0]["cmd"] == [cli.sys.executable, "-m", "scripts.run_btc_regime_sweep"]
    assert calls[0]["env"]["VBT_SWEEP_MODE"] == "refine"


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
    runtime_cfg = tmp_path / "artifacts" / "sweep_config.json"
    payload = json.loads(runtime_cfg.read_text(encoding="utf-8"))
    assert payload["max_workers"] == 2
    assert calls[0]["cmd"] == [cli.sys.executable, "-m", "scripts.run_autowfo_baseline"]


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

    monkeypatch.setattr(cli, "_run_workflow", _fake_run_workflow)

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

    def _fake_run_workflow(cwd, config_path, workflow, mode, workers):
        calls.append((str(config_path), workflow))
        if config_path.name == "bad.json":
            raise RuntimeError("boom")

    monkeypatch.setattr(cli, "_run_workflow", _fake_run_workflow)

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
