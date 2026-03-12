import http.client
import json
import threading
import time
from contextlib import contextmanager

from scripts import control_panel as cp
from scripts import control_panel_experiments as cp_experiments
from scripts.autowfo.artifact_store import ArtifactStore


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
            "indicators": ["BB"],
            "conditions": {"BB": {"operator": "near_lower", "bb_period_values": [20], "pct_values": [0.02]}},
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


def test_get_experiments_list_shape_with_zero_and_two_experiments(tmp_path, monkeypatch):
    artifacts = _setup_env(tmp_path, monkeypatch)
    with _serve_handler_connection() as conn:
        conn.request("GET", "/experiments.json")
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        assert response.status == 200
        assert payload == {"experiments": [], "total": 0}

    exp_root = artifacts / "experiments"
    exp_a = exp_root / "exp_a"
    exp_b = exp_root / "exp_b"
    exp_a.mkdir(parents=True)
    exp_b.mkdir(parents=True)
    (exp_a / "config.json").write_text(json.dumps(_valid_experiment_config("exp_a")), encoding="utf-8")
    (exp_b / "config.json").write_text(json.dumps(_valid_experiment_config("exp_b")), encoding="utf-8")
    run_dir = exp_a / "runs" / "20260301_020000"
    run_dir.mkdir(parents=True)
    (run_dir / "run_meta.json").write_text(
        json.dumps({"last_run_utc": "2026-03-01T02:00:00Z", "best_oos_sharpe": 1.23}),
        encoding="utf-8",
    )

    with _serve_handler_connection() as conn:
        conn.request("GET", "/experiments.json")
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        assert response.status == 200
        assert payload["total"] == 2
        rows = {row["experiment_id"]: row for row in payload["experiments"]}
        assert set(rows.keys()) == {"exp_a", "exp_b"}
        assert rows["exp_a"]["runs"] == 1
        assert rows["exp_a"]["last_run_utc"] == "2026-03-01T02:00:00Z"
        assert rows["exp_a"]["best_oos_sharpe"] == 1.23
        assert rows["exp_b"]["runs"] == 0
        assert rows["exp_b"]["status"] == "idle"


def test_post_experiments_create_valid_and_invalid(tmp_path, monkeypatch):
    artifacts = _setup_env(tmp_path, monkeypatch)
    valid = _valid_experiment_config("exp_create_ok")
    invalid = _valid_experiment_config("exp_create_bad")
    invalid["mode"] = "invalid_mode"

    with _serve_handler_connection() as conn:
        conn.request(
            "POST",
            "/experiments/create",
            body=json.dumps(valid).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response_ok = conn.getresponse()
        payload_ok = json.loads(response_ok.read().decode("utf-8"))
        assert response_ok.status == 200
        assert payload_ok["ok"] is True
        assert payload_ok["experiment_id"] == "exp_create_ok"

        config_path = artifacts / "experiments" / "exp_create_ok" / "config.json"
        assert config_path.exists()

        conn.request(
            "POST",
            "/experiments/create",
            body=json.dumps(invalid).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response_bad = conn.getresponse()
        payload_bad = json.loads(response_bad.read().decode("utf-8"))
        assert response_bad.status == 400
        assert "error" in payload_bad
        assert "field" in payload_bad


def test_get_experiment_config_existing_and_missing(tmp_path, monkeypatch):
    artifacts = _setup_env(tmp_path, monkeypatch)
    config = _valid_experiment_config("exp_cfg")
    cfg_path = artifacts / "experiments" / "exp_cfg" / "config.json"
    cfg_path.parent.mkdir(parents=True)
    cfg_path.write_text(json.dumps(config), encoding="utf-8")

    with _serve_handler_connection() as conn:
        conn.request("GET", "/experiments/exp_cfg/config.json")
        response_ok = conn.getresponse()
        payload_ok = json.loads(response_ok.read().decode("utf-8"))
        assert response_ok.status == 200
        assert payload_ok["experiment_id"] == "exp_cfg"

        conn.request("GET", "/experiments/not_exists/config.json")
        response_404 = conn.getresponse()
        payload_404 = json.loads(response_404.read().decode("utf-8"))
        assert response_404.status == 404
        assert "error" in payload_404


def test_delete_experiment_success_and_conflict_on_runs(tmp_path, monkeypatch):
    artifacts = _setup_env(tmp_path, monkeypatch)
    exp_delete = artifacts / "experiments" / "exp_delete"
    exp_delete.mkdir(parents=True)
    (exp_delete / "config.json").write_text(json.dumps(_valid_experiment_config("exp_delete")), encoding="utf-8")

    exp_busy = artifacts / "experiments" / "exp_busy"
    (exp_busy / "runs" / "20260301_020000").mkdir(parents=True)
    (exp_busy / "config.json").write_text(json.dumps(_valid_experiment_config("exp_busy")), encoding="utf-8")

    with _serve_handler_connection() as conn:
        conn.request("DELETE", "/experiments/exp_delete")
        response_ok = conn.getresponse()
        payload_ok = json.loads(response_ok.read().decode("utf-8"))
        assert response_ok.status == 200
        assert payload_ok["ok"] is True
        assert not (exp_delete / "config.json").exists()

        conn.request("DELETE", "/experiments/exp_busy")
        response_conflict = conn.getresponse()
        payload_conflict = json.loads(response_conflict.read().decode("utf-8"))
        assert response_conflict.status == 409
        assert payload_conflict["error"] == "experiment has runs, cannot delete"


def test_post_experiment_run_adds_job_to_batch_queue(tmp_path, monkeypatch):
    artifacts = _setup_env(tmp_path, monkeypatch)
    exp_id = "exp_queue"
    cfg_path = artifacts / "experiments" / exp_id / "config.json"
    cfg_path.parent.mkdir(parents=True)
    cfg_path.write_text(json.dumps(_valid_experiment_config(exp_id)), encoding="utf-8")

    with _serve_handler_connection() as conn:
        conn.request(
            "POST",
            f"/experiments/{exp_id}/run",
            body=json.dumps({}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        assert response.status == 200
        assert payload["ok"] is True
        assert payload["queued"] is True
        assert payload["job_id"]

    queue_path = artifacts / "batch_queue.json"
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    assert len(queue["jobs"]) == 1
    assert queue["jobs"][0]["workflow"] == "run"
    assert queue["jobs"][0]["config"] == str(cfg_path)


def _insert_combo_row(conn, *, combo_id, experiment_id, run_id, wf_score):
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
            combo_id,
            experiment_id,
            run_id,
            "long",
            "BTC/USDT",
            "ETH/USDT",
            "{\"trigger\":\"RSI\"}",
            "{\"operator\":\"below\"}",
            "{\"risk_stoploss_pct\":-2}",
            1.0,
            0.5,
            10,
            0.2,
            wf_score,
            "2026-03-01T00:00:00+00:00",
        ),
    )


def test_get_experiment_runs_list_endpoint(tmp_path, monkeypatch):
    artifacts = _setup_env(tmp_path, monkeypatch)
    exp_id = "exp_runs_api"
    exp_dir = artifacts / "experiments" / exp_id
    exp_dir.mkdir(parents=True)
    (exp_dir / "config.json").write_text(json.dumps(_valid_experiment_config(exp_id)), encoding="utf-8")

    with _serve_handler_connection() as conn:
        conn.request("GET", f"/experiments/{exp_id}/runs.json")
        response_empty = conn.getresponse()
        payload_empty = json.loads(response_empty.read().decode("utf-8"))
        assert response_empty.status == 200
        assert payload_empty == {"experiment_id": exp_id, "runs": [], "total": 0}

    store = ArtifactStore(exp_id, base_dir=artifacts)
    store.init_run("20260301_020000")
    store.write_run_meta(
        "20260301_020000",
        {"run_id": "20260301_020000", "n_combos": 2, "best_oos_sharpe": 0.7, "duration_seconds": 12.3},
    )
    store.init_run("20260302_030000")
    store.write_run_meta(
        "20260302_030000",
        {"run_id": "20260302_030000", "n_combos": 3, "best_oos_sharpe": 1.8, "duration_seconds": 22.5},
    )

    with _serve_handler_connection() as conn:
        conn.request("GET", f"/experiments/{exp_id}/runs.json")
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        assert response.status == 200
        assert payload["experiment_id"] == exp_id
        assert payload["total"] == 2
        assert [row["run_id"] for row in payload["runs"]] == ["20260301_020000", "20260302_030000"]
        assert payload["runs"][1]["n_combos"] == 3
        assert payload["runs"][1]["n_completed"] == 0
        assert payload["runs"][1]["n_errors"] == 0
        assert payload["runs"][1]["best_oos_sharpe"] == 1.8
        assert payload["runs"][1]["duration_seconds"] == 22.5

        conn.request("GET", "/experiments/not_exists/runs.json")
        response_404 = conn.getresponse()
        payload_404 = json.loads(response_404.read().decode("utf-8"))
        assert response_404.status == 404
        assert payload_404["error"] == "experiment not found"


def test_get_experiment_run_results_endpoint_with_limit_and_not_found(tmp_path, monkeypatch):
    artifacts = _setup_env(tmp_path, monkeypatch)
    exp_id = "exp_results_api"
    exp_dir = artifacts / "experiments" / exp_id
    exp_dir.mkdir(parents=True)
    (exp_dir / "config.json").write_text(json.dumps(_valid_experiment_config(exp_id)), encoding="utf-8")

    store = ArtifactStore(exp_id, base_dir=artifacts)
    run_id = "20260301_020000"
    conn_db = store.init_results_db(run_id)
    try:
        _insert_combo_row(conn_db, combo_id="combo_low", experiment_id=exp_id, run_id=run_id, wf_score=0.1)
        _insert_combo_row(conn_db, combo_id="combo_high", experiment_id=exp_id, run_id=run_id, wf_score=0.9)
        conn_db.commit()
    finally:
        conn_db.close()

    with _serve_handler_connection() as conn:
        conn.request("GET", f"/experiments/{exp_id}/runs/{run_id}/results.json?limit=1")
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        assert response.status == 200
        assert payload["run_id"] == run_id
        assert payload["total"] == 1
        row = payload["results"][0]
        assert row["combo_id"] == "combo_high"
        assert set(row.keys()) == {
            "combo_id",
            "direction",
            "indicator_params",
            "condition_params",
            "risk_params",
            "oos_sharpe",
            "oos_win_rate",
            "oos_n_trades",
            "wf_score",
        }

        conn.request("GET", f"/experiments/{exp_id}/runs/not_exists/results.json")
        response_run_404 = conn.getresponse()
        payload_run_404 = json.loads(response_run_404.read().decode("utf-8"))
        assert response_run_404.status == 404
        assert payload_run_404["error"] == "run not found"

        conn.request("GET", "/experiments/not_exists/runs/20260301_020000/results.json")
        response_exp_404 = conn.getresponse()
        payload_exp_404 = json.loads(response_exp_404.read().decode("utf-8"))
        assert response_exp_404.status == 404
        assert payload_exp_404["error"] == "experiment not found"


def test_post_experiments_queue_and_scheduler_status_depth_changes(tmp_path, monkeypatch):
    artifacts = _setup_env(tmp_path, monkeypatch)
    executed = []

    def _fake_execute(item):
        exp_cfg = item.get("experiment_config") or {}
        exp_id = str(exp_cfg.get("experiment_id"))
        run_id = f"run_{len(executed) + 1:03d}"
        store = ArtifactStore(exp_id, base_dir=artifacts)
        store.init_run(run_id)
        store.write_run_meta(
            run_id,
            {
                "run_id": run_id,
                "experiment_id": exp_id,
                "n_combos": 1,
                "n_completed": 1,
                "n_errors": 0,
                "best_oos_sharpe": 0.5,
                "duration_seconds": 0.01,
            },
        )
        executed.append(exp_id)
        return {"experiment_id": exp_id, "run_id": run_id, "n_combos": 1, "n_completed": 1, "n_errors": 0}

    monkeypatch.setattr(cp_experiments, "_execute_scheduled_experiment", _fake_execute)
    payload_a = {"experiment_config": _valid_experiment_config("exp_sched_a"), "priority": "discovery"}
    payload_b = {"experiment_config": _valid_experiment_config("exp_sched_b"), "priority": "discovery"}

    with _serve_handler_connection() as conn:
        conn.request(
            "POST",
            "/experiments/queue",
            body=json.dumps(payload_a).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response_a = conn.getresponse()
        body_a = json.loads(response_a.read().decode("utf-8"))
        assert response_a.status == 200
        assert body_a["queued"] is True
        assert body_a["queue_depth"] == 1

        conn.request(
            "POST",
            "/experiments/queue",
            body=json.dumps(payload_b).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response_b = conn.getresponse()
        body_b = json.loads(response_b.read().decode("utf-8"))
        assert response_b.status == 200
        assert body_b["queued"] is True
        assert body_b["queue_depth"] == 2

        conn.request("GET", "/scheduler/status.json")
        response_status = conn.getresponse()
        status_payload = json.loads(response_status.read().decode("utf-8"))
        assert response_status.status == 200
        assert status_payload["queue_depth"] == 2
        assert status_payload["next_experiment_id"] == "exp_sched_a"
        assert status_payload["is_running"] is False
        assert set(status_payload.keys()) >= {"queue_depth", "next_experiment_id", "is_running"}

    outcome = cp_experiments._scheduler_run_once()
    assert outcome["processed"] is True
    assert outcome["ok"] is True
    assert executed == ["exp_sched_a"]

    with _serve_handler_connection() as conn:
        conn.request("GET", "/scheduler/status.json")
        response_after = conn.getresponse()
        payload_after = json.loads(response_after.read().decode("utf-8"))
        assert response_after.status == 200
        assert payload_after["queue_depth"] == 1
        assert payload_after["next_experiment_id"] == "exp_sched_b"


def test_get_analytics_endpoints_payload_shape(tmp_path, monkeypatch):
    _setup_env(tmp_path, monkeypatch)

    class DummyAnalyticsStore:
        def query_indicator_leaderboard(self, limit=20):
            _ = limit
            return [{"trigger_indicators": '["RSI"]', "n_combos": 2}]

        def query_all_time_best(self, limit=50):
            _ = limit
            return [{"combo_id": "combo_top", "wf_score": 0.9}]

        def query_indicator_coverage_map(self):
            return [{"indicator_a": "RSI", "indicator_b": "MACD", "tested": True, "avg_sharpe": 1.2}]

        def query_analytics_growth(self):
            return {
                "total_experiments": 2,
                "total_runs": 3,
                "total_combos": 7,
                "leaderboard_size": 4,
            }

    monkeypatch.setattr(cp_experiments, "_analytics_store", lambda: DummyAnalyticsStore())

    with _serve_handler_connection() as conn:
        conn.request("GET", "/analytics/leaderboard.json")
        response_leaderboard = conn.getresponse()
        payload_leaderboard = json.loads(response_leaderboard.read().decode("utf-8"))
        assert response_leaderboard.status == 200
        assert payload_leaderboard["total"] == 1
        assert payload_leaderboard["indicators"][0]["n_combos"] == 2

        conn.request("GET", "/analytics/best.json")
        response_best = conn.getresponse()
        payload_best = json.loads(response_best.read().decode("utf-8"))
        assert response_best.status == 200
        assert payload_best["total"] == 1
        assert payload_best["combos"][0]["combo_id"] == "combo_top"

        conn.request("GET", "/analytics/coverage-map.json")
        response_cov = conn.getresponse()
        payload_cov = json.loads(response_cov.read().decode("utf-8"))
        assert response_cov.status == 200
        assert payload_cov["total"] == 1
        assert payload_cov["pairs"][0]["indicator_a"] == "RSI"

        conn.request("GET", "/analytics/growth.json")
        response_growth = conn.getresponse()
        payload_growth = json.loads(response_growth.read().decode("utf-8"))
        assert response_growth.status == 200
        assert payload_growth["growth"]["total_experiments"] == 2
        assert payload_growth["growth"]["leaderboard_size"] == 4


def test_get_analytics_report_html_endpoint_returns_html(tmp_path, monkeypatch):
    _setup_env(tmp_path, monkeypatch)

    class DummyAnalyticsStore:
        def query_indicator_leaderboard(self, limit=10):
            _ = limit
            return [
                {
                    "trigger_indicators": '["RSI"]',
                    "action_indicators": '["BB"]',
                    "avg_sharpe": 1.2,
                    "avg_win_rate": 0.55,
                    "n_combos": 5,
                    "n_experiments": 2,
                    "paper_avg_pnl": 1.1,
                }
            ]

        def query_experiment_comparison(self):
            return [
                {
                    "experiment_id": "exp_html",
                    "avg_oos_sharpe": 1.0,
                    "avg_oos_win_rate": 0.5,
                    "total_combos": 10,
                    "total_runs": 2,
                    "best_wf_score": 0.8,
                }
            ]

    monkeypatch.setattr(cp_experiments, "_analytics_store", lambda: DummyAnalyticsStore())

    with _serve_handler_connection() as conn:
        conn.request("GET", "/analytics/report.html")
        response = conn.getresponse()
        body = response.read().decode("utf-8")
        content_type = response.getheader("Content-Type", "")
        assert response.status == 200
        assert "text/html" in content_type
        assert "AUTOWFO Research Report" in body
        assert "Indicator Leaderboard (Top 10)" in body
        assert "trigger_indicators" in body


def test_post_scheduler_stop_graceful_worker_exit(tmp_path, monkeypatch):
    _setup_env(tmp_path, monkeypatch)

    def _slow_execute(item):
        _ = item
        time.sleep(0.2)
        return {
            "experiment_id": "exp_stop",
            "run_id": "run_001",
            "n_combos": 1,
            "n_completed": 1,
            "n_errors": 0,
        }

    monkeypatch.setattr(cp_experiments, "_execute_scheduled_experiment", _slow_execute)
    payload = {"experiment_config": _valid_experiment_config("exp_stop"), "priority": "discovery", "auto_start": True}

    with _serve_handler_connection(timeout=10) as conn:
        conn.request(
            "POST",
            "/experiments/queue",
            body=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response_queue_a = conn.getresponse()
        body_queue_a = json.loads(response_queue_a.read().decode("utf-8"))
        assert response_queue_a.status == 200
        assert body_queue_a["queued"] is True
        assert body_queue_a["worker_started"] is True

        conn.request(
            "POST",
            "/experiments/queue",
            body=json.dumps({"experiment_config": _valid_experiment_config("exp_stop_2"), "priority": "discovery"}).encode(
                "utf-8"
            ),
            headers={"Content-Type": "application/json"},
        )
        response_queue_b = conn.getresponse()
        _ = json.loads(response_queue_b.read().decode("utf-8"))
        assert response_queue_b.status == 200

        conn.request(
            "POST",
            "/scheduler/stop",
            body=b"{}",
            headers={"Content-Type": "application/json"},
        )
        response_stop = conn.getresponse()
        payload_stop = json.loads(response_stop.read().decode("utf-8"))
        assert response_stop.status == 200
        assert payload_stop["ok"] is True
        assert payload_stop["stopped"] is True
        assert payload_stop["thread_alive"] is False

    deadline = time.time() + 5.0
    while time.time() < deadline:
        thread = getattr(cp_experiments, "_SCHEDULER_THREAD", None)
        if thread is None or not thread.is_alive():
            break
        time.sleep(0.05)
    thread = getattr(cp_experiments, "_SCHEDULER_THREAD", None)
    assert thread is None or not thread.is_alive()


def test_get_analytics_endpoints_empty_on_store_failure(tmp_path, monkeypatch):
    _setup_env(tmp_path, monkeypatch)

    class FailingAnalyticsStore:
        def query_indicator_leaderboard(self, limit=20):
            _ = limit
            raise RuntimeError("no duckdb")

        def query_all_time_best(self, limit=50):
            _ = limit
            raise RuntimeError("no duckdb")

        def query_indicator_coverage_map(self):
            raise RuntimeError("no duckdb")

        def query_analytics_growth(self):
            raise RuntimeError("no duckdb")

    monkeypatch.setattr(cp_experiments, "_analytics_store", lambda: FailingAnalyticsStore())

    with _serve_handler_connection() as conn:
        conn.request("GET", "/analytics/leaderboard.json")
        response_leaderboard = conn.getresponse()
        payload_leaderboard = json.loads(response_leaderboard.read().decode("utf-8"))
        assert response_leaderboard.status == 200
        assert payload_leaderboard == {"indicators": [], "total": 0}

        conn.request("GET", "/analytics/best.json")
        response_best = conn.getresponse()
        payload_best = json.loads(response_best.read().decode("utf-8"))
        assert response_best.status == 200
        assert payload_best == {"combos": [], "total": 0}

        conn.request("GET", "/analytics/coverage-map.json")
        response_cov = conn.getresponse()
        payload_cov = json.loads(response_cov.read().decode("utf-8"))
        assert response_cov.status == 200
        assert payload_cov == {"pairs": [], "total": 0}

        conn.request("GET", "/analytics/growth.json")
        response_growth = conn.getresponse()
        payload_growth = json.loads(response_growth.read().decode("utf-8"))
        assert response_growth.status == 200
        assert payload_growth == {
            "growth": {
                "total_experiments": 0,
                "total_runs": 0,
                "total_combos": 0,
                "leaderboard_size": 0,
            }
        }


def test_post_discovery_tick_invalid_pool_returns_structured_error(tmp_path, monkeypatch):
    _setup_env(tmp_path, monkeypatch)

    with _serve_handler_connection() as conn:
        conn.request(
            "POST",
            "/discovery/tick",
            body=json.dumps({"pool_path": "artifacts/not_exists_pool.json"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        assert response.status == 400
        assert payload["ok"] is False
        assert payload["error_code"] == "invalid_pool_config"
        assert isinstance(payload.get("message"), str) and payload["message"]


def test_post_experiments_queue_invalid_payload_returns_structured_error(tmp_path, monkeypatch):
    _setup_env(tmp_path, monkeypatch)
    invalid_payload = {
        "experiment_config": {
            "experiment_id": "bad-exp",
            "mode": "invalid_mode",
        }
    }

    with _serve_handler_connection() as conn:
        conn.request(
            "POST",
            "/experiments/queue",
            body=json.dumps(invalid_payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        assert response.status == 400
        assert payload["ok"] is False
        assert payload["error_code"] == "invalid_experiment_config"
        assert isinstance(payload.get("message"), str) and payload["message"]


def test_paper_position_endpoints_open_close_and_list(tmp_path, monkeypatch):
    _setup_env(tmp_path, monkeypatch)

    with _serve_handler_connection() as conn:
        conn.request(
            "POST",
            "/paper/open",
            body=json.dumps(
                {
                    "signal_id": "sig_ep_1",
                    "experiment_id": "exp_ep_1",
                    "open_price": 100.0,
                    "open_ts": "2026-03-01T00:00:00Z",
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response_open = conn.getresponse()
        payload_open = json.loads(response_open.read().decode("utf-8"))
        assert response_open.status == 200
        assert payload_open["ok"] is True
        assert payload_open["position"]["status"] == "open"

        conn.request("GET", "/paper/positions.json")
        response_list_a = conn.getresponse()
        payload_list_a = json.loads(response_list_a.read().decode("utf-8"))
        assert response_list_a.status == 200
        assert payload_list_a["total"] == 1
        assert set(payload_list_a["positions"][0].keys()) == {
            "signal_id",
            "experiment_id",
            "open_ts",
            "open_price",
            "close_ts",
            "close_price",
            "pnl_pct",
            "status",
        }

        conn.request(
            "POST",
            "/paper/close",
            body=json.dumps(
                {
                    "signal_id": "sig_ep_1",
                    "close_price": 110.0,
                    "close_ts": "2026-03-01T01:00:00Z",
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response_close = conn.getresponse()
        payload_close = json.loads(response_close.read().decode("utf-8"))
        assert response_close.status == 200
        assert payload_close["ok"] is True
        assert payload_close["position"]["status"] == "closed"
        assert round(payload_close["pnl_pct"], 8) == 10.0

        conn.request("GET", "/paper/positions.json")
        response_list_b = conn.getresponse()
        payload_list_b = json.loads(response_list_b.read().decode("utf-8"))
        assert response_list_b.status == 200
        assert payload_list_b["total"] == 1
        assert payload_list_b["positions"][0]["status"] == "closed"


def test_paper_portfolio_endpoint_returns_open_positions_with_unrealized_pnl(tmp_path, monkeypatch):
    artifacts = _setup_env(tmp_path, monkeypatch)
    (artifacts / "paper_latest_prices.json").write_text(
        json.dumps({"signals": {"sig_pf_1": 120.0, "sig_pf_2": 90.0}}),
        encoding="utf-8",
    )

    with _serve_handler_connection() as conn:
        for signal_id, open_price in [("sig_pf_1", 100.0), ("sig_pf_2", 100.0)]:
            conn.request(
                "POST",
                "/paper/open",
                body=json.dumps(
                    {
                        "signal_id": signal_id,
                        "experiment_id": f"exp_{signal_id}",
                        "open_price": open_price,
                        "open_ts": "2026-03-01T00:00:00Z",
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            response_open = conn.getresponse()
            _ = json.loads(response_open.read().decode("utf-8"))
            assert response_open.status == 200

        conn.request("GET", "/paper/portfolio.json")
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        assert response.status == 200
        assert payload["open_total"] == 2
        assert len(payload["positions"]) == 2
        assert set(payload["positions"][0].keys()) >= {
            "signal_id",
            "experiment_id",
            "status",
            "mark_price",
            "unrealized_pnl_pct",
        }
        rows = {row["signal_id"]: row for row in payload["positions"]}
        assert round(float(rows["sig_pf_1"]["unrealized_pnl_pct"]), 8) == 20.0
        assert round(float(rows["sig_pf_2"]["unrealized_pnl_pct"]), 8) == -10.0
        assert round(float(payload["total_unrealized_pnl_pct"]), 8) == 10.0


def test_paper_close_endpoint_calls_analytics_feedback(tmp_path, monkeypatch):
    _setup_env(tmp_path, monkeypatch)
    calls = []

    class DummyAnalytics:
        def add_paper_feedback(self, experiment_id, pnl_pct, close_ts):
            calls.append(
                {
                    "experiment_id": experiment_id,
                    "pnl_pct": pnl_pct,
                    "close_ts": close_ts,
                }
            )
            return 1

    monkeypatch.setattr(cp_experiments, "_analytics_store", lambda: DummyAnalytics())

    with _serve_handler_connection() as conn:
        conn.request(
            "POST",
            "/paper/open",
            body=json.dumps(
                {
                    "signal_id": "sig_ep_2",
                    "experiment_id": "exp_ep_2",
                    "open_price": 100.0,
                    "open_ts": "2026-03-01T00:00:00Z",
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response_open = conn.getresponse()
        _ = json.loads(response_open.read().decode("utf-8"))
        assert response_open.status == 200

        conn.request(
            "POST",
            "/paper/close",
            body=json.dumps(
                {
                    "signal_id": "sig_ep_2",
                    "close_price": 90.0,
                    "close_ts": "2026-03-01T01:00:00Z",
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response_close = conn.getresponse()
        payload_close = json.loads(response_close.read().decode("utf-8"))
        assert response_close.status == 200
        assert payload_close["analytics_updated"] is True

    assert len(calls) == 1
    assert calls[0]["experiment_id"] == "exp_ep_2"
    assert round(float(calls[0]["pnl_pct"]), 8) == -10.0
    assert calls[0]["close_ts"] == "2026-03-01T01:00:00Z"


def test_paper_close_endpoint_emits_notifications(tmp_path, monkeypatch):
    _setup_env(tmp_path, monkeypatch)
    events = []

    def _fake_notify(event_type, payload, config_path=None):
        event_name = str(getattr(event_type, "value", event_type))
        events.append({"event_type": event_name, "payload": dict(payload), "config_path": config_path})
        return {"ok": True, "sent": [], "skipped": ["config_missing"], "errors": []}

    monkeypatch.setattr(cp_experiments, "notify", _fake_notify)
    monkeypatch.setattr(cp_experiments, "should_trigger_pnl_threshold", lambda pnl_pct, config_path=None: abs(float(pnl_pct)) >= 5)

    with _serve_handler_connection() as conn:
        conn.request(
            "POST",
            "/paper/open",
            body=json.dumps(
                {
                    "signal_id": "sig_nt_1",
                    "experiment_id": "exp_nt_1",
                    "open_price": 100.0,
                    "open_ts": "2026-03-01T00:00:00Z",
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response_open = conn.getresponse()
        _ = json.loads(response_open.read().decode("utf-8"))
        assert response_open.status == 200

        conn.request(
            "POST",
            "/paper/close",
            body=json.dumps(
                {
                    "signal_id": "sig_nt_1",
                    "close_price": 90.0,
                    "close_ts": "2026-03-01T01:00:00Z",
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response_close = conn.getresponse()
        payload_close = json.loads(response_close.read().decode("utf-8"))
        assert response_close.status == 200
        assert payload_close["ok"] is True

    event_types = [row["event_type"] for row in events]
    assert "POSITION_CLOSED" in event_types
    assert "PNL_THRESHOLD_HIT" in event_types


def test_paper_open_duplicate_and_close_without_open_return_400(tmp_path, monkeypatch):
    _setup_env(tmp_path, monkeypatch)

    with _serve_handler_connection() as conn:
        conn.request(
            "POST",
            "/paper/open",
            body=json.dumps(
                {
                    "signal_id": "sig_guard",
                    "experiment_id": "exp_guard",
                    "open_price": 100.0,
                    "open_ts": "2026-03-01T00:00:00Z",
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response_open_1 = conn.getresponse()
        _ = json.loads(response_open_1.read().decode("utf-8"))
        assert response_open_1.status == 200

        conn.request(
            "POST",
            "/paper/open",
            body=json.dumps(
                {
                    "signal_id": "sig_guard",
                    "experiment_id": "exp_guard",
                    "open_price": 101.0,
                    "open_ts": "2026-03-01T00:01:00Z",
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response_open_2 = conn.getresponse()
        payload_open_2 = json.loads(response_open_2.read().decode("utf-8"))
        assert response_open_2.status == 400
        assert payload_open_2["ok"] is False
        assert payload_open_2["error"] == "already open"

        conn.request(
            "POST",
            "/paper/close",
            body=json.dumps(
                {
                    "signal_id": "sig_missing",
                    "close_price": 99.0,
                    "close_ts": "2026-03-01T01:00:00Z",
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response_close = conn.getresponse()
        payload_close = json.loads(response_close.read().decode("utf-8"))
        assert response_close.status == 400
        assert payload_close["ok"] is False
        assert payload_close["error"] == "no open position"
