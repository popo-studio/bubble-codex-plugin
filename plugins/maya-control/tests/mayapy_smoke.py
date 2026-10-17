"""Run only with mayapy, in a fresh standalone process. Creates temporary scenes."""
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "maya"))
import maya.standalone
maya.standalone.initialize(name="python")
from maya import cmds
import bubble_maya_bridge as bridge

try:
    runtime = Path(__file__).resolve().parents[1] / ".test-runtime"
    runtime.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="bubble-maya-smoke-", dir=runtime) as directory:
        root = Path(directory)
        # This is a new standalone process; all scenes/files below are scratch data.
        cmds.file(new=True, force=True)
        cmds.polyCube(name="referenceCube")
        source = str(root / "reference.ma")
        cmds.file(rename=source)
        cmds.file(save=True, type="mayaAscii")
        cmds.file(new=True, force=True)
        cmds.file(source, reference=True, namespace="testReference")
        (root / "albedo.1001.exr").touch()
        texture = cmds.shadingNode("file", asTexture=True, name="udimTexture")
        cmds.setAttr(texture + ".fileTextureName", str(root / "albedo.<UDIM>.exr"), type="string")
        cmds.setAttr(texture + ".uvTilingMode", 3)
        missing = cmds.shadingNode("file", asTexture=True, name="missingTexture")
        cmds.setAttr(missing + ".fileTextureName", str(root / "missing.exr"), type="string")
        selected = cmds.polyCube(name="selectedCube")[0]
        cmds.select(selected)
        scene = str(root / "inspection.ma")
        cmds.file(rename=scene)
        cmds.file(save=True, type="mayaAscii")
        before = bridge.dispatch("scene_info", {})
        report = bridge.dispatch("inspect_scene", {})
        after = bridge.dispatch("scene_info", {})
        assert before["modified"] is False and after["modified"] is False, (before, after)
        assert before["selection"] == after["selection"]
        assert len(report["references"]) == 1 and not report["missing_references"], report
        assert [item["node"] for item in report["missing_textures"]] == [missing], report
        assert any(item["node"] == texture and item["exists"] and item["pattern"] for item in report["textures"]), report
        python = bridge.dispatch("execute_python", {"code": "print('maya smoke'); result = {'maya': cmds.about(version=True), 'value': 42}"})
        assert python["result"]["value"] == 42 and "maya smoke" in python["stdout"], python
        assert bridge.dispatch("execute_mel", {"code": 'size("abcdefg")'})["result"] == 7
        print(json.dumps({"ok": True, "maya_version": cmds.about(version=True), "checks": ["reference paths", "UDIM", "missing textures", "selection preserved", "dirty state preserved", "Python", "MEL"]}))
        cmds.file(new=True, force=True)
finally:
    maya.standalone.uninitialize()
