import json

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
