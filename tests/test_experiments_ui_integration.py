import http.client
import json
import threading
from contextlib import contextmanager

from autowfo.control_panel import server as cp
from autowfo.control_panel import experiments as cp_experiments


def _valid_experiment_config(experiment_id="exp_demo"):
    return {
        "experiment_id": experiment_id,
        "description": "demo",
        "version": 1,
        "created_utc": "2026-03-01T00:00:00Z",
        "mode": "hypothesis",
        "trigger": {
            "asset": "BTC/USDT",
            "timeframe": "1h",
            "indicators": ["RSI"],
            "conditions": {
                "RSI": {
                    "operator": "below",
                    "param_name": "rsi_period",
                    "param_values": [14],
                    "threshold_values": [30],
                }
            },
            "require_all": True,
        },
        "action": {
            "asset": "ETH/USDT",
            "timeframe": "4h",
            "indicators": ["EMA"],
            "conditions": {
                "EMA": {
                    "operator": "above",
                    "param_name": "ema_period",
                    "param_values": [20],
                    "threshold_values": [0],
                }
            },
            "require_all": True,
            "direction": "both",
        },
        "risk": {
            "stoploss_pct_values": [-3],
            "take_profit_pct_values": [5],
            "max_hold_bars_values": [24],
        },
        "wf": {"train_days": 90, "test_days": 30, "step_days": 30},
    }


def _setup_env(tmp_path, monkeypatch):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    cp.configure_runtime(
        root=tmp_path,
        artifacts_dir=artifacts,
        config_json=artifacts / "sweep_config.json",
        control_json=artifacts / "run_control.json",
        run_log=artifacts / "run_console.log",
        reset_state=True,
    )
    return artifacts


@contextmanager
def _serve_handler_connection(timeout=10):
    server = cp.ThreadingHTTPServer(("127.0.0.1", 0), cp.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    conn = None
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=timeout)
        yield conn
    finally:
        if conn is not None:
            conn.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_create_list_delete_roundtrip(tmp_path, monkeypatch):
    _setup_env(tmp_path, monkeypatch)
    config = _valid_experiment_config("exp_ui_roundtrip")

    with _serve_handler_connection() as conn:
        conn.request(
            "POST",
            "/experiments/create",
            body=json.dumps(config).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response_create = conn.getresponse()
        payload_create = json.loads(response_create.read().decode("utf-8"))
        assert response_create.status == 200
        assert payload_create["ok"] is True

        conn.request("GET", "/experiments.json")
        response_list_a = conn.getresponse()
        payload_list_a = json.loads(response_list_a.read().decode("utf-8"))
        assert response_list_a.status == 200
        assert payload_list_a["total"] == 1
        assert payload_list_a["experiments"][0]["experiment_id"] == "exp_ui_roundtrip"

        conn.request("DELETE", "/experiments/exp_ui_roundtrip")
        response_delete = conn.getresponse()
        payload_delete = json.loads(response_delete.read().decode("utf-8"))
        assert response_delete.status == 200
        assert payload_delete["ok"] is True

        conn.request("GET", "/experiments.json")
        response_list_b = conn.getresponse()
        payload_list_b = json.loads(response_list_b.read().decode("utf-8"))
        assert response_list_b.status == 200
        assert payload_list_b == {"experiments": [], "total": 0}


def test_queue_status_depth_plus_one_then_run_once_minus_one(tmp_path, monkeypatch):
    _setup_env(tmp_path, monkeypatch)
    config = _valid_experiment_config("exp_ui_queue")
    executed = []

    def _fake_execute(item):
        exp_cfg = item.get("experiment_config") or {}
        exp_id = str(exp_cfg.get("experiment_id") or "")
        executed.append(exp_id)
        return {"experiment_id": exp_id, "run_id": "run_001", "n_combos": 1, "n_completed": 1, "n_errors": 0}

    monkeypatch.setattr(cp_experiments, "_execute_scheduled_experiment", _fake_execute)

    with _serve_handler_connection() as conn:
        conn.request(
            "POST",
            "/experiments/create",
            body=json.dumps(config).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response_create = conn.getresponse()
        assert response_create.status == 200
        _ = response_create.read()

        queue_payload = {"experiment_config": config, "priority": "discovery", "auto_start": False}
        conn.request(
            "POST",
            "/experiments/queue",
            body=json.dumps(queue_payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response_queue = conn.getresponse()
        payload_queue = json.loads(response_queue.read().decode("utf-8"))
        assert response_queue.status == 200
        assert payload_queue["queued"] is True

        conn.request("GET", "/scheduler/status.json")
        response_status_a = conn.getresponse()
        payload_status_a = json.loads(response_status_a.read().decode("utf-8"))
        assert response_status_a.status == 200
        assert payload_status_a["queue_depth"] == 1
        assert payload_status_a["next_experiment_id"] == "exp_ui_queue"

    outcome = cp_experiments._scheduler_run_once()
    assert outcome["processed"] is True
    assert outcome["ok"] is True
    assert executed == ["exp_ui_queue"]

    with _serve_handler_connection() as conn:
        conn.request("GET", "/scheduler/status.json")
        response_status_b = conn.getresponse()
        payload_status_b = json.loads(response_status_b.read().decode("utf-8"))
        assert response_status_b.status == 200
        assert payload_status_b["queue_depth"] == 0
        assert payload_status_b["next_experiment_id"] is None


def test_discovery_tick_enqueues_new_items(tmp_path, monkeypatch):
    _setup_env(tmp_path, monkeypatch)

    class DummyAnalyticsStore:
        def query_indicator_leaderboard(self, limit=20):
            _ = limit
            return [
                {"trigger_indicators": '["RSI"]', "action_indicators": "[]"},
                {"trigger_indicators": '["EMA"]', "action_indicators": "[]"},
                {"trigger_indicators": '["MACD"]', "action_indicators": "[]"},
            ]

    monkeypatch.setattr(cp_experiments, "_analytics_store", lambda: DummyAnalyticsStore())
    tick_payload = {
        "pool_config": {
            "combo_size_range": [2, 2],
            "pruning": {"enabled": False},
        },
        "auto_start": False,
    }

    with _serve_handler_connection() as conn:
        conn.request(
            "POST",
            "/discovery/tick",
            body=json.dumps(tick_payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response_tick = conn.getresponse()
        payload_tick = json.loads(response_tick.read().decode("utf-8"))
        assert response_tick.status == 200
        assert payload_tick["ok"] is True
        assert payload_tick["tick"]["generated"] == 3
        assert payload_tick["tick"]["enqueued"] == 3

        conn.request("GET", "/scheduler/status.json")
        response_status = conn.getresponse()
        payload_status = json.loads(response_status.read().decode("utf-8"))
        assert response_status.status == 200
        assert payload_status["queue_depth"] == 3

