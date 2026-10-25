"""Structured HOM operations; no arbitrary evaluation or automatic rendering."""
import hashlib
import json
import math
import os
import secrets
from pathlib import Path

GENERATION=0
SESSION_NONCE=secrets.token_hex(32)


def new_session():
    global SESSION_NONCE
    SESSION_NONCE=secrets.token_hex(32)


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
    raw=[SESSION_NONCE,GENERATION,scene,sorted((n.path(),n.sessionId()) for n in nodes)]
    return {'scene':scene,'snapshot':hashlib.sha256(json.dumps(raw,sort_keys=True).encode()).hexdigest(),'node_count':len(nodes),'guard_scope':'path, dirty flag, node session identities, bridge session and scene generation; not every parameter edit'}


def dispatch(op,a):
    global GENERATION
    import hou
    state=snapshot(hou)
    reads=op in ('state','query') or (op in ('attribute','timeline','connections','keyframes','network_box') and a.get('action','get')=='get')
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
    elif op=='keyframes':result=keyframes(hou,a)
    elif op=='transfer':result=transfer(hou,a)
    elif op=='network_box':result=network_box(hou,a)
    else: raise ValueError('Unsupported structured operation')
    return {'result':result,**snapshot(hou)}


def keyframes(hou,a):
    n=node(hou,a['node']);p=n.parm(a['attribute'])
    if p is None or p.parmTemplate().type() not in (hou.parmTemplateType.Int,hou.parmTemplateType.Float):raise ValueError('Numeric scalar parameter required')
    if p.getReferencedParm()!=p:raise ValueError('Referenced parameter is protected')
    raw=p.keyframes()
    if len(raw)>2000:raise ValueError('More than 2000 keys')
    keys=[]
    for key in raw:
        try:expression=key.expression()
        except hou.KeyframeValueNotSet:expression=''
        if expression and expression not in ('linear()','bezier()','cubic()','constant()','qlinear()'):raise ValueError('Expression-driven keys require specialist handling')
        if expression and key.expressionLanguage()!=hou.exprLanguage.Hscript:raise ValueError('Python key expressions are protected')
        try:value=key.value()
        except hou.KeyframeValueNotSet:raise ValueError('Key has no numeric value')
        keys.append({'frame':key.frame(),'value':value,'expression':expression})
    revision=hashlib.sha256(json.dumps(keys,sort_keys=True).encode()).hexdigest();action=a.get('action','get')
    if action=='get':return {'keys':keys,'revision':revision}
    if action not in ('set','delete'):raise ValueError('action must be get, set or delete')
    node(hou,a['node'],True)
    if p.isLocked():raise ValueError('Parameter is locked')
    if a.get('expected_keys')!=revision:raise ValueError('Key list changed; read keyframes again')
    frame=finite(a['frame']);exists=any(x['frame']==frame for x in keys)
    if action=='set':
        value=finite(a['value'])
        if exists and a.get('overwrite') is not True:raise ValueError('Existing key requires overwrite=true')
        key=hou.Keyframe();key.setFrame(frame);key.setValue(value);key.setExpression('linear()',hou.exprLanguage.Hscript);p.setKeyframe(key)
    else:
        if a.get('confirm_delete') is not True or not exists:raise ValueError('Deletion requires existing exact frame and confirm_delete=true')
        p.deleteKeyframeAtFrame(frame)
    return keyframes(hou,{**a,'action':'get'})


def transfer(hou,a):
    parent=node(hou,a['parent'],True);action=a['action'];p=Path(a['path'])
    if not parent.isNetwork():raise ValueError('Parent must be an editable network')
    if action not in ('import','export') or not p.is_absolute() or p.suffix.lower()!='.cpio':raise ValueError('Absolute .cpio file and import/export required')
    if action=='import':
        if not p.is_file():raise ValueError('Snippet file does not exist')
        before={n.sessionId() for n in parent.children()};parent.loadItemsFromFile(str(p),ignore_load_warnings=False)
        created=[n.path() for n in parent.children() if n.sessionId() not in before]
        return {'path':str(p),'created_nodes':created[:1000],'truncated':len(created)>1000}
    if not p.parent.is_dir() or (p.exists() and a.get('overwrite') is not True):raise ValueError('Existing parent and explicit overwrite authorization required')
    paths=a.get('nodes')
    if not isinstance(paths,list) or not 1<=len(paths)<=1000:raise ValueError('Choose 1..1000 child nodes')
    selected=[node(hou,x) for x in paths]
    if any(n.parent()!=parent for n in selected):raise ValueError('Every node must be an immediate child of parent')
    parent.saveItemsToFile(tuple(selected),str(p),save_hda_fallbacks=False)
    return {'path':str(p),'exported_nodes':[n.path() for n in selected],'note':'External assets and HDA definitions are not bundled.'}


def network_box(hou,a):
    action=a.get('action','get');parent=node(hou,a['parent'],action!='get')
    if not parent.isNetwork():raise ValueError('Parent must be a network')
    def row(box):return {'name':box.name(),'comment':box.comment(),'nodes':[n.path() for n in box.nodes(recurse=False)]}
    if action=='get':return {'boxes':[row(b) for b in parent.networkBoxes()]}
    if action not in ('create','add','remove'):raise ValueError('action must be get, create, add or remove')
    name=a.get('name','');paths=a.get('nodes');comment=a.get('comment','')
    if not isinstance(name,str) or not name.isidentifier():raise ValueError('Simple network box name required')
    if not isinstance(comment,str) or len(comment)>2000:raise ValueError('Comment limit is 2000 characters')
    if not isinstance(paths,list) or not 1<=len(paths)<=1000:raise ValueError('Choose 1..1000 child nodes')
    selected=[node(hou,x) for x in paths]
    if any(n.parent()!=parent for n in selected):raise ValueError('Every node must be an immediate child of parent')
    box=parent.findNetworkBox(name)
    if action=='create':
        if box is not None:raise ValueError('Network box name already exists')
    elif box is None:raise ValueError('Network box no longer exists')
    # Do not silently move nodes away from another box.
    if action!='remove' and any(n.parentNetworkBox() not in (None,box) for n in selected):raise ValueError('Node belongs to another network box')
    if action=='remove' and any(n not in box.nodes(recurse=False) for n in selected):raise ValueError('Node is not a direct member of this box')
    if action=='create':box=parent.createNetworkBox(name);box.setComment(comment)
    for n in selected:
        if action=='remove':box.removeItem(n)
        else:box.addItem(n)
    box.fitAroundContents()
    return row(box)
