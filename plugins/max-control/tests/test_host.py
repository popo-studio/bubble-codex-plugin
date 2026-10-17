import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
import bubble_max_bridge as bridge


class HostTests(unittest.TestCase):
    def runtime(self):
        return types.SimpleNamespace(
            maxFileName="hero.max", maxFilePath="D:/scene/", getSaveRequired=lambda: True,
            maxVersion=lambda: (27000, 0), pathConfig=types.SimpleNamespace(getCurrentProjectFolder=lambda: "D:/project"),
            selection=[types.SimpleNamespace(name="selected")], objects=[1, 2], sliderTime=10,
            Bitmaptexture=object(), getClassInstances=lambda cls: [types.SimpleNamespace(filename="texture.exr", name="bitmap")],
            mapPaths=types.SimpleNamespace(getFullFilePath=lambda path: "D:/maps/" + path),
            xrefPaths=types.SimpleNamespace(getFullFilePath=lambda path: "D:/refs/" + path),
            doesFileExist=lambda path: path == "D:/maps/texture.exr",
            xrefs=types.SimpleNamespace(getXRefFileCount=lambda: 1, getXRefFile=lambda index: types.SimpleNamespace(filename="missing.max")),
            execute=lambda code: 7)

    def test_missing_xref_and_resolved_bitmap_do_not_change_selection_or_dirty_state(self):
        rt = self.runtime()
        with patch.dict(sys.modules, {"pymxs": types.SimpleNamespace(runtime=rt)}):
            before = bridge._host.scene_info()
            report = bridge._host.inspect_scene()
            self.assertEqual([item["kind"] for item in report["missing_assets"]], ["scene_xref"])
            self.assertEqual(report["assets"][0]["resolved_path"], "D:/maps/texture.exr")
            self.assertEqual(bridge._host.scene_info(), before)

    def test_python_result_and_error_and_maxscript(self):
        with patch.dict(sys.modules, {"pymxs": types.SimpleNamespace(runtime=self.runtime())}):
            reply = bridge.dispatch("execute_python", {"code": "print('hello'); result = rt.maxFileName"})
            self.assertEqual(reply["result"], "hero.max")
            self.assertEqual(reply["stdout"], "hello\n")
            self.assertEqual(bridge.dispatch("execute_maxscript", {"code": "1+6"})["result"], 7)
            reply = bridge.dispatch("execute_python", {"code": "raise RuntimeError('oops')"})
            self.assertFalse(reply["ok"])
            self.assertIn("RuntimeError: oops", reply["error"]["traceback"])

    def test_untitled_scene_has_no_file_identity(self):
        rt = self.runtime()
        rt.maxFileName = ""
        with patch.dict(sys.modules, {"pymxs": types.SimpleNamespace(runtime=rt)}):
            self.assertEqual(bridge._host.scene_info()["path"], "")
