"""Real Python brokers + file discovery + Node CEP auto-manager, with mock Adobe DOM.

Runs only in an isolated temporary APPDATA/LOCALAPPDATA profile. No Adobe process,
registry preference, Creative Cloud, or real extension directory is touched.
This is integration evidence, not native Premiere acceptance.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
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
PLUGIN=ROOT/'plugins/premiere-control'
sys.path.insert(0,str(PLUGIN/'server'))


def until(check,description,timeout=12):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        value=check()
        if value:return value
        time.sleep(.05)
    raise AssertionError('Timed out: '+description)


class NodeHost:
    def __init__(self,source,environment):
        self.process=subprocess.Popen([shutil.which('node'),'-e',source,str(PLUGIN)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',env=environment)
        self.rows=queue.Queue();self.errors=[]
        threading.Thread(target=self._read,daemon=True).start()
        threading.Thread(target=self._errors,daemon=True).start()

    def _read(self):
        for line in self.process.stdout:
            try:self.rows.put(json.loads(line))
            except ValueError:self.errors.append(line)

    def _errors(self):
        for line in self.process.stderr:self.errors.append(line)

    def command(self,action,**args):
        request_id=uuid.uuid4().hex
        self.process.stdin.write(json.dumps(dict(id=request_id,action=action,**args))+'\n');self.process.stdin.flush()
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            try:row=self.rows.get(timeout=.2)
            except queue.Empty:
                if self.process.poll() is not None:raise AssertionError('Node host stopped: '+''.join(self.errors))
                continue
            if row.get('id')==request_id:
                assert row.get('ok'),row
                return row.get('data')
        raise AssertionError('Node command timeout: '+action+' '+''.join(self.errors))

    def close(self):
        if self.process.poll() is None:
            try:self.command('stop')
            finally:
                try:self.process.wait(timeout=4)
                except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=4)
        for stream in [self.process.stdin,self.process.stdout,self.process.stderr]:stream.close()


def install_receipt_fixture(profile):
    """Use production ownership checks against an explicitly labelled fake install."""
    import installation
    target=installation._target()
    target.mkdir(parents=True)
    (target/'acceptance-fixture.txt').write_text('Mock extension receipt only; no Adobe runtime.',encoding='utf-8')
    installation._receipt_path(target).write_text(json.dumps({'plugin_id':installation.PLUGIN_ID,'target':str(target),'version':'0.3.0','files':installation._hashes(target)}),encoding='utf-8')
    return target


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    from broker import Broker
    from discovery import Publisher,cleanup_records,runtime_directory,installation_enabled
    import installation
    node_source=r'''
const path=require('node:path'),fs=require('node:fs'),readline=require('node:readline');
const root=process.argv[1];
const {createAutoManager}=require(path.join(root,'cep/auto'));
const {createDiscoveryReader}=require(path.join(root,'cep/discovery'));
const {createTransport}=require(path.join(root,'cep/transport'));
const {createHost}=require(path.join(root,'cep/host'));
const {fixture}=require(path.join(root,'tests/mock_host'));
const target=path.join(process.env.APPDATA,'Adobe/CEP/extensions/com.popostudio.bubble.premiere');
const hosts=['a','b'].map(id=>{
 const f=fixture();f.set('project.documentID='+JSON.stringify('project-'+id)+';project.path='+JSON.stringify('D:/'+id+'/hero.prproj')+';');
 const native=createHost(f.evalScript),stats={active:0,maxActive:0,writes:[],delay:120};
 const host={info:()=>native.info(),dispatch:async(op,args,deadline)=>{
  stats.active++;stats.maxActive=Math.max(stats.active,stats.maxActive);
  try{await new Promise(r=>setTimeout(r,stats.delay));const result=await native.dispatch(op,args,deadline);if(op==='save_project')stats.writes.push({project:args.project_id,time:Date.now()});return result;}
  finally{stats.active--;}
 }};
 const read=createDiscoveryReader(fs,path,process.env,target);
 const manager=createAutoManager(host,read,adapter=>createTransport(adapter,()=>{}));
 return {id,stats,manager};
});
const timer=setInterval(()=>hosts.forEach(h=>h.manager.scan()),80);
readline.createInterface({input:process.stdin}).on('line',async line=>{
 let q;try{q=JSON.parse(line);let data;
 if(q.action==='stats')data=hosts.map(h=>({id:h.id,...h.stats,connections:h.manager.count()}));
 else if(q.action==='delay'){hosts.find(h=>h.id===q.host).stats.delay=q.ms;data=true;}
 else if(q.action==='stop'){clearInterval(timer);await Promise.all(hosts.map(h=>h.manager.close()));data=true;}
 else throw Error('Unknown command');
 process.stdout.write(JSON.stringify({id:q.id,ok:true,data})+'\n');
 if(q.action==='stop')setTimeout(()=>process.exit(0),10);
 }catch(e){process.stdout.write(JSON.stringify({id:q&&q.id,ok:false,error:String(e)})+'\n');}
});
'''
    phases=[]
    with tempfile.TemporaryDirectory(prefix='bubble-premiere-auto-acceptance-') as folder:
        profile=Path(folder)
        environment={**os.environ,'APPDATA':str(profile/'roaming'),'LOCALAPPDATA':str(profile/'local')}
        with patch.dict(os.environ,{'APPDATA':environment['APPDATA'],'LOCALAPPDATA':environment['LOCALAPPDATA']}):
            target=install_receipt_fixture(profile)
            assert installation_enabled()
            brokers=[Broker(),Broker()];publishers=[];host=None
            try:
                for broker in brokers:
                    publisher=Publisher(broker.http.server_port,broker.token)
                    assert publisher.publish()
                    publisher.start();publishers.append(publisher)
                directory=runtime_directory()
                stale_id=str(uuid.uuid4())
                stale=directory/(stale_id+'.json')
                stale.write_text(json.dumps({'schema':1,'plugin_id':installation.PLUGIN_ID,'broker_id':stale_id,'pid':999999,'port':1,'token':'a'*48,'expires_at':time.time()-1}),encoding='utf-8')
                unknown=directory/'not-ours.json';unknown.write_text('{"owner":"test"}',encoding='utf-8')
                host=NodeHost(node_source,environment)
                until(lambda:all(len(b.sessions()['data'])==2 for b in brokers),'two hosts automatically connecting to both brokers')
                for broker in brokers:
                    listing=broker.sessions('hero')
                    assert listing['selection']['status']=='ambiguous',listing
                    assert len(listing['selection']['matches'])==2
                    path=broker.sessions('D:/a/hero.prproj')
                    assert path['selection']['status']=='unique',path
                    assert path['selection']['selected']['target_id']=='project-a'
                    assert broker.token not in json.dumps(listing)
                    assert not broker.request('project_info',{'project_id':'project-a'})['ok']
                assert all(row['connections']==2 for row in host.command('stats'))
                phases.append('two brokers and two hosts automatically discovered; ambiguous name and exact path selection; expired record ignored')

                def selected(broker,letter='a'):
                    return broker.sessions('D:/'+letter+'/hero.prproj')['selection']['selected']['session_id']

                with ThreadPoolExecutor(max_workers=4) as pool:
                    jobs=[pool.submit(brokers[i%2].request,'save_project',{'project_id':'project-a'},selected(brokers[i%2]),5) for i in range(4)]
                    results=[job.result(timeout=8) for job in jobs]
                assert all(result.get('ok') for result in results),results
                stats=host.command('stats')
                assert stats[0]['maxActive']==1,stats
                assert len(stats[0]['writes'])==4 and len(stats[1]['writes'])==0,stats
                phases.append('four concurrent cross-broker writes serialized on one host with no other-host mutation')

                before=len(stats[0]['writes']);old=selected(brokers[0])
                host.command('delay',host='a',ms=900)
                with ThreadPoolExecutor(max_workers=1) as pool:
                    job=pool.submit(brokers[0].request,'save_project',{'project_id':'project-a'},old,4)
                    until(lambda:host.command('stats')[0]['active']==1,'delivered host write')
                    assert brokers[0].handle('/unregister',{'session_id':old})['ok']
                    result=job.result(timeout=6)
                assert result.get('ok') is False and result['error']['execution_uncertain'] is True,result
                until(lambda:len(brokers[0].sessions()['data'])==2 and selected(brokers[0])!=old,'automatic reconnect with a fresh session UUID')
                time.sleep(.8)
                stats=host.command('stats')
                assert len(stats[0]['writes'])==before+1,stats
                assert not brokers[0].request('save_project',{'project_id':'project-a'},old,1)['ok']
                assert len(host.command('stats')[0]['writes'])==before+1
                host.command('delay',host='a',ms=120)
                info=brokers[0].request('project_info',{'project_id':'project-a'},selected(brokers[0]),4)
                assert info.get('ok'),info
                phases.append('disconnect after delivery reports uncertain outcome; fresh-session reconnect performs no write replay')

                retained=selected(brokers[1]);old_token=brokers[0].token
                publishers[0].close();brokers[0].close()
                brokers[0]=Broker()
                publishers[0]=Publisher(brokers[0].http.server_port,brokers[0].token)
                assert publishers[0].publish();publishers[0].start()
                until(lambda:len(brokers[0].sessions()['data'])==2,'replacement Codex broker discovered automatically')
                assert brokers[0].token!=old_token
                assert selected(brokers[1])==retained
                assert len(host.command('stats')[0]['writes'])==before+1
                phases.append('replacement broker with new port/token reconnects both hosts without disturbing the other broker or replaying writes')

                installation._receipt_path(target).unlink()
                for publisher in publishers:assert not publisher.publish()
                until(lambda:all(not b.sessions()['data'] for b in brokers),'receipt removal revokes both hosts and both brokers')
                assert all(not p.path.exists() for p in publishers)
                cleanup_records()
                assert not stale.exists() and unknown.exists()
                phases.append('receipt revocation disconnects all hosts; owned discovery records cleaned and unknown files preserved')
            finally:
                if host:host.close()
                for publisher in publishers:publisher.close()
                for broker in brokers:broker.close()
    print(json.dumps({'ok':True,'integration_phases':len(phases),'phases':phases,'transport':'real Python Broker HTTP + protected file discovery + production Node auto manager/transport/host + mocked Adobe DOM','native_adobe_tested':False,'real_profile_modified':False},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
