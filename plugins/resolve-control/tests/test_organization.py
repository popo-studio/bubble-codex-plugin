"""Contract behavior for documented timeline organization APIs; no native claim."""
import unittest
from unittest.mock import Mock
from test_resolve import Resolve
import operations as op


class OrganizationTests(unittest.TestCase):
    def setUp(self):
        self.resolve=Resolve(); self.check=Mock(); self.timeline=self.resolve.current.timeline
        self.state={'name':'Video 1','enabled':True,'locked':False}
        self.timeline.GetTrackName=lambda *args:self.state['name']
        self.timeline.GetIsTrackEnabled=lambda *args:self.state['enabled']
        self.timeline.GetIsTrackLocked=lambda *args:self.state['locked']
        def setter(field):
            def update(kind,index,value):self.state[field]=value;return True
            return update
        self.timeline.SetTrackName=setter('name');self.timeline.SetTrackEnable=setter('enabled');self.timeline.SetTrackLock=setter('locked')
        self.timeline.DeleteMarkerAtFrame=lambda frame:self.timeline.markers.pop(frame,None) is not None
    def run_op(self,operation,**args):
        return op.dispatch(self.resolve,{'operation':operation,'arguments':{'project_id':'project-1','timeline_id':'timeline-1',**args}},self.check)
    def test_track_read_preview_apply(self):
        a=dict(track_type='video',index=1)
        before=self.run_op('track_state',**a)
        self.assertFalse(self.run_op('track_state',**a,enabled=False,expected_state=before,confirmed=False)['applied'])
        self.assertTrue(self.state['enabled'])
        self.assertFalse(self.run_op('track_state',**a,enabled=False,locked=True,expected_state=before,confirmed=True)['result']['enabled'])
        self.assertTrue(self.state['locked'])
    def test_track_changed_between_checks_does_not_write(self):
        a=dict(track_type='video',index=1);before=self.run_op('track_state',**a)
        self.check.side_effect=lambda:self.state.update(name='User changed')
        with self.assertRaisesRegex(ValueError,'changed'):
            self.run_op('track_state',**a,enabled=False,expected_state=before,confirmed=True)
        self.assertTrue(self.state['enabled'])
    def test_track_invalid_boolean_and_index_refused(self):
        with self.assertRaises(ValueError):self.run_op('track_state',track_type='video',index=0)
        before=self.run_op('track_state',track_type='video',index=1)
        with self.assertRaises(ValueError):self.run_op('track_state',track_type='video',index=1,enabled='false',expected_state=before,confirmed=True)
    def test_marker_delete_preview_stale_and_success(self):
        original={'name':'Review','color':'Blue','note':'Fix','duration':1};self.timeline.markers[3]=dict(original)
        self.assertFalse(self.run_op('delete_marker',frame=3,expected_marker=original,confirmed=False)['applied'])
        with self.assertRaises(ValueError):self.run_op('delete_marker',frame=3,expected_marker={**original,'name':'stale'},confirmed=True)
        self.assertTrue(self.run_op('delete_marker',frame=3,expected_marker=original,confirmed=True)['applied'])
        self.assertEqual(self.timeline.markers,{})
    def test_marker_changed_before_apply_refused(self):
        marker={'name':'A'};self.timeline.markers[0]=dict(marker)
        self.check.side_effect=lambda:self.timeline.markers[0].update(name='B')
        with self.assertRaises(ValueError):self.run_op('delete_marker',frame=0,expected_marker=marker,confirmed=True)
        self.assertEqual(self.timeline.markers[0]['name'],'B')
    def test_timeline_duplicate_id_and_rename(self):
        duplicate=Mock();duplicate.GetUniqueId.return_value='timeline-copy';duplicate.GetName.return_value='Copy'
        self.timeline.DuplicateTimeline=Mock(return_value=duplicate)
        self.assertFalse(self.run_op('manage_timeline',action='duplicate',name='Copy',confirmed=False)['applied'])
        self.timeline.DuplicateTimeline.assert_not_called()
        self.assertEqual(self.run_op('manage_timeline',action='duplicate',name='Copy',confirmed=True)['result']['timeline']['id'],'timeline-copy')
        self.timeline.SetName=Mock(return_value=True)
        self.run_op('manage_timeline',action='rename',name='New',confirmed=True)
        self.timeline.SetName.assert_called_once_with('New')
        with self.assertRaises(ValueError):self.run_op('manage_timeline',action='rename',name='Main',confirmed=True)


if __name__=='__main__':unittest.main()
