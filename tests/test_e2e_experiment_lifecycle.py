import http.client
import json
import threading
from contextlib import contextmanager

import pandas as pd
import pytest

from autowfo.control_panel import server as cp
from autowfo.control_panel import experiments as cp_experiments
from autowfo.analytics import AnalyticsStore
from autowfo.artifact_store import ArtifactStore


def _valid_experiment_config(experiment_id: str = "exp_e2e") -> dict:
    return {
        "experiment_id": experiment_id,
        "description": "e2e lifecycle",
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
                    "threshold_values": [50],
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
        "wf": {"train_days": 30, "test_days": 10, "step_days": 10},
    }


def _setup_env(tmp_path, monkeypatch):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(cp, "ROOT", tmp_path)
    monkeypatch.setattr(cp, "ARTIFACTS", artifacts)
    monkeypatch.setattr(cp, "CONFIG_JSON", artifacts / "sweep_config.json")
    monkeypatch.setattr(cp, "CONTROL_JSON", artifacts / "run_control.json")
    monkeypatch.setattr(cp, "RUN_LOG", artifacts / "run_console.log")
    cp.PROCESS = None
    cp.BATCH_PROCESS = None
    cp_experiments._scheduler_reset_runtime_state()
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


def test_e2e_experiment_lifecycle_smoke(tmp_path, monkeypatch):
    artifacts = _setup_env(tmp_path, monkeypatch)
    experiment_id = "exp_e2e_lifecycle"
    config = _valid_experiment_config(experiment_id=experiment_id)

    action_index = pd.date_range("2026-01-01", periods=96, freq="4h", tz="UTC")
    trigger_index = pd.date_range("2026-01-01", periods=384, freq="1h", tz="UTC")

    trigger_ohlcv = pd.DataFrame(
        {
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0 + pd.Series(range(len(trigger_index)), index=trigger_index) * 0.01,
            "volume": 1000.0,
        },
        index=trigger_index,
    )
    action_ohlcv = pd.DataFrame(
        {
            "open": 200.0,
            "high": 201.0,
            "low": 199.0,
            "close": 200.0 + pd.Series(range(len(action_index)), index=action_index) * 0.02,
            "volume": 1500.0,
        },
        index=action_index,
    )

    def _fake_load_experiment_data(*args, **kwargs):
        _ = args, kwargs
        return trigger_ohlcv, action_ohlcv

    monkeypatch.setattr("autowfo.data_multi.load_experiment_data", _fake_load_experiment_data)

    class _FakeTrades:
        def count(self):
            return 12

        def win_rate(self):
            return 0.58

    class _FakePortfolio:
        def __init__(self):
            self.trades = _FakeTrades()

        def sharpe_ratio(self):
            return 1.2

        def total_return(self):
            return 0.15

    monkeypatch.setattr(
        "autowfo.experiment_runner.vbt.Portfolio.from_signals",
        lambda *args, **kwargs: _FakePortfolio(),
    )

    analytics_store = AnalyticsStore(artifacts / "analytics.duckdb")
    analytics_calls = []

    class _SpyAnalyticsStore:
        def __init__(self, inner_store):
            self._inner_store = inner_store

        def update_from_run(self, experiment_id_arg, run_id_arg, artifact_store):
            analytics_calls.append((str(experiment_id_arg), str(run_id_arg)))
            return self._inner_store.update_from_run(experiment_id_arg, run_id_arg, artifact_store)

        def query_indicator_leaderboard(self, limit=20):
            return self._inner_store.query_indicator_leaderboard(limit=limit)

        def query_all_time_best(self, limit=50):
            return self._inner_store.query_all_time_best(limit=limit)

    spy_analytics_store = _SpyAnalyticsStore(analytics_store)
    monkeypatch.setattr(cp_experiments, "_analytics_store", lambda: spy_analytics_store)

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
        assert payload_create["experiment_id"] == experiment_id

        conn.request(
            "POST",
            "/experiments/queue",
            body=json.dumps({"experiment_config": config, "priority": "user_submitted", "auto_start": False}).encode(
                "utf-8"
            ),
            headers={"Content-Type": "application/json"},
        )
        response_queue = conn.getresponse()
        payload_queue = json.loads(response_queue.read().decode("utf-8"))
        assert response_queue.status == 200
        assert payload_queue["ok"] is True
        assert payload_queue["queued"] is True
        assert payload_queue["queue_depth"] == 1

    outcome = cp_experiments._scheduler_run_once()
    assert outcome["processed"] is True
    assert outcome["ok"] is True
    run_id = str(outcome["result"]["run_id"])

    store = ArtifactStore(experiment_id, base_dir=artifacts)
    meta = store.read_run_meta(run_id)
    assert meta["run_id"] == run_id
    assert store.get_run_db_path(run_id).exists()
    run_results = store.query_run_results(run_id=run_id, limit=10)
    assert len(run_results) >= 1

    assert analytics_calls
    assert analytics_calls[0][0] == experiment_id
    assert analytics_calls[0][1] == run_id

    with _serve_handler_connection() as conn:
        conn.request("GET", f"/experiments/{experiment_id}/runs.json")
        response_runs = conn.getresponse()
        payload_runs = json.loads(response_runs.read().decode("utf-8"))
        assert response_runs.status == 200
        assert payload_runs["total"] == 1
        assert payload_runs["runs"][0]["run_id"] == run_id

        conn.request("GET", "/analytics/leaderboard.json")
        response_lb = conn.getresponse()
        payload_lb = json.loads(response_lb.read().decode("utf-8"))
        assert response_lb.status == 200
        pytest.importorskip("duckdb", reason="duckdb not installed; skip leaderboard assertion")
        assert payload_lb["total"] >= 1
        assert len(payload_lb["indicators"]) >= 1

