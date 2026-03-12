import json

from scripts.autowfo.scheduler import ExperimentQueue, SchedulerConfig


def _exp_cfg(exp_id):
    return {"experiment_id": exp_id, "mode": "hypothesis"}


def test_priority_ordering_pop_sequence(tmp_path):
    cfg = SchedulerConfig(priority_order=["user_submitted", "discovery", "refine"], max_concurrent=1, schedule_cron="")
    queue = ExperimentQueue(queue_path=tmp_path / "scheduler_queue.json", config=cfg)
    queue.add(_exp_cfg("exp_refine"), priority="refine")
    queue.add(_exp_cfg("exp_discovery"), priority="discovery")
    queue.add(_exp_cfg("exp_user"), priority="user_submitted")

    assert queue.size() == 3
    assert queue.pop()["experiment_id"] == "exp_user"
    assert queue.pop()["experiment_id"] == "exp_discovery"
    assert queue.pop()["experiment_id"] == "exp_refine"


def test_persist_and_reload_state_consistent(tmp_path):
    queue_path = tmp_path / "scheduler_queue.json"
    cfg = SchedulerConfig(priority_order=["user_submitted", "discovery", "refine"], max_concurrent=1, schedule_cron="")
    queue_a = ExperimentQueue(queue_path=queue_path, config=cfg)
    queue_a.add(_exp_cfg("exp_a"), priority="discovery")
    queue_a.add(_exp_cfg("exp_b"), priority="refine")

    queue_b = ExperimentQueue(queue_path=queue_path, config=cfg)
    assert queue_b.size() == 2
    assert queue_b.peek()["experiment_id"] == "exp_a"
    raw = json.loads(queue_path.read_text(encoding="utf-8"))
    assert raw["next_seq"] == 3
    assert len(raw["items"]) == 2


def test_empty_pop_returns_none(tmp_path):
    queue = ExperimentQueue(queue_path=tmp_path / "scheduler_queue.json")
    assert queue.pop() is None
    assert queue.peek() is None
    assert queue.size() == 0
