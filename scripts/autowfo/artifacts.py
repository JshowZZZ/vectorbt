"""Artifact IO helpers extracted from run_btc_regime_sweep monolith."""

import csv
import json
import os
import sqlite3

import numpy as np
import pandas as pd


def _ensure_csv_schema(path, columns):
    if not os.path.exists(path):
        return
    try:
        df = pd.read_csv(path, low_memory=False)
    except Exception:
        return
    missing = [col for col in columns if col not in df.columns]
    if not missing:
        return
    for col in missing:
        df[col] = np.nan
    df = df.reindex(columns=[col for col in columns if col in df.columns])
    df.to_csv(path, index=False)


def _append_rows(path, rows, columns):
    if not rows:
        return 0
    file_exists = os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        if not file_exists:
            writer.writeheader()
        for row in rows:
            record = {col: row.get(col, None) for col in columns}
            writer.writerow(record)
    return len(rows)


def _ensure_db_schema(db_path, table, columns, indexes=None):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        col_defs = ", ".join([f'"{col}" TEXT' for col in columns])
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS {table} "
            f"(id INTEGER PRIMARY KEY AUTOINCREMENT, "
            f"created_utc TEXT DEFAULT CURRENT_TIMESTAMP, "
            f"{col_defs})"
        )
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if "created_utc" not in existing:
            conn.execute(f'ALTER TABLE {table} ADD COLUMN "created_utc" TEXT')
        for col in columns:
            if col not in existing:
                conn.execute(f'ALTER TABLE {table} ADD COLUMN "{col}" TEXT')
        if indexes:
            for idx_name, idx_cols in indexes:
                cols_sql = ", ".join([f'"{col}"' for col in idx_cols])
                conn.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({cols_sql})")
        conn.commit()
    finally:
        conn.close()


def _append_db_rows(db_path, table, rows, columns, normalize_key_value_fn=None):
    if not rows:
        return 0
    if normalize_key_value_fn is None:
        normalize_key_value_fn = lambda x: x
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        col_sql = ", ".join([f'"{col}"' for col in columns])
        placeholders = ", ".join(["?"] * len(columns))
        sql = f"INSERT INTO {table} ({col_sql}) VALUES ({placeholders})"
        values = [
            tuple(normalize_key_value_fn(row.get(col, None)) for col in columns)
            for row in rows
        ]
        conn.executemany(sql, values)
        conn.commit()
    finally:
        conn.close()
    return len(rows)


def _write_status(status_json_path, status_html_path, payload, labels):
    with open(status_json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="5">
  <title>{labels['status_title']}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 20px; color: #111; }}
    table {{ border-collapse: collapse; width: 100%; max-width: 680px; }}
    th, td {{ border: 1px solid #ddd; padding: 6px 8px; text-align: left; }}
    th {{ background: #f3f3f3; }}
  </style>
</head>
<body>
  <h1>{labels['status_title']}</h1>
  <table>
    <tr><th>{labels['run_id']}</th><td>{payload.get('run_id','')}</td></tr>
    <tr><th>{labels['status_stage']}</th><td>{payload.get('stage','')}</td></tr>
    <tr><th>{labels['status_total']}</th><td>{payload.get('total','')}</td></tr>
    <tr><th>{labels['status_done']}</th><td>{payload.get('done','')}</td></tr>
    <tr><th>{labels['status_remaining']}</th><td>{payload.get('remaining','')}</td></tr>
    <tr><th>{labels['status_skipped']}</th><td>{payload.get('skipped','')}</td></tr>
    <tr><th>{labels['status_percent']}</th><td>{payload.get('percent','')}</td></tr>
    <tr><th>{labels['status_elapsed']}</th><td>{payload.get('elapsed','')}</td></tr>
    <tr><th>{labels['status_eta']}</th><td>{payload.get('eta','')}</td></tr>
    <tr><th>{labels['status_updated']}</th><td>{payload.get('updated','')}</td></tr>
  </table>
</body>
</html>
"""
    with open(status_html_path, "w", encoding="utf-8") as f:
        f.write(html)
