"""Real MCP SDK stdio handshake/tool calls against a fake local Houdini bridge."""
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
sys.path.insert(0, str(ROOT / "houdini"))
import bubble_houdini_bridge as bridge


async def main():
    def dispatch(operation, arguments):
        if operation == "scene_info":
            return {"path": "D:/projects/hero.hip", "modified": False, "houdini_version": "20.5"}
        return {"operation": operation, "echo": arguments}
    server = bridge.Bridge(dispatch, lambda fn: fn())
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        runtime = ROOT / ".test-runtime"
        runtime.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="bubble-mcp-smoke-", dir=runtime) as directory:
            Path(directory, "123.json").write_text(json.dumps({"protocol": 1, "pid": 123, "host": "127.0.0.1", "port": server.server_address[1], "token": server.token}))
            params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "server" / "main.py")], env={**os.environ, "BUBBLE_HOUDINI_SESSION_DIR": directory, "HOUDINI_USER_PREF_DIR": str(Path(directory) / "houdini-user-__HVER__")})
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    listing = await session.list_tools()
                    names = {tool.name for tool in listing.tools}
                    legacy_names = {"houdini_list_sessions", "houdini_status", "houdini_scene_info", "houdini_inspect_scene", "houdini_execute_python", "houdini_installation_status", "houdini_install_bridge", "houdini_uninstall_bridge"}
                    additional = {"houdini_"+suffix for suffix in ["scene_state","scene_file","query_nodes","create_node","edit_node","select_nodes","node_attribute","node_connections","timeline"]}
                    assert names == legacy_names | additional, names
                    for name in sorted(names):
                        arguments = {"code": "result = 42"} if name.startswith("houdini_execute_") else {}
                        suffix=name.removeprefix("houdini_")
                        common={"pid":123,"expected_snapshot":"fake snapshot"}
                        if suffix=='scene_file':arguments=dict(common,action='save',path='D:/scratch')
                        elif suffix=='create_node':arguments=dict(common,kind='transform',name='scratch')
                        elif suffix=='edit_node':arguments=dict(common,action='rename',node='scratch',name='newName')
                        elif suffix=='select_nodes':arguments=dict(common,nodes=[])
                        elif suffix=='node_attribute':arguments=dict(pid=123,node='scratch',attribute='tx')
                        elif suffix=='node_connections':arguments=dict(pid=123,node='scratch')
                        elif suffix=='timeline':arguments=dict(pid=123)
                        response = await session.call_tool(name, arguments)
                        assert not response.isError, response
                        payload = json.loads(response.content[0].text)
                        assert payload["ok"], payload
                        assert server.token not in response.content[0].text
                    response = await session.call_tool("houdini_list_sessions", {"scene": "HERO.hip"})
                    assert not response.isError, response
                    payload = json.loads(response.content[0].text)
                    assert payload["selection"]["status"] == "unique", payload
                    assert payload["selection"]["selected_pid"] == 123, payload
                    assert payload["data"][0]["scene_name"] == "hero.hip", payload
                    assert server.token not in response.content[0].text
                    assert not Path(directory, "houdini-user-20.5").exists(), "Unconfirmed install previews must not write"
                    print(json.dumps({"ok": True, "tools": sorted(names), "transport": "stdio -> loopback TCP fake Houdini"}))
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


if __name__ == "__main__":
    asyncio.run(asyncio.wait_for(main(), timeout=60))
