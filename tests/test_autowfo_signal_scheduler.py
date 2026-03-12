import json
from datetime import datetime, timezone

from scripts.autowfo.signal_scheduler import SignalScheduler


class _FakeAnalyticsStore:
    def __init__(self, rows):
        self.rows = list(rows)

    def query_all_time_best(self, limit=1):
        _ = limit
        return list(self.rows)


def _top_row(experiment_id: str, trigger: str = "RSI", action: str = "BB") -> dict:
    return {
        "experiment_id": experiment_id,
        "combo_id": f"combo_{experiment_id}",
        "indicator_params": json.dumps(
            {
                "trigger_indicators": [trigger],
                "action_indicators": [action],
            }
        ),
        "wf_score": 0.9,
        "oos_sharpe": 1.2,
        "oos_win_rate": 0.55,
        "oos_n_trades": 12,
    }


def _now_sequence(*timestamps):
    queue = list(timestamps)

    def _now():
        if queue:
            return queue.pop(0)
        return datetime.now(timezone.utc)

    return _now


def test_signal_scheduler_switches_strategy_close_then_open(tmp_path):
    artifacts = tmp_path / "artifacts"
    analytics = _FakeAnalyticsStore([_top_row("exp_a", trigger="RSI", action="BB")])
    scheduler = SignalScheduler(
        analytics_store=analytics,
        state_path=artifacts / "signal_schedule_state.json",
        export_path=artifacts / "live_signal_config.json",
        positions_path=artifacts / "paper_positions.json",
        schedule_interval_seconds=120,
        now_func=_now_sequence(
            datetime(2026, 3, 1, 1, 0, tzinfo=timezone.utc),
            datetime(2026, 3, 1, 2, 0, tzinfo=timezone.utc),
        ),
    )

    first = scheduler.tick()
    assert first["ok"] is True
    assert first["action"] == "switched_strategy"
    assert first["changed"] is True
    assert first["previous_experiment_id"] is None
    assert first["experiment_id"] == "exp_a"

    analytics.rows = [_top_row("exp_b", trigger="MACD", action="EMA")]
    second = scheduler.tick()
    assert second["ok"] is True
    assert second["action"] == "switched_strategy"
    assert second["changed"] is True
    assert second["previous_experiment_id"] == "exp_a"
    assert second["experiment_id"] == "exp_b"
    assert second["close_result"]["attempted"] is True
    assert second["close_result"]["closed"] is True
    assert second["close_result"]["error"] == ""

    positions_path = artifacts / "paper_positions.json"
    positions = json.loads(positions_path.read_text(encoding="utf-8"))
    assert len(positions) == 2
    assert positions[0]["signal_id"] == "signal::exp_a"
    assert positions[0]["status"] == "closed"
    assert positions[1]["signal_id"] == "signal::exp_b"
    assert positions[1]["status"] == "open"

    state_path = artifacts / "signal_schedule_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert set(state.keys()) >= {
        "tracked_experiment_ids",
        "last_experiment_id",
        "last_export_ts",
        "schedule_interval_seconds",
        "top_n",
    }
    assert state["last_experiment_id"] == "exp_b"
    assert state["schedule_interval_seconds"] == 120
    assert state["tracked_experiment_ids"] == ["exp_b"]
    assert state["last_export_ts"].startswith("2026-03-01T02:00:00")

    export_path = artifacts / "live_signal_config.json"
    exported = json.loads(export_path.read_text(encoding="utf-8"))
    assert exported["experiment_id"] == "exp_b"
    assert exported["trigger_indicator"] == "MACD"
    assert exported["action_indicator"] == "EMA"


def test_signal_scheduler_skips_when_top_strategy_unchanged(tmp_path):
    artifacts = tmp_path / "artifacts"
    analytics = _FakeAnalyticsStore([_top_row("exp_same", trigger="RSI", action="BB")])
    scheduler = SignalScheduler(
        analytics_store=analytics,
        state_path=artifacts / "signal_schedule_state.json",
        export_path=artifacts / "live_signal_config.json",
        positions_path=artifacts / "paper_positions.json",
        now_func=_now_sequence(
            datetime(2026, 3, 1, 1, 0, tzinfo=timezone.utc),
            datetime(2026, 3, 1, 1, 5, tzinfo=timezone.utc),
        ),
    )

    first = scheduler.tick()
    assert first["action"] == "switched_strategy"
    second = scheduler.tick()
    assert second["ok"] is True
    assert second["action"] == "skip_same_strategy"
    assert second["changed"] is False
    assert second["experiment_id"] == "exp_same"

    positions = json.loads((artifacts / "paper_positions.json").read_text(encoding="utf-8"))
    assert len(positions) == 1
    assert positions[0]["status"] == "open"
    assert positions[0]["signal_id"] == "signal::exp_same"


def test_signal_scheduler_top3_opens_and_closes_dropped_strategy(tmp_path):
    artifacts = tmp_path / "artifacts"
    analytics = _FakeAnalyticsStore(
        [
            _top_row("exp_a", trigger="RSI", action="BB"),
            _top_row("exp_b", trigger="MACD", action="EMA"),
            _top_row("exp_c", trigger="CCI", action="VWMA"),
        ]
    )
    scheduler = SignalScheduler(
        analytics_store=analytics,
        state_path=artifacts / "signal_schedule_state.json",
        export_path=artifacts / "live_signal_config.json",
        positions_path=artifacts / "paper_positions.json",
        top_n=3,
        now_func=_now_sequence(
            datetime(2026, 3, 1, 1, 0, tzinfo=timezone.utc),
            datetime(2026, 3, 1, 2, 0, tzinfo=timezone.utc),
        ),
    )

    first = scheduler.tick()
    assert first["ok"] is True
    assert first["changed"] is True
    assert first["tracked_experiment_ids"] == ["exp_a", "exp_b", "exp_c"]
    positions_after_first = json.loads((artifacts / "paper_positions.json").read_text(encoding="utf-8"))
    open_first = [row for row in positions_after_first if row["status"] == "open"]
    assert len(open_first) == 3

    analytics.rows = [
        _top_row("exp_b", trigger="MACD", action="EMA"),
        _top_row("exp_c", trigger="CCI", action="VWMA"),
        _top_row("exp_d", trigger="ADX", action="ATR"),
    ]
    second = scheduler.tick()
    assert second["ok"] is True
    assert second["changed"] is True
    assert second["tracked_experiment_ids"] == ["exp_b", "exp_c", "exp_d"]
    positions_after_second = json.loads((artifacts / "paper_positions.json").read_text(encoding="utf-8"))
    rows_by_signal = {row["signal_id"]: row for row in positions_after_second}
    assert rows_by_signal["signal::exp_a"]["status"] == "closed"
    assert rows_by_signal["signal::exp_d"]["status"] == "open"


def test_signal_scheduler_retry_and_patrol_anomaly_notify(tmp_path, monkeypatch):
    artifacts = tmp_path / "artifacts"
    analytics = _FakeAnalyticsStore([_top_row("exp_retry")])
    scheduler = SignalScheduler(
        analytics_store=analytics,
        state_path=artifacts / "signal_schedule_state.json",
        export_path=artifacts / "live_signal_config.json",
        positions_path=artifacts / "paper_positions.json",
        max_retries=3,
        backoff_cap_seconds=30,
    )

    tick_calls = {"n": 0}
    sleep_calls = []
    notify_calls = []

    def _always_fail_tick():
        tick_calls["n"] += 1
        raise RuntimeError("boom")

    def _fake_sleep(seconds):
        sleep_calls.append(float(seconds))

    def _fake_notify(event_type, payload, config_path=None):
        notify_calls.append(
            {
                "event_type": str(getattr(event_type, "value", event_type)),
                "payload": dict(payload),
                "config_path": config_path,
            }
        )
        return {"ok": True, "sent": [], "skipped": ["config_missing"], "errors": []}

    monkeypatch.setattr(scheduler, "tick", _always_fail_tick)
    import scripts.autowfo.signal_scheduler as signal_scheduler_mod
    monkeypatch.setattr(signal_scheduler_mod, "notify", _fake_notify)

    ticks = scheduler.run_forever(max_ticks=1, sleep_func=_fake_sleep)
    assert ticks == 1
    assert tick_calls["n"] == 4
    assert sleep_calls == [1.0, 2.0, 4.0]
    assert any(row["event_type"] == "PATROL_ANOMALY" for row in notify_calls)
