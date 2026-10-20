"""Native Maya plug-in. Installed alongside bridge.py; no sys.path changes."""
import importlib.util
from pathlib import Path
import sys

_bridge = None
_bridge_path = None
_active = False
_exit_callback = None


def maya_useNewAPI():
    pass


def _start():
    global _bridge
    if not _active or _bridge is not None:
        return
    from maya import cmds
    try:
        # Hand over a manually started bridge without leaving two listeners alive.
        previous = sys.modules.get("bubble_maya_bridge")
        if previous is not None and getattr(previous, "_bridge", None) is not None:
            previous.stop()
        if _bridge_path is None:
            raise RuntimeError("Maya did not provide the installed bridge location")
        spec = importlib.util.spec_from_file_location("_bubble_maya_installed_bridge", _bridge_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.start()
        _bridge = module
    except Exception as error:
        cmds.warning("Bubble Maya bridge failed to start: %s" % error)


def _stop(*args):
    global _bridge, _active
    _active = False
    if _bridge is not None:
        _bridge.stop()
        _bridge = None


def initializePlugin(plugin):
    global _active, _exit_callback, _bridge_path
    from maya import cmds, utils
    from maya.api import OpenMaya
    plugin_fn = OpenMaya.MFnPlugin(plugin, "Bubble", "0.2.7", "Any")
    # Maya's native Python plug-in loader can execute without defining __file__.
    # Capture its authoritative location while the MObject is available; the
    # deferred callback must not infer a path from the working directory.
    loaded_path = Path(plugin_fn.loadPath())
    if not loaded_path.is_absolute():
        raise RuntimeError("Maya returned a non-absolute plug-in load path")
    if loaded_path.is_file():
        directory = loaded_path.parent
    elif loaded_path.is_dir():
        directory = loaded_path
    else:
        raise RuntimeError("Maya plug-in load path does not exist: %s" % loaded_path)
    _bridge_path = directory / "bridge.py"
    _active = True
    if not cmds.about(batch=True):
        _exit_callback = OpenMaya.MSceneMessage.addCallback(OpenMaya.MSceneMessage.kMayaExiting, _stop)
        utils.executeDeferred(_start)


def uninitializePlugin(plugin):
    global _active, _exit_callback, _bridge_path
    from maya.api import OpenMaya
    _active = False
    _stop()
    _bridge_path = None
    if _exit_callback is not None:
        OpenMaya.MMessage.removeCallback(_exit_callback)
        _exit_callback = None
