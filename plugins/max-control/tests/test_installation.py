import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
import installation


class InstallationTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / ".test-runtime"
        scratch.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.location = self.base / "scripts" / "startup"

    def test_preview_writes_nothing_and_install_uninstall_preserves_unrelated(self):
        before = {str(p.relative_to(self.base)): p.read_bytes() for p in self.base.rglob("*") if p.is_file()}
        preview = installation.install_bridge(str(self.location))
        self.assertTrue(preview["ok"], preview)
        self.assertFalse(preview["applied"])
        self.assertTrue(preview["requires_confirmation"])
        self.assertEqual(before, {str(p.relative_to(self.base)): p.read_bytes() for p in self.base.rglob("*") if p.is_file()})
        result = installation.install_bridge(str(self.location), True)
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["applied"])
        target = Path(result["installation_directory"])
        unrelated = target / "user-file.txt"
        unrelated.write_text("keep")
        self.assertEqual(installation.install_bridge(str(self.location), True)["changes"], [])
        un = installation.uninstall_bridge(str(self.location))
        self.assertFalse(un["applied"])
        self.assertTrue(installation.uninstall_bridge(str(self.location), True)["ok"])
        self.assertEqual(unrelated.read_text(), "keep")
        for relative, data in before.items():
            self.assertEqual((self.base / relative).read_bytes(), data)

    def test_edited_file_blocks_update_and_removal(self):
        result = installation.install_bridge(str(self.location), True)
        path = Path(next(item["path"] for item in result["changes"] if item["path"].endswith("host.py")))
        path.write_text("# user edit")
        for fn in (installation.install_bridge, installation.uninstall_bridge):
            response = fn(str(self.location), True)
            self.assertFalse(response["ok"])
            self.assertEqual(path.read_text(), "# user edit")

    def test_unowned_file_is_never_overwritten(self):
        target, manifest, files, _, _ = installation._layout(str(self.location))
        path = target / next(iter(files))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("existing content")
        self.assertFalse(installation.install_bridge(str(self.location), True)["ok"])
        self.assertEqual(path.read_text(), "existing content")
        self.assertFalse((target / manifest).exists())

    def test_manifest_path_traversal_is_rejected(self):
        result = installation.install_bridge(str(self.location), True)
        target, manifest, files, _, _ = installation._layout(str(self.location))
        state = json.loads((target / manifest).read_text())
        state["files"]["../../user-file"] = "bad"
        (target / manifest).write_text(json.dumps(state))
        self.assertFalse(installation.uninstall_bridge(str(self.location), True)["ok"])

    def test_malformed_files_manifest_returns_conflict_without_writes(self):
        self.assertTrue(installation.install_bridge(str(self.location), True)["ok"])
        target, manifest, files, _, _ = installation._layout(str(self.location))
        manifest_path = target / manifest
        state = json.loads(manifest_path.read_text())
        state["files"] = list(files)
        manifest_path.write_text(json.dumps(state))
        before = {path: path.read_bytes() for path in target.rglob("*") if path.is_file()}
        for response in (installation.installation_status(str(self.location)),
                         installation.install_bridge(str(self.location), True),
                         installation.uninstall_bridge(str(self.location), True)):
            self.assertFalse(response["ok"])
            self.assertEqual(response["error"]["code"], "installation_conflict")
        self.assertEqual(before, {path: path.read_bytes() for path in target.rglob("*") if path.is_file()})

    def test_transaction_rolls_back_after_write_failure(self):
        original = installation._atomic_write
        calls = []
        def fail_second(path, data):
            calls.append(path)
            if len(calls) == 2:
                raise OSError("fixture IO failure")
            return original(path, data)
        with patch.object(installation, "_atomic_write", side_effect=fail_second):
            result = installation.install_bridge(str(self.location), True)
        self.assertFalse(result["ok"])
        self.assertFalse(calls[0].exists())

    def test_non_boolean_confirmation_rejected(self):
        for value in ("true", "false", 1, None):
            self.assertFalse(installation.install_bridge(str(self.location), value)["ok"])

    def test_relative_path_rejected(self):
        self.assertFalse(installation.install_bridge("relative", True)["ok"])

    def test_auto_detection_only_selects_supported_unique_profile(self):
        import os
        base = self.base / "Autodesk" / "3dsMax"
        for version in ("2020 - 64bit", "2025 - 64bit"):
            (base / version / "ENU" / "scripts" / "startup").mkdir(parents=True)
        with patch.dict(os.environ, {"LOCALAPPDATA": str(self.base)}):
            self.assertEqual(len(installation.profile_candidates()), 1)
            self.assertTrue(installation.installation_status()["ok"])
            (base / "2026 - 64bit" / "CHS" / "scripts" / "startup").mkdir(parents=True)
            self.assertFalse(installation.installation_status()["ok"])

    def test_unknown_reparse_ancestor_rejected(self):
        import types
        with patch.object(Path, "lstat", return_value=types.SimpleNamespace(st_mode=0, st_file_attributes=0x400, st_reparse_tag=0xA0000003)):
            self.assertFalse(installation.install_bridge(str(self.location), True)["ok"])


if __name__ == "__main__":
    unittest.main()
