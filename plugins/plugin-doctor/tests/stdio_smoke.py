"""Harmless MCP calls over real stdio; no DCC or user profile writes."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


async def main():
    (ROOT / ".test-runtime").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT / ".test-runtime") as directory:
        config = StdioServerParameters(command=sys.executable, args=[str(ROOT / "server/main.py")])
        async with stdio_client(config) as streams:
            async with ClientSession(*streams) as client:
                await client.initialize()
                tools = await client.list_tools()
                assert len(tools.tools) == 8
                for name, args in (("doctor_status", {}),
                    ("doctor_inventory", {"codex_home": directory}),
                    ("doctor_check_package", {"package_path": str(ROOT)}),
                    ("doctor_list_sessions", {"app": "maya", "session_directory": directory}),
                    ("doctor_repair_guidance", {"plugin_name": "maya-control", "action": "uninstall"})):
                    response = await client.call_tool(name, args)
                    assert not response.isError, response
                    result = json.loads(response.content[0].text)
                    assert result["ok"], result
                print("PASS doctor stdio: 8 tools; read-only status, inventory, package, sessions and maintenance guidance")


if __name__ == "__main__":
    asyncio.run(main())
