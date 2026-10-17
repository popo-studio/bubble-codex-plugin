"""Run via UE5.5 PythonScript commandlet in an isolated disposable project.

Environment BUBBLE_UNREAL_NATIVE_RESULT selects a scratch JSON result path.
This verifies native API availability, project plugin autoload and batch opt-out;
interactive UI dispatch still requires acceptance in Unreal Editor.
"""
import importlib.util
import json
import os
from pathlib import Path
import sys

import unreal

root = Path(__file__).resolve().parents[1]
runtime = root / "runtime" / "bubble_unreal_bridge.py"
spec = importlib.util.spec_from_file_location("bubble_unreal_native_test", runtime)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)
assert hasattr(unreal.UnrealEditorSubsystem, "get_editor_world")
assert hasattr(unreal.EditorActorSubsystem, "get_selected_level_actors")
assert hasattr(unreal.EditorLoadingAndSavingUtils, "get_dirty_map_packages")
assert hasattr(unreal.Paths, "get_project_file_path")
assert hasattr(unreal.AssetRegistry, "get_dependencies")
assert hasattr(unreal, "register_slate_post_tick_callback")
assert hasattr(unreal.LevelEditorSubsystem, "is_in_play_in_editor")
assert not bridge._host.is_interactive()
assert bridge.dispatch("execute_python", {"code": "result = 6 * 7"})["result"] == 42
try:
    bridge.start()
except RuntimeError:
    pass
else:
    raise AssertionError("Commandlet must not open a listener")
assert "bubble_unreal_bridge" in sys.modules, "Project init_unreal.py did not auto-load"
assert sys.modules["bubble_unreal_bridge"]._bridge is None
scene_before = bridge._host.scene_info()
report = bridge._host.inspect_scene("/Engine/EngineMaterials/DefaultMaterial")
assert bridge._host.scene_info() == scene_before, "Read-only queries changed scene state"
result = {"ok": True, "engine": unreal.SystemLibrary.get_engine_version(),
          "native_api_available": True, "project_plugin_autoloaded": True,
          "commandlet_listener_disabled": True, "python_result": 42,
          "scene_query": True, "registry_inspection": True,
          "registry_complete": report.get("complete")}
Path(os.environ["BUBBLE_UNREAL_NATIVE_RESULT"]).write_text(json.dumps(result, indent=2), encoding="utf-8")
print("BUBBLE_NATIVE_SMOKE_OK", json.dumps(result))
