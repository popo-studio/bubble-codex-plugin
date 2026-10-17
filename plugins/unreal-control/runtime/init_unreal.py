"""Owned startup bootstrap. Repeated loading is idempotent; updates require restart."""
import importlib.util
from pathlib import Path
import sys

_key = "bubble_unreal_bridge"
if _key in sys.modules:
    _bubble_module = sys.modules[_key]
else:
    _bubble_spec = importlib.util.spec_from_file_location(_key, Path(__file__).with_name("bubble_unreal_bridge.py"))
    _bubble_module = importlib.util.module_from_spec(_bubble_spec)
    _bubble_spec.loader.exec_module(_bubble_module)
    sys.modules[_key] = _bubble_module
if _bubble_module._host.is_interactive():
    _bubble_module.start()
