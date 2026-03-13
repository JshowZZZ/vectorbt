"""DuckDB-based cross-run analytics store."""

from __future__ import annotations

import itertools
import json
import sqlite3
from pathlib import Path

import pandas as pd

from autowfo.storage_contract import ANALYTICS_STORE_SCHEMA_VERSION

try:
    import duckdb  # type: ignore
except Exception:  # pragma: no cover
    duckdb = None


_COMBO_RESULTS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS combo_results (
    combo_id TEXT,
    experiment_id TEXT,
    run_id TEXT,
    direction TEXT,
    trigger_asset TEXT,
    action_asset TEXT,
    indicator_params TEXT,
    condition_params TEXT,
    risk_params TEXT,
    oos_sharpe DOUBLE,
    oos_win_rate DOUBLE,
    oos_n_trades BIGINT,
    oos_total_return DOUBLE,
    wf_score DOUBLE,
    created_utc TEXT
);
"""

_PAPER_FEEDBACK_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS paper_feedback (
    experiment_id TEXT NOT NULL,
    pnl_pct DOUBLE,
    close_ts TEXT
);
"""

_ANALYTICS_METADATA_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS analytics_metadata (
    meta_key TEXT PRIMARY KEY,
    meta_value TEXT NOT NULL
);
"""


class AnalyticsStore:
    def __init__(self, db_path: str | Path = "artifacts/analytics.duckdb"):
        self.db_path = Path(db_path) if str(db_path) != ":memory:" else ":memory:"

    def _connect(self):
        if duckdb is None:
            raise RuntimeError("duckdb package is required for AnalyticsStore")
        if self.db_path != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        return duckdb.connect(str(self.db_path))

    def _db_exists(self) -> bool:
        if self.db_path == ":memory:":
            return True
        return self.db_path.exists()

    @staticmethod
    def _ensure_schema(conn) -> None:
        conn.execute(_COMBO_RESULTS_SCHEMA_SQL)
        conn.execute(_PAPER_FEEDBACK_SCHEMA_SQL)
        conn.execute(_ANALYTICS_METADATA_SCHEMA_SQL)
        conn.execute("DELETE FROM analytics_metadata WHERE meta_key = 'schema_version'")
        conn.execute(
            "INSERT INTO analytics_metadata (meta_key, meta_value) VALUES ('schema_version', ?)",
            [ANALYTICS_STORE_SCHEMA_VERSION],
        )

    @staticmethod
    def _create_views(conn) -> None:
        conn.execute(
            """
CREATE OR REPLACE VIEW indicator_effectiveness AS
SELECT
  c.trigger_indicators,
  c.action_indicators,
  COUNT(*) AS n_combos,
  AVG(c.oos_win_rate) AS avg_win_rate,
  AVG(c.oos_sharpe) AS avg_sharpe,
  COUNT(DISTINCT c.experiment_id) AS n_experiments,
  AVG(f.paper_avg_pnl) AS paper_avg_pnl
FROM (
  SELECT
    json_extract(indicator_params, '$.trigger_indicators') AS trigger_indicators,
    json_extract(indicator_params, '$.action_indicators') AS action_indicators,
    experiment_id,
    oos_win_rate,
    oos_sharpe
  FROM combo_results
  WHERE oos_n_trades >= 10
) AS c
LEFT JOIN (
  SELECT
    experiment_id,
    AVG(pnl_pct) AS paper_avg_pnl
  FROM paper_feedback
  GROUP BY experiment_id
) AS f
ON c.experiment_id = f.experiment_id
GROUP BY 1, 2
ORDER BY avg_sharpe DESC
"""
        )
        conn.execute(
            """
CREATE OR REPLACE VIEW all_time_best AS
SELECT * FROM combo_results
WHERE oos_n_trades >= 10
ORDER BY wf_score DESC
LIMIT 100
"""
        )

    def get_metadata(self) -> dict:
        if duckdb is None or not self._db_exists():
            return {"schema_version": ANALYTICS_STORE_SCHEMA_VERSION}
        conn = self._connect()
        try:
            self._ensure_schema(conn)
            rows = conn.execute("SELECT meta_key, meta_value FROM analytics_metadata").fetchall()
            return {str(key): value for key, value in rows}
        finally:
            conn.close()

    def update_from_run(self, experiment_id: str, run_id: str, artifact_store) -> int:
        db_path = artifact_store.get_run_db_path(run_id)
        if not db_path.exists():
            raise FileNotFoundError(db_path)

        sqlite_conn = sqlite3.connect(db_path)
        try:
            frame = pd.read_sql_query(
                """
SELECT
    combo_id,
    experiment_id,
    run_id,
    direction,
    trigger_asset,
    action_asset,
    indicator_params,
    condition_params,
    risk_params,
    oos_sharpe,
    oos_win_rate,
    oos_n_trades,
    oos_total_return,
    wf_score,
    created_utc
FROM combo_results
WHERE experiment_id = ?
""",
                sqlite_conn,
                params=[experiment_id],
            )
        finally:
            sqlite_conn.close()

        if frame.empty:
            return 0

        conn = self._connect()
        try:
            self._ensure_schema(conn)
            conn.register("incoming_df", frame)
            conn.execute("BEGIN TRANSACTION")
            conn.execute(
                """
DELETE FROM combo_results
USING incoming_df
WHERE combo_results.combo_id = incoming_df.combo_id
"""
            )
            conn.execute("INSERT INTO combo_results SELECT * FROM incoming_df")
            conn.execute("COMMIT")
            conn.unregister("incoming_df")
        finally:
            conn.close()
        return int(len(frame))

    def create_views(self) -> None:
        conn = self._connect()
        try:
            self._ensure_schema(conn)
            self._create_views(conn)
        finally:
            conn.close()

    def add_paper_feedback(self, experiment_id: str, pnl_pct: float, close_ts: str) -> int:
        experiment = str(experiment_id or "").strip()
        timestamp = str(close_ts or "").strip()
        if not experiment:
            raise ValueError("experiment_id is required")
        if not timestamp:
            raise ValueError("close_ts is required")
        try:
            pnl_value = float(pnl_pct)
        except Exception as exc:
            raise ValueError("pnl_pct must be numeric") from exc

        conn = self._connect()
        try:
            self._ensure_schema(conn)
            exists_row = conn.execute(
                """
SELECT 1
FROM paper_feedback
WHERE experiment_id = ? AND close_ts = ?
LIMIT 1
""",
                [experiment, timestamp],
            ).fetchone()
            if exists_row is not None:
                return 0
            conn.execute(
                """
INSERT INTO paper_feedback (
    experiment_id,
    pnl_pct,
    close_ts
) VALUES (?, ?, ?)
""",
                [experiment, pnl_value, timestamp],
            )
        finally:
            conn.close()
        return 1

    def query_indicator_leaderboard(self, limit: int = 20) -> list[dict]:
        if duckdb is None or not self._db_exists():
            return []
        self.create_views()
        limit_n = max(1, int(limit))
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM indicator_effectiveness LIMIT ?",
                [limit_n],
            ).fetchdf()
            return rows.to_dict(orient="records")
        finally:
            conn.close()

    def query_all_time_best(self, limit: int = 50) -> list[dict]:
        if duckdb is None or not self._db_exists():
            return []
        self.create_views()
        limit_n = max(1, int(limit))
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM all_time_best LIMIT ?",
                [limit_n],
            ).fetchdf()
            return rows.to_dict(orient="records")
        finally:
            conn.close()

    def query_experiment_comparison(self) -> list[dict]:
        if duckdb is None or not self._db_exists():
            return []
        conn = self._connect()
        try:
            self._ensure_schema(conn)
            rows = conn.execute(
                """
SELECT
    experiment_id,
    AVG(oos_sharpe) AS avg_oos_sharpe,
    AVG(oos_win_rate) AS avg_oos_win_rate,
    COUNT(*) AS total_combos,
    COUNT(DISTINCT run_id) AS total_runs,
    MAX(wf_score) AS best_wf_score
FROM combo_results
GROUP BY experiment_id
ORDER BY avg_oos_sharpe DESC, best_wf_score DESC, experiment_id ASC
"""
            ).fetchdf()
            return rows.to_dict(orient="records")
        finally:
            conn.close()

    @staticmethod
    def _indicator_list_from_row(raw_indicator_params: str | None) -> list[str]:
        if raw_indicator_params in (None, ""):
            return []
        try:
            payload = json.loads(str(raw_indicator_params))
        except Exception:
            return []
        if not isinstance(payload, dict):
            return []

        values = []
        for key in ("trigger_indicators", "action_indicators"):
            raw_value = payload.get(key)
            if isinstance(raw_value, list):
                values.extend([str(item).strip() for item in raw_value if str(item).strip()])
            elif isinstance(raw_value, str):
                text = raw_value.strip()
                if not text:
                    continue
                try:
                    parsed = json.loads(text)
                except Exception:
                    values.append(text)
                    continue
                if isinstance(parsed, list):
                    values.extend([str(item).strip() for item in parsed if str(item).strip()])
                elif isinstance(parsed, str) and parsed.strip():
                    values.append(parsed.strip())
        deduped = []
        seen = set()
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            deduped.append(value)
        return deduped

    def query_indicator_coverage_map(self) -> list[dict]:
        if duckdb is None or not self._db_exists():
            return []
        conn = self._connect()
        try:
            self._ensure_schema(conn)
            rows = conn.execute(
                """
SELECT
    indicator_params,
    oos_sharpe
FROM combo_results
"""
            ).fetchall()
        finally:
            conn.close()

        stats = {}
        discovered = set()
        for raw_indicator_params, raw_sharpe in rows:
            indicators = self._indicator_list_from_row(raw_indicator_params)
            if not indicators:
                continue
            discovered.update(indicators)
            try:
                sharpe = float(raw_sharpe)
            except Exception:
                sharpe = None
            for left, right in itertools.combinations_with_replacement(sorted(set(indicators)), 2):
                key = (left, right)
                bucket = stats.setdefault(key, {"sum_sharpe": 0.0, "count_sharpe": 0, "total_combos": 0})
                bucket["total_combos"] += 1
                if sharpe is not None:
                    bucket["sum_sharpe"] += sharpe
                    bucket["count_sharpe"] += 1

        if not discovered:
            return []
        indicator_axis = sorted(discovered)
        out = []
        for left, right in itertools.combinations_with_replacement(indicator_axis, 2):
            key = (left, right)
            bucket = stats.get(key)
            if bucket is None:
                out.append(
                    {
                        "indicator_a": left,
                        "indicator_b": right,
                        "tested": False,
                        "avg_sharpe": None,
                        "total_combos": 0,
                    }
                )
                continue
            avg_sharpe = (
                bucket["sum_sharpe"] / bucket["count_sharpe"]
                if bucket["count_sharpe"] > 0
                else None
            )
            out.append(
                {
                    "indicator_a": left,
                    "indicator_b": right,
                    "tested": True,
                    "avg_sharpe": avg_sharpe,
                    "total_combos": int(bucket["total_combos"]),
                }
            )
        return out

    def query_analytics_growth(self) -> dict:
        default = {
            "total_experiments": 0,
            "total_runs": 0,
            "total_combos": 0,
            "leaderboard_size": 0,
        }
        if duckdb is None or not self._db_exists():
            return dict(default)

        conn = self._connect()
        try:
            self._ensure_schema(conn)
            stats = conn.execute(
                """
SELECT
    COUNT(DISTINCT experiment_id) AS total_experiments,
    COUNT(DISTINCT run_id) AS total_runs,
    COUNT(*) AS total_combos
FROM combo_results
"""
            ).fetchone()
            try:
                self._create_views(conn)
                leaderboard_size = conn.execute("SELECT COUNT(*) FROM indicator_effectiveness").fetchone()[0]
            except Exception:
                leaderboard_size = 0
        finally:
            conn.close()

        if not stats:
            return dict(default)
        return {
            "total_experiments": int(stats[0] or 0),
            "total_runs": int(stats[1] or 0),
            "total_combos": int(stats[2] or 0),
            "leaderboard_size": int(leaderboard_size or 0),
        }

