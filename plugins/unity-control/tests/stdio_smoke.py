"""Official MCP ClientSession handshake and all nine tools using isolated fixtures."""
import asyncio
import json
import os
from pathlib import Path
import secrets
import socketserver
import sys
import tempfile
import threading

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


async def main():
    token = secrets.token_urlsafe(32)
    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            request = json.loads(self.rfile.readline(1024 * 1024))
            assert request["token"] == token
            data = {"path": "Assets/Scenes/Main.unity", "project": str(project), "project_name": "Project", "unity_version": "6000.1.0f1", "modified": False, "scenes": []}
            self.wfile.write(json.dumps({"ok": True, "data": data}).encode() + b"\n")
    server = socketserver.TCPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    scratch_root = ROOT.parents[1] / ".test-runtime"
    scratch_root.mkdir(exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="unity-stdio-", dir=scratch_root) as directory:
            scratch = Path(directory)
            project = scratch / "Project"
            (project / "Assets").mkdir(parents=True)
            (project / "ProjectSettings").mkdir()
            (project / "ProjectSettings/ProjectVersion.txt").write_text("m_EditorVersion: 6000.1.0f1\n")
            (project / "Packages").mkdir()
            (project / "Packages/manifest.json").write_text('{"dependencies":{}}\n')
            before = {str(path.relative_to(project)): path.read_bytes() for path in project.rglob("*") if path.is_file()}
            (scratch / "123.json").write_text(json.dumps({"protocol": 1, "pid": 123, "host": "127.0.0.1", "port": server.server_address[1], "token": token}))
            params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "server/main.py")], env={**os.environ, "BUBBLE_UNITY_SESSION_DIR": directory})
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    listing = await session.list_tools()
                    names = {tool.name for tool in listing.tools}
                    assert names == {'unity_list_objects', 'unity_inspect_object', 'unity_object_action', 'unity_scene_action', 'unity_settings', "unity_installation_status", "unity_install_bridge", "unity_uninstall_bridge", "unity_list_sessions", "unity_status", "unity_scene_info", "unity_inspect_scene", "unity_invoke_method", "unity_execute_menu"}
                    for name in sorted(names):
                        arguments = {}
                        if "install" in name:
                            arguments["project_path"] = str(project)
                        elif name == "unity_invoke_method":
                            arguments = {"type_name": "Example", "method_name": "ReadOnlyMethod"}
                        elif name == "unity_execute_menu":
                            arguments = {"menu_path": "Fixture/ReadOnly"}
                        if name in {'unity_object_action', 'unity_scene_action', 'unity_inspect_object', 'unity_list_objects', 'unity_settings'}:
                            arguments["pid"] = 123
                            if name.endswith(("inspect_object", "object_action", "scene_action")): arguments["expected_scene"] = "fixture"
                            if name.endswith("inspect_object"): arguments["object_id"] = 1
                            if name.endswith("object_action"): arguments["action"] = "create"
                            if name.endswith("scene_action"): arguments["action"] = "new"
                        response = await session.call_tool(name, arguments)
                        assert not response.isError, response
                        payload = json.loads(response.content[0].text)
                        assert payload["ok"], payload
                        assert token not in response.content[0].text
                    response = await session.call_tool("unity_list_sessions", {"scene": "Main.unity"})
                    payload = json.loads(response.content[0].text)
                    assert payload["selection"]["selected_pid"] == 123
                    assert before == {str(path.relative_to(project)): path.read_bytes() for path in project.rglob("*") if path.is_file()}
                    assert not (project / "Packages/com.bubble.codex-control").exists()
                    print(json.dumps({"ok": True, "tools": sorted(names), "transport": "official MCP stdio -> fake Unity loopback; fixture install previews write nothing"}))
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == "__main__":
    asyncio.run(asyncio.wait_for(main(), timeout=60))
