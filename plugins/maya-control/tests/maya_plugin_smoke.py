"""Real native plug-in test. Parent cleans up after child's Maya file locks exit."""
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
import installation

def child(temporary):
    os.environ["MAYA_APP_DIR"] = str(Path(temporary) / "maya")
    os.environ["BUBBLE_MAYA_SESSION_DIR"] = str(Path(temporary) / "sessions")
    result = installation.install_bridge(confirmed=True)
    assert result["ok"], result
    import maya.standalone
    maya.standalone.initialize(name="python")
    from maya import cmds
    try:
        path = str(Path(result["installation_directory"]) / "bubble_maya_plugin.py")
        name = cmds.loadPlugin(path, quiet=True)[0]
        assert cmds.pluginInfo(name, query=True, loaded=True)
        assert cmds.pluginInfo(name, query=True, vendor=True) == "Bubble"
        assert not Path(os.environ["BUBBLE_MAYA_SESSION_DIR"]).exists(), "Batch must not start listener"
        cmds.unloadPlugin(name)
        assert not cmds.pluginInfo(name, query=True, loaded=True)
        removed = installation.uninstall_bridge(confirmed=True)
        assert removed["ok"], removed
        print(json.dumps({"ok": True, "maya_version": cmds.about(version=True), "checks": ["native plug-in load", "metadata", "batch listener disabled", "unload", "user-level uninstall"]}))
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--profile":
        child(sys.argv[2])
    else:
        runtime = ROOT / ".test-runtime"
        runtime.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="bubble-native-smoke-", dir=runtime) as profile:
            result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--profile", profile], timeout=120)
            if result.returncode:
                raise SystemExit(result.returncode)
