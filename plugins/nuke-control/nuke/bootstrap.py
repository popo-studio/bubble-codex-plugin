"""Idempotent GUI startup loader; installed beside bridge.py."""
import importlib.util
from pathlib import Path
import sys

key = "_bubble_nuke_runtime"
module = sys.modules.get(key)
if module is None:
    spec = importlib.util.spec_from_file_location(key, Path(__file__).with_name("bridge.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(key, None)
        raise
module.start()
