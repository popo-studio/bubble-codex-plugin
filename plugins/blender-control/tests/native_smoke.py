"""Run inside Blender background with isolated user paths; writes only named temporary directory."""
import bpy
import json
import os
from pathlib import Path
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'runtime'))
import operations as ops

def call(op,**args):
 args.update(pid=os.getpid(),expected_snapshot=ops.state(bpy)['snapshot'])
 return ops.dispatch(op,args)

def rejects(op,**args):
 try:call(op,**args)
 except (ValueError,RuntimeError):return
 raise AssertionError('Expected rejection '+op)

with tempfile.TemporaryDirectory(prefix='bubble-blender-native-') as temp:
 bpy.ops.wm.read_homefile(use_empty=True)
 call('create',kind='cube',name='OwnedCube');call('create',kind='camera',name='OwnedCamera');call('create',kind='area_light',name='OwnedLight')
 call('edit',action='transform',name='OwnedCube',values={'location':[1,2,3],'scale':[2,2,2]})
 assert list(bpy.data.objects['OwnedCube'].location)==[1,2,3]
 bpy.data.objects['OwnedCube'].lock_location[0]=True;rejects('edit',action='transform',name='OwnedCube',values={'location':[0,0,0]});bpy.data.objects['OwnedCube'].lock_location[0]=False
 bpy.data.objects['OwnedCube'].rotation_mode='QUATERNION';rejects('edit',action='transform',name='OwnedCube',values={'rotation_euler':[1,0,0]});assert bpy.data.objects['OwnedCube'].rotation_mode=='QUATERNION';bpy.data.objects['OwnedCube'].rotation_mode='XYZ'
 rejects('create',kind='cube',name='OwnedCube')
 call('edit',action='duplicate',name='OwnedCube',new_name='OwnedCopy');call('edit',action='rename',name='OwnedCopy',new_name='OwnedRenamed');rejects('edit',action='delete',name='OwnedRenamed');call('edit',action='delete',name='OwnedRenamed',confirm_delete=True)
 call('material',action='create',name='OwnedMat',values={'diffuse_color':[.2,.3,.4,1],'roughness':.4,'metallic':.2});call('material',action='assign',name='OwnedMat',object_name='OwnedCube');assert len(bpy.data.objects['OwnedCube'].data.materials)==1
 call('camera',action='set',name='OwnedCamera',values={'lens':50,'clip_start':.1,'clip_end':500});call('camera',action='activate',name='OwnedCamera');assert bpy.context.scene.camera.name=='OwnedCamera'
 call('light',action='set',name='OwnedLight',values={'energy':500,'color':[1,.5,.25]});assert bpy.data.objects['OwnedLight'].data.energy==500
 rejects('create',kind='cube',name='中'*30)
 rejects('timeline',action='set',values={'frame_start':-1})
 rejects('render_settings',action='set',values={'resolution_x':1})
 call('timeline',action='set',values={'frame_start':1,'frame_end':48,'frame_current':12,'fps':24});assert bpy.context.scene.frame_current==12
 call('render_settings',action='set',values={'resolution_x':512,'resolution_y':512,'resolution_percentage':100});assert bpy.context.scene.render.resolution_x==512
 call('selection',names=['OwnedCube']);assert bpy.context.active_object.name=='OwnedCube'
 call('collection',action='create',name='OwnedGroup')
 call('collection',action='create',name='OwnedChildGroup',parent='OwnedGroup')
 call('collection',action='link',name='OwnedGroup',object_name='OwnedCube')
 call('collection',action='unlink',name='',object_name='OwnedCube')
 rejects('collection',action='unlink',name='OwnedGroup',object_name='OwnedCube')
 call('collection',action='rename',name='OwnedGroup',new_name='RenamedGroup')
 assert any(c['name']=='RenamedGroup' for c in call('collection')['result']['collections'])
 second_scene=bpy.data.scenes.new('OtherScene');second_scene.collection.children.link(bpy.data.collections['RenamedGroup'])
 rejects('collection',action='rename',name='RenamedGroup',new_name='MustNotRename')
 second_scene.collection.children.unlink(bpy.data.collections['RenamedGroup']);bpy.data.scenes.remove(second_scene)
 call('create',kind='empty',name='OwnedParent')
 call('edit',action='transform',name='OwnedParent',values={'location':[4,5,6],'rotation_euler':[.2,.4,.7],'scale':[2,3,4]})
 bpy.context.view_layer.update();before=bpy.data.objects['OwnedCube'].matrix_world.copy()
 call('parent',name='OwnedCube',parent='OwnedParent')
 assert bpy.data.objects['OwnedCube'].parent.name=='OwnedParent'
 assert all(abs(bpy.data.objects['OwnedCube'].matrix_world[r][c]-before[r][c])<1e-4 for r in range(4) for c in range(4))
 rejects('parent',name='OwnedParent',parent='OwnedCube')
 call('parent',name='OwnedCube',parent='');assert bpy.data.objects['OwnedCube'].parent is None
 assert all(abs(bpy.data.objects['OwnedCube'].matrix_world[r][c]-before[r][c])<1e-4 for r in range(4) for c in range(4))
 stale=ops.state(bpy)['snapshot'];call('collection',action='link',name='OwnedChildGroup',object_name='OwnedCube')
 try:ops.dispatch('parent',dict(name='OwnedCube',parent='OwnedParent',pid=os.getpid(),expected_snapshot=stale))
 except ValueError:pass
 else:raise AssertionError('Collection membership changes must invalidate snapshot')
 image=bpy.data.images.new('MissingFixture',1,1);image.source='FILE';image.filepath=str(Path(temp)/'missing.png');rows=call('assets')['result']['assets'];assert any(r['status']=='missing' for r in rows)
 saved=str(Path(temp)/'owned.blend');call('file',action='save',path=saved);assert Path(saved).is_file();rejects('file',action='save',path=saved)
 call('file',action='new',discard_changes=True);assert not bpy.data.objects;call('file',action='open',path=saved,discard_changes=True);assert bpy.data.objects.get('OwnedCube')
 try:ops.dispatch('create',dict(kind='cube',name='Wrong',pid=-1,expected_snapshot=ops.state(bpy)['snapshot']))
 except ValueError:pass
 else:raise AssertionError('wrongPID accepted')
 try:ops.dispatch('create',dict(kind='cube',name='Stale',pid=os.getpid(),expected_snapshot='stale'))
 except ValueError:pass
 else:raise AssertionError('stale accepted')
 print('BUBBLE_NATIVE_PASS '+json.dumps({'version':bpy.app.version_string,'operations':16,'guards':['wrong_pid','stale_snapshot','locked_transform','duplicate_name','delete_confirmation','overwrite','parent_cycle','collection_orphan','shared_collection','membership_snapshot'],'world_matrix_preserved':True,'user_profile_modified':False}))
