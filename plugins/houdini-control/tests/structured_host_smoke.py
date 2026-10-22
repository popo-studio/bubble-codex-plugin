"""Run only in a NEW isolated host batch process; never against an existing GUI."""
import os
from pathlib import Path
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'houdini'))
import hou
import bubble_houdini_bridge as bridge

def read(op,**args):return bridge.dispatch('structured_'+op,args)
def change(op,**args):
    return read(op,pid=os.getpid(),expected_snapshot=read('state')['snapshot'],**args)
def refuse(op,**args):
    try:change(op,**args)
    except (ValueError,RuntimeError):return
    raise AssertionError('Unsafe operation was not refused: '+op)

with tempfile.TemporaryDirectory(prefix='bubble-structured-') as directory:
    p=Path(directory)/'scratch.hip'
    change('file',action='new',discard_changes=True)
    created=change('create',kind='geo',name='bubbleFixture',parent='/obj')['result']['node']
    assert any(n['path']==created for n in read('query',parent='/obj')['result']['nodes'])
    refuse('file',action='new')
    stale=read('state')['snapshot']
    other=change('create',kind='geo',name='bubbleOther',parent='/obj')['result']['node']
    try:read('selection',nodes=[created],pid=os.getpid(),expected_snapshot=stale)
    except ValueError:pass
    else:raise AssertionError('Stale scene state accepted')
    change('selection',nodes=[created])
    value=read('attribute',node=created,attribute='tx')['result']['value']
    change('attribute',action='set',node=created,attribute='tx',value=2.5,expected_value=value)
    assert read('attribute',node=created,attribute='tx')['result']['value']==2.5
    refuse('attribute',action='set',node=created,attribute='tx',value=2.5,expected_value='stale value')
    change('timeline',action='set',start=1,end=48,frame=12)
    assert read('timeline')['result']['frame']==12
    change('edit',action='position',node=created,values={'x':1,'y':2})
    first=change('create',kind='null',name='source',parent=created)['result']['node']
    second=change('create',kind='null',name='destination',parent=created)['result']['node']
    change('connections',action='connect',node=second,source=first,index=0,expected_input=None)
    assert read('connections',node=second)['result']['inputs'][0]['node']==first
    change('connections',action='disconnect',node=second,index=0,expected_input=first)
    duplicate=change('edit',action='duplicate',node=other,name='bubbleCopy')['result']
    duplicated=duplicate.get('node') or duplicate['nodes'][0]
    renamed=change('edit',action='rename',node=duplicated,name='bubbleRenamed')['result']['node']
    change('edit',action='delete',node=renamed,confirm_delete=True)
    change('file',action='save',path=str(p))
    assert p.is_file()
    refuse('file',action='save',path=str(p))
    refuse('edit',action='delete',node=other)
    change('edit',action='delete',node=other,confirm_delete=True)
    change('file',action='open',path=str(p),discard_changes=True)
    assert any(n['path']==other for n in read('query',parent='/obj')['result']['nodes'])
print('BUBBLE_STRUCTURED_NATIVE_OK houdini')
