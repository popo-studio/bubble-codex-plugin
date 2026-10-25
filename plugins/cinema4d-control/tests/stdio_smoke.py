"""Real outer MCP stdio -> Bubble -> synthetic native MCP stdio acceptance."""
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]

async def main():
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "native.json"
        source.write_text(json.dumps({"mcpServers": {"native": {"command": sys.executable, "args": [str(ROOT / "tests" / "fixture_native.py")]}}}))
        params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "launch-0.1.0.py")], env={**os.environ, "BUBBLE_CINEMA4D_CONFIG_DIR": str(Path(directory) / "registry")})
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = (await session.list_tools()).tools
                assert len(tools) == 7
                async def call(tool_name, **args):
                    result = await session.call_tool(tool_name, args)
                    assert not result.isError, result
                    payload = json.loads(result.content[0].text)
                    assert "error" not in payload, payload
                    return payload
                assert (await call("cinema4d_setup_status"))["connections"] == []
                args = dict(action="register", name="synthetic", config_path=str(source), entry_name="native")
                preview = await call("cinema4d_configure", **args)
                assert not (Path(directory) / "registry").exists()
                await call("cinema4d_configure", **args, confirmed=True, expected_revision=preview["revision"], expected_config_hash=preview["config_hash"])
                sid = (await call("cinema4d_connect", name="synthetic", authorized=True))["session_id"]
                assert (await call("cinema4d_list_sessions"))["sessions"][0]["session_id"] == sid
                await call("cinema4d_discover_tools", session_id=sid)
                result = await call("cinema4d_call_tool", session_id=sid, tool="fixture_echo", arguments={"value": "nested MCP works"}, request_id="smoke-test-1", authorized=True)
                assert "nested MCP works" in json.dumps(result)
                await call("cinema4d_disconnect", session_id=sid)
                print(json.dumps({"ok": True, "tools": len(tools), "transport": "real MCP stdio -> Bubble -> synthetic native MCP stdio", "native_c4d_tested": False}))

if __name__ == "__main__":
    asyncio.run(asyncio.wait_for(main(), 60))
