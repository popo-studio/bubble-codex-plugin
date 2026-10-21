import asyncio
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'server'))
import main
import native
import operations
import transport


class ValidationTests(unittest.TestCase):
    def test_tool_contracts(self):
        tools=asyncio.run(main.mcp.list_tools())
        self.assertEqual(len(tools),11)
        for tool in tools:
            if tool.name in {'after_effects_create_comp','after_effects_add_layer','after_effects_set_transform','after_effects_save_project','after_effects_execute_script','after_effects_import_file'}:
                self.assertFalse(tool.annotations.readOnlyHint)
                self.assertIn('expected_project_state',tool.inputSchema['required'])
                self.assertIn('session_id',tool.inputSchema['required'])

    def test_invalid_comp(self):
        with patch.object(main,'call') as call:
            for values in [('',512,512,25),('X',0,512,25),('X',512,512,float('nan'))]:
                name,w,h,fps=values
                self.assertFalse(main.after_effects_create_comp(name,w,h,'s',{},frame_rate=fps)['ok'])
            call.assert_not_called()

    def test_invalid_transform(self):
        with patch.object(main,'call') as call:
            self.assertFalse(main.after_effects_set_transform(1,2,'s',{},opacity=101)['ok'])
            self.assertFalse(main.after_effects_set_transform(1,2,'s',{},position=[1])['ok'])
            self.assertFalse(main.after_effects_set_transform(1,2,'s',{})['ok'])
            call.assert_not_called()

    def test_import_script_rejected(self):
        with patch.object(main,'call') as call:
            self.assertFalse(main.after_effects_import_file('C:/script.jsx','s',{})['ok'])
            call.assert_not_called()

    def test_save_overwrite_guard(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(main,'call') as call:
            path=Path(folder)/'existing.aep';path.write_text('original')
            self.assertFalse(main.after_effects_save_project(str(path),'s',{})['ok'])
            call.assert_not_called()
            self.assertEqual(path.read_text(),'original')

    def test_latest_only_and_ambiguity(self):
        def row(major,pid=1):return dict(pid=pid,executable='C:/AfterFX.exe',started='123',major=major)
        with patch.object(native,'powershell',return_value=[row(24)]):self.assertEqual(native.discover()[0]['status'],'unsupported')
        with patch.object(native,'powershell',return_value=[row(26),row(24,2)]):self.assertTrue(all(r['status']=='unrouteable' for r in native.discover()))
        with patch.object(native,'powershell',return_value=[row(26)]):self.assertEqual(native.select('1:123')['status'],'available')

    def test_write_requires_prior_handshake(self):
        with patch.object(transport,'select',return_value={}),patch.object(transport.subprocess,'Popen') as popen:
            self.assertFalse(transport.call('create_comp','unseen',{})['ok'])
            popen.assert_not_called()

    def test_packaging(self):
        portable=json.loads((ROOT/'plugin.json').read_text(encoding='utf-8'))
        codex=json.loads((ROOT/'.codex-plugin/plugin.json').read_text(encoding='utf-8'))
        self.assertEqual(portable['version'],codex['version'])
        manifest=json.loads((ROOT/'.mcp.json').read_text(encoding='utf-8'))
        args=manifest['mcpServers']['after_effects']['args']
        self.assertIn('--locked',args)
        self.assertTrue((ROOT/'launch-0.1.0.py.lock').exists())


class TransportTests(unittest.TestCase):
    def setUp(self):
        transport._tokens.clear();transport._handshake_tokens.clear()
        self.row={'session_id':'test','executable':'C:/AfterFX.exe','pid':1,'started':'123'}

    def capture(self,command,**kwargs):
        path=Path(command[-1]);self.folder=path.parent
        source=path.read_text(encoding='utf-8')
        self.request=json.loads(source.split('var q=',1)[1].split(', result, f, layerBudget=',1)[0])
        return object()

    def test_timeout_does_not_retry_or_verify(self):
        with patch.object(transport,'select',return_value=self.row),patch.object(transport.subprocess,'Popen',side_effect=self.capture) as popen,patch.object(transport.time,'monotonic',side_effect=[0,2]):
            result=transport.call('project_info','test',timeout=1)
        self.assertEqual(result['error']['code'],'timeout_outcome_unknown');self.assertEqual(popen.call_count,1)
        self.assertNotIn('test',transport._tokens);self.assertFalse(self.folder.exists())
        self.assertEqual(transport._handshake_tokens['test'],self.request['token'])

    def test_wrong_response_cannot_verify(self):
        def dispatch(command,**kwargs):
            result=self.capture(command,**kwargs)
            Path(self.request['response_path']).write_text(json.dumps({'ok':True,'request_id':'wrong'}),encoding='utf-8')
            return result
        with patch.object(transport,'select',return_value=self.row),patch.object(transport.subprocess,'Popen',side_effect=dispatch):
            result=transport.call('project_info','test')
        self.assertFalse(result['ok']);self.assertNotIn('test',transport._tokens);self.assertFalse(self.folder.exists())

    def test_success_verifies_and_cleans(self):
        def dispatch(command,**kwargs):
            result=self.capture(command,**kwargs)
            Path(self.request['response_path']).write_text(json.dumps({'ok':True,'request_id':self.request['request_id'],'data':{}}),encoding='utf-8')
            return result
        with patch.object(transport,'select',return_value=self.row),patch.object(transport.subprocess,'Popen',side_effect=dispatch):
            result=transport.call('project_info','test')
        self.assertTrue(result['ok']);self.assertIn('test',transport._tokens);self.assertFalse(self.folder.exists())


@unittest.skipUnless(shutil.which('node'),'Node is needed for JavaScript guard simulation (not native AE acceptance)')
class ScriptGuardTests(unittest.TestCase):
    def run_js(self,operation='create_comp',state=None,token='valid',expired=False,prelude=''):
        request=dict(operation=operation,args=dict(name='Test',width=512,height=512,duration=1,frame_rate=25),server_id='test',token=token,request_id='request',expires_at=0 if expired else int(time.time()*1000)+30000,response_path='result',expected_project_state=state or dict(path=None,revision=1,root_id=1,items=[]))
        stub=r'''var output='',mutations=0;var $={global:{}};var app={version:'26.0',preferences:{getPrefAsLong:function(){return 1;}},project:{file:null,revision:1,rootFolder:{id:1},numItems:0,items:{addComp:function(){mutations++;throw Error('simulated mutation');}}},beginUndoGroup:function(){},endUndoGroup:function(){}};$.global.BubbleAE_test={token:'valid',project:app.project};function File(){this.open=function(){return true;};this.write=function(s){output=s;};this.close=function(){};}'''
        source=stub+prelude+operations.script(request)+"process.stdout.write(JSON.stringify({result:JSON.parse(output),mutations:mutations}));"
        result=subprocess.run(['node','-e',source],capture_output=True,text=True,check=True)
        return json.loads(result.stdout)

    def test_expired_request_cannot_mutate(self):
        result=self.run_js(expired=True);self.assertEqual(result['mutations'],0);self.assertIn('expired',result['result']['error']['message'])

    def test_wrong_token_cannot_mutate(self):
        result=self.run_js(token='other');self.assertEqual(result['mutations'],0);self.assertIn('session changed',result['result']['error']['message'])

    def test_project_revision_change_cannot_mutate(self):
        result=self.run_js(state=dict(path=None,revision=2,root_id=1,items=[]));self.assertEqual(result['mutations'],0)

    def test_project_object_change_cannot_mutate(self):
        result=self.run_js(prelude='$.global.BubbleAE_test.project={};');self.assertEqual(result['mutations'],0)

    def test_reordered_keys_are_equivalent(self):
        result=self.run_js(state=dict(items=[],root_id=1,revision=1,path=None));self.assertEqual(result['mutations'],1)

    def test_old_version_rejected(self):
        result=self.run_js(prelude="app.version='24.6';");self.assertEqual(result['mutations'],0)

    def test_project_item_limit_fails_closed(self):
        result=self.run_js(prelude='app.project.numItems=10001;');self.assertEqual(result['mutations'],0);self.assertIn('limit',result['result']['error']['message'])

    def test_preference_not_changed(self):
        result=self.run_js(prelude='app.preferences.getPrefAsLong=function(){return 0;};');self.assertEqual(result['mutations'],0);self.assertIn('manually',result['result']['error']['message'])


if __name__=='__main__':unittest.main()
