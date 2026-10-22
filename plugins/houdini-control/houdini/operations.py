"""Structured HOM operations; no arbitrary evaluation or automatic rendering."""
import hashlib
import json
import math
import os
from pathlib import Path

GENERATION=0


def finite(v):
    if type(v) not in (int,float) or not math.isfinite(v): raise ValueError('Finite number required')
    return v


def node(hou,path,write=False):
    if not isinstance(path,str) or not path.startswith('/'): raise ValueError('Absolute node path required')
    n=hou.node(path)
    if n is None: raise ValueError('Node no longer exists')
    if write and (not n.isEditable() or n.isInsideLockedHDA()): raise ValueError('Locked assets cannot be changed')
    return n


def snapshot(hou):
    nodes=hou.node('/').allSubChildren()
    if len(nodes)>50000: raise ValueError('Scene exceeds 50000-node snapshot limit')
    scene={'path':'' if hou.hipFile.isNewFile() else hou.hipFile.path(),'modified':bool(hou.hipFile.hasUnsavedChanges())}
    raw=[GENERATION,scene,sorted((n.path(),n.sessionId()) for n in nodes)]
    return {'scene':scene,'snapshot':hashlib.sha256(json.dumps(raw,sort_keys=True).encode()).hexdigest(),'node_count':len(nodes),'guard_scope':'path, dirty flag, node session identities, bridge scene generation; not every parameter edit'}


def dispatch(op,a):
    global GENERATION
    import hou
    state=snapshot(hou)
    reads=op in ('state','query') or (op in ('attribute','timeline','connections') and a.get('action','get')=='get')
    if not reads:
        if type(a.get('pid')) is not int or a['pid']!=os.getpid(): raise ValueError('Explicit current PID required for changes')
        if a.get('expected_snapshot')!=state['snapshot']: raise ValueError('Scene changed; read scene_state again')
    if op=='state':
        state['render_nodes']=[{'path':n.path(),'type':n.type().name()} for n in hou.node('/out').children()] if hou.node('/out') else []
        return state
    result=None
    if op=='file':
        action=a['action']
        if action not in ('new','open','save'): raise ValueError('action must be new, open or save')
        if action in ('new','open') and state['scene']['modified'] and a.get('discard_changes') is not True: raise ValueError('Unsaved scene: save first or explicitly authorize discard_changes')
        if action!='new':
            p=Path(a.get('path') or state['scene']['path'])
            if not p.is_absolute() or p.suffix.lower() not in ('.hip','.hiplc','.hipnc'): raise ValueError('Absolute Houdini scene path required')
            if action=='open' and not p.is_file(): raise ValueError('Scene does not exist')
            if action=='save' and (not p.parent.is_dir() or (p.exists() and a.get('overwrite') is not True)): raise ValueError('Existing parent and overwrite authorization required')
        if action=='new': hou.hipFile.clear(suppress_save_prompt=True);GENERATION+=1
        elif action=='open': hou.hipFile.load(str(p),suppress_save_prompt=True,ignore_load_warnings=False);GENERATION+=1
        else: hou.hipFile.save(str(p),save_to_recent_files=False)
        result={'action':action}
    elif op=='query':
        limit=a.get('limit',200)
        if type(limit) is not int or not 1<=limit<=1000: raise ValueError('limit must be 1..1000')
        values=hou.selectedNodes() if a.get('selected') else node(hou,a.get('parent') or '/obj').children()
        if a.get('node_type'): values=[n for n in values if n.type().name()==a['node_type']]
        result={'nodes':[{'path':n.path(),'type':n.type().name(),'session_id':n.sessionId(),'parameters':[p.name() for p in n.parms()][:200],'position':list(n.position())} for n in values[:limit]],'truncated':len(values)>limit}
    elif op=='create':
        parent=node(hou,a.get('parent') or '/obj',True);label=a['name'];kind=a['kind']
        if not isinstance(label,str) or not label.isidentifier() or parent.node(label): raise ValueError('Unique simple node name required')
        # Node types are data, not Python source. Custom assets may run their own creation callbacks.
        if not isinstance(kind,str) or not kind or any(c in kind for c in '\n\r/'): raise ValueError('Exact node type required')
        result={'node':parent.createNode(kind,node_name=label,run_init_scripts=False).path()}
    elif op=='edit':
        n=node(hou,a['node'],True);action=a['action']
        if action in ('rename','duplicate'):
            label=a['name']
            if not isinstance(label,str) or not label.isidentifier() or n.parent().node(label): raise ValueError('Unique simple name required')
            if action=='duplicate': n=hou.copyNodesTo((n,),n.parent())[0]
            n.setName(label,unique_name=False);result={'node':n.path()}
        elif action=='delete':
            if a.get('confirm_delete') is not True: raise ValueError('Deletion requires confirm_delete=true')
            if n.path().count('/')<2: raise ValueError('Cannot delete top-level networks')
            n.destroy();result={'deleted':a['node']}
        elif action=='position':
            values=a['values']
            if set(values)!={'x','y'}: raise ValueError('x/y required')
            n.setPosition(hou.Vector2(finite(values['x']),finite(values['y'])));result={'node':n.path()}
        elif action=='flags':
            values=a['values']
            if not values or set(values)-{'bypass','display','render'} or any(type(v) is not bool for v in values.values()): raise ValueError('Boolean bypass/display/render flags required')
            methods={'bypass':'bypass','display':'setDisplayFlag','render':'setRenderFlag'}
            if any(not hasattr(n,methods[k]) for k in values): raise ValueError('Node does not support these flags')
            for k,v in values.items(): getattr(n,methods[k])(v)
            result={'node':n.path()}
        else: raise ValueError('action must be rename, duplicate, delete, position or flags')
    elif op=='selection':
        paths=a.get('nodes',[])
        if len(paths)>1000: raise ValueError('Selection limit is 1000')
        values=[node(hou,p) for p in paths]
        for n in hou.selectedNodes(): n.setSelected(False)
        for n in values: n.setSelected(True)
        result={'selection':[n.path() for n in values]}
    elif op=='attribute':
        n=node(hou,a['node']);p=n.parm(a['attribute'])
        if p is None: raise ValueError('Scalar parameter not found; use component name such as tx')
        if p.parmTemplate().type() not in (hou.parmTemplateType.Int,hou.parmTemplateType.Float,hou.parmTemplateType.String,hou.parmTemplateType.Toggle,hou.parmTemplateType.Menu): raise ValueError('Unsupported parameter type; buttons are never executed')
        value=p.eval()
        if a.get('action','get')=='set':
            node(hou,a['node'],True)
            if value!=a.get('expected_value'): raise ValueError('Parameter changed; read it again')
            if p.isLocked() or p.keyframes() or p.getReferencedParm()!=p: raise ValueError('Locked, animated or referenced parameters require explicit scripting')
            v=a['value']
            if type(v) in (int,float): finite(v)
            elif not isinstance(v,(str,bool)): raise ValueError('Scalar value required')
            if isinstance(v,str) and '`' in v: raise ValueError('Backtick evaluation is not allowed in structured strings')
            p.set(v,follow_parm_reference=False);value=p.eval()
        elif a.get('action','get')!='get': raise ValueError('action must be get or set')
        result={'value':value,'type':str(p.parmTemplate().type())}
    elif op=='connections':
        n=node(hou,a['node']);action=a.get('action','get')
        if action=='get': result={'inputs':[{'index':i,'node':x.path() if x else None} for i,x in enumerate(n.inputs())]}
        else:
            node(hou,a['node'],True);index=a.get('index')
            if type(index) is not int or not 0<=index<=1023: raise ValueError('Input index must be 0..1023')
            inputs=n.inputs();current=inputs[index].path() if index<len(inputs) and inputs[index] else None
            if current!=a.get('expected_input'): raise ValueError('Input changed; read connections again')
            source=node(hou,a['source']) if action=='connect' else None
            if action not in ('connect','disconnect'): raise ValueError('action must be get, connect or disconnect')
            if source is n: raise ValueError('Cannot connect node to itself')
            n.setInput(index,source);result={'node':n.path(),'index':index}
    elif op=='timeline':
        if a.get('action','get')=='set':
            start,end,frame=[finite(a[k]) for k in ('start','end','frame')]
            if start>end: raise ValueError('start must not exceed end')
            hou.playbar.setFrameRange(start,end);hou.playbar.setPlaybackRange(start,end);hou.setFrame(frame)
        elif a.get('action','get')!='get': raise ValueError('action must be get or set')
        result={'start':hou.playbar.frameRange()[0],'end':hou.playbar.frameRange()[1],'frame':hou.frame(),'fps':hou.fps()}
    else: raise ValueError('Unsupported structured operation')
    return {'result':result,**snapshot(hou)}
