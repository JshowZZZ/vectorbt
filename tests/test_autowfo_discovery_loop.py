import json

from autowfo import cli
from autowfo.discovery_loop import DiscoveryLoop
from autowfo.pool_discovery import generate_experiment_configs
from autowfo.scheduler import ExperimentQueue, SchedulerConfig


class DummyAnalyticsStore:
    def __init__(self, rows):
        self.rows = list(rows)

    def query_indicator_leaderboard(self, limit=20):
        return self.rows[: int(limit)]


def _scheduler(tmp_path):
    cfg = SchedulerConfig(priority_order=["user_submitted", "discovery", "refine"], max_concurrent=1, schedule_cron="")
    return ExperimentQueue(queue_path=tmp_path / "scheduler_queue.json", config=cfg)


def test_tick_enqueues_from_top_indicators_and_is_idempotent(tmp_path):
    analytics = DummyAnalyticsStore(
        [
            {"trigger_indicators": '["RSI"]', "action_indicators": "[]"},
            {"trigger_indicators": '["EMA"]', "action_indicators": "[]"},
            {"trigger_indicators": '["MACD"]', "action_indicators": "[]"},
        ]
    )
    loop = DiscoveryLoop(
        pool_config={"combo_size_range": [2, 2], "pruning": {"enabled": False}},
        scheduler=_scheduler(tmp_path),
        analytics_store=analytics,
        experiments_root=tmp_path / "experiments",
    )

    first = loop.tick()
    assert first["generated"] == 3
    assert first["enqueued"] == 3
    assert first["queue_depth"] == 3

    second = loop.tick()
    assert second["generated"] == 3
    assert second["enqueued"] == 0
    assert second["queue_depth"] == 3
    assert second["skipped_existing"] >= 3


def test_tick_filters_existing_experiment_ids(tmp_path):
    top_indicators = ["RSI", "EMA", "MACD"]
    analytics = DummyAnalyticsStore(
        [{"trigger_indicators": json.dumps([item]), "action_indicators": "[]"} for item in top_indicators]
    )
    scheduler = _scheduler(tmp_path)
    experiments_root = tmp_path / "experiments"

    generated = generate_experiment_configs(
        {"indicator_ids": top_indicators, "combo_size_range": [2, 2], "pruning": {"enabled": False}}
    )
    existing_id = generated[0]["experiment_id"]
    cfg_path = experiments_root / existing_id / "config.json"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps({"experiment_id": existing_id}), encoding="utf-8")

    loop = DiscoveryLoop(
        pool_config={"combo_size_range": [2, 2], "pruning": {"enabled": False}},
        scheduler=scheduler,
        analytics_store=analytics,
        experiments_root=experiments_root,
    )
    result = loop.tick()
    assert result["generated"] == 3
    assert result["enqueued"] == 2
    assert result["queue_depth"] == 2
    assert result["skipped_existing"] >= 1


def test_cli_discover_triggers_single_tick_and_persists_queue(tmp_path):
    pool_path = tmp_path / "pool.json"
    pool_path.write_text(
        json.dumps(
            {
                "indicator_ids": ["RSI", "EMA", "MACD"],
                "combo_size_range": [2, 2],
                "pruning": {"enabled": False},
            }
        ),
        encoding="utf-8",
    )

    code = cli.main(["discover", "--pool", str(pool_path), "--cwd", str(tmp_path)])
    assert code == 0

    queue_path = tmp_path / "artifacts" / "scheduler_queue.json"
    payload = json.loads(queue_path.read_text(encoding="utf-8"))
    assert len(payload["items"]) == 3


def test_tick_cold_start_uses_full_pool_expansion(tmp_path, caplog):
    class EmptyAnalyticsStore:
        def query_indicator_leaderboard(self, limit=20):
            _ = limit
            return []

    loop = DiscoveryLoop(
        pool_config={
            "indicator_ids": ["RSI", "EMA", "MACD", "BB"],
            "combo_size_range": [2, 2],
            "pruning": {"enabled": True},
        },
        scheduler=_scheduler(tmp_path),
        analytics_store=EmptyAnalyticsStore(),
        experiments_root=tmp_path / "experiments",
    )

    with caplog.at_level("WARNING"):
        result = loop.tick()

    assert result["generated"] == 6
    assert result["enqueued"] == 6
    assert result["queue_depth"] == 6
    assert "analytics cold-start: using full pool expansion" in caplog.text

