import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'nuke'))
import bubble_nuke_bridge as bridge

class Node:
    def __init__(self, name, path, kind='Read'):
        self.name_, self.path_, self.kind = name, path, kind
    def fullName(self): return self.name_
    def Class(self): return self.kind
    def knob(self, key): return types.SimpleNamespace(value=lambda: self.path_) if key=='file' else None

class HostTests(unittest.TestCase):
    def test_printf_frames_follow_minimum_width_and_sign(self):
        with tempfile.TemporaryDirectory() as directory:
            for frame in (-10000, -1, 0, 10000):
                name = "shot.%04d.exr" % frame
                file = Path(directory, name)
                file.touch()
                report = bridge.inspect_scene(self.fake(directory, [Node("Read1", "shot.%04d.exr")]))
                self.assertEqual(report["missing_files"], [], name)
                file.unlink()
            for name in ("shot.1.exr", "shot.00001.exr", "shot.-01.exr"):
                file = Path(directory, name)
                file.touch()
                self.assertFalse(bridge.path_status("shot.%04d.exr", directory)["exists"], name)
                file.unlink()
            Path(directory, "shot.0001.exr").touch()
            self.assertFalse(bridge.path_status("shot.%099999999999999999999d.exr", directory)["exists"])

    def fake(self, directory, nodes=()):
        root=types.SimpleNamespace(name=lambda: 'Root', knob=lambda key: types.SimpleNamespace(value=lambda: directory))
        return types.SimpleNamespace(root=lambda: root, modified=lambda: True, NUKE_VERSION_STRING='15.1v5', selectedNodes=lambda: [], allNodes=lambda **kw: nodes, frame=lambda: 1, GUI=False)
    def test_read_inputs_skip_outputs_expressions_and_sequence_width(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory,'seq.0001.exr').touch()
            nodes=[Node('good','seq.%04d.exr'),Node('missing','missing.exr'),Node('expr','[python evil()].exr'),Node('output','future.exr','Write')]
            report=bridge.inspect_scene(self.fake(directory,nodes))
            self.assertEqual([x['node'] for x in report['missing_files']],['missing'])
            self.assertEqual([x['node'] for x in report['unverified']],['expr'])
            self.assertEqual(report['scene']['path'],'')
            self.assertEqual(len(report['references']),3)
    def test_script_output_exception_and_batch_refusal(self):
        with patch.dict(sys.modules,{'nuke':self.fake('')}):
            self.assertEqual(bridge.dispatch('execute_python',{'code':"print('hi'); result = 42"})['result'],42)
            self.assertEqual(bridge.dispatch('execute_python',{'code':"raise ValueError('x')"})['error']['code'],'script_error')
            with self.assertRaisesRegex(RuntimeError,'interactive'):bridge.start()
    def test_start_is_idempotent_and_failure_leaves_no_listener(self):
        with tempfile.TemporaryDirectory() as directory:
            host=self.fake(directory);host.GUI=True;host.executeInMainThread=lambda fn:fn()
            with patch.dict(sys.modules,{'nuke':host}), patch.dict(os.environ,{'BUBBLE_NUKE_SESSION_DIR':directory}):
                try:
                    first=bridge.start(); second=bridge.start()
                    self.assertTrue(second['already_running']);self.assertEqual(first['port'],second['port'])
                    self.assertEqual(len(list(Path(directory).glob('*.json'))),1)
                finally:bridge.stop()
                self.assertEqual(list(Path(directory).glob('*.json')),[])
                with patch.object(Path,'mkdir',side_effect=OSError('blocked')):
                    with self.assertRaises(OSError):bridge.start()
                self.assertIsNone(bridge._bridge)
if __name__=='__main__':unittest.main()
