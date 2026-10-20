"""Routing, bounded execution and request invariants; native acceptance is separate."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch, MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
import native
import worker
import main

SESSION={'pid':12,'started':'123','version':'26.2.0','executable':r'C:\PS\Photoshop.exe','prog_id':'Photoshop.Application.190','session_id':'12:123:Photoshop.Application.190','status':'available'}

class RoutingTests(unittest.TestCase):
    def test_unique_and_explicit(self):
        self.assertEqual(native.select([SESSION],None),SESSION)
        self.assertEqual(native.select([SESSION],SESSION['session_id']),SESSION)
    def test_pid_reuse_is_stale(self):
        with self.assertRaises(ValueError):native.select([{**SESSION,'session_id':'12:456:Photoshop.Application.190'}],SESSION['session_id'])
    def test_ambiguous_requires_selection(self):
        with self.assertRaises(ValueError):native.select([SESSION,{**SESSION,'pid':13}],None)
    def test_unrouteable_refused(self):
        with self.assertRaises(ValueError):native.select([{**SESSION,'status':'unrouteable'}],None)
    def test_discovery_same_binary_multiple_instances(self):
        with patch.object(native,'installations',return_value=[SESSION]),patch.object(native,'running_processes',return_value=[SESSION,{**SESSION,'pid':13}]):
            rows=native.discover()
        self.assertEqual([r['status'] for r in rows],['unrouteable','unrouteable'])
    def test_unknown_process_path_blocks_explicit_routing(self):
        with patch.object(native,"installations",return_value=[SESSION]),patch.object(native,"running_processes",return_value=[SESSION,{"pid":13,"started":"2","executable":None}]):
            rows=native.discover()
        with self.assertRaises(ValueError):native.select(rows,SESSION["session_id"])
    def test_expired_request_never_generates_script(self):
        with self.assertRaises(ValueError):worker.source({"operation":"scene_info","expires_at":1})
    def test_javascript_deadline_guard(self):
        self.assertIn("new Date().getTime()>",worker.source({"operation":"scene_info"}))
    def test_unknown_registration_not_selected(self):
        with patch.object(native,'installations',return_value=[]),patch.object(native,'running_processes',return_value=[SESSION]):
            self.assertEqual(native.discover()[0]['status'],'unrouteable')
    def test_document_selection_incomplete_not_unique(self):
        with patch.object(main,'discover',return_value=[SESSION,{**SESSION,'status':'unrouteable'}]),patch.object(main,'call',return_value={'ok':True,'data':{'documents':[{'name':'shot.psd','id':1}]}}):
            result=main.photoshop_list_sessions('shot')
        self.assertEqual(result['selection']['status'],'incomplete')
        self.assertIsNone(result['selection']['selected'])
    def test_timeout_never_retries(self):
        with patch.object(main,'discover',return_value=[SESSION]),patch.object(main.subprocess,'run',side_effect=subprocess.TimeoutExpired('worker',1)) as run:
            result=main.call('execute_script',SESSION['session_id'],1,document_id=2,code='1')
        self.assertEqual(result['error']['code'],'timeout_outcome_unknown')
        self.assertEqual(run.call_count,1)
    def test_explicit_id_retained_for_worker(self):
        with patch.object(main,'discover',return_value=[SESSION]),patch.object(main.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'{"ok":true}', '')) as run:
            main.call('execute_script',SESSION['session_id'],1,document_id=2,code='1')
        self.assertEqual(json.loads(run.call_args.kwargs['input'])['session_id'],SESSION['session_id'])
    def test_invalid_timeout(self):
        self.assertFalse(main.call('scene_info',timeout=121)['ok'])
    def test_document_guard_for_script(self):
        source=worker.source({'operation':'execute_script','document_id':123,'code':'app.version'})
        self.assertIn('app.activeDocument.id!==123',source)
    def test_bad_ids_rejected(self):
        for value in [True,0,-1,1.5,'1']:
            with self.assertRaises(ValueError):worker.source({'operation':'inspect_document','document_id':value})
    def test_large_code_rejected(self):
        with self.assertRaises(ValueError):worker.source({'operation':'execute_script','document_id':1,'code':'x'*250001})
    def test_no_bridge_files_claimed(self):
        self.assertEqual(main.photoshop_uninstall_bridge(True)['data']['removed_files'],[])

class ComGuardTests(unittest.TestCase):
    def assert_rejected_before_script(self, path=r'C:\PS', version='26.2.0', discoveries=None):
        import pythoncom
        import win32com.client.dynamic
        app=MagicMock(); app.Path=path; app.Version=version
        with patch.object(worker,'discover',side_effect=discoveries or [[SESSION]]),patch.object(pythoncom,'GetActiveObject'),patch.object(win32com.client.dynamic,'Dispatch',return_value=app):
            with self.assertRaises((RuntimeError,ValueError)):
                worker.execute({'operation':'scene_info','session_id':SESSION['session_id']})
        app.DoJavaScript.assert_not_called()
    def test_different_com_path_rejected(self):
        self.assert_rejected_before_script(path=r'C:\OtherPS')
    def test_old_com_version_rejected(self):
        self.assert_rejected_before_script(version='25.0.0')
    def test_different_com_version_rejected(self):
        self.assert_rejected_before_script(version='27.0.0')
    def test_session_disappeared_after_connect_rejected(self):
        self.assert_rejected_before_script(discoveries=[[SESSION],[]])

if __name__=='__main__':unittest.main()
