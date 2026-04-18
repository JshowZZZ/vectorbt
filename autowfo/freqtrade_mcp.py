from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from autowfo.paper_dryrun_reconcile import load_freqtrade_config, resolve_freqtrade_db_path


def _resolve_config_path(config_path: str | Path) -> Path:
    resolved = Path(config_path).resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Freqtrade config not found: {resolved}")
    return resolved


def _resolve_runtime_paths(config_path: str | Path, db_path: str | Path | None = None) -> tuple[Path, dict[str, Any], Path]:
    resolved_config_path = _resolve_config_path(config_path)
    config = load_freqtrade_config(resolved_config_path)
    resolved_db_path = resolve_freqtrade_db_path(
        db_path=db_path,
        freqtrade_config_path=resolved_config_path,
        freqtrade_config=config,
    )
    return resolved_config_path, config, resolved_db_path


def _count_trades(db_path: Path) -> tuple[int, int]:
    if not db_path.exists():
        return 0, 0
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        total = int(conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0])
        open_count = int(conn.execute("SELECT COUNT(*) FROM trades WHERE is_open = 1").fetchone()[0])
    finally:
        conn.close()
    return total, open_count


def load_runtime_summary(config_path: str | Path, *, db_path: str | Path | None = None) -> dict[str, Any]:
    resolved_config_path, config, resolved_db_path = _resolve_runtime_paths(config_path, db_path=db_path)
    total_trades, open_trades = _count_trades(resolved_db_path)
    exchange = dict(config.get("exchange") or {})
    api_server = dict(config.get("api_server") or {})
    pair_whitelist = list(exchange.get("pair_whitelist") or [])
    return {
        "config_path": str(resolved_config_path),
        "db_path": str(resolved_db_path),
        "db_exists": resolved_db_path.exists(),
        "bot_name": str(config.get("bot_name") or ""),
        "dry_run": bool(config.get("dry_run")),
        "timeframe": str(config.get("timeframe") or ""),
        "trading_mode": str(config.get("trading_mode") or ""),
        "strategy": str(config.get("strategy") or ""),
        "signal_manifest_path": str(config.get("autowfo_signal_manifest") or ""),
        "exchange_name": str(exchange.get("name") or ""),
        "pair_count": len(pair_whitelist),
        "pair_whitelist": pair_whitelist,
        "trades_total": total_trades,
        "open_trades": open_trades,
        "api_server": {
            "enabled": bool(api_server.get("enabled")),
            "listen_ip_address": str(api_server.get("listen_ip_address") or ""),
            "listen_port": int(api_server.get("listen_port") or 0),
            "username": str(api_server.get("username") or ""),
        },
    }


def load_recent_trades(
    config_path: str | Path,
    *,
    db_path: str | Path | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    _, _, resolved_db_path = _resolve_runtime_paths(config_path, db_path=db_path)
    if not resolved_db_path.exists():
        return []
    conn = sqlite3.connect(f"file:{resolved_db_path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT pair, is_open, open_date, close_date, enter_tag, strategy, timeframe, is_short
            FROM trades
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
    finally:
        conn.close()
    payload: list[dict[str, Any]] = []
    for row in rows:
        payload.append(
            {
                "pair": str(row["pair"] or ""),
                "is_open": bool(row["is_open"]),
                "open_date": row["open_date"],
                "close_date": row["close_date"],
                "enter_tag": str(row["enter_tag"] or ""),
                "strategy": str(row["strategy"] or ""),
                "timeframe": str(row["timeframe"] or ""),
                "is_short": bool(row["is_short"]),
            }
        )
    return payload


def build_mcp_server(config_path: str | Path, *, db_path: str | Path | None = None) -> FastMCP:
    server = FastMCP(name="freqtrade_runtime_awf342b")

    @server.tool()
    def runtime_summary() -> str:
        return json.dumps(load_runtime_summary(config_path, db_path=db_path), ensure_ascii=False, indent=2)

    @server.tool()
    def recent_trades(limit: int = 10) -> str:
        return json.dumps(
            load_recent_trades(config_path, db_path=db_path, limit=limit),
            ensure_ascii=False,
            indent=2,
        )

    return server


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only Freqtrade runtime MCP wrapper for AWF-342b.")
    parser.add_argument("--config", required=True, help="Path to the local Freqtrade config JSON")
    parser.add_argument("--db-path", default="", help="Optional override for the Freqtrade SQLite DB path")
    return parser


def main() -> int:
    args = _build_arg_parser().parse_args()
    server = build_mcp_server(args.config, db_path=(args.db_path or None))
    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
