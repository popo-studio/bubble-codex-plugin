"""Run only in a NEW isolated host batch process; never against an existing GUI."""
import os
from pathlib import Path
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'maya'))
import maya.standalone
maya.standalone.initialize(name="python")
import bubble_maya_bridge as bridge

def read(op,**args):return bridge.dispatch('structured_'+op,args)
def change(op,**args):
    return read(op,pid=os.getpid(),expected_snapshot=read('state')['snapshot'],**args)
def refuse(op,**args):
    try:change(op,**args)
    except (ValueError,RuntimeError):return
    raise AssertionError('Unsafe operation was not refused: '+op)

with tempfile.TemporaryDirectory(prefix='bubble-structured-') as directory:
    p=Path(directory)/'scratch.ma'
    change('file',action='new',discard_changes=True)
    created=change('create',kind='cube',name='bubbleFixture',parent='')['result']['node']
    assert any(n['path']==created for n in read('query',parent='')['result']['nodes'])
    refuse('file',action='new')
    stale=read('state')['snapshot']
    other=change('create',kind='cube',name='bubbleOther',parent='')['result']['node']
    try:read('selection',nodes=[created],pid=os.getpid(),expected_snapshot=stale)
    except ValueError:pass
    else:raise AssertionError('Stale scene state accepted')
    change('selection',nodes=[created])
    value=read('attribute',node=created,attribute='translateX')['result']['value']
    change('attribute',action='set',node=created,attribute='translateX',value=2.5,expected_value=value)
    assert read('attribute',node=created,attribute='translateX')['result']['value']==2.5
    refuse('attribute',action='set',node=created,attribute='translateX',value=2.5,expected_value='stale value')
    change('timeline',action='set',start=1,end=48,frame=12)
    assert read('timeline')['result']['frame']==12
    change('edit',action='transform',node=created,values={'translation':[1,2,3]})
    change('connections',action='connect',node=other,source=created+'.translateX',target=other+'.translateX')
    assert read('connections',node=other)['result']['connections']
    assert read('attribute',node=other,attribute='translateX')['result']['value']==1
    refuse('attribute',action='set',node=other,attribute='translateX',value=9,expected_value=1)
    change('connections',action='disconnect',node=other,source=created+'.translateX',target=other+'.translateX')
    duplicate=change('edit',action='duplicate',node=other,name='bubbleCopy')['result']
    duplicated=duplicate.get('node') or duplicate['nodes'][0]
    renamed=change('edit',action='rename',node=duplicated,name='bubbleRenamed')['result']['node']
    change('edit',action='delete',node=renamed,confirm_delete=True)
    from maya import cmds
    world=cmds.xform(created,q=True,worldSpace=True,matrix=True)
    created=change('hierarchy',node=created,parent=other)['result']['node']
    assert all(abs(x-y)<1e-6 for x,y in zip(world,cmds.xform(created,q=True,worldSpace=True,matrix=True)))
    refuse('hierarchy',node=other,parent=created)
    created=change('hierarchy',node=created,parent='')['result']['node']
    keys=read('keyframes',node=created,attribute='translateX')['result']
    keyed=change('keyframes',action='set',node=created,attribute='translateX',expected_keys=keys['revision'],frame=12,value=5)['result']
    assert keyed['keys']==[{'frame':12.0,'value':5.0}],keyed
    refuse('keyframes',action='set',node=created,attribute='translateX',expected_keys=keys['revision'],frame=13,value=9)
    refuse('keyframes',action='set',node=created,attribute='translateX',expected_keys=keyed['revision'],frame=12,value=9)
    refuse('hierarchy',node=created,parent=other)
    assert not change('keyframes',action='delete',node=created,attribute='translateX',expected_keys=keyed['revision'],frame=12,confirm_delete=True)['result']['keys']
    snippet=Path(directory)/'snippet.ma'
    change('selection',nodes=[other])
    change('transfer',action='export',path=str(snippet),nodes=[created])
    assert cmds.ls(selection=True,long=True)==[other]
    refuse('transfer',action='export',path=str(snippet),nodes=[created])
    imported=change('transfer',action='import',path=str(snippet),namespace='bubbleImport')['result']
    assert imported['created_nodes'] and cmds.objExists('bubbleImport:bubbleFixture')
    refuse('transfer',action='import',path=str(snippet),namespace='bubbleImport')
    token=read('state')['snapshot'];bridge._operations.new_session();assert read('state')['snapshot']!=token
    change('file',action='save',path=str(p))
    assert p.is_file()
    refuse('file',action='save',path=str(p))
    refuse('edit',action='delete',node=other)
    change('edit',action='delete',node=other,confirm_delete=True)
    change('file',action='open',path=str(p),discard_changes=True)
    assert any(n['path']==other for n in read('query',parent='')['result']['nodes'])
print('BUBBLE_STRUCTURED_NATIVE_OK maya')
maya.standalone.uninitialize()
