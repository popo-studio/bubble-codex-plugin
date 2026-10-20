"""Real stdio MCP -> real installed Windows Photoshop COM. Read-only, no mock host.
Requires already running Photoshop. Optional PHOTOSHOP_SESSION_ID selects explicitly.
"""
import asyncio
import json
import os
from pathlib import Path
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT=Path(__file__).resolve().parents[1]

async def main():
    params=StdioServerParameters(command=sys.executable,args=['-B',str(ROOT/'server/main.py')],env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
    async with stdio_client(params) as (read,write):
        async with ClientSession(read,write) as session:
            await session.initialize()
            names={t.name for t in (await session.list_tools()).tools}
            assert names=={'photoshop_installation_status','photoshop_install_bridge','photoshop_uninstall_bridge','photoshop_list_sessions','photoshop_scene_info','photoshop_inspect_document','photoshop_execute_script'}
            async def call(name,args={}):
                result=await session.call_tool(name,args)
                assert not result.isError,result
                value=json.loads(result.content[0].text)
                assert value.get('ok'),value
                return value
            status=await call('photoshop_installation_status')
            assert status['data']['software_bridge_required'] is False
            sessions=await call('photoshop_list_sessions')
            sid=os.environ.get('PHOTOSHOP_SESSION_ID') or sessions['selection']['selected']
            assert sid,'Open one supported Photoshop instance, or set PHOTOSHOP_SESSION_ID'
            info=await call('photoshop_scene_info',{'session_id':sid})
            for doc in info['data']['documents']:
                await call('photoshop_inspect_document',{'session_id':sid,'document_id':doc['id']})
            uninstall=await call('photoshop_uninstall_bridge',{'confirmed':True})
            assert uninstall['data']['removed_files']==[]
            print(json.dumps({'ok':True,'tools':len(names),'session_id':sid,'version':info['data']['version'],'documents':len(info['data']['documents']),'transport':'real stdio MCP + real native Photoshop COM','note':'Software-side zero-install status checked; Codex uninstall acceptance is separate.'}))
if __name__=='__main__':asyncio.run(asyncio.wait_for(main(),120))
