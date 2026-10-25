"""Independent pre-dispatch guards: no host mutation can precede consent/state checks."""
import importlib.util
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('structured_test_nuke',ROOT/'nuke'/'operations.py')
ops=importlib.util.module_from_spec(spec);spec.loader.exec_module(ops)

class StructuredGuardTests(unittest.TestCase):
    def test_root_is_not_a_generic_edit_target(self):
        root=MagicMock();root.fullName.return_value='Root'
        api=MagicMock();api.toNode.return_value=root;api.root.return_value=root
        with self.assertRaisesRegex(ValueError,'Root is reserved'):ops.node(api,'Root')

    def setUp(self):
        self.api=MagicMock()
        self.hosts={'nuke':self.api}
        self.state={'scene':{'path':'','modified':True},'snapshot':'fresh','node_count':0}
        self.addCleanup(patch.stopall)
        patch.dict(sys.modules,self.hosts).start()
        patch.object(ops,'snapshot',return_value=self.state).start()
    def test_status_reports_loaded_bridge_version(self):
        sys.path.insert(0,str(ROOT / "nuke"))
        import bubble_nuke_bridge as bridge
        self.assertEqual(bridge.dispatch("status",{})["bridge_version"],"0.3.0")

    def test_wrong_pid_rejected_before_host_mutation(self):
        with self.assertRaisesRegex(ValueError,'PID'):
            ops.dispatch('file',dict(action='new',pid=os.getpid()+1,expected_snapshot='fresh',discard_changes=True))
        self.assertEqual(self.api.mock_calls,[])
    def test_stale_snapshot_rejected_before_host_mutation(self):
        with self.assertRaisesRegex(ValueError,'Scene changed'):
            ops.dispatch('file',dict(action='new',pid=os.getpid(),expected_snapshot='old',discard_changes=True))
        self.assertEqual(self.api.mock_calls,[])
    def test_dirty_scene_is_not_discarded_by_default(self):
        with self.assertRaises(ValueError):
            ops.dispatch('file',dict(action='new',pid=os.getpid(),expected_snapshot='fresh'))
        self.assertEqual(self.api.mock_calls,[])
    def test_relative_save_is_refused_before_host_mutation(self):
        with self.assertRaises(ValueError):
            ops.dispatch('file',dict(action='save',pid=os.getpid(),expected_snapshot='fresh',path='relative.nk'))
        self.assertEqual(self.api.mock_calls,[])
    def test_nonfinite_numbers_refused(self):
        for value in [float('nan'),float('inf'),True,'1']:
            with self.assertRaises(ValueError):ops.finite(value)
    def test_invalid_timeline_does_not_partially_change_range(self):
        with self.assertRaises(ValueError):
            ops.dispatch('timeline',dict(action='set',pid=os.getpid(),expected_snapshot='fresh',start=100,end=1,frame=1))
        self.api.root.return_value.__getitem__.return_value.setValue.assert_not_called()


    def test_new_operations_refuse_wrong_instance_before_host_calls(self):
        for operation in ['keyframes', 'transfer', 'project']:
            with self.assertRaisesRegex(ValueError,'PID'):
                ops.dispatch(operation,dict(action='set',pid=os.getpid()+1,expected_snapshot='fresh'))
        self.assertEqual(self.api.mock_calls,[])
    def test_restart_renews_session_nonce(self):
        before=ops.SESSION_NONCE;ops.new_session()
        self.assertNotEqual(before,ops.SESSION_NONCE)
    def test_stale_keys_never_reach_native_mutator(self):
        n=MagicMock();k=n.knob.return_value
        patch.object(ops,'node',return_value=n).start()
        k.Class.return_value='Double_Knob';k.arraySize.return_value=1;k.hasExpression.return_value=False;k.animation.return_value=None
        self.api.views.return_value=['main']
        with self.assertRaisesRegex(ValueError,'Key list changed'):
            ops.keyframes(self.api,dict(node='fixture',attribute='tx',action='set',expected_keys='stale',frame=1,value=5))
        k.setAnimated.assert_not_called();k.setValueAt.assert_not_called()

if __name__=='__main__':unittest.main()
