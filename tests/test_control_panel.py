import sqlite3

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
