import json
import sqlite3
from pathlib import Path

import anyio

from autowfo.freqtrade_mcp import load_recent_trades, load_runtime_summary


def _write_config(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "bot_name": "autowfo-dryrun",
        "dry_run": True,
        "timeframe": "2h",
        "trading_mode": "futures",
        "strategy": "AutowfoLiveSignalStrategyLongShort",
        "db_url": "sqlite:///tradesv3.dryrun.sqlite",
        "exchange": {
            "name": "binance",
            "pair_whitelist": ["ETH/USDT:USDT", "ADA/USDT:USDT"],
        },
        "api_server": {
            "enabled": True,
            "listen_ip_address": "127.0.0.1",
            "listen_port": 8080,
            "username": "autowfo",
            "password": "secret",
        },
        "autowfo_signal_manifest": "E:/Project/vectorbt-master/artifacts/live_signal_store/live_manifest.json",
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_trade_db(path: Path) -> Path:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE trades (
                id INTEGER PRIMARY KEY,
                pair TEXT,
                is_open INTEGER,
                open_date TEXT,
                close_date TEXT,
                enter_tag TEXT,
                strategy TEXT,
                timeframe TEXT,
                is_short INTEGER
            )
            """
        )
        conn.execute(
            """
            INSERT INTO trades (pair, is_open, open_date, close_date, enter_tag, strategy, timeframe, is_short)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ETH/USDT:USDT",
                1,
                "2026-04-18T00:00:00Z",
                None,
                "autowfo-long",
                "AutowfoLiveSignalStrategyLongShort",
                "2h",
                0,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return path


def test_load_runtime_summary_sanitizes_config_and_counts_trades(tmp_path):
    config_path = _write_config(tmp_path / "user_data" / "config_autowfo_dryrun.json")
    _write_trade_db(tmp_path / "tradesv3.dryrun.sqlite")

    payload = load_runtime_summary(config_path)

    assert payload["bot_name"] == "autowfo-dryrun"
    assert payload["dry_run"] is True
    assert payload["pair_count"] == 2
    assert payload["trades_total"] == 1
    assert payload["open_trades"] == 1
    assert payload["api_server"]["enabled"] is True
    assert set(payload["api_server"].keys()) == {"enabled", "listen_ip_address", "listen_port", "username"}


def test_load_recent_trades_reads_latest_trade_rows(tmp_path):
    config_path = _write_config(tmp_path / "user_data" / "config_autowfo_dryrun.json")
    _write_trade_db(tmp_path / "tradesv3.dryrun.sqlite")

    rows = load_recent_trades(config_path, limit=5)

    assert len(rows) == 1
    assert rows[0]["pair"] == "ETH/USDT:USDT"
    assert rows[0]["is_open"] is True
    assert rows[0]["enter_tag"] == "autowfo-long"


def test_freqtrade_mcp_stdio_smoke_lists_tools_and_calls_runtime_summary(tmp_path):
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    config_path = _write_config(tmp_path / "user_data" / "config_autowfo_dryrun.json")
    _write_trade_db(tmp_path / "tradesv3.dryrun.sqlite")

    async def _run() -> None:
        params = StdioServerParameters(
            command="python",
            args=["-m", "autowfo.freqtrade_mcp", "--config", str(config_path)],
            cwd=Path.cwd(),
        )
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools = await session.list_tools()
                tool_names = sorted(tool.name for tool in tools.tools)
                assert tool_names == ["recent_trades", "runtime_summary"]

                result = await session.call_tool("runtime_summary", {})
                text_blocks = [getattr(item, "text", "") for item in result.content]
                assert any("autowfo-dryrun" in block for block in text_blocks)

    anyio.run(_run)


def test_runtime_summary_opens_db_in_readonly_uri_mode(tmp_path, monkeypatch):
    import sqlite3 as _sqlite3
    from autowfo import freqtrade_mcp

    config_path = _write_config(tmp_path / "user_data" / "config_autowfo_dryrun.json")
    _write_trade_db(tmp_path / "tradesv3.dryrun.sqlite")

    captured = []
    real_connect = _sqlite3.connect

    def spy_connect(*args, **kwargs):
        captured.append((args, kwargs))
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(freqtrade_mcp.sqlite3, "connect", spy_connect)
    freqtrade_mcp.load_runtime_summary(config_path)

    assert captured, "sqlite3.connect was not called"
    first_args, first_kwargs = captured[0]
    assert first_kwargs.get("uri") is True
    assert isinstance(first_args[0], str)
    assert first_args[0].startswith("file:")
    assert "mode=ro" in first_args[0]


def test_recent_trades_opens_db_in_readonly_uri_mode(tmp_path, monkeypatch):
    import sqlite3 as _sqlite3
    from autowfo import freqtrade_mcp

    config_path = _write_config(tmp_path / "user_data" / "config_autowfo_dryrun.json")
    _write_trade_db(tmp_path / "tradesv3.dryrun.sqlite")

    captured = []
    real_connect = _sqlite3.connect

    def spy_connect(*args, **kwargs):
        captured.append((args, kwargs))
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(freqtrade_mcp.sqlite3, "connect", spy_connect)
    freqtrade_mcp.load_recent_trades(config_path, limit=5)

    assert captured, "sqlite3.connect was not called"
    first_args, first_kwargs = captured[0]
    assert first_kwargs.get("uri") is True
    assert "mode=ro" in first_args[0]
