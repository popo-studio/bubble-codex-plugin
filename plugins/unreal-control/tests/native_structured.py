"""Execute ONLY in a new marked disposable UE project using full Editor mode.

Use -ExecutePythonScript, not the PythonScript commandlet: map lifecycle needs
the initialized editor/Slate context. See README for native validation scope.
"""
import importlib.util
import json
import os
from pathlib import Path
import unreal

project=Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
assert (project/'BUBBLE_DISPOSABLE_FIXTURE').is_file(), 'Refuse non-fixture projects'
spec=importlib.util.spec_from_file_location('bubble_host',Path(__file__).resolve().parents[1]/'runtime/host.py')
host=importlib.util.module_from_spec(spec);spec.loader.exec_module(host)
unreal.EditorLoadingAndSavingUtils.new_blank_map(False)
def call(op,**args):return host.structured(op,args)
token=call('list_objects')['scene_token']
actor=call('object_action',action='create',expected_scene=token,kind='point_light',name='Fixture light')
changed=call('object_action',action='transform',expected_scene=token,object_id=actor['id'],position=[10,20,30],scale=[1,1,1])
assert changed['position']==[10,20,30]
assert call('inspect_object',expected_scene=token,object_id=actor['id'])['components']
duplicate=call('object_action',action='duplicate',expected_scene=token,object_id=actor['id'])
assert duplicate['id']!=actor['id']
call('object_action',action='rename',expected_scene=token,object_id=duplicate['id'],name='Fixture duplicate')
call('object_action',action='delete',expected_scene=token,object_id=duplicate['id'])
try:call('scene_action',action='new',expected_scene=token)
except ValueError:pass
else:raise AssertionError('Dirty map discarded')
call('scene_action',action='save',expected_scene=token,path='/Game/BubbleFixture')
token=call('list_objects')['scene_token']
try:call('scene_action',action='save',expected_scene=token,path='/Game/BubbleFixture')
except ValueError:pass
else:raise AssertionError('Existing map overwritten without consent')
new=call('scene_action',action='new',expected_scene=token)
assert new['scene_token']!=token
try:call('object_action',action='rename',expected_scene=token,object_id=actor['id'],name='Wrong world')
except ValueError:pass
else:raise AssertionError('Old world token accepted')
call('scene_action',action='open',expected_scene=new['scene_token'],path='/Game/BubbleFixture')
assert any(x['name']=='Fixture light' for x in call('list_objects')['objects'])
(project/'native-result.json').write_text(json.dumps({'ok':True,'engine':unreal.SystemLibrary.get_engine_version(),'structured_operations':True,'dirty_overwrite_world_guards':True}),encoding='utf-8')
print('BUBBLE_STRUCTURED_NATIVE_PASS')
