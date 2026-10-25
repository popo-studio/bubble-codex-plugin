"""Own two hidden GUI Blender processes and scratch profiles; never use existing instances."""
import asyncio,json,os,subprocess,sys,tempfile,time
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'server'))
import installation
EXE=Path('C:/Program Files/Blender Foundation/Blender 4.5/blender.exe')

async def main():
 processes=[];logs=[]
 with tempfile.TemporaryDirectory(prefix='bubble-blender-gui-') as tmp:
  tmp=Path(tmp);registry=tmp/'sessions'
  try:
   for index in range(2):
    profile=tmp/str(index);scripts=profile/'scripts';config=profile/'config';config.mkdir(parents=True)
    result=installation.install_bridge(str(scripts),True);assert result['ok'],result
    env={**os.environ,'BLENDER_USER_SCRIPTS':str(scripts),'BLENDER_USER_CONFIG':str(config),'BLENDER_USER_DATAFILES':str(profile/'datafiles'),'BUBBLE_BLENDER_SESSION_DIR':str(registry)}
    startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
    log=open(profile/'blender.log','wb');logs.append(log)
    processes.append(subprocess.Popen([str(EXE),'--disable-autoexec'],env=env,cwd=tmp,stdout=log,stderr=subprocess.STDOUT,startupinfo=startup))
   params=StdioServerParameters(command=sys.executable,args=[str(ROOT/'launch-0.1.0.py')],env={**os.environ,'BUBBLE_BLENDER_SESSION_DIR':str(registry)})
   async with stdio_client(params) as streams:
    async with ClientSession(*streams) as session:
     await session.initialize()
     async def call(operation,**a):
      response=await session.call_tool('blender_'+operation,a);assert not response.isError,response
      return response.structuredContent or json.loads(response.content[0].text)
     deadline=time.monotonic()+90
     while time.monotonic()<deadline:
      listing=await call('list_sessions');rows=listing.get('data',[])
      if len(rows)==2 and all(r['status']=='available' for r in rows):break
      if any(p.poll() is not None for p in processes):raise AssertionError('Owned Blender exited before automatic startup')
      await asyncio.sleep(.5)
     else:raise AssertionError('Automatic startup registration did not complete')
     assert {r['pid'] for r in rows}=={p.pid for p in processes},rows
     for index,p in enumerate(processes):
      async def write(operation,**a):
       state=await call('scene_state',pid=p.pid);assert state['ok'],state
       result=await call(operation,pid=p.pid,expected_snapshot=state['data']['snapshot'],**a);assert result['ok'],result
       return result
      await write('create_object',kind='cube',name='Owned_'+str(index))
      scene=await call('list_objects',pid=p.pid);assert any(o['name']=='Owned_'+str(index) for o in scene['data']['result']['objects'])
      await write('scene_file',action='save',path=str(tmp/str(index)/'hero.blend'))
     listing=await call('list_sessions',scene='hero.blend');assert listing['selection']['status']=='ambiguous',listing
     listing=await call('list_sessions',scene=str(tmp/'0/hero.blend'));assert listing['selection']['selected_pid']==processes[0].pid,listing
     processes[0].terminate();processes[0].wait(timeout=20)
     dead=await call('status',pid=processes[0].pid);assert not dead['ok'],dead
     alive=await call('list_objects',pid=processes[1].pid);assert alive['ok'],alive
     assert not any(o['name']=='Owned_0' for o in alive['data']['result']['objects'])
     print('PASS real GUI automatic Startup+timers, two instances, MCP create/read/save, ambiguous filename/exact path, dead PID no fallback')
  finally:
   for p in processes:
    if p.poll() is None:
     p.terminate()
     try:p.wait(timeout=20)
     except subprocess.TimeoutExpired:p.kill();p.wait(timeout=10)
   for log in logs:log.close()
   # Only owned fixture installs; preserve unrelated profile files.
   for index in range(2):
    result=installation.uninstall_bridge(str(tmp/str(index)/'scripts'),True);assert result['ok'],result
   if sys.exc_info()[0]:
    for path in tmp.glob('*/blender.log'):print(path.name,path.read_text(encoding='utf-8',errors='replace')[-6000:])

if __name__=='__main__':asyncio.run(main())
