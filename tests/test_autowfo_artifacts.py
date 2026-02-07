import json
import sqlite3

from scripts.autowfo import artifacts as a
from scripts.autowfo.constants import LABELS


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
