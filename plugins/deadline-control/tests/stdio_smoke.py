"""Real MCP transport, read-only absent-client path; never touches the farm."""
import asyncio
import json
import os
from pathlib import Path
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


async def main():
    params=StdioServerParameters(command=sys.executable,args=[str(ROOT/'launch-0.1.1.py')],env=dict(os.environ))
    async with stdio_client(params) as (read,write):
        async with ClientSession(read,write) as session:
            await session.initialize()
            listing=await session.list_tools()
            names={tool.name for tool in listing.tools}
            assert names=={'deadline_status','deadline_list_jobs','deadline_job_info','deadline_job_tasks','deadline_job_reports','deadline_submit_job','deadline_retry_tasks'},names
            result=await session.call_tool('deadline_status',{'command':str(ROOT/'not-installed'/'deadlinecommand.exe')})
            payload=json.loads(result.content[0].text)
            assert not result.isError and payload['ok'] and not payload['data']['available'],payload
            result=await session.call_tool('deadline_job_info',{'job_id':'-DeleteJob all'})
            payload=json.loads(result.content[0].text)
            assert not payload['ok'],payload
            print(json.dumps({'ok':True,'tools':sorted(names),'transport':'real MCP stdio','farm_mutations':False}))


if __name__=='__main__':
    asyncio.run(asyncio.wait_for(main(),60))
