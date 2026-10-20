"""Real stdio MCP -> authenticated HTTP broker -> simulated UXP panel. No Adobe mutation."""
import asyncio
import json
import os
from pathlib import Path
import sys
import urllib.request
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT = Path(__file__).resolve().parents[1]

async def main():
    params = StdioServerParameters(command=sys.executable,args=[str(ROOT/'server/main.py')],env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
    async with stdio_client(params) as (read,write):
        async with ClientSession(read,write) as session:
            await session.initialize()
            names={t.name for t in (await session.list_tools()).tools}
            assert names=={'photoshop_installation_status','photoshop_install_bridge','photoshop_uninstall_bridge','photoshop_pairing','photoshop_list_sessions','photoshop_scene_info','photoshop_inspect_document','photoshop_batch_play'}
            async def call(name,args={}):
                result=await session.call_tool(name,args)
                assert not result.isError,result
                return json.loads(result.content[0].text)
            assert (await call('photoshop_list_sessions'))['data']==[]
            pairing=await call('photoshop_pairing')
            _,_,port,token=pairing['data']['connection_code'].split(':')
            def post(endpoint,data):
                req=urllib.request.Request('http://127.0.0.1:'+port+endpoint,json.dumps(data).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
                with urllib.request.urlopen(req,timeout=3) as response:return json.load(response)
            info={'app':'photoshop','version':'26.2.0','targets':[{'id':12,'name':'hero.psd','path':'D:/hero.psd'}]}
            sid=(await asyncio.to_thread(post,'/register',{'info':info}))['data']['session_id']
            found=await call('photoshop_list_sessions',{'document':'hero.psd'})
            assert found['selection']['status']=='unique'
            assert token not in json.dumps(found)
            pending=asyncio.create_task(call('photoshop_scene_info',{'session_id':sid}))
            job=None
            for _ in range(100):
                job=(await asyncio.to_thread(post,'/poll',{'session_id':sid,'info':info}))['data']
                if job:break
                await asyncio.sleep(.01)
            assert job and job['operation']=='scene_info'
            await asyncio.to_thread(post,'/result',{'session_id':sid,'request_id':job['request_id'],'response':{'ok':True,'data':info}})
            assert (await pending)['data']['version']=='26.2.0'
            await asyncio.to_thread(post,'/unregister',{'session_id':sid})
            assert (await call('photoshop_list_sessions'))['data']==[]
            print(json.dumps({'ok':True,'tool_count':len(names),'transport':'real stdio + loopback HTTP, simulated UXP panel'}))
if __name__=='__main__':asyncio.run(asyncio.wait_for(main(),45))
