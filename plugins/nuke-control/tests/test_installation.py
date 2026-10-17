import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
import stat
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
import installation as install


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="bubble-install-")
        self.addCleanup(self.temp.cleanup)
        self.app = Path(self.temp.name) / "nuke"
        self.startup = self.app / "menu.py"
        self.target = self.startup.parent / "bubble_nuke_runtime"

    def run_install(self, confirmed=True):
        return install.install_bridge(confirmed=confirmed, nuke_app_dir=self.app)

    def run_uninstall(self, confirmed=True):
        return install.uninstall_bridge(confirmed=confirmed, nuke_app_dir=self.app)

    def test_previews_are_read_only_and_environment_is_respected(self):
        with patch.dict(os.environ, {"BUBBLE_NUKE_USER_DIR": str(self.app)}):
            status = install.installation_status()
            preview = install.install_bridge()
            uninstall = install.uninstall_bridge()
        self.assertTrue(status["ok"] and preview["ok"] and uninstall["ok"])
        self.assertEqual(preview["nuke_app_dir"], str(self.app))
        self.assertFalse(self.app.exists())

    def test_non_boolean_consent_is_rejected(self):
        self.assertFalse(self.run_install("false")["ok"])
        self.assertFalse(self.app.exists())

    def test_install_idempotence_uninstall_and_reinstall(self):
        result = self.run_install()
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["restart_required"])
        self.assertTrue((self.target / "bootstrap.py").is_file())
        again = self.run_install()
        self.assertEqual(again["changes"], [])
        self.assertFalse(again["restart_required"])
        # Nuke's generated cache and user-added files must remain untouched.
        extra = self.target / "notes.txt"
        extra.write_text("keep")
        cache = self.target / "__pycache__"
        cache.mkdir()
        (cache / "bridge.cpython-311.pyc").write_bytes(b"generated")
        self.assertTrue(self.run_uninstall()["ok"])
        self.assertFalse(self.startup.exists())
        self.assertEqual(extra.read_text(), "keep")
        self.assertEqual((cache / "bridge.cpython-311.pyc").read_bytes(), b"generated")
        self.assertFalse((self.target / install.MANIFEST).exists())
        self.assertTrue(self.run_install()["ok"])

    def test_startup_preserves_encoding_newlines_and_backup(self):
        for original in [b"# coding: latin-1\r\n# caf\xe9\r\nx = 2", b"\xef\xbb\xbf# UTF8\r\nx = 1\r\n", b"print('hello')\n", b""]:
            with self.subTest(original=original):
                self.startup.parent.mkdir(parents=True, exist_ok=True)
                self.startup.write_bytes(original)
                result = self.run_install()
                self.assertTrue(result["ok"], result)
                self.assertTrue(self.startup.read_bytes().startswith(original))
                self.assertEqual(Path(result["startup_backup"]).read_bytes(), original)
                compile(self.startup.read_bytes(), str(self.startup), "exec")
                self.assertTrue(self.run_uninstall()["ok"])
                self.assertEqual(self.startup.read_bytes(), original)

    def test_user_edits_outside_block_survive_uninstall(self):
        self.run_install()
        with self.startup.open("ab") as handle:
            handle.write(b"\ncustom = 42\n")
        result = self.run_uninstall()
        self.assertTrue(result["ok"], result)
        self.assertEqual(self.startup.read_bytes(), b"\ncustom = 42\n")

    def test_modified_runtime_refuses_update_and_removal(self):
        self.run_install()
        runtime = self.target / "bridge.py"
        runtime.write_text("# local modification")
        before = self.startup.read_bytes()
        self.assertFalse(self.run_install()["ok"])
        self.assertFalse(self.run_uninstall()["ok"])
        self.assertEqual(runtime.read_text(), "# local modification")
        self.assertEqual(self.startup.read_bytes(), before)

    def test_modified_startup_block_refuses(self):
        self.run_install()
        original = self.startup.read_bytes().replace(b"exec(compile", b"eval(compile")
        self.startup.write_bytes(original)
        self.assertFalse(self.run_install()["ok"])
        self.assertFalse(self.run_uninstall()["ok"])
        self.assertEqual(self.startup.read_bytes(), original)

    def test_update_replaces_only_owned_runtime(self):
        self.run_install()
        payload = install._runtime_files()
        payload["bridge.py"] += b"\n# updated runtime\n"
        with patch.object(install, "_runtime_files", return_value=payload):
            preview = self.run_install(False)
            self.assertEqual(preview["action"], "update")
            self.assertTrue(self.run_install()["ok"])
        self.assertEqual((self.target / "bridge.py").read_bytes(), payload["bridge.py"])
        self.assertTrue(self.run_uninstall()["ok"])

    def test_unowned_partial_install_and_invalid_startup_refuse(self):
        self.target.mkdir(parents=True)
        (self.target / "bridge.py").write_text("# existing")
        self.assertFalse(self.run_install()["ok"])
        (self.target / "bridge.py").unlink()
        self.startup.write_text("this is invalid python !")
        self.assertFalse(self.run_install()["ok"])
        self.assertEqual(list(self.target.iterdir()), [])

    def test_malformed_ownership_manifest_returns_conflict(self):
        self.target.mkdir(parents=True)
        for value in ["[]", "null", '{"owner":"bubble-nuke-control","files":[]}']:
            (self.target / install.MANIFEST).write_text(value)
            self.assertEqual(self.run_install()["error"]["code"], "installation_conflict")

    def test_unsupported_version_rejects_without_writes(self):
        self.assertFalse(install.install_bridge("../../outside", True, self.app)["ok"])
        self.assertFalse(self.app.exists())

    def test_io_failure_rolls_back_files_and_startup(self):
        self.startup.parent.mkdir(parents=True)
        self.startup.write_bytes(b"x = 1\n")
        real = install._atomic_write
        def fail_manifest(path, data):
            if path.name == install.MANIFEST:
                raise OSError("simulated write error")
            return real(path, data)
        with patch.object(install, "_atomic_write", side_effect=fail_manifest):
            result = self.run_install()
        self.assertFalse(result["ok"])
        self.assertEqual(self.startup.read_bytes(), b"x = 1\n")
        self.assertFalse((self.target / "bridge.py").exists())

    def test_symlink_target_rejects(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        self.startup.parent.mkdir(parents=True)
        try:
            self.target.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Symlink creation requires developer mode on Windows")
        self.assertFalse(self.run_install()["ok"])
        self.assertEqual(list(outside.iterdir()), [])

    def test_cloud_placeholder_allowed_but_junction_and_unknown_reparse_rejected(self):
        info = types.SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400, st_reparse_tag=0x9000301A)
        with patch("installation.os.path.lexists", return_value=True), patch.object(Path, "lstat", return_value=info):
            self.assertEqual(install._safe_path(self.app), self.app)
            info.st_reparse_tag = 0xA0000003  # IO_REPARSE_TAG_MOUNT_POINT
            with self.assertRaises(ValueError):
                install._safe_path(self.app)
            info.st_reparse_tag = 0x12345678
            with self.assertRaises(ValueError):
                install._safe_path(self.app)


if __name__ == "__main__":
    unittest.main()
