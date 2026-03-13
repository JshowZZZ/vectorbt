import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from autowfo.commands import cron as cron_cmd
from autowfo.scheduler import ExperimentQueue, SchedulerConfig


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class _FakeCli:
    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    @staticmethod
    def _load_config(path: Path):
        return json.loads(path.read_text(encoding="utf-8-sig"))


@pytest.mark.slow
def test_scheduler_patrol_stability_for_ten_cycles(tmp_path, monkeypatch):
    artifacts = tmp_path / "artifacts"
    _write_json(
        artifacts / "scheduler.json",
        {
            "priority_order": ["user_submitted", "discovery", "refine"],
            "max_concurrent": 1,
            "schedule_cron": "0 0 * * *",
            "max_runs_per_patrol": 1,
        },
    )
    _write_json(
        artifacts / "pool_config.json",
        {
            "indicator_ids": ["RSI", "MACD", "BB", "EMA", "Volume"],
            "combo_sizes": [2],
            "default_trigger": {"asset": "BTC/USDT", "timeframe": "1h", "require_all": True},
            "default_action": {"asset": "ETH/USDT", "timeframe": "4h", "require_all": True, "direction": "long"},
            "default_risk": {
                "stoploss_pct_values": [-2],
                "take_profit_pct_values": [3],
                "max_hold_bars_values": [24],
            },
            "default_wf": {"train_days": 30, "test_days": 10, "step_days": 10},
            "pruning": {"enabled": False},
        },
    )

    runner_calls = []
    analytics_calls = []

    def _mock_runner_run(exp_cfg: dict) -> dict:
        exp_id = str(exp_cfg.get("experiment_id", ""))
        runner_calls.append(exp_id)
        return {"run_id": f"run_{len(runner_calls):03d}", "experiment_id": exp_id}

    def _mock_analytics_update(exp_cfg: dict) -> None:
        analytics_calls.append(str(exp_cfg.get("experiment_id", "")))

    def _fake_run_scheduler_once(cwd: Path, cli_impl) -> dict:
        _ = cli_impl
        cfg = SchedulerConfig.from_file(cwd / "artifacts" / "scheduler.json")
        queue = ExperimentQueue(queue_path=cwd / "artifacts" / "scheduler_queue.json", config=cfg)
        item = queue.pop()
        if item is None:
            return {"processed": False, "ok": True, "item": None}

        exp_cfg = dict(item.get("experiment_config") or {})
        exp_id = str(exp_cfg.get("experiment_id") or "").strip()
        if exp_id:
            cfg_path = cwd / "artifacts" / "experiments" / exp_id / "config.json"
            cfg_path.parent.mkdir(parents=True, exist_ok=True)
            cfg_path.write_text(json.dumps(exp_cfg, ensure_ascii=False, indent=2), encoding="utf-8")

        run_result = _mock_runner_run(exp_cfg)
        _mock_analytics_update(exp_cfg)
        return {"processed": True, "ok": True, "item": item, "result": run_result}

    monkeypatch.setattr(cron_cmd, "_run_scheduler_queue_once", _fake_run_scheduler_once)

    cli_impl = _FakeCli()
    cycle_rows = []
    queue_path = artifacts / "scheduler_queue.json"

    for _ in range(10):
        row = cron_cmd._run_scheduler_patrol_cycle(
            cwd=tmp_path,
            cli_impl=cli_impl,
            schedule_cron="0 0 * * *",
            max_runs_per_patrol=1,
        )
        cycle_rows.append(row)

        queue_payload = json.loads(queue_path.read_text(encoding="utf-8-sig"))
        assert isinstance(queue_payload, dict)
        assert isinstance(queue_payload.get("items"), list)
        assert isinstance(queue_payload.get("next_seq"), int)

    assert len(cycle_rows) == 10
    assert cycle_rows[0]["discovery_tick"]["enqueued"] == 10
    assert cycle_rows[-1]["discovery_tick"]["enqueued"] == 0
    assert cycle_rows[-1]["discovery_tick"]["generated"] == 10
    assert len(runner_calls) == 10
    assert len(analytics_calls) == 10

    queue = ExperimentQueue(
        queue_path=queue_path,
        config=SchedulerConfig.from_file(artifacts / "scheduler.json"),
    )
    assert queue.size() == 0

    started = time.perf_counter()
    empty_cycle = cron_cmd._run_scheduler_patrol_cycle(
        cwd=tmp_path,
        cli_impl=cli_impl,
        schedule_cron="0 0 * * *",
        max_runs_per_patrol=1,
    )
    elapsed = time.perf_counter() - started
    assert elapsed < 2.0
    assert empty_cycle["scheduler_runs_processed"] == 0
    assert empty_cycle["scheduler_run_once"]["processed"] is False
    assert queue.size() == 0

