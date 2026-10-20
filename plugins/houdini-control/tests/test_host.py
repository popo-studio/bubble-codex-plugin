import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'houdini'))
import bubble_houdini_bridge as bridge
class HostTests(unittest.TestCase):
    def fake(self,directory,refs=()):
        return types.SimpleNamespace(hipFile=types.SimpleNamespace(isNewFile=lambda:True,hasUnsavedChanges=lambda:False,path=lambda:'untitled.hip'),applicationVersionString=lambda:'20.5.487',getenv=lambda key:directory,selectedNodes=lambda:[],frame=lambda:1,fileReferences=lambda:refs,expandString=lambda value:value.replace('$HIP',directory),isUIAvailable=lambda:False)
    def test_sequences_expressions_and_output_ambiguity(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory,'seq.0001.exr').touch()
            refs=[(None,'$HIP/seq.$F4.exr'),(None,'$HIP/seq.${F4}.exr'),(None,'`danger()`'),(None,'opdef:/embedded'),(None,'$HIP/future.bgeo'),(None,'$MISSING/test.exr')]
            report=bridge.inspect_scene(self.fake(directory,refs))
            self.assertEqual(len(report['missing_path_candidates']),1)
            self.assertEqual(len(report['unverified']),3)
            self.assertTrue(report['references'][0]['exists'])
            self.assertTrue(report['references'][1]['exists'])
            self.assertIn('future output',report['coverage'])
    def test_frame_like_variables_and_unbounded_padding_do_not_expand(self):
        report=bridge.inspect_scene(self.fake('',[(None,'$F4BAR/test.exr'),(None,'clip.$F1000000000.exr')]))
        self.assertEqual(len(report['unverified']),1)
        self.assertEqual(len(report['warnings']),1)
        self.assertEqual(report['missing_path_candidates'],[])

    def test_houdini_frame_padding_allows_negative_and_overwidth_frames(self):
        for token in ('$F4', '${F4}', '%04d'):
            for frame in (-10000, -1, 0, 10000):
                with self.subTest(token=token, frame=frame), tempfile.TemporaryDirectory() as directory:
                    Path(directory, 'seq.%04d.exr' % frame).touch()
                    report = bridge.inspect_scene(self.fake(directory, [(None, '$HIP/seq.' + token + '.exr')]))
                    self.assertTrue(report['references'][0]['exists'], report)
        for suffix in ('1', '00001', '-01'):
            with self.subTest(invalid_padding=suffix), tempfile.TemporaryDirectory() as directory:
                Path(directory, 'seq.' + suffix + '.exr').touch()
                report = bridge.inspect_scene(self.fake(directory, [(None, '$HIP/seq.$F4.exr')]))
                self.assertFalse(report['references'][0]['exists'])

    def test_unpadded_negative_and_space_padded_frames(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'seq.-1.exr').touch()
            Path(directory, 'space.  -1.exr').touch()
            for token in ('$F', '${F}', '%d'):
                report = bridge.inspect_scene(self.fake(directory, [(None, '$HIP/seq.' + token + '.exr')]))
                self.assertTrue(report['references'][0]['exists'], report)
            self.assertTrue(bridge.path_status(str(Path(directory, 'space.%4d.exr')))['exists'])
            with self.assertRaises(ValueError):
                bridge.path_status(str(Path(directory, 'seq.%1000000000d.exr')))
            Path(directory, 'seq.0001.exr').touch()
            report = bridge.inspect_scene(self.fake(directory, [(None, '$HIP/seq.%099999999999999999999d.exr')]))
            self.assertEqual(len(report['warnings']), 1)
            self.assertEqual(report['missing_path_candidates'], [])

    def test_python_result_and_headless_refused(self):
        with patch.dict(sys.modules,{'hou':self.fake('')}):
            self.assertEqual(bridge.dispatch('execute_python',{'code':'result = 42'})['result'],42)
            with self.assertRaisesRegex(RuntimeError,'interactive'):bridge.start()
    def test_idle_dispatch_and_unregister(self):
        with tempfile.TemporaryDirectory() as directory:
            host=self.fake(directory);host.isUIAvailable=lambda:True
            callbacks=[];host.ui=types.SimpleNamespace(addEventLoopCallback=callbacks.append,removeEventLoopCallback=callbacks.remove)
            with patch.dict(sys.modules,{'hou':host}), patch.dict(os.environ,{'BUBBLE_HOUDINI_SESSION_DIR':directory}),patch.object(sys,'version_info',(3,11)):
                try:
                    first=bridge.start();self.assertTrue(bridge.start()['already_running']);self.assertEqual(len(callbacks),1)
                    called=[];bridge._bridge.schedule_fn(lambda:called.append(1));self.assertEqual(called,[]);callbacks[0]();self.assertEqual(called,[1])
                finally:bridge.stop()
                self.assertEqual(callbacks,[]);self.assertEqual(list(Path(directory).glob('*.json')),[])
                with patch.object(Path,'mkdir',side_effect=OSError('blocked')):
                    with self.assertRaises(OSError):bridge.start()
                self.assertEqual(callbacks,[])
if __name__=='__main__':unittest.main()
