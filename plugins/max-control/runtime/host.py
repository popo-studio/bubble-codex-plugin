"""Host integration. Imported only inside interactive 3ds Max, on its main thread."""
import os
import queue

_timer = None
_quit_connection = None
_queue = queue.Queue(maxsize=64)


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
