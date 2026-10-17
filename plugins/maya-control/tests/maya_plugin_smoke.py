"""Real native plug-in test. Parent cleans up after child's Maya file locks exit."""
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

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
    from maya import cmds, utils
    try:
        path = str(Path(result["installation_directory"]) / "bubble_maya_plugin.py")
        name = cmds.loadPlugin(path, quiet=True)[0]
        assert cmds.pluginInfo(name, query=True, loaded=True)
        assert cmds.pluginInfo(name, query=True, vendor=True) == "Bubble"
        assert not Path(os.environ["BUBBLE_MAYA_SESSION_DIR"]).exists(), "Batch must not start listener"
        cmds.unloadPlugin(name)
        assert not cmds.pluginInfo(name, query=True, loaded=True)
        # Exercise the real native loader's interactive startup path without
        # opening a GUI. Maya's loader does not supply __file__; MFnPlugin and
        # loadPath remain real. Only the batch guard and idle scheduling are
        # replaced, with callbacks explicitly pumped on this Maya main thread.
        original_about = cmds.about
        deferred, warnings = [], []
        def interactive_about(*args, **kwargs):
            return False if kwargs.get("batch") else original_about(*args, **kwargs)
        before = (cmds.file(query=True, sceneName=True), cmds.file(query=True, modified=True), cmds.ls(selection=True))
        with patch.object(cmds, "about", side_effect=interactive_about), patch.object(utils, "executeDeferred", side_effect=deferred.append), patch.object(cmds, "warning", side_effect=warnings.append):
            name = cmds.loadPlugin(path, quiet=True)[0]
            try:
                assert deferred, "Native initializePlugin did not schedule GUI startup"
                while deferred:
                    deferred.pop(0)()
                assert not warnings, warnings
                session_path = Path(os.environ["BUBBLE_MAYA_SESSION_DIR"]) / (str(os.getpid()) + ".json")
                assert session_path.is_file(), "Native GUI startup did not create the bridge"
                from client import request
                with ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(request, "scene_info", pid=os.getpid(), timeout=5)
                    deadline = time.monotonic() + 8
                    while not future.done() and time.monotonic() < deadline:
                        while deferred:
                            deferred.pop(0)()
                        time.sleep(0.01)
                    response = future.result(timeout=1)
                assert response["ok"], response
                after = (cmds.file(query=True, sceneName=True), cmds.file(query=True, modified=True), cmds.ls(selection=True))
                assert before == after, "Read-only bridge query changed the scene"
            finally:
                cmds.unloadPlugin(name)
            assert not session_path.exists(), "Unload must remove discovery metadata"
        removed = installation.uninstall_bridge(confirmed=True)
        assert removed["ok"], removed
        print(json.dumps({"ok": True, "maya_version": cmds.about(version=True), "checks": ["native plug-in load", "metadata", "batch listener disabled", "native GUI-branch startup without __file__", "main-thread scene query over real TCP", "scene unchanged", "unload removes discovery metadata", "user-level uninstall"]}))
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
