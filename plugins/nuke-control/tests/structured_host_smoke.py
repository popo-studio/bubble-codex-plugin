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
    change('file',action='save',path=str(p))
    assert p.is_file()
    refuse('file',action='save',path=str(p))
    refuse('edit',action='delete',node=other)
    change('edit',action='delete',node=other,confirm_delete=True)
    change('file',action='open',path=str(p),discard_changes=True)
    assert any(n['path']==other for n in read('query',parent='')['result']['nodes'])
print('BUBBLE_STRUCTURED_NATIVE_OK nuke')
