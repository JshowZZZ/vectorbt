import json
import sqlite3

from scripts import run_btc_regime_sweep as sweep
from scripts.autowfo import artifacts as a


def test_artifacts_db_schema_and_append_module(tmp_path):
    db_path = tmp_path / "results.db"
    columns = ["timeframe", "value"]

    a._ensure_db_schema(str(db_path), "combo_summary", columns, indexes=[("idx_tf", ["timeframe"])])
    inserted = a._append_db_rows(
        str(db_path),
        "combo_summary",
        [{"timeframe": "3m", "value": 1.0}, {"timeframe": "15m", "value": 2.0}],
        columns,
    )

    assert inserted == 2
    with sqlite3.connect(db_path) as conn:
        cols = [row[1] for row in conn.execute("PRAGMA table_info(combo_summary)").fetchall()]
        assert "created_utc" in cols
        count = conn.execute("SELECT COUNT(*) FROM combo_summary").fetchone()[0]
        assert count == 2


def test_write_status_wrapper_matches_module(tmp_path):
    payload = {
        "run_id": "r1",
        "stage": "combo",
        "total": 10,
        "done": 3,
        "remaining": 7,
        "skipped": 0,
        "percent": 30.0,
        "elapsed": "00:00:10",
        "eta": "00:00:20",
        "updated": "2026-02-07T00:00:00Z",
    }

    module_json = tmp_path / "module.json"
    module_html = tmp_path / "module.html"
    wrapper_json = tmp_path / "wrapper.json"
    wrapper_html = tmp_path / "wrapper.html"

    a._write_status(str(module_json), str(module_html), payload, labels=sweep.LABELS)
    sweep._write_status(str(wrapper_json), str(wrapper_html), payload)

    assert json.loads(module_json.read_text(encoding="utf-8")) == json.loads(
        wrapper_json.read_text(encoding="utf-8")
    )
    assert module_html.read_text(encoding="utf-8") == wrapper_html.read_text(encoding="utf-8")
