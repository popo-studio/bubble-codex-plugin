"""Real MCP SDK stdio handshake/tool calls against a fake local Nuke bridge."""
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
sys.path.insert(0, str(ROOT / "nuke"))
import bubble_nuke_bridge as bridge


async def main():
    def dispatch(operation, arguments):
        if operation == "scene_info":
            return {"path": "D:/projects/hero.nk", "modified": False, "nuke_version": "15.1"}
        return {"operation": operation, "echo": arguments}
    server = bridge.Bridge(dispatch, lambda fn: fn())
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        runtime = ROOT / ".test-runtime"
        runtime.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="bubble-mcp-smoke-", dir=runtime) as directory:
            Path(directory, "123.json").write_text(json.dumps({"protocol": 1, "pid": 123, "host": "127.0.0.1", "port": server.server_address[1], "token": server.token}))
            params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "server" / "main.py")], env={**os.environ, "BUBBLE_NUKE_SESSION_DIR": directory, "BUBBLE_NUKE_USER_DIR": str(Path(directory) / "nuke-user")})
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    listing = await session.list_tools()
                    names = {tool.name for tool in listing.tools}
                    legacy_names = {"nuke_list_sessions", "nuke_status", "nuke_scene_info", "nuke_inspect_scene", "nuke_execute_python", "nuke_installation_status", "nuke_install_bridge", "nuke_uninstall_bridge"}
                    additional = {"nuke_"+suffix for suffix in ["scene_state","scene_file","query_nodes","create_node","edit_node","select_nodes","node_attribute","node_connections","timeline","keyframes","graph_transfer","project_settings"]}
                    assert names == legacy_names | additional, names
                    for name in sorted(names):
                        arguments = {"code": "result = 42"} if name.startswith("nuke_execute_") else {}
                        suffix=name.removeprefix("nuke_")
                        common={"pid":123,"expected_snapshot":"fake snapshot"}
                        if suffix=='scene_file':arguments=dict(common,action='save',path='D:/scratch')
                        elif suffix=='create_node':arguments=dict(common,kind='transform',name='scratch')
                        elif suffix=='edit_node':arguments=dict(common,action='rename',node='scratch',name='newName')
                        elif suffix=='select_nodes':arguments=dict(common,nodes=[])
                        elif suffix=='node_attribute':arguments=dict(pid=123,node='scratch',attribute='tx')
                        elif suffix=='node_connections':arguments=dict(pid=123,node='scratch')
                        elif suffix=='timeline':arguments=dict(pid=123)
                        elif suffix=='parent_node':arguments=dict(common,node='scratch')
                        elif suffix=='keyframes':arguments=dict(pid=123,node='scratch',attribute='tx')
                        elif suffix in ('scene_transfer','graph_transfer'):arguments=dict(common,action='export',path='D:/scratch',nodes=['scratch'])
                        elif suffix=='project_settings':arguments=dict(pid=123)
                        elif suffix=='network_box':arguments=dict(pid=123,parent='/obj')
                        response = await session.call_tool(name, arguments)
                        assert not response.isError, response
                        payload = json.loads(response.content[0].text)
                        assert payload["ok"], payload
                        assert server.token not in response.content[0].text
                    response = await session.call_tool("nuke_list_sessions", {"scene": "HERO.nk"})
                    assert not response.isError, response
                    payload = json.loads(response.content[0].text)
                    assert payload["selection"]["status"] == "unique", payload
                    assert payload["selection"]["selected_pid"] == 123, payload
                    assert payload["data"][0]["scene_name"] == "hero.nk", payload
                    assert server.token not in response.content[0].text
                    assert not Path(directory, "nuke-user").exists(), "Unconfirmed install previews must not write"
                    print(json.dumps({"ok": True, "tools": sorted(names), "transport": "stdio -> loopback TCP fake Nuke"}))
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


if __name__ == "__main__":
    asyncio.run(asyncio.wait_for(main(), timeout=60))
