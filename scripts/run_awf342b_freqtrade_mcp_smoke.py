from __future__ import annotations

import argparse
import json
from pathlib import Path

import anyio
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


DEFAULT_OUTPUT_DIR = Path("artifacts/scratch/freqtrade_mcp_smoke")
DEFAULT_CONFIG_PATH = Path("E:/Project/freqtrade/user_data/config_autowfo_dryrun.json")


async def _run_smoke(config_path: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    server = StdioServerParameters(
        command="python",
        args=["-m", "autowfo.freqtrade_mcp", "--config", str(config_path)],
        cwd=Path.cwd(),
    )
    async with stdio_client(server) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = await session.list_tools()
            runtime_summary = await session.call_tool("runtime_summary", {})
            recent_trades = await session.call_tool("recent_trades", {"limit": 5})

    tool_payload = {"tools": [tool.name for tool in tools.tools]}
    (output_dir / "tools.json").write_text(json.dumps(tool_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "runtime_summary.json").write_text(
        runtime_summary.content[0].text if runtime_summary.content else "[]",
        encoding="utf-8",
    )
    (output_dir / "recent_trades.json").write_text(
        recent_trades.content[0].text if recent_trades.content else "[]",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the AWF-342b Freqtrade MCP smoke check and save outputs.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Path to the Freqtrade config JSON.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for smoke output JSON files.")
    args = parser.parse_args()
    anyio.run(_run_smoke, Path(args.config).resolve(), Path(args.output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
