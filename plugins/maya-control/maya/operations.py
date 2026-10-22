"""Structured Maya commands. Scene guards are structural, not a full edit history."""
import hashlib
import json
import math
import os
from pathlib import Path

GENERATION = 0


def finite(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('A finite number is required')
    return value


def name(value):
    if not isinstance(value, str) or not value or any(c in value for c in '*?[]'):
        raise ValueError('Use an exact nonempty name, without wildcards')
    return value


def node(cmds, value):
    matches = cmds.ls(name(value), long=True) or []
    if len(matches) != 1:
        raise ValueError('Node is missing or ambiguous; use its full DAG path')
    return matches[0]


def snapshot(cmds):
    nodes = sorted(cmds.ls(uuid=True) or [])
    if len(nodes) > 50000:
        raise ValueError('Scene exceeds the 50000-node structural snapshot limit')
    scene = {'path': cmds.file(q=True, sceneName=True), 'modified': bool(cmds.file(q=True, modified=True))}
    raw = [GENERATION, scene, nodes]
    return {'scene': scene, 'snapshot': hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest(),
            'guard_scope': 'scene path, dirty flag, node identities, bridge scene generation; not every attribute edit',
            'node_count': len(nodes)}


def editable(cmds, value):
    value = node(cmds, value)
    if cmds.referenceQuery(value, isNodeReferenced=True) or any(cmds.lockNode(value, q=True, lock=True) or []):
        raise ValueError('Referenced or locked nodes require an explicit specialist operation')
    return value


def dispatch(op, a):
    global GENERATION
    from maya import cmds
    state = snapshot(cmds)
    if op == 'state':
        state['render'] = {key: cmds.getAttr('defaultRenderGlobals.' + key) for key in ['currentRenderer', 'startFrame', 'endFrame']}
        return state
    reads = op == 'query' or (op in ('attribute', 'timeline', 'connections') and a.get('action', 'get') == 'get')
    if not reads:
        if type(a.get('pid')) is not int or a['pid'] != os.getpid():
            raise ValueError('An explicit current process PID is required for changes')
        if a.get('expected_snapshot') != state['snapshot']:
            raise ValueError('Scene changed; read scene_state again before changing it')
    result = None
    if op == 'file':
        action = a['action']
        if action not in ('new', 'open', 'save'):
            raise ValueError('action must be new, open or save')
        if action in ('new', 'open') and state['scene']['modified'] and a.get('discard_changes') is not True:
            raise ValueError('Scene has unsaved changes; save first or explicitly authorize discard_changes')
        if action != 'new':
            p = Path(a.get('path') or state['scene']['path'])
            if not p.is_absolute() or p.suffix.lower() not in ('.ma', '.mb'):
                raise ValueError('An absolute .ma or .mb path is required')
            if action == 'open' and not p.is_file():
                raise ValueError('Input scene does not exist')
            if action == 'save' and (not p.parent.is_dir() or (p.exists() and a.get('overwrite') is not True)):
                raise ValueError('Parent must exist; existing files require overwrite=true')
        if action == 'new':
            cmds.file(new=True, force=True); GENERATION += 1
        elif action == 'open':
            cmds.file(str(p), open=True, force=True, executeScriptNodes=False, prompt=False); GENERATION += 1
        else:
            cmds.file(rename=str(p)); cmds.file(save=True, type='mayaAscii' if p.suffix.lower() == '.ma' else 'mayaBinary', force=a.get('overwrite') is True)
        result = {'action': action}
    elif op == 'query':
        limit = a.get('limit', 200)
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError('limit must be 1..1000')
        values = cmds.ls(selection=True, long=True) if a.get('selected') else cmds.ls(long=True, **({'type': name(a['node_type'])} if a.get('node_type') else {}))
        values = values or []
        result = {'nodes': [{'path': n, 'type': cmds.nodeType(n), 'uuid': (cmds.ls(n, uuid=True) or [None])[0]} for n in values[:limit]], 'truncated': len(values) > limit}
    elif op == 'create':
        kind = a['kind']; label = name(a['name'])
        if cmds.objExists(label):
            raise ValueError('Name already exists')
        methods = {'cube': cmds.polyCube, 'sphere': cmds.polySphere, 'plane': cmds.polyPlane, 'cylinder': cmds.polyCylinder, 'locator': cmds.spaceLocator}
        if kind in methods:
            result = methods[kind](name=label)[0]
        elif kind in ('transform', 'camera'):
            result = cmds.createNode(kind, name=label)
        else:
            raise ValueError('Supported kinds: cube, sphere, plane, cylinder, locator, transform, camera')
        result = {'node': node(cmds, result)}
    elif op == 'edit':
        n = editable(cmds, a['node']); action = a['action']
        if action == 'rename':
            label = name(a['name'])
            if cmds.objExists(label): raise ValueError('Name already exists')
            result = {'node': node(cmds, cmds.rename(n, label))}
        elif action == 'duplicate':
            label = name(a['name'])
            if cmds.objExists(label): raise ValueError('Name already exists')
            result = {'nodes': cmds.duplicate(n, name=label)}
        elif action == 'delete':
            if a.get('confirm_delete') is not True: raise ValueError('Deletion requires confirm_delete=true')
            cmds.delete(n); result = {'deleted': n}
        elif action == 'transform':
            values = a.get('values') or {}
            if not values or set(values) - {'translation', 'rotation', 'scale'}: raise ValueError('Provide translation, rotation and/or scale')
            for key, v in values.items():
                if not isinstance(v, list) or len(v) != 3: raise ValueError('Transform values require three numbers')
                for x in v: finite(x)
                attr = {'translation':'translate', 'rotation':'rotate', 'scale':'scale'}[key]
                if not cmds.getAttr(n+'.'+attr, settable=True) or cmds.listConnections(n+'.'+attr,source=True,destination=False): raise ValueError('Transform is locked, animated or connected')
            cmds.xform(n, objectSpace=True, **values); result = {'node': n}
        else: raise ValueError('action must be rename, duplicate, delete or transform')
    elif op == 'selection':
        values = [node(cmds, n) for n in a.get('nodes', [])]
        if len(values) > 1000: raise ValueError('Selection limit is 1000')
        if values: cmds.select(values, replace=True)
        else: cmds.select(clear=True)
        result = {'selection': values}
    elif op == 'attribute':
        n = node(cmds, a['node']); attr = name(a['attribute'])
        if '.' in attr: raise ValueError('Provide a direct attribute name')
        plug = n+'.'+attr; value = cmds.getAttr(plug)
        if a.get('action', 'get') == 'set':
            editable(cmds, n)
            if value != a.get('expected_value'): raise ValueError('Attribute value changed; read it again')
            if not cmds.getAttr(plug, settable=True) or cmds.listConnections(plug,source=True,destination=False): raise ValueError('Attribute is locked, animated or connected')
            v = a['value']; typ = cmds.getAttr(plug, type=True)
            if typ == 'string' and isinstance(v, str): cmds.setAttr(plug, v, type='string')
            elif typ in ('double','float','long','short','byte','bool','enum','doubleLinear','doubleAngle'):
                if isinstance(v, bool): v = int(v)
                cmds.setAttr(plug, finite(v))
            else: raise ValueError('Structured attribute writes support scalar numbers and strings only')
            value = cmds.getAttr(plug)
        elif a.get('action', 'get') != 'get': raise ValueError('action must be get or set')
        result = {'value': value, 'type': cmds.getAttr(plug, type=True)}
    elif op == 'connections':
        n = node(cmds, a['node']); action = a.get('action', 'get')
        if action == 'get': result = {'connections': cmds.listConnections(n, connections=True, plugs=True) or []}
        else:
            editable(cmds, n); source = a['source']; target = a['target']
            for plug in (source, target):
                if '.' not in plug or not cmds.objExists(plug): raise ValueError('Exact existing source/target plugs required')
                node(cmds, plug.rsplit('.',1)[0])
            if node(cmds, target.rsplit('.',1)[0]) != n: raise ValueError('Target must belong to selected node')
            if action == 'connect': cmds.connectAttr(source, target, force=False)
            elif action == 'disconnect': cmds.disconnectAttr(source, target)
            else: raise ValueError('action must be get, connect or disconnect')
            result = {'source': source, 'target': target}
    elif op == 'timeline':
        if a.get('action', 'get') == 'set':
            start, end = finite(a['start']), finite(a['end'])
            frame = finite(a['frame'])
            if start > end: raise ValueError('start must not exceed end')
            cmds.playbackOptions(minTime=start, maxTime=end); cmds.currentTime(frame)
        elif a.get('action', 'get') != 'get': raise ValueError('action must be get or set')
        result = {'start': cmds.playbackOptions(q=True,minTime=True), 'end': cmds.playbackOptions(q=True,maxTime=True), 'frame': cmds.currentTime(q=True)}
    else: raise ValueError('Unsupported structured operation')
    return {'result': result, **snapshot(cmds)}
