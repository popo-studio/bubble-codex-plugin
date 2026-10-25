"""Owned Blender startup module. Defer bpy data access until initialization ends."""
import importlib.util
from pathlib import Path
import sys

KEY='_bubble_blender_runtime'
_pending=None

def register():
    global _pending
    import bpy
    if _pending is not None and bpy.app.timers.is_registered(_pending):return
    if bpy.app.background:return
    def load():
        if KEY in sys.modules:return None
        path=Path(__file__).resolve().parents[1]/'modules/bubble_blender_runtime/bridge.py'
        spec=importlib.util.spec_from_file_location(KEY,path);module=importlib.util.module_from_spec(spec)
        sys.modules[KEY]=module
        try:spec.loader.exec_module(module);module.start()
        except Exception:
            sys.modules.pop(KEY,None)
            raise
        return None
    _pending=load
    bpy.app.timers.register(load,first_interval=0.5)

def unregister():
    global _pending
    import bpy
    if _pending is not None and bpy.app.timers.is_registered(_pending):bpy.app.timers.unregister(_pending)
    _pending=None
    module=sys.modules.pop(KEY,None)
    if module is not None:module.stop()
