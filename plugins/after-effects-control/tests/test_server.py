import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import shutil
import subprocess
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'server'))
import installation
import main
import transport

class ServerTests(unittest.TestCase):
 def test_tools_and_identity(self):
  tools=asyncio.run(main.mcp.list_tools());self.assertEqual(len(tools),27)
  for tool in tools:
   if tool.name.endswith(('create_comp','add_layer','set_transform','save_project','execute_script','import_file')):
    self.assertIn('expected_project_state',tool.inputSchema['required']);self.assertIn('session_id',tool.inputSchema['required'])
 def test_no_application_launch(self):
  self.assertNotIn('Popen',(ROOT/'server/transport.py').read_text(encoding='utf-8'))
  self.assertNotIn('AfterFX.exe -r',(ROOT/'server/main.py').read_text(encoding='utf-8'))
 def test_invalid_mutations_fail_before_transport(self):
  with patch.object(main,'call') as call:
   self.assertFalse(main.after_effects_create_comp('test',0,512,'s',{})['ok'])
   self.assertFalse(main.after_effects_set_transform(1,2,'s',{},opacity=101)['ok'])
   self.assertFalse(main.after_effects_import_file('C:/x.jsx','s',{})['ok'])
   call.assert_not_called()
 def test_unknown_session_no_fallback(self):
  with patch.object(transport,'discover',return_value={'data':[]}):self.assertFalse(transport.call('project_info','missing')['ok'])
 def test_timeout_validation(self):
  for value in [True,0,float('nan'),121]:self.assertFalse(transport.call('project_info','missing',timeout=value)['ok'])
 def test_launcher_manifest_versions(self):
  p=json.loads((ROOT/'plugin.json').read_text(encoding='utf-8'));self.assertEqual(p['version'],'0.3.0')
  self.assertTrue((ROOT/'launch-0.3.0.py.lock').exists())

class InstallTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  self.profile=self.root/'profile';self.profile.mkdir()
  self.exe=self.root/'Adobe After Effects 2026'/'Support Files'/'AfterFX.exe';self.exe.parent.mkdir(parents=True);self.exe.write_bytes(b'test')
  (self.exe.parent/'Scripts'/'Startup').mkdir(parents=True)
  self.env=patch.dict(os.environ,{'LOCALAPPDATA':str(self.profile)});self.env.start()
  self.apps=patch.object(installation,'installations',return_value=[{'executable':str(self.exe),'major':26,'version':'26.0'}]);self.apps.start()
  self.acl=patch.object(installation,'protect_directory',side_effect=lambda p:p.mkdir(parents=True,exist_ok=True));self.acl.start()
 def tearDown(self):
  self.acl.stop();self.apps.stop();self.env.stop();self.tmp.cleanup()
 def install(self):
  r=installation.install(True,str(self.exe));self.assertTrue(r['ok'],r);return Path(r['data']['target'])
 def test_preview_is_read_only(self):
  r=installation.install(False,str(self.exe));self.assertTrue(r['ok']);self.assertFalse(Path(r['data']['target']).exists());self.assertIsNone(installation.receipt())
 def test_install_update_rotates_generation_and_uninstall(self):
  target=self.install();old=installation.receipt()['installation_id'];self.install();self.assertNotEqual(old,installation.receipt()['installation_id'])
  r=installation.uninstall(True);self.assertTrue(r['ok'],r);self.assertFalse(target.exists());self.assertIsNone(installation.receipt())
 def test_rollback_failed_receipt_commit_new_install(self):
  real=installation.os.replace
  def fail(source,target):
   if Path(target).name=='receipt.json':raise OSError('simulated receipt failure')
   return real(source,target)
  with patch.object(installation.os,'replace',side_effect=fail):self.assertFalse(installation.install(True,str(self.exe))['ok'])
  self.assertEqual(list((self.exe.parent/'Scripts/Startup').iterdir()),[]);self.assertIsNone(installation.receipt())
 def test_rollback_failed_receipt_commit_update(self):
  target=self.install();old=target.read_bytes();r=installation.receipt();real=installation.os.replace
  def fail(source,target):
   if Path(target).name=='receipt.json':raise OSError('simulated receipt failure')
   return real(source,target)
  with patch.object(installation.os,'replace',side_effect=fail):self.assertFalse(installation.install(True,str(self.exe))['ok'])
  self.assertEqual(target.read_bytes(),old);self.assertEqual(installation.receipt(),r)
 def test_modified_startup_preserved_and_revoked(self):
  target=self.install();target.write_text('user-modified');r=installation.uninstall(True)
  self.assertTrue(r['ok']);self.assertTrue(r['data']['connection_revoked']);self.assertEqual(target.read_text(encoding='utf-8'),'user-modified');self.assertIsNone(installation.receipt())
 def test_managed_old_receipt_upgrade_rotates_generation(self):
  self.install();rp=installation.runtime_directory()/'receipt.json';r=json.loads(rp.read_text(encoding='utf-8'));old=r['installation_id'];r['version']='0.2.0';rp.write_text(json.dumps(r))
  result=installation.install(True,str(self.exe));self.assertTrue(result['ok'],result);self.assertEqual(installation.receipt()['version'],'0.3.0');self.assertNotEqual(installation.receipt()['installation_id'],old)
 def test_missing_startup_still_revokes(self):
  target=self.install();target.unlink();self.assertTrue(installation.uninstall(True)['ok']);self.assertIsNone(installation.receipt())
 def test_unknown_startup_is_not_overwritten(self):
  target,_,_=installation.plan(str(self.exe));target.write_text('foreign')
  self.assertFalse(installation.install(True,str(self.exe))['ok']);self.assertEqual(target.read_text(encoding='utf-8'),'foreign')
 def test_exclusive_install_lock_blocks_competing_mutations(self):
  with installation.install_lock():
   self.assertFalse(installation.install(True,str(self.exe))['ok'])
   self.assertFalse(installation.uninstall(True)['ok'])
  self.assertTrue(installation.install(True,str(self.exe))['ok'])
 def test_runtime_cleanup_preserves_unknown_and_live_claim(self):
  self.install();sid='a'*32;root=installation.runtime_directory()/'hosts'/sid
  (root/'requests').mkdir(parents=True);(root/'results').mkdir()
  (root/'.owner.json').write_text(json.dumps({'schema':1,'session_id':sid,'installation_id':installation.receipt()['installation_id'],'bridge_version':'0.3.0'}))
  (root/'heartbeat.json').write_text(json.dumps({'session_id':sid}))
  expired=root/'requests'/('b'*32+'.running');expired.write_text(json.dumps({'request_id':'b'*32,'session_id':sid,'expires_at':0}))
  live=root/'requests'/('c'*32+'.running');live.write_text(json.dumps({'request_id':'c'*32,'session_id':sid,'expires_at':10**15}))
  unknown=root/'requests'/'keep.txt';unknown.write_text('keep')
  result=installation.uninstall(True);self.assertTrue(result['ok'],result)
  self.assertFalse(expired.exists());self.assertTrue(live.exists());self.assertTrue(unknown.exists());self.assertFalse((root/'heartbeat.json').exists())
 def test_discovery_skips_300_empty_hosts_and_deleted_candidate(self):
  self.install();root=installation.runtime_directory()/'hosts';root.mkdir()
  for i in range(300):(root/format(i,'032x')).mkdir()
  sid='f'*32;folder=root/sid;folder.mkdir()
  (folder/'heartbeat.json').write_text(json.dumps({'schema':1,'session_id':sid,'token':'a'*64,'installation_id':installation.receipt()['installation_id'],'bridge_version':'0.3.0','version':'26.0','expires_at':time.time()*1000+12000,'project':{'name':'hero.aep','path':'D:/hero.aep'}}))
  for bad_id,value in [('d'*32,[]),('e'*32,{'project':'bad'})]:
   bad=root/bad_id;bad.mkdir();(bad/'heartbeat.json').write_text(json.dumps(value))
  real=Path.stat;deleted=root/format(0,'032x')/'heartbeat.json'
  def stat(path,*args,**kwargs):
   if path==deleted:raise FileNotFoundError('simulated concurrent removal')
   return real(path,*args,**kwargs)
  with patch.object(Path,'stat',stat),patch.object(transport.time,'sleep') as sleep:rows=transport.discover()['data']
  self.assertEqual([r['session_id'] for r in rows],[sid]);sleep.assert_not_called()
 def test_old_versions_rejected(self):
  with patch.object(installation,'installations',return_value=[{'executable':str(self.exe),'major':24}]):self.assertFalse(installation.install(True,str(self.exe))['ok'])
 def test_source_loaded_before_package_removal(self):
  self.assertIn('createBubbleAEBridge',installation.SOURCE)
  self.assertIn('bubbleExecute',installation.SOURCE)
 def test_other_profile_guard_precedes_script_definitions(self):
  text=self.install().read_text(encoding='utf-8');self.assertLess(text.index('$.getenv'),text.index('function bubbleExecute'))
  self.assertIn('app.scheduleTask',text);self.assertNotIn('start(){if(!enabled())return;tick()',text)

@unittest.skipUnless(shutil.which('node'),'Node required for host guard simulations')
class HostGuardTests(unittest.TestCase):
 def run_host(self,state=None,token='valid',prelude='',expired=False):
  q=dict(operation='create_comp',args=dict(name='Test',width=512,height=512,duration=1,frame_rate=25),server_id='test',token=token,request_id='request',expires_at=0 if expired else int(time.time()*1000)+30000,expected_project_state=state or dict(path=None,revision=1,root_id=1,items=[]))
  stub="var mutations=0;var $={global:{}};var app={version:'26.0',preferences:{getPrefAsLong:function(){return 1;}},project:{file:null,revision:1,rootFolder:{id:1},numItems:0,items:{addComp:function(){mutations++;throw Error('simulated mutation');}}},beginUndoGroup:function(){},endUndoGroup:function(){}};$.global.BubbleAE_test={token:'valid',project:app.project};"
  source=stub+prelude+(ROOT/'host/operations.jsx').read_text(encoding='utf-8')+"var result=bubbleExecute("+json.dumps(q)+");process.stdout.write(JSON.stringify({result:result,mutations:mutations}));"
  return json.loads(subprocess.run(['node','-e',source],capture_output=True,text=True,check=True).stdout)
 def test_expiry(self):self.assertEqual(self.run_host(expired=True)['mutations'],0)
 def test_wrong_token(self):self.assertEqual(self.run_host(token='wrong')['mutations'],0)
 def test_project_reference_changed(self):self.assertEqual(self.run_host(prelude='$.global.BubbleAE_test.project={};')['mutations'],0)
 def test_revision_changed(self):self.assertEqual(self.run_host(state=dict(path=None,revision=2,root_id=1,items=[]))['mutations'],0)
 def test_reordered_state_equivalent(self):self.assertEqual(self.run_host(state=dict(items=[],root_id=1,revision=1,path=None))['mutations'],1)
 def test_older_version(self):self.assertEqual(self.run_host(prelude="app.version='24.6';")['mutations'],0)
 def test_newer_unverified_version(self):self.assertEqual(self.run_host(prelude="app.version='27.0';")['mutations'],0)
 def test_item_limit(self):self.assertEqual(self.run_host(prelude='app.project.numItems=10001;')['mutations'],0)
 def test_preference_disabled(self):self.assertEqual(self.run_host(prelude='app.preferences.getPrefAsLong=function(){return 0;};')['mutations'],0)

if __name__=='__main__':unittest.main()
