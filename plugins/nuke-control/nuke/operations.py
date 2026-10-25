"""Structured Nuke graph operations, with structural scene guards."""
import hashlib
import json
import math
import os
import secrets
from pathlib import Path

GENERATION = 0
SESSION_NONCE = secrets.token_hex(32)


def new_session():
    global SESSION_NONCE
    SESSION_NONCE = secrets.token_hex(32)


def finite(v):
    if type(v) not in (int, float) or not math.isfinite(v): raise ValueError('Finite number required')
    return v


def node(nuke, path):
    if not isinstance(path,str) or not path: raise ValueError('Exact node path required')
    n = nuke.toNode(path)
    if n is None or n.fullName() != path: raise ValueError('Node does not exist at the exact path')
    if n is nuke.root(): raise ValueError('Root is reserved for scene-file and timeline tools')
    return n


def snapshot(nuke):
    nodes = nuke.allNodes(recurseGroups=True)
    if len(nodes)>50000: raise ValueError('Graph exceeds 50000-node snapshot limit')
    root = nuke.root(); path = root.name()
    scene = {'path': '' if path in ('Root','') else path, 'modified': bool(nuke.modified())}
    raw = [SESSION_NONCE,GENERATION,scene,sorted((n.fullName(),n.Class()) for n in nodes)]
    return {'scene':scene,'snapshot':hashlib.sha256(json.dumps(raw,sort_keys=True).encode()).hexdigest(),'node_count':len(nodes),'guard_scope':'path, dirty flag, node names/types and bridge session and scene generation; not every knob edit'}


def dispatch(op,a):
    global GENERATION
    import nuke
    state=snapshot(nuke)
    reads=op in ('state','query') or (op in ('attribute','timeline','connections','keyframes','project') and a.get('action','get')=='get')
    if not reads:
        if type(a.get('pid')) is not int or a['pid']!=os.getpid(): raise ValueError('Explicit current PID required for changes')
        if a.get('expected_snapshot')!=state['snapshot']: raise ValueError('Scene changed; read scene_state again')
    if op=='state':
        state['render_outputs']=[{'node':n.fullName(),'file':n['file'].value() if n.knob('file') else None} for n in nuke.allNodes(recurseGroups=True) if n.Class() in ('Write','DeepWrite')]
        return state
    result=None
    if op=='file':
        action=a['action']
        if action not in ('new','open','save'): raise ValueError('action must be new, open or save')
        if action in ('new','open') and state['scene']['modified'] and a.get('discard_changes') is not True: raise ValueError('Unsaved script: save first or explicitly authorize discard_changes')
        if action!='new':
            p=Path(a.get('path') or state['scene']['path'])
            if not p.is_absolute() or p.suffix.lower()!='.nk': raise ValueError('Absolute .nk path required')
            if action=='open' and not p.is_file(): raise ValueError('Script does not exist')
            if action=='save' and (not p.parent.is_dir() or (p.exists() and a.get('overwrite') is not True)): raise ValueError('Existing parent and overwrite authorization required')
        if action=='new': nuke.scriptClear(); GENERATION+=1
        elif action=='open': nuke.scriptClear(); nuke.scriptOpen(str(p)); GENERATION+=1
        else: nuke.scriptSaveAs(str(p),overwrite=a.get('overwrite') is True)
        result={'action':action}
    elif op=='query':
        limit=a.get('limit',200)
        if type(limit) is not int or not 1<=limit<=1000: raise ValueError('limit must be 1..1000')
        values=nuke.selectedNodes() if a.get('selected') else nuke.allNodes(recurseGroups=True)
        if a.get('node_type'): values=[n for n in values if n.Class()==a['node_type']]
        result={'nodes':[{'path':n.fullName(),'type':n.Class(),'x':n.xpos(),'y':n.ypos(),'knobs':sorted(n.knobs())} for n in values[:limit]],'truncated':len(values)>limit}
    elif op=='create':
        kind=a['kind'];label=a['name']
        if kind not in ('Read','Write','Constant','CheckerBoard2','Blur','Grade','Merge2','Transform','Crop','Reformat','Shuffle2','Dot','BackdropNode'): raise ValueError('Unsupported node kind; use an explicitly authorized script for custom plugins')
        if not isinstance(label,str) or not label.isidentifier() or nuke.toNode(label): raise ValueError('Unique simple node name required')
        with nuke.root(): n=getattr(nuke.nodes,kind)(name=label)
        result={'node':n.fullName()}
    elif op=='edit':
        n=node(nuke,a['node']);action=a['action']
        if action=='rename':
            label=a['name']
            if not isinstance(label,str) or not label.isidentifier() or nuke.toNode(label): raise ValueError('Unique simple node name required')
            n.setName(label);result={'node':n.fullName()}
        elif action=='delete':
            if a.get('confirm_delete') is not True: raise ValueError('Deletion requires confirm_delete=true')
            if n is nuke.root(): raise ValueError('Cannot delete Root')
            nuke.delete(n);result={'deleted':a['node']}
        elif action=='position':
            values=a['values']
            if set(values)!={'x','y'} or any(type(v) is not int for v in values.values()): raise ValueError('Integer x/y required')
            n.setXYpos(values['x'],values['y']);result={'node':n.fullName()}
        else: raise ValueError('action must be rename, delete or position')
    elif op=='selection':
        paths=a.get('nodes',[])
        if len(paths)>1000: raise ValueError('Selection limit is 1000')
        selected=[node(nuke,p) for p in paths]
        for n in nuke.allNodes(recurseGroups=True):
            if n.knob('selected'): n['selected'].setValue(n in selected)
        result={'selection':[n.fullName() for n in selected]}
    elif op=='attribute':
        n=node(nuke,a['node']);k=n.knob(a['attribute'])
        if k is None: raise ValueError('Knob not found')
        # Script/button knobs are not executable through structured reads or writes.
        if k.Class() not in ('Double_Knob','Int_Knob','Boolean_Knob','String_Knob','File_Knob','Enumeration_Knob','XY_Knob','WH_Knob','XYZ_Knob','Color_Knob','AColor_Knob'): raise ValueError('Unsupported knob class; no script/button execution')
        value=k.value()
        if a.get('action','get')=='set':
            if value!=a.get('expected_value'): raise ValueError('Knob value changed; read it again')
            if k.isAnimated() or k.hasExpression(): raise ValueError('Animated/expression knobs require explicit scripting')
            v=a['value']
            if isinstance(v,list):
                if len(v)>4: raise ValueError('Vector limit is 4')
                for x in v: finite(x)
            elif type(v) in (int,float): finite(v)
            elif not isinstance(v,(str,bool)): raise ValueError('Scalar/vector value required')
            if isinstance(v,str) and ('[' in v or ']' in v): raise ValueError('Expression syntax is not allowed in structured strings')
            k.setValue(v);value=k.value()
        elif a.get('action','get')!='get': raise ValueError('action must be get or set')
        result={'value':value,'type':k.Class()}
    elif op=='connections':
        n=node(nuke,a['node']);action=a.get('action','get')
        if action=='get': result={'inputs':[{'index':i,'node':n.input(i).fullName() if n.input(i) else None} for i in range(n.inputs())]}
        else:
            index=a.get('index')
            if type(index) is not int or not 0<=index<n.maxInputs(): raise ValueError('Input index is out of range')
            current=n.input(index);current=current.fullName() if current else None
            if current!=a.get('expected_input'): raise ValueError('Input changed; read connections again')
            source=node(nuke,a['source']) if action=='connect' else None
            if action not in ('connect','disconnect'): raise ValueError('action must be get, connect or disconnect')
            if source is n: raise ValueError('Cannot connect node to itself')
            if not n.setInput(index,source): raise ValueError('Connection rejected')
            result={'node':n.fullName(),'index':index}
    elif op=='timeline':
        r=nuke.root()
        if a.get('action','get')=='set':
            start,end,frame=[finite(a[k]) for k in ('start','end','frame')]
            if start>end: raise ValueError('start must not exceed end')
            r['first_frame'].setValue(start);r['last_frame'].setValue(end);nuke.frame(frame)
        elif a.get('action','get')!='get': raise ValueError('action must be get or set')
        result={'start':r['first_frame'].value(),'end':r['last_frame'].value(),'frame':nuke.frame(),'fps':r['fps'].value()}
    elif op=='keyframes': result=keyframes(nuke,a)
    elif op=='transfer': result=transfer(nuke,a)
    elif op=='project': result=project(nuke,a)
    else: raise ValueError('Unsupported structured operation')
    return {'result':result,**snapshot(nuke)}


def keyframes(nuke,a):
    k=node(nuke,a['node']).knob(a['attribute']);index=a.get('component',0)
    if k is None or k.Class() not in ('Double_Knob','Int_Knob','XY_Knob','WH_Knob','XYZ_Knob','Color_Knob','AColor_Knob'):
        raise ValueError('Numeric knob required')
    if nuke.views()!=['main']: raise ValueError('Multi-view animation requires specialist handling')
    if type(index) is not int or not 0<=index<k.arraySize(): raise ValueError('Component index out of range')
    if k.hasExpression(index): raise ValueError('Expression-driven animation is protected')
    curve=k.animation(index)
    keys=[{'frame':x.x,'value':x.y} for x in curve.keys()] if curve else []
    if len(keys)>2000: raise ValueError('More than 2000 keys')
    revision=hashlib.sha256(json.dumps(keys,sort_keys=True).encode()).hexdigest()
    action=a.get('action','get')
    if action=='get': return {'keys':keys,'revision':revision,'component':index}
    if action not in ('set','delete'): raise ValueError('action must be get, set or delete')
    if not k.enabled(): raise ValueError('Knob is disabled')
    if a.get('expected_keys')!=revision: raise ValueError('Key list changed; read keyframes again')
    frame=finite(a['frame']);exists=any(x['frame']==frame for x in keys)
    if action=='set':
        value=finite(a['value'])
        if exists and a.get('overwrite') is not True: raise ValueError('Existing key requires overwrite=true')
        k.setAnimated(index);k.setValueAt(value,frame,index)
    else:
        if a.get('confirm_delete') is not True or not exists: raise ValueError('Deletion requires existing exact frame and confirm_delete=true')
        k.removeKeyAt(frame,index)
    return keyframes(nuke,{**a,'action':'get'})


def transfer(nuke,a):
    action=a['action'];p=Path(a['path'])
    if action not in ('import','export') or not p.is_absolute() or p.suffix.lower()!='.nk': raise ValueError('Absolute .nk file and import/export required')
    if action=='import':
        if not p.is_file(): raise ValueError('Snippet file does not exist')
    else:
        if not p.parent.is_dir() or (p.exists() and a.get('overwrite') is not True): raise ValueError('Existing parent and overwrite authorization required')
        if nuke.root().name() not in ('','Root') and Path(nuke.root().name()).resolve()==p.resolve(): raise ValueError('Cannot export over the current script')
        paths=a.get('nodes')
        if not isinstance(paths,list) or not 1<=len(paths)<=1000: raise ValueError('Choose 1..1000 exact root-level nodes')
        targets=[node(nuke,x) for x in paths]
        if any('.' in n.fullName() for n in targets): raise ValueError('Select root-level nodes or whole Groups')
    all_before=nuke.allNodes(recurseGroups=True);selected=[n.fullName() for n in all_before if n.knob('selected') and n['selected'].value()]
    try:
        for n in all_before:
            if n.knob('selected'): n['selected'].setValue(False)
        with nuke.root():
            if action=='export':
                for n in targets:n['selected'].setValue(True)
                nuke.nodeCopy(str(p))
                return {'path':str(p),'exported_nodes':[n.fullName() for n in targets]}
            names={n.fullName() for n in all_before};nuke.nodePaste(str(p))
            created=[n.fullName() for n in nuke.allNodes(recurseGroups=True) if n.fullName() not in names]
            return {'path':str(p),'created_nodes':created[:1000],'truncated':len(created)>1000}
    finally:
        for n in nuke.allNodes(recurseGroups=True):
            if n.knob('selected'): n['selected'].setValue(n.fullName() in selected)


def project(nuke,a):
    r=nuke.root();f=r.format()
    data={'width':f.width(),'height':f.height(),'pixel_aspect':f.pixelAspect(),'fps':r['fps'].value(),'image_area':[f.x(),f.y(),f.r(),f.t()],'format_name':f.name()}
    revision=hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
    action=a.get('action','get')
    if action=='get':return {**data,'revision':revision}
    if action!='set':raise ValueError('action must be get or set')
    if a.get('expected_settings')!=revision:raise ValueError('Project settings changed; read again')
    values={k:data[k] if a.get(k) is None else a[k] for k in ('width','height','pixel_aspect','fps')}
    width=values['width'];height=values['height'];aspect=finite(values['pixel_aspect']);fps=finite(values['fps'])
    if any(type(x) is not int or not 1<=x<=32768 for x in (width,height)) or not 0.01<=aspect<=100 or not 0.001<=fps<=1000: raise ValueError('Invalid resolution, pixel aspect or FPS')
    if any(values[k]!=data[k] for k in ('width','height','pixel_aspect')):
        # An FPS-only change must not replace a format with a custom image area.
        area=data['image_area'] if (width,height)==(data['width'],data['height']) else [0,0,width,height]
        label='Bubble_{}_{}_{}'.format(width,height,str(aspect).replace('.','_'))
        fmt=nuke.addFormat('{} {} {} {} {} {} {} {}'.format(width,height,*area,aspect,label))
        r['format'].setValue(fmt)
    if fps!=data['fps']:r['fps'].setValue(fps)
    return project(nuke,{'action':'get'})
