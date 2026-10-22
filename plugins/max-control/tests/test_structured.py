import sys
import types
import unittest
from unittest.mock import patch
from test_host import bridge


class StructuredTests(unittest.TestCase):
    def setUp(self):
        self.node=types.SimpleNamespace(handle=12,name='Box',parent=None,position=types.SimpleNamespace(x=0,y=0,z=0),scale=types.SimpleNamespace(x=1,y=1,z=1),isHidden=False,isFrozen=False,material=None,modifiers=[])
        self.rt=types.SimpleNamespace(objects=[self.node],classOf=lambda n:'Box',maxOps=types.SimpleNamespace(getNodeByHandle=lambda i:self.node if i==12 else None),getSaveRequired=lambda:True,isAnimated=lambda n:False,Point3=lambda *v:types.SimpleNamespace(x=v[0],y=v[1],z=v[2]))
        self.p=patch.dict(sys.modules,{'pymxs':types.SimpleNamespace(runtime=self.rt)});self.p.start();self.addCleanup(self.p.stop)
        self.info=patch.object(bridge._host,'scene_info',return_value={'path':'fixture.max'});self.info.start();self.addCleanup(self.info.stop)
    def call(self,op,**args):return bridge.dispatch(op,args)
    def test_readback_and_transform(self):
        r=self.call('list_objects');token=r['scene_token'];self.assertEqual(r['objects'][0]['id'],12)
        r=self.call('object_action',action='transform',expected_scene=token,object_id=12,position=[1,2,3]);self.assertEqual(r['position'],[1,2,3])
    def test_scene_epoch_prevents_old_handle_use(self):
        token=self.call('list_objects')['scene_token'];bridge._host.invalidate_scene()
        with self.assertRaises(ValueError):self.call('object_action',action='rename',expected_scene=token,object_id=12,name='wrong')
        self.assertEqual(self.node.name,'Box')
    def test_dirty_scene_never_discarded(self):
        with self.assertRaisesRegex(ValueError,'unsaved'):self.call('scene_action',action='new',expected_scene=self.call('list_objects')['scene_token'])
    def test_invalid_vector_before_any_write(self):
        with self.assertRaises(ValueError):self.call('object_action',action='transform',expected_scene=self.call('list_objects')['scene_token'],object_id=12,position=[2,3,4],scale=[float('nan'),1,1])
        self.assertEqual(self.node.position.x,0)
    def test_animated_node_refused(self):
        self.rt.isAnimated=lambda n:True
        with self.assertRaisesRegex(ValueError,'Animated'):self.call('object_action',action='transform',expected_scene=self.call('list_objects')['scene_token'],object_id=12,position=[1,2,3])
    def test_unknown_node_refused(self):
        with self.assertRaisesRegex(ValueError,'no longer'):self.call('inspect_object',expected_scene=self.call('list_objects')['scene_token'],object_id=99)
