"""Real MCP stdio and authenticated loopback, isolated fake Blender host."""
import asyncio,json,os,sys,tempfile,threading
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'runtime'))
import bridge

async def main():
 server=bridge.Bridge(lambda op,a: {'path':'D:/hero.blend','modified':False,'blender_version':'4.5.3'} if op=='scene_info' else {'operation':op},lambda fn:fn())
 threading.Thread(target=server.serve_forever,daemon=True).start()
 try:
  with tempfile.TemporaryDirectory() as tmp:
   Path(tmp,'123.json').write_text(json.dumps({'protocol':1,'pid':123,'host':'127.0.0.1','port':server.server_address[1],'token':server.token}))
   params=StdioServerParameters(command=sys.executable,args=[str(ROOT/'launch-0.2.0.py')],env={**os.environ,'BUBBLE_BLENDER_SESSION_DIR':tmp})
   async with stdio_client(params) as streams:
    async with ClientSession(*streams) as session:
     await session.initialize();tools=await session.list_tools();assert len(tools.tools)==21
     for tool in tools.tools:
      suffix=tool.name.removeprefix('blender_');a={'pid':123,'expected_snapshot':'fixture'}
      if suffix in ('installation_status','install_bridge','uninstall_bridge'):a={'scripts_directory':str(Path(tmp)/'scripts')}
      elif suffix=='list_sessions':a={}
      elif suffix in ('status','scene_info','scene_state','inspect_scene','list_objects'):a={'pid':123}
      elif suffix=='scene_file':a.update(action='new')
      elif suffix=='create_object':a.update(kind='cube',name='fixture')
      elif suffix=='edit_object':a.update(action='rename',name='fixture',new_name='new')
      elif suffix=='parent_object':a.update(name='fixture')
      elif suffix=='select_objects':a.update(names=[])
      elif suffix in ('material','camera','light'):a.update(name='fixture')
      elif suffix=='execute_python':a.update(code='result=42')
      result=await session.call_tool(tool.name,a);assert not result.isError,result
      payload=result.structuredContent or json.loads(result.content[0].text);assert payload['ok'],payload
      assert server.token not in str(result)
     assert not (Path(tmp)/'scripts').exists()
     print('PASS21tools realMCP -> authenticated fakeBlender; previews made no writes')
 finally:server.shutdown();server.server_close()

if __name__=='__main__':asyncio.run(main())
