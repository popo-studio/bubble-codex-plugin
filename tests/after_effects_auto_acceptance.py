"""Independent AE automatic file-queue acceptance with production JSX and real temp files.

Adobe itself is mocked in a Node VM. This never launches an Adobe application or
writes actual Adobe preferences/startup directories; native AE26 acceptance remains separate.
"""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import asyncio
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
PLUGIN=ROOT/'plugins/after-effects-control'
sys.path.insert(0,str(PLUGIN/'server'))


def until(check,description,timeout=12):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        result=check()
        if result:return result
        time.sleep(.05)
    raise AssertionError('Timed out: '+description)


NODE_SOURCE=r"""
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),readline=require('node:readline');
const config=JSON.parse(process.argv[1]);let context,paused=false,tasks=new Map(),taskCounter=0;
function pathname(value){return value&&value.fsName?value.fsName:String(value);}
function File(value){if(!(this instanceof File))return new File(value);this.fsName=path.resolve(pathname(value));this.encoding='UTF-8';this.position=0;this.mode=null;}
Object.defineProperties(File.prototype,{exists:{get(){return fs.existsSync(this.fsName)&&fs.statSync(this.fsName).isFile();}},name:{get(){return path.basename(this.fsName);}},parent:{get(){return new Folder(path.dirname(this.fsName));}},length:{get(){return this.exists?fs.statSync(this.fsName).size:0;}},modified:{get(){return this.exists?new Date(fs.statSync(this.fsName).mtimeMs):null;}},fullName:{get(){return this.fsName;}},absoluteURI:{get(){return this.fsName;}}});
File.prototype.open=function(mode){this.mode=mode;this.position=0;try{if(mode==='r'){this.content=fs.readFileSync(this.fsName,'utf8');}else if(mode==='w'){fs.writeFileSync(this.fsName,'');this.content='';}else if(mode==='a'){this.content=fs.existsSync(this.fsName)?fs.readFileSync(this.fsName,'utf8'):'';}else throw Error('Unsupported mode');return true;}catch(_){return false;}};
File.prototype.read=function(){return this.content;};File.prototype.write=function(value){if(this.mode!=='w'&&this.mode!=='a')throw Error('File not writable');fs.appendFileSync(this.fsName,String(value));return true;};
File.prototype.close=function(){this.mode=null;return true;};File.prototype.remove=function(){try{fs.unlinkSync(this.fsName);return true;}catch(_){return false;}};
File.prototype.rename=function(name){const dest=path.isAbsolute(name)?name:path.join(path.dirname(this.fsName),name);try{if(fs.existsSync(dest))return false;fs.renameSync(this.fsName,dest);this.fsName=dest;return true;}catch(_){return false;}};
File.prototype.toString=function(){return this.fsName;};File.decode=decodeURIComponent;File.encode=encodeURIComponent;
function Folder(value){if(!(this instanceof Folder))return new Folder(value);this.fsName=path.resolve(pathname(value));}
Object.defineProperties(Folder.prototype,{exists:{get(){return fs.existsSync(this.fsName)&&fs.statSync(this.fsName).isDirectory();}},name:{get(){return path.basename(this.fsName);}},parent:{get(){return new Folder(path.dirname(this.fsName));}},fullName:{get(){return this.fsName;}}});
Folder.prototype.create=function(){try{fs.mkdirSync(this.fsName,{recursive:true});return true;}catch(_){return false;}};
Folder.prototype.getFiles=function(filter){if(!this.exists)return [];let list=fs.readdirSync(this.fsName).map(name=>{const full=path.join(this.fsName,name);return fs.statSync(full).isDirectory()?new Folder(full):new File(full);});if(typeof filter==='function')return list.filter(filter);if(typeof filter==='string'){const re=new RegExp('^'+filter.replace(/[.+^${}()|[\]\\]/g,'\\$&').replace(/\*/g,'.*').replace(/\?/g,'.')+'$');list=list.filter(f=>re.test(f.name));}return list;};
Folder.prototype.remove=function(){try{fs.rmdirSync(this.fsName);return true;}catch(_){return false;}};Folder.prototype.toString=function(){return this.fsName;};Folder.userData=new Folder(config.profile);Folder.temp=new Folder(config.profile);
function build(){
 const sandbox={File,Folder,console:{log(){}},setTimeout,clearTimeout};context=vm.createContext(sandbox);
 vm.runInContext(`var $={global:{},os:'Windows',getenv:function(name){return PROFILE;}};var PROFILE=${JSON.stringify(config.profile)};var taskLog=[];var nextID=10;
 function CompItem(name,w,h,duration,fps){this.id=nextID++;this.name=name;this.typeName='Composition';this.width=w;this.height=h;this.duration=duration;this.frameRate=fps;this.numLayers=0;}
 function FootageItem(){};function ImportOptions(file){this.file=file;}
 var project={file:new File(${JSON.stringify(config.project)}),revision:1,rootFolder:{id:1},_items:[],item:function(i){return this._items[i-1];},itemByID:function(id){for(var i=0;i<this._items.length;i++)if(this._items[i].id===id)return this._items[i];return null;}};
 Object.defineProperty(project,'numItems',{get:function(){return this._items.length;}});
 project.items={addComp:function(name,w,h,aspect,duration,fps){taskLog.push(name);var item=new CompItem(name,w,h,duration,fps);project._items.push(item);project.revision++;return item;}};
 var app={version:'26.0',project:project,preferences:{getPrefAsLong:function(){return 1;}},beginUndoGroup:function(){},endUndoGroup:function(){}};`,context);
 context.app.scheduleTask=(code,delay,repeat)=>{const id=++taskCounter;tasks.set(id,{code,repeat});return id;};context.app.cancelTask=id=>tasks.delete(id);
 context.$.evalFile=file=>vm.runInContext(fs.readFileSync(pathname(file),'utf8'),context);
 for(const source of config.sources||[config.source])vm.runInContext(fs.readFileSync(source,'utf8'),context);
 if(!config.generated)vm.runInContext('$.global.BubbleAEBridge=createBubbleAEBridge('+JSON.stringify({root:config.root,profile:config.profile,installation_id:config.installation_id})+');$.global.BubbleAEBridge.start();',context);
}
build();
const interval=setInterval(()=>{if(paused)return;try{for(const [id,task] of tasks){vm.runInContext(task.code,context);if(!task.repeat)tasks.delete(id);}}catch(e){process.stderr.write(String(e.stack||e)+'\n');}},500);
readline.createInterface({input:process.stdin}).on('line',line=>{let q;try{q=JSON.parse(line);let data;
 if(q.action==='state')data=vm.runInContext('({session_id:$.global.BubbleAEBridge.session_id,log:taskLog.slice(),count:project.numItems})',context);
 else if(q.action==='pause'){paused=true;data=true;}
 else if(q.action==='resume'){paused=false;data=true;}
 else if(q.action==='project'){vm.runInContext('project.file=new File('+JSON.stringify(q.path)+');project.revision++;',context);data=true;}
 else if(q.action==='stop'){vm.runInContext('$.global.BubbleAEBridge.stop()',context);clearInterval(interval);data=true;}
 else throw Error('Unknown action');process.stdout.write(JSON.stringify({id:q.id,ok:true,data})+'\n');if(q.action==='stop')process.exit(0);
 }catch(e){process.stdout.write(JSON.stringify({id:q&&q.id,ok:false,error:String(e.stack||e)})+'\n');}});
"""


class Host:
    def __init__(self,config):
        self.process=subprocess.Popen([shutil.which('node'),'-e',NODE_SOURCE,json.dumps(config)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8')
        self.rows=queue.Queue();self.errors=[]
        threading.Thread(target=self.read,daemon=True).start()
        threading.Thread(target=lambda:self.errors.extend(self.process.stderr),daemon=True).start()
    def read(self):
        for line in self.process.stdout:
            try:self.rows.put(json.loads(line))
            except ValueError:self.errors.append(line)
    def command(self,action,**args):
        identifier=uuid.uuid4().hex
        self.process.stdin.write(json.dumps(dict(id=identifier,action=action,**args))+'\n');self.process.stdin.flush()
        end=time.monotonic()+10
        while time.monotonic()<end:
            try:row=self.rows.get(timeout=.1)
            except queue.Empty:
                if self.process.poll() is not None:raise AssertionError('Host stopped: '+''.join(self.errors))
                continue
            if row.get('id')==identifier:
                assert row.get('ok'),row
                return row['data']
        raise AssertionError('Host command timeout: '+''.join(self.errors))
    def close(self):
        if self.process.poll() is None:
            try:self.command('stop')
            finally:
                try:self.process.wait(timeout=4)
                except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=4)
        for stream in [self.process.stdin,self.process.stdout,self.process.stderr]:stream.close()


def main():
    with tempfile.TemporaryDirectory(prefix='ae-auto-acceptance-') as temporary:
        profile=Path(temporary);root=profile/'Bubble/Codex/after-effects';root.mkdir(parents=True)
        support=profile/'fake-adobe'/'Support Files';(support/'Scripts/Startup').mkdir(parents=True)
        executable=support/'AfterFX.exe';executable.write_bytes(b'fixture only, never executed')
        hosts=[]
        with patch.dict(os.environ,{'LOCALAPPDATA':str(profile)}):
            from privacy import protect_directory
            import installation
            protect_directory(root)
            applications=[{'major':26,'executable':str(executable)}]
            def install_fixture():
                with patch.object(installation,'installations',return_value=applications):
                    result=installation.install(True,str(executable));assert result['ok'],result
                return installation.receipt()
            receipt=install_fixture();source=Path(receipt['target']);installation_id=receipt['installation_id']
            clients=[]
            for i in range(2):
                spec=importlib.util.spec_from_file_location('acceptance_client_'+str(i),PLUGIN/'server/transport.py')
                module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);clients.append(module)
            a,b=clients
            def spawn(project):
                h=Host(dict(profile=str(profile),project=str(project),root=str(root),installation_id=installation_id,source=str(source),generated=True))
                hosts.append(h);return h
            def ok(result):
                assert result.get('ok'),result
                return result
            try:
                h1=spawn(profile/'one/shared.aep');h2=spawn(profile/'two/shared.aep')
                until(lambda:len(a.discover()['data'])==2,'two host instances')
                sid1=h1.command('state')['session_id'];sid2=h2.command('state')['session_id']
                assert sid1!=sid2
                assert a.discover('shared.aep')['selection']['status']=='ambiguous'
                assert a.discover(str(profile/'one/shared.aep'))['selection']['selected']==sid1
                assert all('token' not in row for row in a.discover()['data'])
                for client in clients:
                    for sid in [sid1,sid2]:ok(client.call('project_info',sid))
                print('PASS two hosts / two independent Python clients / filename ambiguity / explicit path selection / private tokens')

                state=ok(a.call('project_info',sid1))['project_state']
                created=ok(a.call('create_comp',sid1,expected_project_state=state,name='512 canvas',width=512,height=512,duration=5,frame_rate=24))
                assert created['data']['width']==512 and created['data']['height']==512
                # Concurrent clients use one snapshot: only one mutation can commit;
                # the second must observe the changed state, never clobber it.
                state=ok(a.call('project_info',sid1))['project_state']
                with ThreadPoolExecutor(max_workers=2) as pool:
                    results=list(pool.map(lambda pair:pair[0].call('create_comp',sid1,expected_project_state=state,name=pair[1],width=512,height=512,duration=5,frame_rate=24),[(a,'client A'),(b,'client B')]))
                assert sum(bool(r['ok']) for r in results)==1,results
                assert h1.command('state')['count']==2 and h2.command('state')['count']==0
                print('PASS empty project creation / cross-client serialized writes / stale state rejected / other instance untouched')

                state=ok(a.call('project_info',sid1))['project_state']
                h1.command('pause')
                timed=a.call('create_comp',sid1,expected_project_state=state,timeout=1,name='expired',width=512,height=512,duration=5,frame_rate=24)
                assert not timed['ok'] and timed['error']['code']=='timeout_outcome_unknown',timed
                h1.command('resume');time.sleep(.7)
                assert 'expired' not in h1.command('state')['log']
                # A claimed request is left after crash; new ticks must never replay it.
                claimed=root/'hosts'/sid1/'requests'/(uuid.uuid4().hex+'.running')
                heartbeat=json.loads((root/'hosts'/sid1/'heartbeat.json').read_text(encoding='utf-8'))
                claimed.write_text(json.dumps(dict(operation='create_comp',session_id=sid1,host_token=heartbeat['token'],request_id=claimed.stem,server_id=a._server_id,token=a._tokens[sid1],expires_at=int((time.time()+60)*1000),expected_project_state=state,args=dict(name='must not replay',width=512,height=512,duration=5,frame_rate=24))),encoding='utf-8')
                time.sleep(.7);assert h1.command('state')['count']==2
                h1.close();hosts.remove(h1)
                h3=spawn(profile/'one/shared.aep');sid3=h3.command('state')['session_id']
                until(lambda:any(r['session_id']==sid3 for r in a.discover()['data']),'replacement host')
                assert sid3!=sid1 and not a.call('project_info',sid1)['ok']
                assert h3.command('state')['count']==0 and claimed.exists()
                print('PASS timed-out queue removed / claimed requests not replayed / restart creates new identity / old session refused')

                updated=install_fixture();assert updated['installation_id']!=installation_id
                until(lambda:not (root/'hosts'/sid2/'heartbeat.json').exists() and not (root/'hosts'/sid3/'heartbeat.json').exists(),'update revokes old generation')
                assert not a.call('project_info',sid3)['ok']
                h4=spawn(profile/'three/updated.aep');sid4=h4.command('state')['session_id']
                until(lambda:any(r['session_id']==sid4 for r in a.discover()['data']),'updated bootstrap connects')
                ok(a.call('project_info',sid4))
                print('PASS real installer update rotates generation / stops old pumps / new startup connects')
                async def mcp_acceptance():
                    from mcp import ClientSession, StdioServerParameters
                    from mcp.client.stdio import stdio_client
                    parameters=StdioServerParameters(command=sys.executable,args=[str(PLUGIN/'server/main.py')],env=dict(os.environ))
                    async with stdio_client(parameters) as (reader,writer):
                        async with ClientSession(reader,writer) as session:
                            await session.initialize()
                            listing=await session.list_tools();assert len(listing.tools)==27
                            async def invoke(name,args):
                                response=await session.call_tool(name,args)
                                assert not response.isError,response
                                value=response.structuredContent
                                if not value:value=json.loads(next(c.text for c in response.content if c.type=='text'))
                                return ok(value)
                            sessions=await invoke('after_effects_list_sessions',{})
                            assert any(row['session_id']==sid4 for row in sessions['data'])
                            info=await invoke('after_effects_project_info',{'session_id':sid4})
                            assert info['data']['items']==[]
                            result=await invoke('after_effects_create_comp',dict(session_id=sid4,expected_project_state=info['project_state'],name='MCP 512',width=512,height=512))
                            assert result['data']['width']==512 and result['data']['height']==512
                            inspected=await invoke('after_effects_project_info',{'session_id':sid4})
                            assert len(inspected['data']['items'])==1 and inspected['data']['items'][0]['name']=='MCP 512'
                async def bounded_mcp():
                    return await asyncio.wait_for(mcp_acceptance(),timeout=45)
                asyncio.run(bounded_mcp())
                assert h4.command('state')['log']==['MCP 512']
                print('PASS actual MCP stdio / 27 tools / discovery / project info / empty-project512 creation / readback')

                # Both user-specific Startup files coexist in one Adobe directory.
                # Loading the other profile first or last must not stop our bridge.
                other_profile=profile/'second-profile';other_profile.mkdir()
                with patch.dict(os.environ,{'LOCALAPPDATA':str(other_profile)}):
                    other=install_fixture()
                for current_profile in [profile,other_profile]:
                    for order in [[str(source),other['target']],[other['target'],str(source)]]:
                        h=Host(dict(profile=str(current_profile),project=str(current_profile/'order.aep'),sources=order,generated=True))
                        try:
                            sid=h.command('state')['session_id'];heartbeat=current_profile/'Bubble/Codex/after-effects/hosts'/sid/'heartbeat.json'
                            until(heartbeat.exists,'profile bootstrap preserves own pump')
                        finally:h.close()
                print('PASS generated startup files for two Windows profiles in both load orders')

                unknown=root/'keep-user-file.txt';unknown.write_text('keep',encoding='utf-8')
                ok(installation.uninstall(True))
                until(lambda:not (root/'hosts'/sid2/'heartbeat.json').exists() and not (root/'hosts'/sid3/'heartbeat.json').exists(),'uninstall revokes live hosts')
                until(lambda:not (root/'hosts'/sid4/'heartbeat.json').exists(),'uninstall stops updated host')
                assert a.discover()['data']==[] and not b.call('project_info',sid4)['ok']
                assert Path(other['target']).exists(),'Other Windows profile startup must remain'
                assert unknown.read_text(encoding='utf-8')=='keep'
                print('PASS receipt revocation stops live bridges / no fallback / unrelated file preserved')
            finally:
                for host in hosts:host.close()
    print('AE automatic file IPC acceptance passed. Adobe DOM is mocked; AE 26 native validation remains pending.')

if __name__=='__main__':main()
