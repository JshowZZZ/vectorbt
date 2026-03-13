"""Artifact directory and per-run SQLite store helpers for experiments."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from autowfo.storage_contract import RUN_META_SCHEMA_VERSION


_ORDERABLE_COLUMNS = {
    "combo_id",
    "experiment_id",
    "run_id",
    "direction",
    "trigger_asset",
    "action_asset",
    "indicator_params",
    "condition_params",
    "risk_params",
    "oos_sharpe",
    "oos_win_rate",
    "oos_n_trades",
    "oos_total_return",
    "wf_score",
    "created_utc",
}


def _normalize_order_by(order_by: str | None, default: str = "wf_score DESC") -> tuple[str, str]:
    text = str(order_by or "").strip()
    if not text:
        text = default
    parts = text.split()
    column = parts[0].strip().lower() if parts else "wf_score"
    if column not in _ORDERABLE_COLUMNS:
        column = "wf_score"
    direction = parts[1].strip().upper() if len(parts) > 1 else "DESC"
    if direction not in {"ASC", "DESC"}:
        direction = "DESC"
    return column, direction


class ArtifactStore:
    def __init__(self, experiment_id: str, base_dir: Path = None):
        self.experiment_id = str(experiment_id)
        self.base_dir = Path("artifacts") if base_dir is None else Path(base_dir)

    @property
    def experiment_dir(self) -> Path:
        return self.base_dir / "experiments" / self.experiment_id

    def init_run(self, run_id: str) -> Path:
        run_dir = self.experiment_dir / "runs" / str(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    def get_run_db_path(self, run_id: str) -> Path:
        return self.experiment_dir / "runs" / str(run_id) / "results.db"

    def get_run_meta_path(self, run_id: str) -> Path:
        return self.experiment_dir / "runs" / str(run_id) / "run_meta.json"

    def write_run_meta(self, run_id: str, meta: dict) -> None:
        run_dir = self.init_run(run_id)
        path = run_dir / "run_meta.json"
        payload = dict(meta) if isinstance(meta, dict) else {}
        payload.setdefault("schema_version", RUN_META_SCHEMA_VERSION)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def read_run_meta(self, run_id: str) -> dict:
        path = self.get_run_meta_path(run_id)
        if not path.exists():
            raise FileNotFoundError(path)
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(payload, dict):
            raise ValueError(f"run_meta.json must decode to object: {path}")
        normalized = dict(payload)
        normalized.setdefault("schema_version", RUN_META_SCHEMA_VERSION)
        return normalized

    def list_runs(self) -> list[str]:
        runs_dir = self.experiment_dir / "runs"
        if not runs_dir.exists():
            return []
        return sorted([path.name for path in runs_dir.iterdir() if path.is_dir()])

    def init_results_db(self, run_id: str) -> sqlite3.Connection:
        self.init_run(run_id)
        db_path = self.get_run_db_path(run_id)
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
CREATE TABLE IF NOT EXISTS combo_results (
    combo_id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    direction TEXT NOT NULL,
    trigger_asset TEXT,
    action_asset TEXT NOT NULL,
    indicator_params TEXT NOT NULL,
    condition_params TEXT NOT NULL,
    risk_params TEXT NOT NULL,
    oos_sharpe REAL,
    oos_win_rate REAL,
    oos_n_trades INTEGER,
    oos_total_return REAL,
    wf_score REAL,
    created_utc TEXT
);
"""
        )
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_experiment ON combo_results(experiment_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_wf_score ON combo_results(wf_score DESC)")
        conn.commit()
        return conn

    def query_run_results(
        self,
        run_id: str,
        order_by: str = "wf_score DESC",
        limit: int = 50,
    ) -> list[dict]:
        run_dir = self.experiment_dir / "runs" / str(run_id)
        if not run_dir.exists():
            raise FileNotFoundError(run_dir)
        db_path = self.get_run_db_path(run_id)
        if not db_path.exists():
            raise FileNotFoundError(db_path)

        sort_col, sort_dir = _normalize_order_by(order_by)
        try:
            limit_n = int(limit)
        except Exception:
            limit_n = 50
        limit_n = max(1, limit_n)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                f"""
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
ORDER BY {sort_col} {sort_dir}, combo_id ASC
LIMIT ?
""",
                (limit_n,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def query_experiment_summary(self) -> dict:
        runs_dir = self.experiment_dir / "runs"
        if not runs_dir.exists():
            return {
                "experiment_id": self.experiment_id,
                "runs_count": 0,
                "total_combos": 0,
                "best_oos_sharpe": None,
                "latest_run_id": None,
            }

        run_ids = self.list_runs()
        total_combos = 0
        best_oos_sharpe = None

        for run_id in run_ids:
            try:
                meta = self.read_run_meta(run_id)
            except FileNotFoundError:
                continue
            if not isinstance(meta, dict):
                continue
            try:
                total_combos += int(meta.get("n_combos", 0) or 0)
            except Exception:
                pass
            try:
                run_best = float(meta.get("best_oos_sharpe"))
                if best_oos_sharpe is None or run_best > best_oos_sharpe:
                    best_oos_sharpe = run_best
            except Exception:
                pass

        return {
            "experiment_id": self.experiment_id,
            "runs_count": len(run_ids),
            "total_combos": int(total_combos),
            "best_oos_sharpe": best_oos_sharpe,
            "latest_run_id": run_ids[-1] if run_ids else None,
        }

    def query_all_results(
        self,
        order_by: str = "wf_score DESC",
        limit: int = 100,
    ) -> list[dict]:
        sort_col, sort_dir = _normalize_order_by(order_by)
        try:
            limit_n = int(limit)
        except Exception:
            limit_n = 100
        limit_n = max(1, limit_n)

        collected: list[dict] = []
        for run_id in self.list_runs():
            db_path = self.get_run_db_path(run_id)
            if not db_path.exists():
                continue
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(
                    f"""
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
ORDER BY {sort_col} {sort_dir}, combo_id ASC
LIMIT ?
""",
                    (limit_n,),
                ).fetchall()
                collected.extend(dict(row) for row in rows)
            finally:
                conn.close()

        reverse = sort_dir == "DESC"
        collected.sort(
            key=lambda row: (
                row.get(sort_col) is None,
                row.get(sort_col),
                row.get("combo_id"),
            ),
            reverse=reverse,
        )
        return collected[:limit_n]

