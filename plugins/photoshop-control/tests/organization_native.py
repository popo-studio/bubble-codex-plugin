"""Opt-in real MCP/COM scratch acceptance; never edits/closes existing documents."""
import asyncio
import json
import os
from pathlib import Path
import sys
import time
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT=Path(__file__).resolve().parents[1]


async def main():
    params=StdioServerParameters(command=sys.executable,args=['-B',str(ROOT/'server/main.py')],env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
    async with stdio_client(params) as (read,write):
        async with ClientSession(read,write) as session:
            await session.initialize()
            assert len((await session.list_tools()).tools)==42
            async def call(tool,**args):
                result=await session.call_tool('photoshop_'+tool,args)
                assert not result.isError,result
                data=json.loads(result.content[0].text)
                assert data.get('ok'),data
                return data['data'] if 'data' in data else data
            discovered=await session.call_tool('photoshop_list_sessions',{})
            discovered=json.loads(discovered.content[0].text)
            sid=discovered['selection']['selected']
            assert sid,'Exactly one safely addressable Photoshop must already be running'
            before=await call('scene_info',session_id=sid)
            original_ids=[d['id'] for d in before['documents']]
            active=before.get('active_document_id')
            scratch=None
            try:
                created=await call('create_document',session_id=sid,width=512,height=512,name='Bubble organization acceptance '+str(time.time_ns()),background='transparent')
                scratch=created['id'];target=dict(session_id=sid,document_id=scratch)
                layer=await call('create_layer',**target,kind='pixel',name='Clipped test')
                lid=layer['layer_id']
                assert (await call('layer_lock',**target,layer_id=lid,locked=True))['locked'] is True
                assert (await call('layer_lock',**target,layer_id=lid,locked=False))['locked'] is False
                assert (await call('clipping_mask',**target,layer_id=lid,enabled=True))['clipped'] is True
                assert (await call('clipping_mask',**target,layer_id=lid,enabled=False))['clipped'] is False
                await call('selection',**target,action='rectangle',left=10,top=10,right=100,bottom=100)
                await call('save_selection',**target,name='Bubble alpha')
                channels=await call('channels',**target,action='list')
                assert any(c['name']=='Bubble alpha' and c['alpha'] for c in channels['channels'])
                await call('channels',**target,action='rename',name='Bubble alpha',new_name='Renamed alpha')
                await call('channels',**target,action='delete',name='Renamed alpha')
                channels=await call('channels',**target,action='list')
                assert not any(c['alpha'] for c in channels['channels'])
                group=await call('create_layer',**target,kind='group',name='Group lock test')
                gid=group['layer_id']
                assert (await call('layer_lock',**target,layer_id=gid,locked=True))['locked'] is True
                assert (await call('layer_lock',**target,layer_id=gid,locked=False))['locked'] is False
                inspected=await call('inspect_document',**target)
                assert inspected['id']==scratch
            finally:
                if scratch is not None:
                    await call('activate_document',session_id=sid,document_id=scratch)
                    await call('close_document',session_id=sid,document_id=scratch,discard_changes=True)
                if active in original_ids:
                    await call('activate_document',session_id=sid,document_id=active)
            after=await call('scene_info',session_id=sid)
            assert [d['id'] for d in after['documents']]==original_ids
            print(json.dumps({'ok':True,'version':before['version'],'existing_documents_preserved':len(original_ids),'new_tools_native_tested':['layer_lock','clipping_mask','channels'],'scratch_closed':True,'transport':'real MCP stdio -> Photoshop native COM'}))


if __name__=='__main__':asyncio.run(asyncio.wait_for(main(),300))
