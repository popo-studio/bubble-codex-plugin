"""Host API contracts; native Editor validation remains a separate test."""
from contextlib import nullcontext
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runtime'))
import host

class Actor:
    def __init__(self,name,level):
        self.name=name;self.level=level;self.parent=None;self.folder='';self.location=NS(x=0,y=0,z=0);self.scale=NS(x=1,y=1,z=1);self.rotation=NS(pitch=0,yaw=0,roll=0);self.rotation_ok=True;self.modified=0
    def get_path_name(self):return '/Game/World.'+self.name
    def get_actor_label(self):return self.name
    def get_class(self):return NS(get_path_name=lambda:'/Script/Engine.Actor')
    def get_attach_parent_actor(self):return self.parent
    def get_level(self):return self.level
    def get_folder_path(self):return self.folder
    def get_actor_location(self):return self.location
    def get_actor_scale3d(self):return self.scale
    def get_actor_rotation(self):return self.rotation
    def modify(self):self.modified+=1
    def set_actor_location(self,v,*args):self.location=v
    def set_actor_scale3d(self,v):self.scale=v
    def set_actor_rotation(self,v,*args):
        if self.rotation_ok:self.rotation=v
        return self.rotation_ok
    def attach_to_actor(self,parent,*args):self.parent=parent
    def detach_from_actor(self,*args):self.parent=None
    def set_folder_path(self,name):self.folder=name

class StructuredTests(unittest.TestCase):
    def setUp(self):
        level=object();self.child=Actor('Child',level);self.parent=Actor('Parent',level);self.nodes=[self.child,self.parent];world=object()
        subs={'actors':NS(get_all_level_actors=lambda:self.nodes),'world':NS(get_editor_world=lambda:world),'level':NS(is_in_play_in_editor=lambda:False)}
        unreal=NS(EditorActorSubsystem='actors',UnrealEditorSubsystem='world',LevelEditorSubsystem='level',get_editor_subsystem=subs.get,Vector=lambda x,y,z:NS(x=x,y=y,z=z),Rotator=lambda **kw:NS(**kw),ScopedEditorTransaction=lambda label:nullcontext(),Name=str,AttachmentRule=NS(KEEP_WORLD=1),DetachmentRule=NS(KEEP_WORLD=1))
        self.patch=patch.dict(sys.modules,{'unreal':unreal});self.patch.start();self.addCleanup(self.patch.stop)
        self.info=patch.object(host,'scene_info',return_value={});self.info.start();self.addCleanup(self.info.stop)
        host._identity_world=None;host._identity_token=None
        self.token=host.structured('list_objects',{})['scene_token']
    def edit(self,action,target=None,**kwargs):return host.structured('object_action',dict(action=action,expected_scene=self.token,object_id=(target or self.child).get_path_name(),**kwargs))
    def test_rotation_failure_reported_and_vectors_prevalidated(self):
        with self.assertRaises(ValueError):self.edit('transform',position=[1,2,3],rotation=[float('inf'),0,0])
        self.assertEqual(self.child.modified,0)
        self.assertEqual(self.edit('transform',rotation=[10,20,30])['rotation'],[10,20,30])
        self.child.rotation_ok=False
        with self.assertRaisesRegex(RuntimeError,'rejected rotation'):self.edit('transform',rotation=[40,50,60])
    def test_parent_detach_cycle_and_cross_level(self):
        result=self.edit('parent',parent_id=self.parent.get_path_name());self.assertEqual(result['parent_id'],self.parent.get_path_name())
        with self.assertRaisesRegex(ValueError,'cycle'):self.edit('parent',target=self.parent,parent_id=self.child.get_path_name())
        self.assertIsNone(self.edit('parent')['parent_id'])
        self.parent.level=object()
        with self.assertRaisesRegex(ValueError,'same level'):self.edit('parent',parent_id=self.parent.get_path_name())
    def test_replaced_parent_identity_must_be_observed_again(self):
        replacement=Actor('Parent',self.child.level);self.nodes[1]=replacement
        with self.assertRaisesRegex(ValueError,'identity'):self.edit('parent',parent_id=replacement.get_path_name())
        self.assertIsNone(self.child.parent)
    def test_folder_validation_does_not_mutate_target(self):
        for folder in ('../Bad','/Root','Double//Slash','Back\\Slash','a\nb','None','none','  ','a/ /b'):
            with self.assertRaises(ValueError):self.edit('folder',folder=folder)
        self.assertEqual(self.child.modified,0)
        self.assertEqual(self.edit('folder',folder='Studio/Lights')['folder'],'Studio/Lights')
        self.assertEqual(self.edit('folder',folder='')['folder'],'')

if __name__=='__main__':unittest.main()
