"""Native Maya plug-in. Installed alongside bridge.py; no sys.path changes."""
import importlib.util
from pathlib import Path
import sys

_bridge = None
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
        path = Path(__file__).with_name("bridge.py")
        spec = importlib.util.spec_from_file_location("_bubble_maya_installed_bridge", path)
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
    global _active, _exit_callback
    from maya import cmds, utils
    from maya.api import OpenMaya
    OpenMaya.MFnPlugin(plugin, "Bubble", "0.2.4", "Any")
    _active = True
    if not cmds.about(batch=True):
        _exit_callback = OpenMaya.MSceneMessage.addCallback(OpenMaya.MSceneMessage.kMayaExiting, _stop)
        utils.executeDeferred(_start)


def uninitializePlugin(plugin):
    global _active, _exit_callback
    from maya.api import OpenMaya
    _active = False
    _stop()
    if _exit_callback is not None:
        OpenMaya.MMessage.removeCallback(_exit_callback)
        _exit_callback = None
