"""Real MCP SDK stdio handshake/tool calls against a fake local 3ds Max bridge."""
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import threading

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
import bubble_max_bridge as bridge


async def main():
    def dispatch(operation, arguments):
        if operation == "scene_info":
            return {"path": "D:/projects/hero.ma", "modified": False, "max_version": "2027"}
        return {"operation": operation, "echo": arguments}
    server = bridge.Bridge(dispatch, lambda fn: fn())
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        runtime = ROOT / ".test-runtime"
        runtime.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="bubble-mcp-smoke-", dir=runtime) as directory:
            Path(directory, "123.json").write_text(json.dumps({"protocol": 1, "pid": 123, "host": "127.0.0.1", "port": server.server_address[1], "token": server.token}))
            location = Path(directory) / "max-user"
            params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "server" / "main.py")], env={**os.environ, "BUBBLE_MAX_SESSION_DIR": directory, "MAX_APP_DIR": str(Path(directory) / "max-user")})
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    listing = await session.list_tools()
                    names = {tool.name for tool in listing.tools}
                    assert names == {'max_layers', 'max_parent_object', 'max_list_objects', 'max_inspect_object', 'max_object_action', 'max_scene_action', 'max_settings', "max_list_sessions", "max_status", "max_scene_info", "max_inspect_scene", "max_execute_python", "max_execute_maxscript", "max_installation_status", "max_install_bridge", "max_uninstall_bridge"}, names
                    for name in sorted(names):
                        arguments = {"code": "result = 42"} if name.startswith("max_execute_") else {}
                        if "install" in name:
                            arguments["startup_directory"] = str(location)
                        if name in {'max_settings', 'max_scene_action', 'max_layers', 'max_parent_object', 'max_list_objects', 'max_inspect_object', 'max_object_action'}:
                            arguments["pid"] = 123
                            if name.endswith(("inspect_object", "object_action", "scene_action", "parent_object")): arguments["expected_scene"] = "fixture"
                            if name.endswith(("inspect_object", "parent_object")): arguments["object_id"] = 1
                            if name.endswith("object_action"): arguments["action"] = "create"
                            if name.endswith("scene_action"): arguments["action"] = "new"
                        response = await session.call_tool(name, arguments)
                        assert not response.isError, response
                        payload = json.loads(response.content[0].text)
                        assert payload["ok"], payload
                        assert server.token not in response.content[0].text
                    response = await session.call_tool("max_list_sessions", {"scene": "HERO.ma"})
                    assert not response.isError, response
                    payload = json.loads(response.content[0].text)
                    assert payload["selection"]["status"] == "unique", payload
                    assert payload["selection"]["selected_pid"] == 123, payload
                    assert payload["data"][0]["scene_name"] == "hero.ma", payload
                    assert server.token not in response.content[0].text
                    assert not Path(directory, "max-user").exists(), "Unconfirmed install previews must not write"
                    print(json.dumps({"ok": True, "tools": sorted(names), "transport": "stdio -> loopback TCP fake 3ds Max"}))
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


if __name__ == "__main__":
    asyncio.run(asyncio.wait_for(main(), timeout=60))
