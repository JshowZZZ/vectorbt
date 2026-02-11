import sqlite3
import json
from pathlib import Path

from scripts import control_panel as cp


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


def _setup_batch_env(tmp_path, monkeypatch):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(cp, "ROOT", tmp_path)
    monkeypatch.setattr(cp, "ARTIFACTS", artifacts)
    monkeypatch.setattr(cp, "CONFIG_JSON", artifacts / "sweep_config.json")
    cp.BATCH_PROCESS = None
    cp.PROCESS = None
    return artifacts


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
