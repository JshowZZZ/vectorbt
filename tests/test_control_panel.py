import sqlite3
import json
import http.client
import threading
import re
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts import control_panel as cp
from scripts import control_panel_state as cp_state


def _setup_db(path):
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE combo_summary ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "created_utc TEXT DEFAULT CURRENT_TIMESTAMP, "
            "timeframe TEXT, "
            "metric TEXT)"
        )
        conn.executemany(
            "INSERT INTO combo_summary (timeframe, metric) VALUES (?, ?)",
            [("15m", "a"), ("3m", "b"), ("15m", "c")],
        )


def test_process_manager_supports_standalone_instantiation():
    class _RunningProc:
        def poll(self):
            return None

    mgr = cp_state.ProcessManager()
    assert not mgr.is_running()
    assert not mgr.is_test_running()
    assert not mgr.is_batch_running()

    mgr.process = _RunningProc()
    mgr.test_process = _RunningProc()
    mgr.batch_process = _RunningProc()
    assert mgr.is_running()
    assert mgr.is_test_running()
    assert mgr.is_batch_running()


def test_get_results_payload_timeframe_filter(tmp_path, monkeypatch):
    db_path = tmp_path / "results.db"
    _setup_db(db_path)

    monkeypatch.setattr(cp, "ROOT", tmp_path)
    monkeypatch.setattr(cp, "ARTIFACTS", tmp_path)
    monkeypatch.setattr(cp, "DB_PATH", db_path)
    cp.TIMEFRAME_CACHE = {"ts": 0, "mtime": 0, "values": []}

    payload = cp._get_results_payload(timeframe="15m")
    combo = payload["combo"]

    assert combo["total"] == 2
    assert all(row["timeframe"] == "15m" for row in combo["rows"])
    assert set(payload["timeframes"]) == {"15m", "3m"}
    assert payload["errors"] == []


def test_get_results_payload_applies_refresh_state_data_end(tmp_path, monkeypatch):
    db_path = tmp_path / "results.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE combo_summary ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "created_utc TEXT DEFAULT CURRENT_TIMESTAMP, "
            "timeframe TEXT, "
            "plot_symbol TEXT, "
            "data_end TEXT, "
            "avg_total_return_pct TEXT)"
        )
        conn.execute(
            "INSERT INTO combo_summary (timeframe, plot_symbol, data_end, avg_total_return_pct) VALUES (?, ?, ?, ?)",
            ("15m", "ETH/BTC", "2024-01-01 00:00:00", "1.23"),
        )

    monkeypatch.setattr(cp, "ROOT", tmp_path)
    monkeypatch.setattr(cp, "ARTIFACTS", tmp_path)
    monkeypatch.setattr(cp, "DB_PATH", db_path)
    cp.TIMEFRAME_CACHE = {"ts": 0, "mtime": 0, "values": []}
    (tmp_path / "data_refresh_state.json").write_text(
        json.dumps(
            {
                "ok": True,
                "timeframe_data_end": {"15m": "2026-02-19 00:00:00"},
                "pair_data_end": [
                    {"timeframe": "15m", "symbol": "ETH/BTC", "data_end": "2026-02-19 12:34:56"}
                ],
            }
        ),
        encoding="utf-8",
    )

    payload = cp._get_results_payload(timeframe="15m")
    combo_row = payload["combo"]["rows"][0]
    top_row = payload["top10"]["rows"][0]

    assert combo_row["data_end"] == "2026-02-19 12:34:56"
    assert top_row["data_end"] == "2026-02-19 12:34:56"


def test_get_results_payload_top10_dual_path(tmp_path, monkeypatch):
    """AWF-107: top10 = all-time best from combo history; top10_latest_run from run file."""
    db_path = tmp_path / "results.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE combo_summary ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "created_utc TEXT DEFAULT CURRENT_TIMESTAMP, "
            "timeframe TEXT, "
            "oos_avg_total_return_pct TEXT)"
        )
        # Insert 3 rows; the best two should appear in top10 (sorted by oos_avg_total_return_pct)
        conn.executemany(
            "INSERT INTO combo_summary (timeframe, oos_avg_total_return_pct) VALUES (?, ?)",
            [("15m", "5.5"), ("15m", "9.9"), ("15m", "1.1")],
        )

    # Write a latest-run top10 file with different content (only 1 row)
    latest_csv = tmp_path / "param_sweep_top10_r999.csv"
    latest_csv.write_text("timeframe,oos_avg_total_return_pct\n15m,2.2\n", encoding="utf-8")

    monkeypatch.setattr(cp, "ROOT", tmp_path)
    monkeypatch.setattr(cp, "ARTIFACTS", tmp_path)
    monkeypatch.setattr(cp, "DB_PATH", db_path)
    cp.TIMEFRAME_CACHE = {"ts": 0, "mtime": 0, "values": []}

    payload = cp._get_results_payload()

    # Both keys must be present in payload
    assert "top10" in payload, "AWF-107: top10 key missing from payload"
    assert "top10_latest_run" in payload, "AWF-107: top10_latest_run key missing from payload"

    # Primary top10 is derived from full combo history (3 rows → top10 picks ≤3 rows)
    top10_rows = payload["top10"]["rows"]
    assert len(top10_rows) >= 1, "top10 should have rows from combo history"
    # Best row is the highest oos_avg_total_return_pct; should be "9.9"
    assert top10_rows[0].get("oos_avg_total_return_pct") == "9.9", (
        f"top10[0] oos return should be 9.9 but got {top10_rows[0].get('oos_avg_total_return_pct')}"
    )

    # Secondary top10_latest_run comes from the run file (1 row with 2.2)
    lr_rows = payload["top10_latest_run"]["rows"]
    assert len(lr_rows) == 1, f"top10_latest_run should have 1 row but got {len(lr_rows)}"
    assert lr_rows[0].get("oos_avg_total_return_pct") == "2.2"


def test_sanitize_config_walk_forward_fields():
    cfg = cp._sanitize_config(
        {
            "wf_train_days": 150,
            "wf_test_days": 45,
            "wf_step_days": 15,
            "timeframes": [{"timeframe": "3m", "days": 90}],
        }
    )

    assert cfg["wf_train_days"] == 150
    assert cfg["wf_test_days"] == 45
    assert cfg["wf_step_days"] == 15
    assert cfg["timeframes"] == [{"timeframe": "3m", "days": 90}]


def test_sanitize_config_walk_forward_fields_min_value():
    cfg = cp._sanitize_config(
        {
            "wf_train_days": 0,
            "wf_test_days": -1,
            "wf_step_days": "bad",
        }
    )

    assert cfg["wf_train_days"] >= 1
    assert cfg["wf_test_days"] >= 1
    assert cfg["wf_step_days"] >= 1


def test_validate_config_guardrails_rejects_wf_step_lt_test():
    with pytest.raises(ValueError, match="wf_step_days"):
        cp._validate_config_guardrails({"wf_test_days": 10, "wf_step_days": 2})


def test_config_endpoint_rejects_invalid_walk_forward_guardrail(tmp_path, monkeypatch):
    _setup_batch_env(tmp_path, monkeypatch)
    request_payload = {
        "wf_train_days": 120,
        "wf_test_days": 10,
        "wf_step_days": 2,
    }

    with _serve_handler_connection() as conn:
        conn.request(
            "POST",
            "/config",
            body=json.dumps(request_payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))

    assert response.status == 400
    assert payload["ok"] is False
    assert "wf_step_days" in payload["message"]


def test_resolve_static_path_and_traversal_guard(tmp_path, monkeypatch):
    static_dir = tmp_path / "scripts" / "control_panel" / "static"
    js_dir = static_dir / "js"
    js_dir.mkdir(parents=True)
    app_js = js_dir / "app.js"
    app_js.write_text("console.log('ok');", encoding="utf-8")

    monkeypatch.setattr(cp, "STATIC_DIR", static_dir)

    assert cp._resolve_static_path("/static/js/app.js") == app_js.resolve()
    assert cp._resolve_static_path("/static/../control_panel.py") is None
    assert cp._resolve_static_path("/status.json") is None


def test_read_static_text_fallback(tmp_path, monkeypatch):
    static_dir = tmp_path / "scripts" / "control_panel" / "static"
    static_dir.mkdir(parents=True)
    monkeypatch.setattr(cp, "STATIC_DIR", static_dir)

    assert cp._read_static_text("index.html", fallback="fallback") == "fallback"
    (static_dir / "index.html").write_text("hello", encoding="utf-8")
    assert cp._read_static_text("index.html", fallback="fallback") == "hello"


def test_favicon_endpoint_serves_static_svg(tmp_path, monkeypatch):
    static_dir = tmp_path / "scripts" / "control_panel" / "static"
    static_dir.mkdir(parents=True)
    favicon = static_dir / "favicon.svg"
    favicon.write_text("<svg xmlns='http://www.w3.org/2000/svg'></svg>", encoding="utf-8")
    monkeypatch.setattr(cp, "STATIC_DIR", static_dir)

    with _serve_handler_connection() as conn:
        conn.request("GET", "/favicon.ico")
        response = conn.getresponse()
        body = response.read().decode("utf-8")

    assert response.status == 200
    assert response.getheader("Content-Type") == "image/svg+xml"
    assert "<svg" in body


def test_normalize_top_n_bounds_and_defaults():
    assert cp._normalize_top_n("bad") == cp.DASHBOARD_TOP_N_DEFAULT
    assert cp._normalize_top_n(-5) == cp.DASHBOARD_TOP_N_MIN
    assert cp._normalize_top_n(0) == cp.DASHBOARD_TOP_N_MIN
    assert cp._normalize_top_n(9999) == cp.DASHBOARD_TOP_N_MAX
    assert cp._normalize_top_n(17) == 17


def _setup_batch_env(tmp_path, monkeypatch):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(cp, "ROOT", tmp_path)
    monkeypatch.setattr(cp, "ARTIFACTS", artifacts)
    monkeypatch.setattr(cp, "CONFIG_JSON", artifacts / "sweep_config.json")
    cp.BATCH_PROCESS = None
    cp.PROCESS = None
    return artifacts


def test_overview_next_action_includes_scheduler_queue_depth(tmp_path, monkeypatch):
    artifacts = _setup_batch_env(tmp_path, monkeypatch)
    (artifacts / "scheduler.json").write_text(
        json.dumps(
            {
                "priority_order": ["user_submitted", "discovery", "refine"],
                "max_concurrent": 1,
                "schedule_cron": "0 2 * * *",
            }
        ),
        encoding="utf-8",
    )
    (artifacts / "discovery_pool.json").write_text(
        json.dumps({"indicator_ids": ["RSI", "EMA", "BB"], "combo_size_range": [2, 2]}),
        encoding="utf-8",
    )
    run_dir = artifacts / "experiments" / "exp_queue" / "runs" / "20260301_020000"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run_meta.json").write_text(
        json.dumps(
            {
                "experiment_id": "exp_queue",
                "run_id": "20260301_020000",
                "n_combos": 3,
                "n_completed": 3,
                "n_errors": 0,
                "best_oos_sharpe": 1.1,
                "duration_seconds": 12.3,
                "completed_utc": "2026-03-01T02:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    from scripts import control_panel_experiments as cp_experiments

    monkeypatch.setattr(
        cp_experiments,
        "_scheduler_runtime_status",
        lambda: {
            "queue_depth": 2,
            "next_experiment_id": "exp_queue_next",
            "is_running": False,
            "last_error": "",
        },
    )

    with _serve_handler_connection() as conn:
        conn.request("GET", "/overview/next-action.json")
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))

    assert response.status == 200
    assert payload["scheduler_enabled"] is True
    assert payload["queue_depth"] == 2
    assert payload["next_experiment_id"] == "exp_queue_next"
    assert payload["discovery_candidates"] == 3
    assert payload["latest_run_summary"]["run_id"] == "20260301_020000"


def test_overview_patrol_history_endpoint_reads_recent_rows(tmp_path, monkeypatch):
    artifacts = _setup_batch_env(tmp_path, monkeypatch)
    log_path = artifacts / "patrol_log.ndjson"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as f:
        for idx in range(25):
            f.write(
                json.dumps(
                    {
                        "utc": f"2026-03-01T00:{idx:02d}:00+00:00",
                        "tick_generated": 10,
                        "tick_enqueued": max(0, 10 - idx),
                        "runs_executed": 1,
                        "runs_errors": 0,
                        "queue_remaining": max(0, 24 - idx),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    with _serve_handler_connection() as conn:
        conn.request("GET", "/overview/patrol-history.json")
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))

    assert response.status == 200
    assert payload["total"] == 20
    assert len(payload["history"]) == 20
    assert payload["history"][0]["utc"] == "2026-03-01T00:24:00+00:00"
    assert payload["history"][0]["queue_remaining"] == 0


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


def _assert_dashboard_cross_run_payload_schema(payload):
    assert isinstance(payload, dict)
    required_keys = {
        "schema_version",
        "generated_utc",
        "registry_path",
        "summary",
        "run_history",
        "global_leaderboard",
        "combo_stability",
        "per_regime_leaderboard",
        "regime_summary",
    }
    assert required_keys.issubset(payload.keys())
    assert payload["schema_version"] == "autowfo.cross_run_payload/v1"

    summary = payload["summary"]
    assert isinstance(summary, dict)
    required_summary_keys = {
        "total_runs",
        "unique_symbols",
        "unique_timeframes",
        "avg_oos_return_pct",
        "avg_bh_return_pct",
        "avg_random_return_pct",
        "avg_alpha_vs_bh",
        "latest_run_id",
        "latest_run_time_utc",
        "coverage_tested_pairs",
        "coverage_untested_pairs",
        "coverage_pct",
    }
    assert required_summary_keys.issubset(summary.keys())

    assert isinstance(payload["run_history"], list)
    assert isinstance(payload["global_leaderboard"], list)
    assert isinstance(payload["combo_stability"], list)
    assert isinstance(payload["per_regime_leaderboard"], dict)
    assert isinstance(payload["regime_summary"], list)


def _assert_dashboard_report_html_structure(html):
    assert "AUTOWFO Cross-Run Report" in html
    assert "<h2>Global Leaderboard</h2>" in html
    assert "<h2>Combo Stability Trends</h2>" in html
    assert "<h2>Regime Summary</h2>" in html
    assert "<h2>Per-Regime Leaderboard</h2>" in html
    assert "<h2>Run History</h2>" in html


def _assert_request_id(value):
    assert isinstance(value, str)
    assert re.fullmatch(r"[0-9a-f]{32}", value), f"invalid request_id: {value!r}"


def _assert_dashboard_error_event_row(row):
    assert isinstance(row, dict)
    required = {
        "event_utc",
        "kind",
        "endpoint",
        "request_id",
        "status",
        "message",
        "error_code",
        "cache_error_code",
    }
    assert required.issubset(row.keys())
    _assert_request_id(row["request_id"])
    assert row["kind"] in {"cache_fallback", "error"}
    assert isinstance(row["status"], int)


def _write_dashboard_error_events(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def test_trim_dashboard_error_events_keeps_tail(tmp_path, monkeypatch):
    artifacts = _setup_batch_env(tmp_path, monkeypatch)
    path = artifacts / "dashboard_error_events.ndjson"
    rows = [
        {
            "event_utc": f"2026-02-21T0{i}:00:00+00:00",
            "kind": "error",
            "endpoint": "dashboard/cross_run.json",
            "request_id": f"{i:032x}",
            "status": 500,
            "message": f"m{i}",
            "error_code": "runtime_error",
            "cache_error_code": "",
        }
        for i in range(5)
    ]
    _write_dashboard_error_events(path, rows)

    kept = cp._trim_dashboard_error_events(max_rows=3)
    assert kept == 3
    out = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(out) == 3
    assert out[0]["message"] == "m2"
    assert out[1]["message"] == "m3"
    assert out[2]["message"] == "m4"


def test_refresh_data_cache_now_writes_state(tmp_path, monkeypatch):
    artifacts = _setup_batch_env(tmp_path, monkeypatch)
    (artifacts / "sweep_config.json").write_text(
        json.dumps(
            {
                "exchange": "binance",
                "base_symbol": "BTC/USDT",
                "timeframes": [{"timeframe": "1h", "days": 30}],
                "trade_symbols": ["ETH/BTC"],
            }
        ),
        encoding="utf-8",
    )

    called = {}

    def _fake_refresh(**kwargs):
        called.update(kwargs)
        return {
            "timeframe_data_end": {"1h": "2026-02-19 00:00:00"},
            "pair_data_end": [{"timeframe": "1h", "symbol": "ETH/BTC", "data_end": "2026-02-19 00:00:00"}],
            "errors": [],
        }

    state, refreshed = cp._refresh_data_cache_now(
        force=True,
        reason="test",
        refresh_ohlcv_cache_fn=_fake_refresh,
    )

    assert refreshed is True
    assert state["ok"] is True
    assert state["reason"] == "test"
    assert state["timeframe_data_end"]["1h"] == "2026-02-19 00:00:00"
    assert called["exchange"] == "binance"
    assert called["symbols"] == ["ETH/BTC"]
    saved = json.loads((artifacts / "data_refresh_state.json").read_text(encoding="utf-8"))
    assert saved["timeframe_data_end"]["1h"] == "2026-02-19 00:00:00"


def test_refresh_data_cache_now_respects_interval(tmp_path, monkeypatch):
    artifacts = _setup_batch_env(tmp_path, monkeypatch)
    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    (artifacts / "data_refresh_state.json").write_text(
        json.dumps({"last_refresh_utc": now_iso, "timeframe_data_end": {"1h": "2026-02-19 00:00:00"}}),
        encoding="utf-8",
    )

    called = {"count": 0}

    def _fake_refresh(**kwargs):  # noqa: ARG001
        called["count"] += 1
        return {}

    state, refreshed = cp._refresh_data_cache_now(
        force=False,
        reason="auto",
        refresh_ohlcv_cache_fn=_fake_refresh,
    )

    assert refreshed is False
    assert called["count"] == 0
    assert state["timeframe_data_end"]["1h"] == "2026-02-19 00:00:00"


class _FakeProcess:
    def __init__(self):
        self._running = True
        self.returncode = None
        self.terminated = False

    def poll(self):
        return None if self._running else self.returncode

    def terminate(self):
        self._running = False
        self.returncode = 1
        self.terminated = True

    def wait(self, timeout=None):  # noqa: ARG002
        self._running = False
        if self.returncode is None:
            self.returncode = 1
        return self.returncode

    def kill(self):
        self._running = False
        self.returncode = -9


def test_batch_queue_enqueue_and_remove(tmp_path, monkeypatch):
    _setup_batch_env(tmp_path, monkeypatch)
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text("{}", encoding="utf-8")

    ok, _msg, job = cp._batch_enqueue(
        {
            "name": "job-a",
            "workflow": "baseline",
            "config": str(cfg_path),
        }
    )
    assert ok
    assert job["status"] == "queued"

    status = cp._batch_status_payload()
    assert status["summary"]["queued"] == 1
    assert status["jobs"][0]["name"] == "job-a"

    ok, _msg = cp._batch_remove(int(job["id"]))
    assert ok
    status = cp._batch_status_payload()
    assert status["summary"]["total"] == 0


def test_batch_start_and_state_sync(tmp_path, monkeypatch):
    artifacts = _setup_batch_env(tmp_path, monkeypatch)
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text("{}", encoding="utf-8")

    ok, _msg, job = cp._batch_enqueue(
        {
            "name": "job-sync",
            "workflow": "run",
            "mode": "combo",
            "config": str(cfg_path),
            "workers": 2,
        }
    )
    assert ok

    fake_proc = _FakeProcess()
    popen_calls = []

    def _fake_popen(cmd, cwd, stdout, stderr):  # noqa: ARG001
        popen_calls.append({"cmd": cmd, "cwd": cwd})
        return fake_proc

    monkeypatch.setattr(cp.subprocess, "Popen", _fake_popen)

    ok, msg = cp._batch_start()
    assert ok, msg
    assert popen_calls
    assert "--plan" in popen_calls[0]["cmd"]
    assert str(artifacts / "control_panel_batch_plan.json") in popen_calls[0]["cmd"]

    queue = cp._load_batch_queue()
    assert queue["jobs"][0]["status"] == "submitted"

    state_path = artifacts / "batch_state.json"
    state_path.write_text(
        """
{
  "history": [
    {"ts": "2026-02-10T10:00:00Z", "status": "running", "job_name": "job-sync"},
    {"ts": "2026-02-10T10:01:00Z", "status": "done", "job_name": "job-sync", "run_label": "run-001"}
  ]
}
        """.strip(),
        encoding="utf-8",
    )

    payload = cp._batch_status_payload()
    assert payload["jobs"][0]["status"] == "done"
    assert payload["jobs"][0]["run_label"] == "run-001"

    fake_proc._running = False
    fake_proc.returncode = 0
    payload = cp._batch_status_payload()
    assert payload["last_exit_code"] == "0"

    # Keep clean state for following tests.
    cp.BATCH_PROCESS = None


def test_batch_cancel_marks_active_jobs(tmp_path, monkeypatch):
    _setup_batch_env(tmp_path, monkeypatch)
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text("{}", encoding="utf-8")
    ok, _msg, _job = cp._batch_enqueue(
        {
            "name": "job-cancel",
            "workflow": "baseline",
            "config": str(cfg_path),
        }
    )
    assert ok

    fake_proc = _FakeProcess()

    def _fake_popen(cmd, cwd, stdout, stderr):  # noqa: ARG001
        return fake_proc

    monkeypatch.setattr(cp.subprocess, "Popen", _fake_popen)
    ok, msg = cp._batch_start()
    assert ok, msg

    ok, msg = cp._batch_cancel()
    assert ok, msg
    payload = cp._batch_status_payload()
    assert payload["jobs"][0]["status"] == "cancelled"


def test_coverage_matrix_payload_marks_tested_and_queued(tmp_path, monkeypatch):
    artifacts = _setup_batch_env(tmp_path, monkeypatch)
    (artifacts / "sweep_config.json").write_text(
        json.dumps(
            {
                "timeframes": [{"timeframe": "1h", "days": 120}],
                "trade_symbols": ["ETH/USDT", "SOL/USDT"],
            }
        ),
        encoding="utf-8",
    )
    (artifacts / "run_registry.json").write_text(
        json.dumps(
            {
                "coverage": {
                    "timeframes": ["1h"],
                    "symbols": ["ETH/USDT", "SOL/USDT"],
                    "tested_pairs": [{"timeframe": "1h", "symbol": "ETH/USDT"}],
                    "untested_pairs": [{"timeframe": "1h", "symbol": "SOL/USDT"}],
                }
            }
        ),
        encoding="utf-8",
    )
    queued_cfg = tmp_path / "queued.json"
    queued_cfg.write_text(
        json.dumps(
            {
                "timeframes": [{"timeframe": "1h", "days": 120}],
                "trade_symbols": ["SOL/USDT"],
            }
        ),
        encoding="utf-8",
    )
    (artifacts / "batch_queue.json").write_text(
        json.dumps(
            {
                "version": 1,
                "next_id": 2,
                "jobs": [
                    {
                        "id": 1,
                        "name": "q1",
                        "status": "queued",
                        "workflow": "baseline",
                        "config": str(queued_cfg),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    payload = cp._coverage_matrix_payload()
    assert payload["summary"]["total"] == 2
    assert payload["summary"]["tested"] == 1
    assert payload["summary"]["queued"] == 1
    assert payload["summary"]["untested"] == 0
    assert payload["summary"]["coverage_pct"] == 50.0

    cell_map = {(cell["timeframe"], cell["symbol"]): cell["status"] for cell in payload["cells"]}
    assert cell_map[("1h", "ETH/USDT")] == "tested"
    assert cell_map[("1h", "SOL/USDT")] == "queued"


def test_coverage_enqueue_pair_creates_config_and_queue_job(tmp_path, monkeypatch):
    artifacts = _setup_batch_env(tmp_path, monkeypatch)
    (artifacts / "sweep_config.json").write_text(
        json.dumps(
            {
                "search_mode": "combo",
                "combo_sizes": [2],
                "timeframes": [{"timeframe": "1h", "days": 100}],
                "trade_symbols": ["ETH/USDT"],
            }
        ),
        encoding="utf-8",
    )
    (artifacts / "run_registry.json").write_text(
        json.dumps(
            {
                "runs": [
                    {
                        "timeframes": [
                            {"timeframe": "4h", "days": 240},
                        ]
                    }
                ],
                "coverage": {},
            }
        ),
        encoding="utf-8",
    )

    ok, _msg, details = cp._coverage_enqueue_pair(
        {
            "timeframe": "4h",
            "symbol": "BNB/USDT",
            "workflow": "baseline",
        }
    )
    assert ok
    assert details is not None
    assert details["job"]["status"] == "queued"

    cfg_path = Path(details["config_path"])
    assert cfg_path.exists()
    cfg_payload = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert cfg_payload["timeframes"] == [{"timeframe": "4h", "days": 240}]
    assert cfg_payload["trade_symbols"] == ["BNB/USDT"]

    queue_payload = cp._load_batch_queue()
    assert len(queue_payload["jobs"]) == 1
    assert queue_payload["jobs"][0]["status"] == "queued"

    ok, msg, details = cp._coverage_enqueue_pair(
        {
            "timeframe": "4h",
            "symbol": "BNB/USDT",
            "workflow": "baseline",
        }
    )
    assert not ok
    assert "already queued" in msg
    assert details is None


def test_cross_run_payload_and_report_generation(tmp_path, monkeypatch):
    artifacts = _setup_batch_env(tmp_path, monkeypatch)
    (artifacts / "run_registry.json").write_text(
        json.dumps(
            {
                "runs": [
                    {
                        "run_id": "r100",
                        "timestamp_utc": "2026-02-10T09:00:00Z",
                        "search_mode": "baseline",
                        "timeframes": [{"timeframe": "2h", "days": 120}],
                        "trade_symbols": ["ETH/USDT", "BNB/USDT"],
                        "oos_avg_total_return_pct": 1.7,
                        "avg_total_return_pct": 1.1,
                    }
                ],
                "coverage": {
                    "tested_pairs": [{"timeframe": "2h", "symbol": "ETH/USDT"}],
                    "untested_pairs": [{"timeframe": "2h", "symbol": "BNB/USDT"}],
                },
            }
        ),
        encoding="utf-8",
    )
    top10_dir = artifacts / "runs" / "pack1" / "refine"
    top10_dir.mkdir(parents=True, exist_ok=True)
    (top10_dir / "param_sweep_top10_r100.csv").write_text(
        "indicator_list,regime_name,vol_mode,oos_avg_total_return_pct,oos_avg_max_drawdown_pct\n"
        "rsi,trend,normal,1.7,-3.2\n",
        encoding="utf-8",
    )

    payload = cp._cross_run_payload(top_n=10)
    assert payload["summary"]["total_runs"] == 1
    assert payload["summary"]["coverage_pct"] == 50.0
    assert len(payload["combo_stability"]) == 1

    report_payload, report_path = cp._cross_run_generate_report(top_n=10)
    assert report_payload["summary"]["total_runs"] == 1
    assert report_path.exists()
    assert "AUTOWFO Cross-Run Report" in report_path.read_text(encoding="utf-8")


def test_export_live_signal_config_from_row(tmp_path, monkeypatch):
    artifacts = _setup_batch_env(tmp_path, monkeypatch)
    (artifacts / "sweep_config.json").write_text(
        json.dumps(
            {
                "capital_mode": "shared",
                "init_cash_usdt": 1000,
                "order_size_pct": 0.5,
                "max_concurrent_positions": 2,
                "slippage_bps": 2.0,
                "spread_bps": 2.0,
                "funding_rate_daily": 0.0,
                "timeframes": [{"timeframe": "1h", "days": 90}],
                "trade_symbols": ["ETH/BTC"],
            }
        ),
        encoding="utf-8",
    )

    row = {
        "timeframe": "1h",
        "plot_symbol": "ETH/BTC",
        "indicator_list": "rsi,macd",
        "regime_name": "trend_high",
        "vol_mode": "high",
        "rsi_long": "60",
        "rsi_short": "40",
        "tp_stop": "0.03",
        "sl_stop": "0.01",
        "oos_avg_total_return_pct": "12.3",
        "oos_avg_max_drawdown_pct": "-4.2",
    }

    payload, out_path = cp._export_live_signal_config(rank=1, row=row)
    assert out_path.exists()
    assert payload["instrument"]["symbol"] == "ETH/BTC"
    assert payload["instrument"]["timeframe"] == "1h"
    assert payload["strategy"]["indicator_list"] == ["rsi", "macd"]
    assert payload["strategy"]["params"]["rsi_long"] == 60
    assert payload["risk"]["tp_stop"] == 0.03
    assert payload["paper_feedback_interface"]["post_endpoint"] == "/signals/paper-feedback"
    assert payload["paper_feedback_interface"]["enqueue_adjusted_batch_endpoint"] == "/signals/enqueue-feedback-adjusted-batch"


def test_paper_feedback_spec_contract():
    spec = cp._paper_feedback_spec()
    assert spec["schema_version"] == "autowfo.paper_feedback/v1"
    assert "signal_config_id" in spec["required_fields"]
    assert spec["endpoint"] == "/signals/paper-feedback"


def test_record_paper_feedback_appends_log(tmp_path, monkeypatch):
    artifacts = _setup_batch_env(tmp_path, monkeypatch)
    payload = {
        "signal_config_id": "sigcfg_20260219_120000_01_1h_eth-btc",
        "timestamp_utc": "2026-02-19T12:00:00Z",
        "symbol": "ETH/BTC",
        "timeframe": "1h",
        "action": "enter_long",
        "entry_price": 0.031,
        "qty": 1.5,
        "pnl_pct": 1.2,
        "note": "paper fill",
    }

    entry, path = cp._record_paper_feedback(payload)
    assert path == artifacts / "paper_feedback.ndjson"
    assert path.exists()
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 1
    assert rows[0]["signal_config_id"] == payload["signal_config_id"]
    assert rows[0]["action"] == "enter_long"
    assert entry["symbol"] == "ETH/BTC"


def test_record_paper_feedback_rejects_invalid_action():
    payload = {
        "signal_config_id": "sigcfg_x",
        "timestamp_utc": "2026-02-19T12:00:00Z",
        "symbol": "ETH/BTC",
        "timeframe": "1h",
        "action": "invalid_action",
    }
    with pytest.raises(ValueError, match="action must be one of"):
        cp._record_paper_feedback(payload)


def test_paper_feedback_summary_metrics():
    rows = [
        {
            "timestamp_utc": "2026-02-19T12:00:00Z",
            "symbol": "ETH/BTC",
            "timeframe": "1h",
            "action": "enter_long",
            "pnl_pct": 1.2,
        },
        {
            "timestamp_utc": "2026-02-19T13:00:00Z",
            "symbol": "ETH/BTC",
            "timeframe": "1h",
            "action": "exit_long",
            "pnl_pct": -0.8,
        },
        {
            "timestamp_utc": "2026-02-19T14:00:00Z",
            "symbol": "BNB/BTC",
            "timeframe": "4h",
            "action": "hold",
        },
    ]

    summary = cp._paper_feedback_summary(rows)
    assert summary["total_feedback"] == 3
    assert summary["latest_timestamp_utc"] == "2026-02-19T14:00:00Z"
    assert summary["action_counts"]["enter_long"] == 1
    assert summary["action_counts"]["exit_long"] == 1
    assert summary["action_counts"]["hold"] == 1
    assert summary["symbol_counts"]["ETH/BTC"] == 2
    assert summary["timeframe_counts"]["1h"] == 2
    assert summary["pnl_pct"]["count"] == 2
    assert summary["pnl_pct"]["mean_pct"] == pytest.approx(0.2)
    assert summary["pnl_pct"]["win_rate_pct"] == pytest.approx(50.0)


def test_paper_feedback_summary_empty():
    summary = cp._paper_feedback_summary([])
    assert summary["total_feedback"] == 0
    assert summary["latest_timestamp_utc"] is None
    assert summary["action_counts"] == {}
    assert summary["pnl_pct"]["count"] == 0


def test_paper_feedback_diagnostics_groups_and_ranking():
    rows = [
        {
            "signal_config_id": "cfg_a",
            "timestamp_utc": "2026-02-19T12:00:00Z",
            "symbol": "ETH/BTC",
            "timeframe": "1h",
            "action": "enter_long",
            "pnl_pct": 1.0,
        },
        {
            "signal_config_id": "cfg_a",
            "timestamp_utc": "2026-02-19T13:00:00Z",
            "symbol": "ETH/BTC",
            "timeframe": "1h",
            "action": "exit_long",
            "pnl_pct": 2.0,
        },
        {
            "signal_config_id": "cfg_b",
            "timestamp_utc": "2026-02-19T14:00:00Z",
            "symbol": "BNB/BTC",
            "timeframe": "4h",
            "action": "enter_short",
            "pnl_pct": -1.5,
        },
        {
            "signal_config_id": "cfg_c",
            "timestamp_utc": "2026-02-19T15:00:00Z",
            "symbol": "SOL/BTC",
            "timeframe": "4h",
            "action": "hold",
        },
    ]

    diag = cp._paper_feedback_diagnostics(rows, top_n=2)
    assert diag["total_feedback"] == 4
    assert diag["signal_config_count"] == 3

    top = diag["top_signal_configs"]
    assert top[0]["signal_config_id"] == "cfg_a"
    assert top[0]["avg_pnl_pct"] == pytest.approx(1.5)
    assert top[0]["win_rate_pct"] == pytest.approx(100.0)

    worst = diag["worst_signal_configs"]
    assert worst[0]["signal_config_id"] == "cfg_b"
    assert worst[0]["avg_pnl_pct"] == pytest.approx(-1.5)

    action_map = {row["action"]: row for row in diag["action_diagnostics"]}
    assert action_map["enter_long"]["count"] == 1
    assert action_map["exit_long"]["count"] == 1
    assert action_map["enter_short"]["avg_pnl_pct"] == pytest.approx(-1.5)
    assert action_map["hold"]["pnl_count"] == 0


def test_paper_feedback_recommendations_profiles():
    rows = [
        {
            "signal_config_id": "cfg_good",
            "timestamp_utc": "2026-02-19T12:00:00Z",
            "symbol": "ETH/BTC",
            "timeframe": "1h",
            "action": "enter_long",
            "pnl_pct": 1.2,
        },
        {
            "signal_config_id": "cfg_good",
            "timestamp_utc": "2026-02-19T13:00:00Z",
            "symbol": "ETH/BTC",
            "timeframe": "1h",
            "action": "exit_long",
            "pnl_pct": 0.9,
        },
        {
            "signal_config_id": "cfg_bad",
            "timestamp_utc": "2026-02-19T14:00:00Z",
            "symbol": "BNB/BTC",
            "timeframe": "4h",
            "action": "enter_short",
            "pnl_pct": -1.4,
        },
        {
            "signal_config_id": "cfg_bad",
            "timestamp_utc": "2026-02-19T15:00:00Z",
            "symbol": "BNB/BTC",
            "timeframe": "4h",
            "action": "exit_short",
            "pnl_pct": -0.7,
        },
    ]
    payload = cp._paper_feedback_recommendations(rows, top_n=5, min_samples=2)
    rec_map = {(r["symbol"], r["timeframe"]): r for r in payload["recommendations"]}

    assert rec_map[("ETH/BTC", "1h")]["recommended_profile"] == "offensive"
    assert rec_map[("BNB/BTC", "4h")]["recommended_profile"] == "defensive"
    assert payload["total_feedback"] == 4
    assert payload["min_samples"] == 2


def test_export_feedback_adjusted_signal_config_with_recommendation(tmp_path, monkeypatch):
    artifacts = _setup_batch_env(tmp_path, monkeypatch)
    (artifacts / "sweep_config.json").write_text(
        json.dumps(
            {
                "capital_mode": "shared",
                "init_cash_usdt": 1000,
                "order_size_pct": 0.5,
                "max_concurrent_positions": 2,
                "slippage_bps": 2.0,
                "spread_bps": 2.0,
                "funding_rate_daily": 0.0,
                "timeframes": [{"timeframe": "1h", "days": 90}],
                "trade_symbols": ["ETH/BTC"],
            }
        ),
        encoding="utf-8",
    )

    row = {
        "timeframe": "1h",
        "plot_symbol": "ETH/BTC",
        "indicator_list": "rsi,macd",
        "regime_name": "trend_high",
        "vol_mode": "high",
        "tp_stop": "0.03",
        "sl_stop": "0.01",
        "max_hold": "48",
    }
    recommendation = {
        "symbol": "ETH/BTC",
        "timeframe": "1h",
        "recommended_profile": "defensive",
        "risk_multipliers": {"tp_stop": 0.9, "sl_stop": 0.85, "max_hold": 0.8},
        "reason": "negative expectancy",
    }

    payload, out_path, rec = cp._export_feedback_adjusted_signal_config(
        profile="auto",
        rank=1,
        row=row,
        recommendation=recommendation,
    )

    assert out_path.exists()
    assert "feedback_adjustment" in payload
    assert payload["feedback_adjustment"]["profile"] == "defensive"
    assert payload["risk"]["tp_stop"] == pytest.approx(0.027)
    assert payload["risk"]["sl_stop"] == pytest.approx(0.0085)
    assert payload["risk"]["max_hold"] == 38
    assert rec["recommended_profile"] == "defensive"


def test_build_feedback_adjusted_sweep_config_from_signal_payload(tmp_path, monkeypatch):
    artifacts = _setup_batch_env(tmp_path, monkeypatch)
    (artifacts / "sweep_config.json").write_text(
        json.dumps(
            {
                "search_mode": "combo",
                "timeframes": [{"timeframe": "1h", "days": 120}],
                "trade_symbols": ["ETH/BTC", "BNB/BTC"],
            }
        ),
        encoding="utf-8",
    )

    source_row = {"timeframe": "1h", "plot_symbol": "ETH/BTC"}
    adjusted_payload = {
        "signal_config_id": "sigcfg_demo_fb_defensive",
        "instrument": {"symbol": "ETH/BTC", "timeframe": "1h"},
        "risk": {"tp_stop": 0.027, "sl_stop": 0.0085, "max_hold": 38},
        "feedback_adjustment": {"profile": "defensive"},
    }

    cfg_payload, plan = cp._build_feedback_adjusted_sweep_config(source_row, adjusted_payload)
    assert cfg_payload["timeframes"] == [{"timeframe": "1h", "days": 120}]
    assert cfg_payload["trade_symbols"] == ["ETH/BTC"]
    assert cfg_payload["tp_stops"] == [0.027]
    assert cfg_payload["sl_stops"] == [0.0085]
    assert cfg_payload["max_holds"] == [38]
    assert cfg_payload["feedback_adjustment"]["profile"] == "defensive"
    assert plan["timeframe"] == "1h"
    assert plan["symbol"] == "ETH/BTC"
    assert plan["days"] == 120


def test_build_feedback_adjusted_sweep_config_applies_risk_guardrails(tmp_path, monkeypatch):
    artifacts = _setup_batch_env(tmp_path, monkeypatch)
    (artifacts / "sweep_config.json").write_text(
        json.dumps(
            {
                "search_mode": "combo",
                "timeframes": [{"timeframe": "1h", "days": 120}],
                "trade_symbols": ["ETH/BTC", "BNB/BTC"],
            }
        ),
        encoding="utf-8",
    )

    source_row = {"timeframe": "1h", "plot_symbol": "ETH/BTC"}
    adjusted_payload = {
        "signal_config_id": "sigcfg_demo_fb_balanced",
        "instrument": {"symbol": "ETH/BTC", "timeframe": "1h"},
        "risk": {"tp_stop": 0.9, "sl_stop": 0.0, "max_hold": 999},
        "feedback_adjustment": {"profile": "balanced"},
    }

    cfg_payload, plan = cp._build_feedback_adjusted_sweep_config(source_row, adjusted_payload)

    assert cfg_payload["tp_stops"] == [0.2]
    assert cfg_payload["sl_stops"] == [0.0005]
    assert cfg_payload["max_holds"] == [240]
    assert cfg_payload["feedback_adjustment"]["risk"]["tp_stop"] == pytest.approx(0.2)
    assert cfg_payload["feedback_adjustment"]["risk"]["sl_stop"] == pytest.approx(0.0005)
    assert cfg_payload["feedback_adjustment"]["risk"]["max_hold"] == 240

    warnings = plan["warnings"]
    assert len(warnings) == 3
    assert cfg_payload["feedback_adjustment"]["risk_guardrails"] == warnings
    warn_map = {row["field"]: row for row in warnings}
    assert set(warn_map.keys()) == {"tp_stop", "sl_stop", "max_hold"}
    assert warn_map["tp_stop"]["input"] == pytest.approx(0.9)
    assert warn_map["tp_stop"]["clamped"] == pytest.approx(0.2)
    assert warn_map["sl_stop"]["input"] == pytest.approx(0.0)
    assert warn_map["sl_stop"]["clamped"] == pytest.approx(0.0005)
    assert warn_map["max_hold"]["input"] == 999
    assert warn_map["max_hold"]["clamped"] == 240


def test_enqueue_feedback_adjusted_batch_creates_config_and_queue_job(tmp_path, monkeypatch):
    artifacts = _setup_batch_env(tmp_path, monkeypatch)
    (artifacts / "sweep_config.json").write_text(
        json.dumps(
            {
                "search_mode": "combo",
                "timeframes": [{"timeframe": "1h", "days": 90}],
                "trade_symbols": ["ETH/BTC", "BNB/BTC"],
                "capital_mode": "shared",
                "init_cash_usdt": 1000,
                "order_size_pct": 0.5,
                "max_concurrent_positions": 2,
                "slippage_bps": 2.0,
                "spread_bps": 2.0,
                "funding_rate_daily": 0.0,
            }
        ),
        encoding="utf-8",
    )

    row = {
        "timeframe": "1h",
        "plot_symbol": "ETH/BTC",
        "indicator_list": "rsi,macd",
        "regime_name": "trend_high",
        "vol_mode": "high",
        "tp_stop": "0.03",
        "sl_stop": "0.01",
        "max_hold": "48",
    }
    recommendation = {
        "symbol": "ETH/BTC",
        "timeframe": "1h",
        "recommended_profile": "defensive",
        "risk_multipliers": {"tp_stop": 0.9, "sl_stop": 0.85, "max_hold": 0.8},
        "reason": "negative expectancy",
    }

    result = cp._enqueue_feedback_adjusted_batch(
        profile="auto",
        rank=1,
        row=row,
        recommendation=recommendation,
        workflow="run",
        mode="combo",
    )

    cfg_path = Path(result["config_path"])
    assert cfg_path.exists()
    cfg_payload = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert cfg_payload["timeframes"] == [{"timeframe": "1h", "days": 90}]
    assert cfg_payload["trade_symbols"] == ["ETH/BTC"]
    assert cfg_payload["tp_stops"] == [0.027]
    assert cfg_payload["sl_stops"] == [0.0085]
    assert cfg_payload["max_holds"] == [38]
    assert result["warnings"] == []

    queue_payload = cp._load_batch_queue()
    assert len(queue_payload["jobs"]) == 1
    job = queue_payload["jobs"][0]
    assert job["workflow"] == "run"
    assert job["mode"] == "combo"
    assert job["status"] == "queued"
    assert Path(job["config"]) == cfg_path


def test_enqueue_feedback_adjusted_batch_returns_guardrail_warnings(tmp_path, monkeypatch):
    artifacts = _setup_batch_env(tmp_path, monkeypatch)
    (artifacts / "sweep_config.json").write_text(
        json.dumps(
            {
                "search_mode": "combo",
                "timeframes": [{"timeframe": "1h", "days": 90}],
                "trade_symbols": ["ETH/BTC", "BNB/BTC"],
                "capital_mode": "shared",
                "init_cash_usdt": 1000,
                "order_size_pct": 0.5,
                "max_concurrent_positions": 2,
                "slippage_bps": 2.0,
                "spread_bps": 2.0,
                "funding_rate_daily": 0.0,
            }
        ),
        encoding="utf-8",
    )

    row = {
        "timeframe": "1h",
        "plot_symbol": "ETH/BTC",
        "indicator_list": "rsi,macd",
        "regime_name": "trend_high",
        "vol_mode": "high",
        "tp_stop": "0.9",
        "sl_stop": "0",
        "max_hold": "999",
    }

    result = cp._enqueue_feedback_adjusted_batch(
        profile="balanced",
        rank=1,
        row=row,
        workflow="run",
        mode="combo",
    )

    cfg_path = Path(result["config_path"])
    assert cfg_path.exists()
    cfg_payload = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert cfg_payload["tp_stops"] == [0.2]
    assert cfg_payload["sl_stops"] == [0.0005]
    assert cfg_payload["max_holds"] == [240]

    warnings = result["warnings"]
    assert len(warnings) == 3
    warn_map = {row["field"]: row for row in warnings}
    assert warn_map["tp_stop"]["clamped"] == pytest.approx(0.2)
    assert warn_map["sl_stop"]["clamped"] == pytest.approx(0.0005)
    assert warn_map["max_hold"]["clamped"] == 240


def test_enqueue_feedback_adjusted_batch_endpoint_returns_warnings(tmp_path, monkeypatch):
    artifacts = _setup_batch_env(tmp_path, monkeypatch)
    planned_dir = artifacts / "planned_configs"
    planned_dir.mkdir(parents=True, exist_ok=True)
    live_dir = artifacts / cp.LIVE_SIGNAL_CONFIG_SUBDIR
    live_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = planned_dir / "feedback_endpoint.json"
    cfg_path.write_text("{}", encoding="utf-8")
    signal_path = live_dir / "feedback_endpoint.json"
    signal_path.write_text("{}", encoding="utf-8")

    captured = {}

    def _fake_enqueue_feedback_adjusted_batch(**kwargs):
        captured.update(kwargs)
        return {
            "job": {"id": 99, "name": "fb-job", "status": "queued"},
            "config_path": cfg_path,
            "signal_config_path": signal_path,
            "adjusted_payload": {"signal_config_id": "sigcfg_fb_demo"},
            "profile": "defensive",
            "recommendation": {"symbol": "ETH/BTC", "timeframe": "1h"},
            "plan": {"timeframe": "1h", "symbol": "ETH/BTC", "days": 90},
            "warnings": [
                {
                    "field": "max_hold",
                    "input": 999,
                    "clamped": 240,
                    "min": 1,
                    "max": 240,
                }
            ],
            "batch_started": False,
            "batch_start_message": "",
        }

    monkeypatch.setattr(cp, "_enqueue_feedback_adjusted_batch", _fake_enqueue_feedback_adjusted_batch)

    response = None
    body = ""
    with _serve_handler_connection(timeout=5) as conn:
        request_payload = {
            "profile": "auto",
            "rank": 2,
            "timeframe": "1h",
            "row": {"timeframe": "1h", "plot_symbol": "ETH/BTC"},
            "workflow": "run",
            "mode": "combo",
            "workers": 3,
            "name": "endpoint-test",
        }
        conn.request(
            "POST",
            "/signals/enqueue-feedback-adjusted-batch",
            body=json.dumps(request_payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        body = response.read().decode("utf-8")

    assert response.status == 200
    payload = json.loads(body)
    assert payload["ok"] is True
    assert payload["config_path"] == str(cfg_path.relative_to(tmp_path))
    assert payload["signal_config_path"] == str(signal_path.relative_to(tmp_path))
    assert payload["warnings"] == [{"field": "max_hold", "input": 999, "clamped": 240, "min": 1, "max": 240}]
    assert payload["job"]["id"] == 99
    assert captured["rank"] == 2
    assert captured["workflow"] == "run"
    assert captured["mode"] == "combo"
    assert captured["workers"] == 3
    assert captured["name"] == "endpoint-test"


def test_enqueue_feedback_adjusted_batch_endpoint_smoke_integration(tmp_path, monkeypatch):
    artifacts = _setup_batch_env(tmp_path, monkeypatch)
    (artifacts / "sweep_config.json").write_text(
        json.dumps(
            {
                "search_mode": "combo",
                "timeframes": [{"timeframe": "1h", "days": 90}],
                "trade_symbols": ["ETH/BTC", "BNB/BTC"],
                "capital_mode": "shared",
                "init_cash_usdt": 1000,
                "order_size_pct": 0.5,
                "max_concurrent_positions": 2,
                "slippage_bps": 2.0,
                "spread_bps": 2.0,
                "funding_rate_daily": 0.0,
            }
        ),
        encoding="utf-8",
    )

    request_payload = {
        "profile": "balanced",
        "rank": 1,
        "row": {
            "timeframe": "1h",
            "plot_symbol": "ETH/BTC",
            "indicator_list": "rsi,macd",
            "regime_name": "trend_high",
            "vol_mode": "high",
            "tp_stop": "0.9",
            "sl_stop": "0",
            "max_hold": "999",
        },
        "workflow": "run",
        "mode": "combo",
    }

    response = None
    body = ""
    with _serve_handler_connection(timeout=10) as conn:
        conn.request(
            "POST",
            "/signals/enqueue-feedback-adjusted-batch",
            body=json.dumps(request_payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        body = response.read().decode("utf-8")

    assert response.status == 200
    payload = json.loads(body)
    assert payload["ok"] is True
    assert payload["job"]["status"] == "queued"
    assert isinstance(payload["warnings"], list)
    assert len(payload["warnings"]) == 3
    warn_fields = {row["field"] for row in payload["warnings"]}
    assert warn_fields == {"tp_stop", "sl_stop", "max_hold"}

    cfg_path = tmp_path / payload["config_path"]
    signal_path = tmp_path / payload["signal_config_path"]
    assert cfg_path.exists()
    assert signal_path.exists()
    cfg_payload = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert cfg_payload["tp_stops"] == [0.2]
    assert cfg_payload["sl_stops"] == [0.0005]
    assert cfg_payload["max_holds"] == [240]

    queue_payload = cp._load_batch_queue()
    assert len(queue_payload["jobs"]) == 1
    assert int(queue_payload["jobs"][0]["id"]) == int(payload["job"]["id"])


def test_export_feedback_adjusted_config_endpoint_smoke_integration(tmp_path, monkeypatch):
    artifacts = _setup_batch_env(tmp_path, monkeypatch)
    (artifacts / "sweep_config.json").write_text(
        json.dumps(
            {
                "search_mode": "combo",
                "timeframes": [{"timeframe": "1h", "days": 90}],
                "trade_symbols": ["ETH/BTC", "BNB/BTC"],
                "capital_mode": "shared",
                "init_cash_usdt": 1000,
                "order_size_pct": 0.5,
                "max_concurrent_positions": 2,
                "slippage_bps": 2.0,
                "spread_bps": 2.0,
                "funding_rate_daily": 0.0,
            }
        ),
        encoding="utf-8",
    )

    request_payload = {
        "profile": "auto",
        "rank": 1,
        "row": {
            "timeframe": "1h",
            "plot_symbol": "ETH/BTC",
            "indicator_list": "rsi,macd",
            "regime_name": "trend_high",
            "vol_mode": "high",
            "tp_stop": "0.03",
            "sl_stop": "0.01",
            "max_hold": "48",
        },
        "recommendation": {
            "symbol": "ETH/BTC",
            "timeframe": "1h",
            "recommended_profile": "defensive",
            "risk_multipliers": {"tp_stop": 0.9, "sl_stop": 0.85, "max_hold": 0.8},
            "reason": "negative expectancy",
        },
    }

    response = None
    body = ""
    with _serve_handler_connection(timeout=10) as conn:
        conn.request(
            "POST",
            "/signals/export-feedback-adjusted-config",
            body=json.dumps(request_payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        body = response.read().decode("utf-8")

    assert response.status == 200
    payload = json.loads(body)
    assert payload["ok"] is True
    assert payload["profile"] == "defensive"
    assert payload["risk"]["tp_stop"] == pytest.approx(0.027)
    assert payload["risk"]["sl_stop"] == pytest.approx(0.0085)
    assert payload["risk"]["max_hold"] == 38

    exported_path = tmp_path / payload["path"]
    assert exported_path.exists()
    exported_payload = json.loads(exported_path.read_text(encoding="utf-8"))
    assert exported_payload["feedback_adjustment"]["profile"] == "defensive"
    assert exported_payload["risk"]["tp_stop"] == pytest.approx(0.027)
    assert exported_payload["risk"]["sl_stop"] == pytest.approx(0.0085)
    assert exported_payload["risk"]["max_hold"] == 38


def test_coverage_matrix_endpoint_smoke_integration(tmp_path, monkeypatch):
    artifacts = _setup_batch_env(tmp_path, monkeypatch)
    (artifacts / "sweep_config.json").write_text(
        json.dumps(
            {
                "timeframes": [{"timeframe": "1h", "days": 120}],
                "trade_symbols": ["ETH/USDT", "SOL/USDT"],
            }
        ),
        encoding="utf-8",
    )
    (artifacts / "run_registry.json").write_text(
        json.dumps(
            {
                "coverage": {
                    "timeframes": ["1h"],
                    "symbols": ["ETH/USDT", "SOL/USDT"],
                    "tested_pairs": [{"timeframe": "1h", "symbol": "ETH/USDT"}],
                    "untested_pairs": [{"timeframe": "1h", "symbol": "SOL/USDT"}],
                }
            }
        ),
        encoding="utf-8",
    )

    queued_cfg = tmp_path / "queued_cov_endpoint.json"
    queued_cfg.write_text(
        json.dumps(
            {
                "timeframes": [{"timeframe": "1h", "days": 120}],
                "trade_symbols": ["SOL/USDT"],
            }
        ),
        encoding="utf-8",
    )
    (artifacts / "batch_queue.json").write_text(
        json.dumps(
            {
                "version": 1,
                "next_id": 2,
                "jobs": [
                    {
                        "id": 1,
                        "name": "cov-q1",
                        "status": "queued",
                        "workflow": "baseline",
                        "config": str(queued_cfg),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    response = None
    body = ""
    with _serve_handler_connection(timeout=10) as conn:
        conn.request("GET", "/coverage/matrix.json")
        response = conn.getresponse()
        body = response.read().decode("utf-8")

    assert response.status == 200
    payload = json.loads(body)
    assert payload["summary"]["total"] == 2
    assert payload["summary"]["tested"] == 1
    assert payload["summary"]["queued"] == 1
    assert payload["summary"]["untested"] == 0

    cell_map = {(cell["timeframe"], cell["symbol"]): cell["status"] for cell in payload["cells"]}
    assert cell_map[("1h", "ETH/USDT")] == "tested"
    assert cell_map[("1h", "SOL/USDT")] == "queued"


def test_coverage_enqueue_endpoint_smoke_integration(tmp_path, monkeypatch):
    artifacts = _setup_batch_env(tmp_path, monkeypatch)
    (artifacts / "sweep_config.json").write_text(
        json.dumps(
            {
                "search_mode": "combo",
                "combo_sizes": [2],
                "timeframes": [{"timeframe": "1h", "days": 100}],
                "trade_symbols": ["ETH/USDT"],
            }
        ),
        encoding="utf-8",
    )
    (artifacts / "run_registry.json").write_text(
        json.dumps(
            {
                "runs": [
                    {
                        "timeframes": [{"timeframe": "4h", "days": 240}],
                    }
                ],
                "coverage": {},
            }
        ),
        encoding="utf-8",
    )

    request_payload = {
        "timeframe": "4h",
        "symbol": "BNB/USDT",
        "workflow": "run",
        "mode": "combo",
        "workers": 2,
        "name": "cov-endpoint-run",
    }

    response = None
    body = ""
    with _serve_handler_connection(timeout=10) as conn:
        conn.request(
            "POST",
            "/coverage/enqueue",
            body=json.dumps(request_payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        body = response.read().decode("utf-8")

    assert response.status == 200
    payload = json.loads(body)
    assert payload["ok"] is True
    details = payload["details"]
    assert details["job"]["status"] == "queued"
    assert details["job"]["workflow"] == "run"
    assert details["job"]["mode"] == "combo"
    assert details["job"]["workers"] == 2

    cfg_path = Path(details["config_path"])
    assert cfg_path.exists()
    cfg_payload = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert cfg_payload["timeframes"] == [{"timeframe": "4h", "days": 240}]
    assert cfg_payload["trade_symbols"] == ["BNB/USDT"]

    queue_payload = cp._load_batch_queue()
    assert len(queue_payload["jobs"]) == 1
    assert queue_payload["jobs"][0]["name"] == "cov-endpoint-run"


def test_batch_endpoints_enqueue_queue_remove_smoke_integration(tmp_path, monkeypatch):
    _setup_batch_env(tmp_path, monkeypatch)
    cfg_path = tmp_path / "batch_endpoint_cfg.json"
    cfg_path.write_text("{}", encoding="utf-8")

    enqueue_payload = {
        "name": "batch-endpoint-job",
        "workflow": "baseline",
        "config": str(cfg_path),
    }

    with _serve_handler_connection(timeout=10) as conn:
        conn.request(
            "POST",
            "/batch/enqueue",
            body=json.dumps(enqueue_payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        enqueue_resp = conn.getresponse()
        enqueue_body = enqueue_resp.read().decode("utf-8")
        assert enqueue_resp.status == 200
        enqueue_result = json.loads(enqueue_body)
        assert enqueue_result["ok"] is True
        assert enqueue_result["job"]["status"] == "queued"
        job_id = int(enqueue_result["job"]["id"])

        conn.request("GET", "/batch/queue.json")
        queue_resp = conn.getresponse()
        queue_body = queue_resp.read().decode("utf-8")
        assert queue_resp.status == 200
        queue_payload = json.loads(queue_body)
        assert queue_payload["summary"]["total"] == 1
        assert queue_payload["summary"]["queued"] == 1
        assert int(queue_payload["jobs"][0]["id"]) == job_id

        conn.request(
            "POST",
            "/batch/remove",
            body=json.dumps({"job_id": job_id}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        remove_resp = conn.getresponse()
        remove_body = remove_resp.read().decode("utf-8")
        assert remove_resp.status == 200
        remove_payload = json.loads(remove_body)
        assert remove_payload["ok"] is True

        conn.request("GET", "/batch/queue.json")
        queue_after_resp = conn.getresponse()
        queue_after_body = queue_after_resp.read().decode("utf-8")
        assert queue_after_resp.status == 200
        queue_after = json.loads(queue_after_body)
        assert queue_after["summary"]["total"] == 0
        assert queue_after["jobs"] == []


def _seed_dashboard_cross_run_artifacts(artifacts: Path) -> None:
    (artifacts / "run_registry.json").write_text(
        json.dumps(
            {
                "runs": [
                    {
                        "run_id": "r100",
                        "timestamp_utc": "2026-02-10T09:00:00Z",
                        "search_mode": "baseline",
                        "timeframes": [{"timeframe": "2h", "days": 120}],
                        "trade_symbols": ["ETH/USDT", "BNB/USDT"],
                        "oos_avg_total_return_pct": 1.7,
                        "avg_total_return_pct": 1.1,
                    }
                ],
                "coverage": {
                    "tested_pairs": [{"timeframe": "2h", "symbol": "ETH/USDT"}],
                    "untested_pairs": [{"timeframe": "2h", "symbol": "BNB/USDT"}],
                },
            }
        ),
        encoding="utf-8",
    )

    top10_dir = artifacts / "runs" / "pack1" / "refine"
    top10_dir.mkdir(parents=True, exist_ok=True)
    (top10_dir / "param_sweep_top10_r100.csv").write_text(
        "indicator_list,regime_name,vol_mode,oos_avg_total_return_pct,oos_avg_max_drawdown_pct\n"
        "rsi,trend,normal,1.7,-3.2\n",
        encoding="utf-8",
    )


def test_dashboard_cross_run_endpoint_smoke_integration(tmp_path, monkeypatch):
    artifacts = _setup_batch_env(tmp_path, monkeypatch)
    _seed_dashboard_cross_run_artifacts(artifacts)

    with _serve_handler_connection(timeout=10) as conn:
        conn.request("GET", "/dashboard/cross_run.json?top_n=10")
        response = conn.getresponse()
        body = response.read().decode("utf-8")
        assert response.status == 200
        payload = json.loads(body)
        _assert_dashboard_cross_run_payload_schema(payload)
        assert payload["payload_source"] == "live"
        _assert_request_id(payload["request_id"])
        assert payload["summary"]["total_runs"] == 1
        assert payload["summary"]["coverage_pct"] == 50.0
        assert len(payload["combo_stability"]) == 1
        assert len(payload["global_leaderboard"]) == 1


def test_dashboard_report_generate_endpoint_smoke_integration(tmp_path, monkeypatch):
    artifacts = _setup_batch_env(tmp_path, monkeypatch)
    _seed_dashboard_cross_run_artifacts(artifacts)

    with _serve_handler_connection(timeout=10) as conn:
        conn.request(
            "POST",
            "/dashboard/report/generate",
            body=json.dumps({"top_n": 10}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        generate_response = conn.getresponse()
        generate_body = generate_response.read().decode("utf-8")
        assert generate_response.status == 200
        generate_payload = json.loads(generate_body)
        assert generate_payload["ok"] is True
        assert generate_payload["payload_source"] == "live"
        _assert_request_id(generate_payload["request_id"])
        report_rel_path = generate_payload["report_path"]
        report_path = tmp_path / report_rel_path
        assert report_path.exists()
        _assert_dashboard_report_html_structure(report_path.read_text(encoding="utf-8"))

        conn.request("GET", "/dashboard/report")
        report_response = conn.getresponse()
        report_html = report_response.read().decode("utf-8")
        assert report_response.status == 200
        _assert_dashboard_report_html_structure(report_html)


def test_cross_run_payload_contract_global_leaderboard(tmp_path, monkeypatch):
    artifacts = _setup_batch_env(tmp_path, monkeypatch)
    _seed_dashboard_cross_run_artifacts(artifacts)

    payload = cp._cross_run_payload(top_n=10)

    _assert_dashboard_cross_run_payload_schema(payload)
    assert payload["summary"]["total_runs"] == 1
    assert payload["summary"]["coverage_pct"] == 50.0
    assert len(payload["global_leaderboard"]) == 1
    row = payload["global_leaderboard"][0]
    assert row["run_id"] == "r100"
    assert row["search_mode"] == "baseline"
    assert set(row["trade_symbols"]) == {"ETH/USDT", "BNB/USDT"}
    assert row["timeframes"] == ["2h"]


def test_dashboard_cross_run_endpoint_falls_back_to_cached_payload_integration(tmp_path, monkeypatch):
    artifacts = _setup_batch_env(tmp_path, monkeypatch)
    (artifacts / "cross_run_report.json").write_text(
        json.dumps(
            {
                "schema_version": "autowfo.cross_run_payload/v0",
                "generated_utc": "2026-02-20T10:00:00Z",
                "summary": {"total_runs": 1, "coverage_pct": 88.0},
                "global_leaderboard": [{"run_id": "legacy-r1"}],
            }
        ),
        encoding="utf-8",
    )

    def _boom(top_n=20):  # noqa: ARG001
        raise RuntimeError("payload boom")

    monkeypatch.setattr(cp, "_cross_run_payload", _boom)

    with _serve_handler_connection(timeout=10) as conn:
        conn.request("GET", "/dashboard/cross_run.json?top_n=10")
        response = conn.getresponse()
        body = response.read().decode("utf-8")
        assert response.status == 200
        payload = json.loads(body)
        _assert_dashboard_cross_run_payload_schema(payload)
        assert payload["payload_source"] == "cache_fallback"
        _assert_request_id(payload["request_id"])
        assert payload["global_leaderboard"][0]["run_id"] == "legacy-r1"
        assert payload["source_schema_version"] == "autowfo.cross_run_payload/v0"
        assert payload["cache_fallback"]["used"] is True
        assert payload["cache_fallback"]["reason_code"] == "runtime_error"
        assert payload["cache_fallback"]["live_error"]["code"] == "runtime_error"
        assert payload["cache_fallback"]["live_error"]["type"] == "RuntimeError"
        assert "payload boom" in payload["cache_fallback"]["live_error"]["message"]
        assert payload["cache_fallback"]["fallback_for"] == "dashboard/cross_run.json"
        assert payload["cache_fallback"]["endpoint"] == "dashboard/cross_run.json"
        assert payload["cache_fallback"]["request_id"] == payload["request_id"]
        assert payload["cache_fallback"]["fallback_utc"]


def test_dashboard_cross_run_endpoint_invalid_cached_payload_returns_500_integration(tmp_path, monkeypatch):
    artifacts = _setup_batch_env(tmp_path, monkeypatch)
    (artifacts / "cross_run_report.json").write_text("{broken", encoding="utf-8")

    def _boom(top_n=20):  # noqa: ARG001
        raise RuntimeError("payload boom")

    monkeypatch.setattr(cp, "_cross_run_payload", _boom)

    with _serve_handler_connection(timeout=10) as conn:
        conn.request("GET", "/dashboard/cross_run.json?top_n=10")
        response = conn.getresponse()
        body = response.read().decode("utf-8")
        assert response.status == 500
        payload = json.loads(body)
        assert payload["ok"] is False
        _assert_request_id(payload["request_id"])
        assert payload["endpoint"] == "dashboard/cross_run.json"
        assert payload["error_utc"]
        assert payload["error_code"] == "runtime_error"
        assert payload["live_error"]["code"] == "runtime_error"
        assert payload["live_error"]["type"] == "RuntimeError"
        assert "payload boom" in payload["live_error"]["message"]
        assert payload["cache_error_code"] == "invalid_json"
        assert payload["cache_error"]["code"] == "invalid_json"
        assert payload["cache_error"]["type"] == "CrossRunPayloadValidationError"
        assert "cross-run payload failed" in payload["message"]


def test_dashboard_cross_run_endpoint_invalid_live_payload_contract_uses_cache_integration(tmp_path, monkeypatch):
    artifacts = _setup_batch_env(tmp_path, monkeypatch)
    (artifacts / "cross_run_report.json").write_text(
        json.dumps(
            {
                "generated_utc": "2026-02-20T10:00:00Z",
                "summary": {"total_runs": 2, "coverage_pct": 92.0},
                "global_leaderboard": [{"run_id": "cache-contract-r1"}],
            }
        ),
        encoding="utf-8",
    )

    def _bad_payload(top_n=20):  # noqa: ARG001
        return {
            "schema_version": "autowfo.cross_run_payload/v1",
            "generated_utc": "2026-02-20T10:00:00Z",
            "registry_path": "artifacts/run_registry.json",
            "summary": {"total_runs": 1},
            "run_history": [],
            "global_leaderboard": [],
            "combo_stability": [],
            "per_regime_leaderboard": {},
            "regime_summary": [],
        }

    monkeypatch.setattr(cp, "_cross_run_payload", _bad_payload)

    with _serve_handler_connection(timeout=10) as conn:
        conn.request("GET", "/dashboard/cross_run.json?top_n=10")
        response = conn.getresponse()
        body = response.read().decode("utf-8")
        assert response.status == 200
        payload = json.loads(body)
        _assert_dashboard_cross_run_payload_schema(payload)
        assert payload["payload_source"] == "cache_fallback"
        _assert_request_id(payload["request_id"])
        assert payload["global_leaderboard"][0]["run_id"] == "cache-contract-r1"
        assert payload["cache_fallback"]["reason_code"] == "missing_summary_keys"
        assert payload["cache_fallback"]["live_error"]["code"] == "missing_summary_keys"
        assert payload["cache_fallback"]["live_error"]["type"] == "CrossRunPayloadValidationError"
        assert payload["cache_fallback"]["fallback_for"] == "dashboard/cross_run.json"
        assert payload["cache_fallback"]["endpoint"] == "dashboard/cross_run.json"
        assert payload["cache_fallback"]["request_id"] == payload["request_id"]


def test_dashboard_cross_run_endpoint_returns_500_on_payload_error_integration(tmp_path, monkeypatch):
    _setup_batch_env(tmp_path, monkeypatch)

    def _boom(top_n=20):  # noqa: ARG001
        raise RuntimeError("payload boom")

    monkeypatch.setattr(cp, "_cross_run_payload", _boom)

    with _serve_handler_connection(timeout=10) as conn:
        conn.request("GET", "/dashboard/cross_run.json?top_n=10")
        response = conn.getresponse()
        body = response.read().decode("utf-8")
        assert response.status == 500
        payload = json.loads(body)
        assert payload["ok"] is False
        _assert_request_id(payload["request_id"])
        assert payload["endpoint"] == "dashboard/cross_run.json"
        assert payload["error_utc"]
        assert payload["error_code"] == "runtime_error"
        assert payload["live_error"]["code"] == "runtime_error"
        assert payload["live_error"]["type"] == "RuntimeError"
        assert payload["cache_error_code"] == "payload_file_missing"
        assert payload["cache_error"]["code"] == "payload_file_missing"
        assert payload["cache_error"]["type"] == "CrossRunPayloadValidationError"
        assert "cross-run payload failed" in payload["message"]


def test_dashboard_report_endpoint_missing_artifact_returns_404_integration(tmp_path, monkeypatch):
    artifacts = _setup_batch_env(tmp_path, monkeypatch)
    (artifacts / "cross_run_report.html").unlink(missing_ok=True)

    def _missing(top_n=20):  # noqa: ARG001
        return (
            {
                "schema_version": "autowfo.cross_run_payload/v1",
                "generated_utc": "2026-02-20T00:00:00Z",
                "registry_path": "artifacts/run_registry.json",
                "summary": {
                    "total_runs": 0,
                    "unique_symbols": 0,
                    "unique_timeframes": 0,
                    "avg_oos_return_pct": None,
                    "avg_bh_return_pct": None,
                    "avg_random_return_pct": None,
                    "avg_alpha_vs_bh": None,
                    "latest_run_id": None,
                    "latest_run_time_utc": None,
                    "coverage_tested_pairs": 0,
                    "coverage_untested_pairs": 0,
                    "coverage_pct": 0.0,
                },
                "run_history": [],
                "global_leaderboard": [],
                "combo_stability": [],
                "per_regime_leaderboard": {},
                "regime_summary": [],
            },
            artifacts / "cross_run_report_missing.html",
        )

    monkeypatch.setattr(cp, "_cross_run_generate_report", _missing)

    with _serve_handler_connection(timeout=10) as conn:
        conn.request("GET", "/dashboard/report")
        response = conn.getresponse()
        body = response.read().decode("utf-8")
        assert response.status == 404
        assert "Cross-run report unavailable" in body


def test_dashboard_report_endpoint_returns_500_on_generation_error_integration(tmp_path, monkeypatch):
    artifacts = _setup_batch_env(tmp_path, monkeypatch)
    (artifacts / "cross_run_report.html").unlink(missing_ok=True)

    def _boom(top_n=20):  # noqa: ARG001
        raise RuntimeError("report boom")

    monkeypatch.setattr(cp, "_cross_run_generate_report", _boom)

    with _serve_handler_connection(timeout=10) as conn:
        conn.request("GET", "/dashboard/report")
        response = conn.getresponse()
        body = response.read().decode("utf-8")
        assert response.status == 500
        assert "Generate report failed: report boom" in body


def test_dashboard_report_endpoint_uses_cached_json_when_generate_fails_integration(tmp_path, monkeypatch):
    artifacts = _setup_batch_env(tmp_path, monkeypatch)
    (artifacts / "cross_run_report.html").unlink(missing_ok=True)
    (artifacts / "cross_run_report.json").write_text(
        json.dumps(
            {
                "generated_utc": "2026-02-20T12:00:00Z",
                "summary": {"total_runs": 1, "coverage_pct": 77.0},
                "global_leaderboard": [{"run_id": "cache-r1"}],
            }
        ),
        encoding="utf-8",
    )

    def _boom(top_n=20):  # noqa: ARG001
        raise RuntimeError("report boom")

    monkeypatch.setattr(cp, "_cross_run_generate_report", _boom)

    with _serve_handler_connection(timeout=10) as conn:
        conn.request("GET", "/dashboard/report")
        response = conn.getresponse()
        body = response.read().decode("utf-8")
        assert response.status == 200
        assert "AUTOWFO Cross-Run Report" in body
        assert "cache-r1" in body


def test_dashboard_report_generate_endpoint_returns_500_on_generation_error_integration(tmp_path, monkeypatch):
    _setup_batch_env(tmp_path, monkeypatch)

    def _boom(top_n=20):  # noqa: ARG001
        raise RuntimeError("generate boom")

    monkeypatch.setattr(cp, "_cross_run_generate_report", _boom)

    with _serve_handler_connection(timeout=10) as conn:
        conn.request(
            "POST",
            "/dashboard/report/generate",
            body=json.dumps({"top_n": 10}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        body = response.read().decode("utf-8")
        assert response.status == 500
        payload = json.loads(body)
        assert payload["ok"] is False
        _assert_request_id(payload["request_id"])
        assert payload["endpoint"] == "dashboard/report/generate"
        assert payload["error_utc"]
        assert payload["error_code"] == "runtime_error"
        assert payload["live_error"]["code"] == "runtime_error"
        assert payload["live_error"]["type"] == "RuntimeError"
        assert payload["cache_error_code"] == "payload_file_missing"
        assert payload["cache_error"]["code"] == "payload_file_missing"
        assert payload["cache_error"]["type"] == "CrossRunPayloadValidationError"
        assert "report generation failed: generate boom" in payload["message"]


def test_dashboard_report_generate_endpoint_falls_back_to_cached_json_on_generation_error_integration(tmp_path, monkeypatch):
    artifacts = _setup_batch_env(tmp_path, monkeypatch)
    (artifacts / "cross_run_report.html").unlink(missing_ok=True)
    (artifacts / "cross_run_report.json").write_text(
        json.dumps(
            {
                "generated_utc": "2026-02-20T12:00:00Z",
                "summary": {"total_runs": 2, "coverage_pct": 66.0},
                "global_leaderboard": [{"run_id": "cache-r2"}],
            }
        ),
        encoding="utf-8",
    )

    def _boom(top_n=20):  # noqa: ARG001
        raise RuntimeError("generate boom")

    monkeypatch.setattr(cp, "_cross_run_generate_report", _boom)

    with _serve_handler_connection(timeout=10) as conn:
        conn.request(
            "POST",
            "/dashboard/report/generate",
            body=json.dumps({"top_n": 10}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        body = response.read().decode("utf-8")
        assert response.status == 200
        payload = json.loads(body)
        assert payload["ok"] is True
        assert payload["payload_source"] == "cache_fallback"
        _assert_request_id(payload["request_id"])
        assert "cache fallback" in payload["message"]
        assert payload["cache_fallback"]["used"] is True
        assert payload["cache_fallback"]["reason_code"] == "runtime_error"
        assert payload["cache_fallback"]["live_error"]["code"] == "runtime_error"
        assert payload["cache_fallback"]["live_error"]["type"] == "RuntimeError"
        assert payload["cache_fallback"]["fallback_for"] == "dashboard/report/generate"
        assert payload["cache_fallback"]["endpoint"] == "dashboard/report/generate"
        assert payload["cache_fallback"]["request_id"] == payload["request_id"]
        assert payload["cache_fallback"]["fallback_utc"]
        report_path = tmp_path / payload["report_path"]
        assert report_path.exists()
        report_html = report_path.read_text(encoding="utf-8")
        assert "AUTOWFO Cross-Run Report" in report_html
        assert "cache-r2" in report_html


def test_dashboard_report_generate_invalid_live_payload_contract_uses_cache_integration(tmp_path, monkeypatch):
    artifacts = _setup_batch_env(tmp_path, monkeypatch)
    (artifacts / "cross_run_report.json").write_text(
        json.dumps(
            {
                "generated_utc": "2026-02-20T12:00:00Z",
                "summary": {"total_runs": 1, "coverage_pct": 73.0},
                "global_leaderboard": [{"run_id": "cache-contract-r2"}],
            }
        ),
        encoding="utf-8",
    )

    def _bad_generate(top_n=20):  # noqa: ARG001
        return (
            {
                "schema_version": "autowfo.cross_run_payload/v1",
                "generated_utc": "2026-02-20T12:00:00Z",
                "registry_path": "artifacts/run_registry.json",
                "summary": {"total_runs": 1},
                "run_history": [],
                "global_leaderboard": [],
                "combo_stability": [],
                "per_regime_leaderboard": {},
                "regime_summary": [],
            },
            artifacts / "cross_run_report.html",
        )

    monkeypatch.setattr(cp, "_cross_run_generate_report", _bad_generate)

    with _serve_handler_connection(timeout=10) as conn:
        conn.request(
            "POST",
            "/dashboard/report/generate",
            body=json.dumps({"top_n": 10}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        body = response.read().decode("utf-8")
        assert response.status == 200
        payload = json.loads(body)
        assert payload["ok"] is True
        assert payload["payload_source"] == "cache_fallback"
        _assert_request_id(payload["request_id"])
        assert payload["cache_fallback"]["used"] is True
        assert payload["cache_fallback"]["reason_code"] == "missing_summary_keys"
        assert payload["cache_fallback"]["live_error"]["code"] == "missing_summary_keys"
        assert payload["cache_fallback"]["live_error"]["type"] == "CrossRunPayloadValidationError"
        assert payload["cache_fallback"]["fallback_for"] == "dashboard/report/generate"
        assert payload["cache_fallback"]["endpoint"] == "dashboard/report/generate"
        assert payload["cache_fallback"]["request_id"] == payload["request_id"]
        report_path = tmp_path / payload["report_path"]
        assert report_path.exists()
        report_html = report_path.read_text(encoding="utf-8")
        assert "cache-contract-r2" in report_html


def test_dashboard_report_generate_invalid_json_keeps_defaults_and_summary_consistent(tmp_path, monkeypatch):
    artifacts = _setup_batch_env(tmp_path, monkeypatch)
    _seed_dashboard_cross_run_artifacts(artifacts)

    with _serve_handler_connection(timeout=10) as conn:
        conn.request(
            "POST",
            "/dashboard/report/generate",
            body=b"{invalid-json",
            headers={"Content-Type": "application/json"},
        )
        generate_response = conn.getresponse()
        generate_body = generate_response.read().decode("utf-8")
        assert generate_response.status == 200
        generate_payload = json.loads(generate_body)
        assert generate_payload["ok"] is True
        assert generate_payload["payload_source"] == "live"

        report_json_path = artifacts / "cross_run_report.json"
        assert report_json_path.exists()
        report_json_payload = json.loads(report_json_path.read_text(encoding="utf-8"))
        _assert_dashboard_cross_run_payload_schema(report_json_payload)
        assert report_json_payload["summary"] == generate_payload["summary"]

        conn.request("GET", "/dashboard/cross_run.json?top_n=20")
        cross_run_response = conn.getresponse()
        cross_run_body = cross_run_response.read().decode("utf-8")
        assert cross_run_response.status == 200
        cross_run_payload = json.loads(cross_run_body)
        _assert_dashboard_cross_run_payload_schema(cross_run_payload)
        assert cross_run_payload["summary"] == generate_payload["summary"]


def test_dashboard_errors_endpoint_empty_integration(tmp_path, monkeypatch):
    _setup_batch_env(tmp_path, monkeypatch)

    with _serve_handler_connection(timeout=10) as conn:
        conn.request("GET", "/dashboard/errors.json?limit=5")
        response = conn.getresponse()
        body = response.read().decode("utf-8")
        assert response.status == 200
        payload = json.loads(body)
        assert payload["ok"] is True
        assert payload["count"] == 0
        assert payload["matched_count"] == 0
        assert payload["total_available"] == 0
        assert payload["offset"] == 0
        assert payload["has_more"] is False
        assert payload["next_offset"] is None
        assert payload["rows"] == []
        assert payload["summary"]["by_kind"] == {}
        assert payload["summary"]["by_endpoint"] == {}
        assert payload["summary"]["by_error_code"] == {}
        assert payload["summary"]["by_cache_error_code"] == {}
        assert payload["filters"]["kind"] == ""
        assert payload["filters"]["error_code"] == ""
        assert payload["filters"]["cache_error_code"] == ""
        assert payload["filters"]["status"] is None
        assert payload["filters"]["message_contains"] == ""
        assert payload["filters"]["since_hours"] == 0
        assert payload["path"] == "artifacts/dashboard_error_events.ndjson"
        assert payload["updated_utc"]


def test_dashboard_cross_run_error_event_logged_and_queryable_integration(tmp_path, monkeypatch):
    _setup_batch_env(tmp_path, monkeypatch)

    def _boom(top_n=20):  # noqa: ARG001
        raise RuntimeError("payload boom")

    monkeypatch.setattr(cp, "_cross_run_payload", _boom)

    with _serve_handler_connection(timeout=10) as conn:
        conn.request("GET", "/dashboard/cross_run.json?top_n=10")
        response = conn.getresponse()
        body = response.read().decode("utf-8")
        assert response.status == 500
        payload = json.loads(body)
        request_id = payload["request_id"]
        _assert_request_id(request_id)

        conn.request(
            "GET",
            f"/dashboard/errors.json?limit=20&endpoint=dashboard/cross_run.json&request_id={request_id}",
        )
        events_response = conn.getresponse()
        events_body = events_response.read().decode("utf-8")
        assert events_response.status == 200
        events_payload = json.loads(events_body)
        assert events_payload["count"] == 1
        row = events_payload["rows"][0]
        _assert_dashboard_error_event_row(row)
        assert row["kind"] == "error"
        assert row["endpoint"] == "dashboard/cross_run.json"
        assert row["request_id"] == request_id
        assert row["status"] == 500
        assert row["error_code"] == "runtime_error"
        assert row["cache_error_code"] == "payload_file_missing"
        assert "cross-run payload failed" in row["message"]


def test_dashboard_cross_run_cache_fallback_event_logged_and_queryable_integration(tmp_path, monkeypatch):
    artifacts = _setup_batch_env(tmp_path, monkeypatch)
    (artifacts / "cross_run_report.json").write_text(
        json.dumps(
            {
                "generated_utc": "2026-02-21T10:00:00Z",
                "summary": {"total_runs": 1, "coverage_pct": 88.0},
                "global_leaderboard": [{"run_id": "cache-r1"}],
            }
        ),
        encoding="utf-8",
    )

    def _boom(top_n=20):  # noqa: ARG001
        raise RuntimeError("payload boom")

    monkeypatch.setattr(cp, "_cross_run_payload", _boom)

    with _serve_handler_connection(timeout=10) as conn:
        conn.request("GET", "/dashboard/cross_run.json?top_n=10")
        response = conn.getresponse()
        body = response.read().decode("utf-8")
        assert response.status == 200
        payload = json.loads(body)
        assert payload["payload_source"] == "cache_fallback"
        request_id = payload["request_id"]
        _assert_request_id(request_id)

        conn.request(
            "GET",
            f"/dashboard/errors.json?limit=20&endpoint=dashboard/cross_run.json&request_id={request_id}",
        )
        events_response = conn.getresponse()
        events_body = events_response.read().decode("utf-8")
        assert events_response.status == 200
        events_payload = json.loads(events_body)
        assert events_payload["count"] == 1
        row = events_payload["rows"][0]
        _assert_dashboard_error_event_row(row)
        assert row["kind"] == "cache_fallback"
        assert row["endpoint"] == "dashboard/cross_run.json"
        assert row["request_id"] == request_id
        assert row["status"] == 200
        assert row["error_code"] == "runtime_error"
        assert row["cache_error_code"] == ""
        assert "cache fallback" in row["message"]
        assert row["cache_fallback"]["request_id"] == request_id


def test_dashboard_report_generate_error_event_logged_and_queryable_integration(tmp_path, monkeypatch):
    _setup_batch_env(tmp_path, monkeypatch)

    def _boom(top_n=20):  # noqa: ARG001
        raise RuntimeError("generate boom")

    monkeypatch.setattr(cp, "_cross_run_generate_report", _boom)

    with _serve_handler_connection(timeout=10) as conn:
        conn.request(
            "POST",
            "/dashboard/report/generate",
            body=json.dumps({"top_n": 10}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        body = response.read().decode("utf-8")
        assert response.status == 500
        payload = json.loads(body)
        request_id = payload["request_id"]
        _assert_request_id(request_id)

        conn.request(
            "GET",
            f"/dashboard/errors.json?limit=20&endpoint=dashboard/report/generate&request_id={request_id}",
        )
        events_response = conn.getresponse()
        events_body = events_response.read().decode("utf-8")
        assert events_response.status == 200
        events_payload = json.loads(events_body)
        assert events_payload["count"] == 1
        row = events_payload["rows"][0]
        _assert_dashboard_error_event_row(row)
        assert row["kind"] == "error"
        assert row["endpoint"] == "dashboard/report/generate"
        assert row["request_id"] == request_id
        assert row["status"] == 500
        assert row["error_code"] == "runtime_error"
        assert row["cache_error_code"] == "payload_file_missing"
        assert "report generation failed" in row["message"]


def test_dashboard_report_generate_cache_fallback_event_logged_and_queryable_integration(tmp_path, monkeypatch):
    artifacts = _setup_batch_env(tmp_path, monkeypatch)
    (artifacts / "cross_run_report.json").write_text(
        json.dumps(
            {
                "generated_utc": "2026-02-21T12:00:00Z",
                "summary": {"total_runs": 2, "coverage_pct": 66.0},
                "global_leaderboard": [{"run_id": "cache-r2"}],
            }
        ),
        encoding="utf-8",
    )

    def _boom(top_n=20):  # noqa: ARG001
        raise RuntimeError("generate boom")

    monkeypatch.setattr(cp, "_cross_run_generate_report", _boom)

    with _serve_handler_connection(timeout=10) as conn:
        conn.request(
            "POST",
            "/dashboard/report/generate",
            body=json.dumps({"top_n": 10}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        body = response.read().decode("utf-8")
        assert response.status == 200
        payload = json.loads(body)
        assert payload["payload_source"] == "cache_fallback"
        request_id = payload["request_id"]
        _assert_request_id(request_id)

        conn.request(
            "GET",
            f"/dashboard/errors.json?limit=20&endpoint=dashboard/report/generate&request_id={request_id}",
        )
        events_response = conn.getresponse()
        events_body = events_response.read().decode("utf-8")
        assert events_response.status == 200
        events_payload = json.loads(events_body)
        assert events_payload["count"] == 1
        row = events_payload["rows"][0]
        _assert_dashboard_error_event_row(row)
        assert row["kind"] == "cache_fallback"
        assert row["endpoint"] == "dashboard/report/generate"
        assert row["request_id"] == request_id
        assert row["status"] == 200
        assert row["error_code"] == "runtime_error"
        assert row["cache_error_code"] == ""
        assert "cache fallback" in row["message"]
        assert row["cache_fallback"]["request_id"] == request_id


def test_dashboard_errors_endpoint_filters_and_summary_integration(tmp_path, monkeypatch):
    artifacts = _setup_batch_env(tmp_path, monkeypatch)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    rows = [
        {
            "event_utc": (now - timedelta(hours=1)).isoformat(),
            "kind": "error",
            "endpoint": "dashboard/cross_run.json",
            "request_id": "a" * 32,
            "status": 500,
            "message": "e1",
            "error_code": "runtime_error",
            "cache_error_code": "payload_file_missing",
        },
        {
            "event_utc": (now - timedelta(hours=2)).isoformat(),
            "kind": "cache_fallback",
            "endpoint": "dashboard/report/generate",
            "request_id": "b" * 32,
            "status": 200,
            "message": "f1",
            "error_code": "missing_summary_keys",
            "cache_error_code": "",
        },
        {
            "event_utc": (now - timedelta(hours=40)).isoformat(),
            "kind": "error",
            "endpoint": "dashboard/cross_run.json",
            "request_id": "c" * 32,
            "status": 500,
            "message": "old",
            "error_code": "runtime_error",
            "cache_error_code": "",
        },
    ]
    _write_dashboard_error_events(artifacts / "dashboard_error_events.ndjson", rows)

    with _serve_handler_connection(timeout=10) as conn:
        conn.request("GET", "/dashboard/errors.json?limit=10&endpoint=dashboard/cross_run.json&kind=error&since_hours=24")
        response = conn.getresponse()
        body = response.read().decode("utf-8")
        assert response.status == 200
        payload = json.loads(body)
        assert payload["ok"] is True
        assert payload["count"] == 1
        assert payload["matched_count"] == 1
        assert payload["rows"][0]["message"] == "e1"
        assert payload["filters"]["endpoint"] == "dashboard/cross_run.json"
        assert payload["filters"]["kind"] == "error"
        assert payload["filters"]["since_hours"] == 24.0
        assert payload["summary"]["by_kind"] == {"error": 1}
        assert payload["summary"]["by_endpoint"] == {"dashboard/cross_run.json": 1}
        assert payload["summary"]["by_error_code"] == {"runtime_error": 1}


def test_dashboard_errors_clear_endpoint_filtered_and_all_integration(tmp_path, monkeypatch):
    artifacts = _setup_batch_env(tmp_path, monkeypatch)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    rows = [
        {
            "event_utc": now,
            "kind": "error",
            "endpoint": "dashboard/cross_run.json",
            "request_id": "d" * 32,
            "status": 500,
            "message": "e-cross",
            "error_code": "runtime_error",
            "cache_error_code": "",
        },
        {
            "event_utc": now,
            "kind": "cache_fallback",
            "endpoint": "dashboard/report/generate",
            "request_id": "e" * 32,
            "status": 200,
            "message": "f-report",
            "error_code": "runtime_error",
            "cache_error_code": "",
        },
    ]
    _write_dashboard_error_events(artifacts / "dashboard_error_events.ndjson", rows)

    with _serve_handler_connection(timeout=10) as conn:
        conn.request(
            "POST",
            "/dashboard/errors/clear",
            body=json.dumps({"endpoint": "dashboard/cross_run.json"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        clear_response = conn.getresponse()
        clear_body = clear_response.read().decode("utf-8")
        assert clear_response.status == 200
        clear_payload = json.loads(clear_body)
        assert clear_payload["ok"] is True
        assert clear_payload["cleared"] == 1
        assert clear_payload["remaining"] == 1
        assert clear_payload["cleared_all"] is False

        conn.request("GET", "/dashboard/errors.json?limit=10")
        remain_response = conn.getresponse()
        remain_body = remain_response.read().decode("utf-8")
        assert remain_response.status == 200
        remain_payload = json.loads(remain_body)
        assert remain_payload["count"] == 1
        assert remain_payload["rows"][0]["endpoint"] == "dashboard/report/generate"

        conn.request(
            "POST",
            "/dashboard/errors/clear",
            body=json.dumps({}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        clear_all_response = conn.getresponse()
        clear_all_body = clear_all_response.read().decode("utf-8")
        assert clear_all_response.status == 200
        clear_all_payload = json.loads(clear_all_body)
        assert clear_all_payload["ok"] is True
        assert clear_all_payload["cleared"] == 1
        assert clear_all_payload["remaining"] == 0
        assert clear_all_payload["cleared_all"] is True

    assert not (artifacts / "dashboard_error_events.ndjson").exists()


def test_dashboard_errors_endpoint_pagination_and_code_filters_integration(tmp_path, monkeypatch):
    artifacts = _setup_batch_env(tmp_path, monkeypatch)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    rows = [
        {
            "event_utc": (now - timedelta(minutes=30)).isoformat(),
            "kind": "error",
            "endpoint": "dashboard/cross_run.json",
            "request_id": "2" * 32,
            "status": 500,
            "message": "runtime-old",
            "error_code": "runtime_error",
            "cache_error_code": "payload_file_missing",
        },
        {
            "event_utc": (now - timedelta(minutes=20)).isoformat(),
            "kind": "cache_fallback",
            "endpoint": "dashboard/report/generate",
            "request_id": "1" * 32,
            "status": 200,
            "message": "fallback",
            "error_code": "missing_summary_keys",
            "cache_error_code": "",
        },
        {
            "event_utc": (now - timedelta(minutes=10)).isoformat(),
            "kind": "error",
            "endpoint": "dashboard/cross_run.json",
            "request_id": "f" * 32,
            "status": 500,
            "message": "runtime-new",
            "error_code": "runtime_error",
            "cache_error_code": "",
        },
    ]
    _write_dashboard_error_events(artifacts / "dashboard_error_events.ndjson", rows)

    with _serve_handler_connection(timeout=10) as conn:
        conn.request("GET", "/dashboard/errors.json?limit=1&offset=0&error_code=runtime_error")
        response_page1 = conn.getresponse()
        body_page1 = response_page1.read().decode("utf-8")
        assert response_page1.status == 200
        payload_page1 = json.loads(body_page1)
        assert payload_page1["count"] == 1
        assert payload_page1["matched_count"] == 2
        assert payload_page1["total_available"] == 2
        assert payload_page1["offset"] == 0
        assert payload_page1["has_more"] is True
        assert payload_page1["next_offset"] == 1
        assert payload_page1["filters"]["error_code"] == "runtime_error"
        assert payload_page1["rows"][0]["message"] == "runtime-new"

        conn.request("GET", "/dashboard/errors.json?limit=1&offset=1&error_code=runtime_error")
        response_page2 = conn.getresponse()
        body_page2 = response_page2.read().decode("utf-8")
        assert response_page2.status == 200
        payload_page2 = json.loads(body_page2)
        assert payload_page2["count"] == 1
        assert payload_page2["matched_count"] == 2
        assert payload_page2["total_available"] == 2
        assert payload_page2["offset"] == 1
        assert payload_page2["has_more"] is False
        assert payload_page2["next_offset"] is None
        assert payload_page2["filters"]["error_code"] == "runtime_error"
        assert payload_page2["rows"][0]["message"] == "runtime-old"
        assert payload_page1["rows"][0]["request_id"] != payload_page2["rows"][0]["request_id"]

        conn.request("GET", "/dashboard/errors.json?limit=10&cache_error_code=payload_file_missing")
        response_cache_code = conn.getresponse()
        body_cache_code = response_cache_code.read().decode("utf-8")
        assert response_cache_code.status == 200
        payload_cache_code = json.loads(body_cache_code)
        assert payload_cache_code["count"] == 1
        assert payload_cache_code["filters"]["cache_error_code"] == "payload_file_missing"
        assert payload_cache_code["rows"][0]["message"] == "runtime-old"


def test_dashboard_errors_endpoint_status_and_message_filters_integration(tmp_path, monkeypatch):
    artifacts = _setup_batch_env(tmp_path, monkeypatch)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    rows = [
        {
            "event_utc": now,
            "kind": "error",
            "endpoint": "dashboard/cross_run.json",
            "request_id": "6" * 32,
            "status": 500,
            "message": "cross-run payload failed: runtime_error",
            "error_code": "runtime_error",
            "cache_error_code": "",
        },
        {
            "event_utc": now,
            "kind": "cache_fallback",
            "endpoint": "dashboard/report/generate",
            "request_id": "7" * 32,
            "status": 200,
            "message": "cross-run report generated from cache fallback",
            "error_code": "missing_summary_keys",
            "cache_error_code": "",
        },
    ]
    _write_dashboard_error_events(artifacts / "dashboard_error_events.ndjson", rows)

    with _serve_handler_connection(timeout=10) as conn:
        conn.request("GET", "/dashboard/errors.json?limit=10&status=500&message_contains=payload")
        response = conn.getresponse()
        body = response.read().decode("utf-8")
        assert response.status == 200
        payload = json.loads(body)
        assert payload["count"] == 1
        assert payload["filters"]["status"] == 500
        assert payload["filters"]["message_contains"] == "payload"
        assert payload["rows"][0]["request_id"] == "6" * 32

        conn.request("GET", "/dashboard/errors.json?limit=10&status=200&message_contains=fallback")
        response_200 = conn.getresponse()
        body_200 = response_200.read().decode("utf-8")
        assert response_200.status == 200
        payload_200 = json.loads(body_200)
        assert payload_200["count"] == 1
        assert payload_200["filters"]["status"] == 200
        assert payload_200["rows"][0]["request_id"] == "7" * 32


def test_dashboard_errors_clear_endpoint_error_code_filter_integration(tmp_path, monkeypatch):
    artifacts = _setup_batch_env(tmp_path, monkeypatch)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    rows = [
        {
            "event_utc": now,
            "kind": "error",
            "endpoint": "dashboard/cross_run.json",
            "request_id": "3" * 32,
            "status": 500,
            "message": "runtime-a",
            "error_code": "runtime_error",
            "cache_error_code": "",
        },
        {
            "event_utc": now,
            "kind": "error",
            "endpoint": "dashboard/report/generate",
            "request_id": "4" * 32,
            "status": 500,
            "message": "runtime-b",
            "error_code": "runtime_error",
            "cache_error_code": "payload_file_missing",
        },
        {
            "event_utc": now,
            "kind": "cache_fallback",
            "endpoint": "dashboard/report/generate",
            "request_id": "5" * 32,
            "status": 200,
            "message": "fallback",
            "error_code": "missing_summary_keys",
            "cache_error_code": "",
        },
    ]
    _write_dashboard_error_events(artifacts / "dashboard_error_events.ndjson", rows)

    with _serve_handler_connection(timeout=10) as conn:
        conn.request(
            "POST",
            "/dashboard/errors/clear",
            body=json.dumps({"error_code": "runtime_error"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        clear_response = conn.getresponse()
        clear_body = clear_response.read().decode("utf-8")
        assert clear_response.status == 200
        clear_payload = json.loads(clear_body)
        assert clear_payload["ok"] is True
        assert clear_payload["cleared"] == 2
        assert clear_payload["remaining"] == 1
        assert clear_payload["filters"]["error_code"] == "runtime_error"
        assert clear_payload["cleared_all"] is False

        conn.request("GET", "/dashboard/errors.json?limit=10")
        response = conn.getresponse()
        body = response.read().decode("utf-8")
        assert response.status == 200
        payload = json.loads(body)
        assert payload["count"] == 1
        assert payload["rows"][0]["error_code"] == "missing_summary_keys"


def test_dashboard_errors_clear_endpoint_status_and_message_filter_integration(tmp_path, monkeypatch):
    artifacts = _setup_batch_env(tmp_path, monkeypatch)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    rows = [
        {
            "event_utc": now,
            "kind": "error",
            "endpoint": "dashboard/cross_run.json",
            "request_id": "8" * 32,
            "status": 500,
            "message": "runtime payload failure",
            "error_code": "runtime_error",
            "cache_error_code": "",
        },
        {
            "event_utc": now,
            "kind": "error",
            "endpoint": "dashboard/report/generate",
            "request_id": "9" * 32,
            "status": 500,
            "message": "runtime report failure",
            "error_code": "runtime_error",
            "cache_error_code": "",
        },
        {
            "event_utc": now,
            "kind": "cache_fallback",
            "endpoint": "dashboard/report/generate",
            "request_id": "a" * 32,
            "status": 200,
            "message": "cache fallback",
            "error_code": "missing_summary_keys",
            "cache_error_code": "",
        },
    ]
    _write_dashboard_error_events(artifacts / "dashboard_error_events.ndjson", rows)

    with _serve_handler_connection(timeout=10) as conn:
        conn.request(
            "POST",
            "/dashboard/errors/clear",
            body=json.dumps({"status": 500, "message_contains": "payload"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        clear_response = conn.getresponse()
        clear_body = clear_response.read().decode("utf-8")
        assert clear_response.status == 200
        clear_payload = json.loads(clear_body)
        assert clear_payload["cleared"] == 1
        assert clear_payload["remaining"] == 2
        assert clear_payload["filters"]["status"] == 500
        assert clear_payload["filters"]["message_contains"] == "payload"

        conn.request("GET", "/dashboard/errors.json?limit=10")
        response = conn.getresponse()
        body = response.read().decode("utf-8")
        assert response.status == 200
        payload = json.loads(body)
        assert payload["count"] == 2
        req_ids = {row["request_id"] for row in payload["rows"]}
        assert req_ids == {"9" * 32, "a" * 32}


def test_dashboard_errors_export_ndjson_filters_integration(tmp_path, monkeypatch):
    artifacts = _setup_batch_env(tmp_path, monkeypatch)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    rows = [
        {
            "event_utc": now,
            "kind": "error",
            "endpoint": "dashboard/cross_run.json",
            "request_id": "b" * 32,
            "status": 500,
            "message": "payload export target",
            "error_code": "runtime_error",
            "cache_error_code": "",
        },
        {
            "event_utc": now,
            "kind": "cache_fallback",
            "endpoint": "dashboard/report/generate",
            "request_id": "c" * 32,
            "status": 200,
            "message": "fallback other",
            "error_code": "missing_summary_keys",
            "cache_error_code": "",
        },
    ]
    _write_dashboard_error_events(artifacts / "dashboard_error_events.ndjson", rows)

    with _serve_handler_connection(timeout=10) as conn:
        conn.request("GET", "/dashboard/errors/export.ndjson?status=500&message_contains=payload&limit=20")
        response = conn.getresponse()
        body = response.read().decode("utf-8")
        assert response.status == 200
        assert response.getheader("Content-Type", "").startswith("text/plain")
        assert "attachment;" in str(response.getheader("Content-Disposition", ""))
        lines = [line for line in body.splitlines() if line.strip()]
        assert len(lines) == 1
        row = json.loads(lines[0])
        assert row["request_id"] == "b" * 32
        assert row["status"] == 500
        assert "payload" in row["message"]


def test_build_advanced_results_analysis_with_monte_carlo():
    rows = [
        {"oos_avg_total_return_pct": "2.0", "oos_avg_max_drawdown_pct": "-3.0", "oos_avg_daily_trades": "4.0"},
        {"oos_avg_total_return_pct": "1.0", "oos_avg_max_drawdown_pct": "-2.0", "oos_avg_daily_trades": "5.0"},
        {"oos_avg_total_return_pct": "-0.5", "oos_avg_max_drawdown_pct": "-4.0", "oos_avg_daily_trades": "3.0"},
    ]

    payload = cp._build_advanced_results_analysis(rows, n_trials=300, sample_size=2, seed=7)

    assert payload["source_rows"] == 3
    assert payload["return_distribution"]["count"] == 3
    assert payload["drawdown_distribution"]["count"] == 3
    assert payload["daily_trades_distribution"]["count"] == 3
    assert payload["monte_carlo"] is not None
    assert payload["monte_carlo"]["n_trials"] == 300
    assert payload["monte_carlo"]["sample_size"] == 2
    assert payload["params"]["seed"] == 7


def test_build_advanced_results_analysis_empty_rows():
    payload = cp._build_advanced_results_analysis([], n_trials=100, sample_size=10, seed=1)
    assert payload["source_rows"] == 0
    assert payload["return_distribution"]["count"] == 0
    assert payload["drawdown_distribution"]["count"] == 0
    assert payload["monte_carlo"] is None
    assert payload["errors"] == []
