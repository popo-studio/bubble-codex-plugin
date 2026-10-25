"""Real MCP stdio lifecycle/discovery smoke; Resolve need not be installed."""
import asyncio
import json
from pathlib import Path
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    root = Path(__file__).resolve().parents[1]
    async with stdio_client(StdioServerParameters(command=sys.executable,args=["-B",str(root/"server/main.py")])) as (read,write):
        async with ClientSession(read,write) as session:
            await session.initialize()
            names={t.name for t in (await session.list_tools()).tools}
            assert len(names)==20, names
            for name in ("resolve_setup_status","resolve_install_bridge","resolve_uninstall_bridge"):
                result=await session.call_tool(name,{})
                assert not result.isError,result
                data=json.loads(result.content[0].text)
                assert data["ok"] and data["data"]["software_bridge_required"] is False,data
            result=await session.call_tool("resolve_project_info",{"session_id":"nonexistent:stale"})
            data=json.loads(result.content[0].text)
            assert data["ok"] is False,data
            print("PASS: 20 real MCP tools, zero-install lifecycle, stale-session refusal; no Resolve host integration claimed")

if __name__=="__main__": asyncio.run(asyncio.wait_for(main(),60))
