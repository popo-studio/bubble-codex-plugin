"""Real MCP stdio -> real broker HTTP -> production CEP transport/host with mock DOM."""
import asyncio
import json
import os
from pathlib import Path
import shutil
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


async def main():
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "server/main.py")],
                                  env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            names = {t.name for t in (await session.list_tools()).tools}
            assert len(names) == 14, names

            async def call(name, args=None):
                result = await session.call_tool(name, args or {})
                assert not result.isError, result
                return json.loads(result.content[0].text)

            assert (await call("premiere_list_sessions"))["data"] == []
            code = (await call("premiere_pairing_code"))["data"]["connection_code"]
            panels = []
            try:
                for _ in range(2):
                    panel = await asyncio.create_subprocess_exec(
                        shutil.which("node"), str(ROOT / "tests/fake_panel.js"),
                        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE)
                    panels.append(panel)
                    panel.stdin.write((code + "\n").encode())
                    await panel.stdin.drain()
                    assert await asyncio.wait_for(panel.stdout.readline(), 5) == b"connected\n"
                listing = await call("premiere_list_sessions", {"project": "hero"})
                assert listing["selection"]["status"] == "ambiguous", listing
                assert code.split(":")[-1] not in json.dumps(listing)
                unselected = await call("premiere_project_info", {"project_id": "mock-project"})
                assert unselected["error"]["code"] == "selection"
                sid = listing["data"][0]["session_id"]
                arguments = {"project_id": "mock-project", "session_id": sid}
                info = await call("premiere_project_info", arguments)
                assert info["data"]["sequences"][0]["name"] == "edit", info
                imported = await call("premiere_import_files", {**arguments, "paths": ["D:/mock.mov"]})
                assert imported["data"]["imported"] is True
                rejected = await call("premiere_save_project", {**arguments, "project_id": "wrong"})
                assert rejected["ok"] is False
                saved = await call("premiere_save_project", arguments)
                assert saved["data"]["saved"] is True
            finally:
                for panel in panels:
                    if panel.returncode is None:
                        panel.stdin.write(b"stop\n")
                        await panel.stdin.drain()
                        try:
                            await asyncio.wait_for(panel.wait(), 3)
                        except asyncio.TimeoutError:
                            panel.kill()
                            await panel.wait()
            assert (await call("premiere_list_sessions"))["data"] == []
            print(json.dumps({"ok": True, "tools": len(names),
                              "transport": "stdio -> actual HTTP -> production CEP transport and host adapter, mocked Adobe DOM",
                              "native_adobe_tested": False}))


if __name__ == "__main__":
    asyncio.run(asyncio.wait_for(main(), 45))
