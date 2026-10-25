"""Run only in a NEW isolated host batch process; never against an existing GUI."""
import os
from pathlib import Path
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'nuke'))
import nuke
import bubble_nuke_bridge as bridge

def read(op,**args):return bridge.dispatch('structured_'+op,args)
def change(op,**args):
    return read(op,pid=os.getpid(),expected_snapshot=read('state')['snapshot'],**args)
def refuse(op,**args):
    try:change(op,**args)
    except (ValueError,RuntimeError):return
    raise AssertionError('Unsafe operation was not refused: '+op)

with tempfile.TemporaryDirectory(prefix='bubble-structured-') as directory:
    p=Path(directory)/'scratch.nk'
    change('file',action='new',discard_changes=True)
    created=change('create',kind='Blur',name='bubbleFixture',parent='')['result']['node']
    assert any(n['path']==created for n in read('query',parent='')['result']['nodes'])
    nuke.modified(True)  # Batch Nuke does not automatically mark scripted edits dirty.
    refuse('file',action='new')
    stale=read('state')['snapshot']
    other=change('create',kind='Blur',name='bubbleOther',parent='')['result']['node']
    try:read('selection',nodes=[created],pid=os.getpid(),expected_snapshot=stale)
    except ValueError:pass
    else:raise AssertionError('Stale scene state accepted')
    change('selection',nodes=[created])
    value=read('attribute',node=created,attribute='size')['result']['value']
    change('attribute',action='set',node=created,attribute='size',value=2.5,expected_value=value)
    assert read('attribute',node=created,attribute='size')['result']['value']==2.5
    refuse('attribute',action='set',node=created,attribute='size',value=2.5,expected_value='stale value')
    change('timeline',action='set',start=1,end=48,frame=12)
    assert read('timeline')['result']['frame']==12
    change('connections',action='connect',node=other,index=0,source=created,expected_input=None)
    assert read('connections',node=other)['result']['inputs'][0]['node']==created
    other=change('edit',action='rename',node=other,name='bubbleRenamed')['result']['node']
    change('edit',action='position',node=other,values={'x':20,'y':40})
    keys=read('keyframes',node=created,attribute='size',component=0)['result']
    keyed=change('keyframes',action='set',node=created,attribute='size',component=0,expected_keys=keys['revision'],frame=12,value=5)['result']
    assert keyed['keys']==[{'frame':12.0,'value':5.0}],keyed
    refuse('keyframes',action='set',node=created,attribute='size',expected_keys=keys['revision'],frame=13,value=9)
    refuse('keyframes',action='set',node=created,attribute='size',expected_keys=keyed['revision'],frame=12,value=9)
    assert not change('keyframes',action='delete',node=created,attribute='size',expected_keys=keyed['revision'],frame=12,confirm_delete=True)['result']['keys']
    snippet=Path(directory)/'snippet.nk'
    change('selection',nodes=[other]);selected=[n.fullName() for n in nuke.selectedNodes()]
    change('transfer',action='export',path=str(snippet),nodes=[created])
    assert [n.fullName() for n in nuke.selectedNodes()]==selected
    refuse('transfer',action='export',path=str(snippet),nodes=[created])
    imported=change('transfer',action='import',path=str(snippet))['result'];assert imported['created_nodes']
    assert [n.fullName() for n in nuke.selectedNodes()]==selected
    settings=read('project')['result']
    nuke.root()['format'].setValue(nuke.addFormat('1920 1080 10 20 1800 1000 1 bubbleCropped'))
    settings=read('project')['result']
    preserved=change('project',action='set',expected_settings=settings['revision'],fps=30)['result']
    assert preserved['image_area']==[10,20,1800,1000] and preserved['format_name']=='bubbleCropped',preserved
    settings=read('project')['result']
    configured=change('project',action='set',expected_settings=settings['revision'],width=512,height=512,pixel_aspect=1,fps=25)['result']
    assert (configured['width'],configured['height'],configured['fps'])==(512,512,25),configured
    refuse('project',action='set',expected_settings=settings['revision'],width=10,height=10,pixel_aspect=1,fps=24)
    token=read('state')['snapshot'];bridge._operations.new_session();assert read('state')['snapshot']!=token
    change('file',action='save',path=str(p))
    assert p.is_file()
    refuse('file',action='save',path=str(p))
    refuse('edit',action='delete',node=other)
    change('edit',action='delete',node=other,confirm_delete=True)
    change('file',action='open',path=str(p),discard_changes=True)
    assert any(n['path']==other for n in read('query',parent='')['result']['nodes'])
print('BUBBLE_STRUCTURED_NATIVE_OK nuke')
