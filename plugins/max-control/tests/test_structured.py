import sys
import types
import unittest
from unittest.mock import patch
from test_host import bridge


class StructuredTests(unittest.TestCase):
    def setUp(self):
        self.node=types.SimpleNamespace(handle=12,name='Box',parent=None,position=types.SimpleNamespace(x=0,y=0,z=0),scale=types.SimpleNamespace(x=1,y=1,z=1),isHidden=False,isFrozen=False,material=None,modifiers=[])
        self.rt=types.SimpleNamespace(objects=[self.node],classOf=lambda n:'Box',maxOps=types.SimpleNamespace(getNodeByHandle=lambda i:self.node if i==12 else None),getSaveRequired=lambda:True,isAnimated=lambda n:False,Point3=lambda *v:types.SimpleNamespace(x=v[0],y=v[1],z=v[2]))
        self.node.rotation=types.SimpleNamespace(x=0,y=0,z=0)
        self.node.transform='world transform'
        self.rt.quatToEuler=lambda v,order=1:v
        self.rt.EulerAngles=self.rt.Point3
        self.rt.eulerToQuat=lambda v,order=1:v
        self.rt.XRefObject=object()
        self.rt.isKindOf=lambda n,k:False
        self.rt.isGroupHead=lambda n:False
        self.rt.isGroupMember=lambda n:False
        self.rt.copy=lambda v:v
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

    def test_rotation_numeric_validation_and_readback(self):
        token=self.call('list_objects')['scene_token']
        result=self.call('object_action',action='transform',expected_scene=token,object_id=12,rotation=[10,20,30])
        self.assertEqual(result['rotation_xyz_degrees'],[10,20,30])
        with self.assertRaises(ValueError):self.call('object_action',action='transform',expected_scene=token,object_id=12,position=[2,3,4],rotation=[float('nan'),0,0])
        self.assertEqual(self.node.position.x,0)
    def test_parent_cycle_and_stale_parent(self):
        token=self.call('list_objects')['scene_token']
        with self.assertRaisesRegex(ValueError,'cycle'):self.call('parent_object',expected_scene=token,object_id=12,parent_id=12)
        with self.assertRaisesRegex(ValueError,'Parent changed'):self.call('parent_object',expected_scene=token,object_id=12,expected_parent_id=99)
        self.assertIsNone(self.node.parent)
        result=self.call('parent_object',expected_scene=token,object_id=12)
        self.assertEqual(result['parent_id'],None)
        self.assertEqual(self.node.transform,'world transform')
    def test_linked_and_grouped_transforms_protected(self):
        token=self.call('list_objects')['scene_token']
        self.rt.isKindOf=lambda n,k:True
        with self.assertRaisesRegex(ValueError,'XRef'):self.call('object_action',action='transform',expected_scene=token,object_id=12,rotation=[0,1,2])
        self.rt.isKindOf=lambda n,k:False
        self.rt.isGroupMember=lambda n:True
        with self.assertRaisesRegex(ValueError,'Grouped'):self.call('parent_object',expected_scene=token,object_id=12)
    def test_layers_revision_prevents_stale_mutation(self):
        layer=types.SimpleNamespace(name='0',ishidden=False,isfrozen=False)
        self.node.layer=layer
        self.rt.LayerManager=types.SimpleNamespace(count=1,getLayer=lambda i:layer,getLayerFromName=lambda name:layer if name=='0' else None)
        read=self.call('layers')
        layer.ishidden=True
        with self.assertRaisesRegex(ValueError,'Layers changed'):self.call('layers',action='flags',expected_scene=read['scene_token'],expected_layers=read['revision'],name='0',hidden=False)
        self.assertTrue(layer.ishidden)
        read=self.call('layers')
        self.call('layers',action='flags',expected_scene=read['scene_token'],expected_layers=read['revision'],name='0',hidden=False,frozen=True)
        self.assertFalse(layer.ishidden);self.assertTrue(layer.isfrozen)
    def test_layer_assign_validates_all_targets_before_write(self):
        layer=types.SimpleNamespace(name='0',ishidden=False,isfrozen=False)
        from unittest.mock import Mock
        layer.addNode=Mock();self.node.layer=layer
        self.rt.LayerManager=types.SimpleNamespace(count=1,getLayer=lambda i:layer,getLayerFromName=lambda name:layer)
        read=self.call('layers')
        with self.assertRaisesRegex(ValueError,'no longer'):self.call('layers',action='assign',expected_scene=read['scene_token'],expected_layers=read['revision'],name='0',object_ids=[12,999])
        layer.addNode.assert_not_called()

    def test_layers_enumerate_objects_once_per_read(self):
        layer=types.SimpleNamespace(name='0',ishidden=False,isfrozen=False);self.node.layer=layer
        class CountedObjects(list):
            iterations=0
            def __iter__(self):self.iterations+=1;return super().__iter__()
        objects=CountedObjects([self.node]);self.rt.objects=objects
        self.rt.LayerManager=types.SimpleNamespace(count=100,getLayer=lambda i:layer)
        result=self.call('layers')
        self.assertEqual(len(result['layers']),100);self.assertEqual(objects.iterations,1)
