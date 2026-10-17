"""Run inside the host's headless Python with an isolated user profile."""
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nuke"))
import bubble_nuke_bridge as bridge
before = bridge.dispatch("scene_info", {})
assert bridge.dispatch("execute_python", {"code": "result = 6 * 7"})["result"] == 42
report = bridge.dispatch("inspect_scene", {})
assert isinstance(report, dict)
assert bridge.dispatch("scene_info", {}) == before, "Read operations must not alter scene state"
try:
    bridge.start()
except RuntimeError as error:
    assert "interactive" in str(error)
else:
    raise AssertionError("Headless bridge must not listen")
print("BUBBLE_HOST_SMOKE_OK", json.dumps(before))
