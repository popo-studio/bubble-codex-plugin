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
    keys=read('keyframes',node=created,attribute='tx')['result']
    keyed=change('keyframes',action='set',node=created,attribute='tx',expected_keys=keys['revision'],frame=12,value=5)['result']
    assert len(keyed['keys'])==1 and keyed['keys'][0]['value']==5,keyed
    refuse('keyframes',action='set',node=created,attribute='tx',expected_keys=keys['revision'],frame=13,value=9)
    refuse('keyframes',action='set',node=created,attribute='tx',expected_keys=keyed['revision'],frame=12,value=9)
    assert not change('keyframes',action='delete',node=created,attribute='tx',expected_keys=keyed['revision'],frame=12,confirm_delete=True)['result']['keys']
    box=change('network_box',action='create',parent=created,name='bubbleBox',nodes=[first],comment='Fixture')['result']
    assert box['nodes']==[first]
    change('network_box',action='add',parent=created,name='bubbleBox',nodes=[second])
    refuse('network_box',action='create',parent=created,name='anotherBox',nodes=[second])
    change('network_box',action='remove',parent=created,name='bubbleBox',nodes=[second])
    assert read('network_box',parent=created)['result']['boxes'][0]['nodes']==[first]
    snippet=Path(directory)/'snippet.cpio'
    change('transfer',action='export',parent=created,path=str(snippet),nodes=[first])
    refuse('transfer',action='export',parent=created,path=str(snippet),nodes=[first])
    imported=change('transfer',action='import',parent=other,path=str(snippet))['result']
    assert imported['created_nodes'] and hou.node(other+'/source')
    token=read('state')['snapshot'];bridge._operations.new_session();assert read('state')['snapshot']!=token
    change('file',action='save',path=str(p))
    assert p.is_file()
    refuse('file',action='save',path=str(p))
    refuse('edit',action='delete',node=other)
    change('edit',action='delete',node=other,confirm_delete=True)
    change('file',action='open',path=str(p),discard_changes=True)
    assert any(n['path']==other for n in read('query',parent='/obj')['result']['nodes'])
print('BUBBLE_STRUCTURED_NATIVE_OK houdini')
