"""Host integration. Imported only inside interactive 3ds Max, on its main thread."""
import os
import queue
import uuid

_timer = None
_quit_connection = None
_queue = queue.Queue(maxsize=64)
_scene_token = uuid.uuid4().hex


def invalidate_scene():
    global _scene_token
    _scene_token = uuid.uuid4().hex


def structured(operation, a):
    """Explicit node handles and guarded scene lifecycle; runs on main thread."""
    import math
    from pymxs import runtime as rt
    def vector(value):
        if not isinstance(value, list) or len(value) != 3 or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in value):
            raise ValueError('Expected three finite numbers')
        return rt.Point3(*value)
    def row(n):
        return {'id': int(n.handle), 'name': str(n.name), 'class': str(rt.classOf(n)),
                'parent_id': int(n.parent.handle) if n.parent else None,
                'position': [n.position.x,n.position.y,n.position.z], 'scale': [n.scale.x,n.scale.y,n.scale.z],
                'hidden': bool(n.isHidden), 'frozen': bool(n.isFrozen),
                'material': str(n.material.name) if n.material else None}
    if operation == 'list_objects':
        limit = a.get('limit', 1000)
        if type(limit) is not int or not 1 <= limit <= 5000: raise ValueError('limit must be 1..5000')
        nodes = list(rt.objects)
        return {'objects': [row(n) for n in nodes[:limit]], 'truncated': len(nodes) > limit, 'scene': scene_info(), 'scene_token': _scene_token}
    if operation == 'settings':
        return {'width': int(rt.renderWidth), 'height': int(rt.renderHeight), 'renderer': str(rt.classOf(rt.renderers.current)), 'frame_rate': int(rt.frameRate), 'range': str(rt.animationRange)}
    if operation == 'inspect_object':
        if a.get('expected_scene') != _scene_token: raise ValueError('Scene changed; list objects again')
        n = rt.maxOps.getNodeByHandle(a['object_id'])
        if not n: raise ValueError('Node no longer exists')
        data = row(n); data['properties'] = [str(x) for x in rt.getPropNames(n)][:500]
        data['modifiers'] = [str(rt.classOf(x)) for x in n.modifiers]
        return data
    if a.get('expected_scene') != _scene_token: raise ValueError('Scene changed; list objects again')
    action = a.get('action')
    if operation == 'scene_action':
        if action in ('new', 'open') and rt.getSaveRequired(): raise ValueError('Scene has unsaved changes; save it first')
        if action == 'new': rt.resetMaxFile(rt.Name('noPrompt'))
        elif action in ('open', 'save'):
            path = a.get('path') or ''
            if not os.path.isabs(path) or not path.lower().endswith('.max'): raise ValueError('Absolute .max path required')
            if action == 'open':
                if not os.path.isfile(path): raise ValueError('File does not exist')
                if not rt.loadMaxFile(path, quiet=True): raise RuntimeError('Scene open failed')
            else:
                if os.path.exists(path) and not a.get('overwrite'): raise ValueError('Existing file requires overwrite=true')
                if not os.path.isdir(os.path.dirname(path)): raise ValueError('Destination directory must exist')
                if not rt.saveMaxFile(path, quiet=True): raise RuntimeError('Scene save failed')
        else: raise ValueError('Unknown scene action')
        if action in ('new', 'open'): invalidate_scene()
        return {'scene': scene_info(), 'scene_token': _scene_token}
    if operation != 'object_action': raise ValueError('Unknown structured operation')
    if action == 'create':
        kinds = {'box': rt.Box, 'sphere': rt.Sphere, 'plane': rt.Plane, 'cylinder': rt.Cylinder, 'point': rt.Point}
        if a.get('kind') not in kinds: raise ValueError('Unsupported primitive')
        n = kinds[a['kind']]()
        if a.get('name'): n.name = a['name']
        return row(n)
    n = rt.maxOps.getNodeByHandle(a.get('object_id', 0))
    if not n: raise ValueError('Node no longer exists')
    if action == 'select': rt.select(n)
    elif action == 'duplicate': n = rt.copy(n)
    elif action == 'rename':
        if not isinstance(a.get('name'), str) or not a['name'].strip(): raise ValueError('Nonempty name required')
        n.name = a['name']
    elif action == 'delete':
        handle = int(n.handle); rt.delete(n); return {'deleted_id': handle}
    elif action == 'transform':
        if n.isFrozen: raise ValueError('Node is frozen')
        if rt.isAnimated(n): raise ValueError('Animated nodes require explicitly authorized scripting')
        values = {k: vector(a[k]) for k in ('position', 'scale') if a.get(k) is not None}
        if not values: raise ValueError('Specify position or scale')
        for k, v in values.items(): setattr(n, k, v)
    else: raise ValueError('Unknown object action')
    return row(n)


def scene_info():
    from pymxs import runtime as rt
    name = str(rt.maxFileName)
    return {"path": os.path.join(str(rt.maxFilePath), name) if name else "",
            "modified": bool(rt.getSaveRequired()), "max_version": str(rt.maxVersion()),
            "project": str(rt.pathConfig.getCurrentProjectFolder()),
            "selection": [str(node.name) for node in rt.selection],
            "node_count": len(rt.objects), "time": str(rt.sliderTime)}


def inspect_scene():
    from pymxs import runtime as rt
    assets, warnings = [], []
    for texture in rt.getClassInstances(rt.Bitmaptexture):
        try:
            path = str(texture.filename or "")
            resolved = str(rt.mapPaths.getFullFilePath(path) or path)
            assets.append({"kind": "bitmap", "name": str(texture.name), "path": path,
                           "resolved_path": resolved, "exists": bool(path and rt.doesFileExist(resolved))})
        except Exception as exc:
            warnings.append(str(exc))
    for index in range(1, int(rt.xrefs.getXRefFileCount()) + 1):
        try:
            reference = rt.xrefs.getXRefFile(index)
            path = str(reference.filename)
            resolved = str(rt.xrefPaths.getFullFilePath(path) or path)
            assets.append({"kind": "scene_xref", "path": path,
                           "resolved_path": resolved, "exists": bool(path and rt.doesFileExist(resolved))})
        except Exception as exc:
            warnings.append(str(exc))
    return {"scene": scene_info(), "assets": assets,
            "missing_assets": [item for item in assets if not item["exists"]], "warnings": warnings,
            "coverage": "Bitmaptexture maps and scene XRefs only; excludes renderer-specific maps/caches, object XRefs and complete sequence/tile checks."}


def install_dispatcher(stop):
    global _timer, _quit_connection
    try:
        from PySide6 import QtCore, QtWidgets
    except ImportError:
        from PySide2 import QtCore, QtWidgets
    app = QtWidgets.QApplication.instance()
    if app is None or QtCore.QThread.currentThread() != app.thread():
        raise RuntimeError("Start the bridge on the interactive 3ds Max main thread")
    from pymxs import runtime as rt
    try:
        for event in ('systemPostReset', 'systemPostNew', 'filePostOpen'):
            rt.callbacks.addScript(rt.Name(event), invalidate_scene, id=rt.Name('BubbleSceneIdentity'))
    except Exception:
        rt.callbacks.removeScripts(id=rt.Name('BubbleSceneIdentity'))
        raise
    def drain():
        for _ in range(8):
            try:
                callback = _queue.get_nowait()
            except queue.Empty:
                break
            callback()
    _timer = QtCore.QTimer(app)
    _timer.setInterval(20)
    _timer.timeout.connect(drain)
    _timer.start()
    app.aboutToQuit.connect(stop)
    _quit_connection = (app, stop)
    return _queue.put_nowait


def remove_dispatcher():
    global _timer, _quit_connection
    from pymxs import runtime as rt
    rt.callbacks.removeScripts(id=rt.Name('BubbleSceneIdentity'))
    if _quit_connection is not None:
        app, callback = _quit_connection
        _quit_connection = None
        try:
            app.aboutToQuit.disconnect(callback)
        except (RuntimeError, TypeError):
            pass
    if _timer is not None:
        _timer.stop()
        _timer.deleteLater()
        _timer = None
    while not _queue.empty():
        try:
            _queue.get_nowait()
        except queue.Empty:
            break
