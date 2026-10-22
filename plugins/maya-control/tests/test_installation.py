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
        self.app = Path(self.temp.name) / "maya"
        self.startup = self.app / "2027" / "scripts" / "userSetup.py"
        self.target = self.startup.parent / "bubble_maya_runtime"

    def run_install(self, confirmed=True):
        return install.install_bridge(confirmed=confirmed, maya_app_dir=self.app)

    def run_uninstall(self, confirmed=True):
        return install.uninstall_bridge(confirmed=confirmed, maya_app_dir=self.app)

    def test_previews_are_read_only_and_environment_is_respected(self):
        with patch.dict(os.environ, {"MAYA_APP_DIR": str(self.app)}):
            status = install.installation_status()
            preview = install.install_bridge()
            uninstall = install.uninstall_bridge()
        self.assertTrue(status["ok"] and preview["ok"] and uninstall["ok"])
        self.assertEqual(preview["maya_app_dir"], str(self.app))
        self.assertFalse(self.app.exists())

    def test_legacy_payload_upgrade_adds_owned_operations(self):
        legacy={k:v for k,v in install._runtime_files().items() if k!='operations.py'}
        with patch.object(install,'_runtime_files',return_value=legacy), patch.object(install,'VERSION','legacy'):
            self.assertTrue(self.run_install()['ok'])
        self.assertFalse((self.target/'operations.py').exists())
        self.assertTrue(self.run_install()['ok'])
        self.assertTrue((self.target/'operations.py').is_file())
        self.assertTrue(self.run_uninstall()['ok'])
        self.assertFalse((self.target/'operations.py').exists())

    def test_legacy_upgrade_preserves_unowned_operations_file(self):
        legacy={k:v for k,v in install._runtime_files().items() if k!='operations.py'}
        with patch.object(install,'_runtime_files',return_value=legacy):
            self.assertTrue(self.run_install()['ok'])
        extra=self.target/'operations.py';extra.write_text('unrelated')
        self.assertFalse(self.run_install()['ok'])
        self.assertTrue(self.run_uninstall()['ok'])
        self.assertEqual(extra.read_text(encoding='utf-8'),'unrelated')

    def test_install_idempotence_uninstall_and_reinstall(self):
        result = self.run_install()
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["restart_required"])
        self.assertTrue((self.target / "bubble_maya_plugin.py").is_file())
        again = self.run_install()
        self.assertEqual(again["changes"], [])
        self.assertFalse(again["restart_required"])
        # Maya's generated cache and user-added files must remain untouched.
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
        original = self.startup.read_bytes().replace(b"quiet=True", b"quiet=False")
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
        for value in ["[]", "null", '{"owner":"bubble-maya-control","files":[]}']:
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


class LifecycleTests(unittest.TestCase):
    def test_native_namespace_without_file_starts_from_host_load_path(self):
        source = ROOT / "maya" / "bubble_maya_plugin.py"
        with tempfile.TemporaryDirectory(prefix="bubble native 路径 ") as temporary:
            directory = Path(temporary)
            native_path = directory / "bubble_maya_plugin.py"
            native_path.write_bytes(source.read_bytes())
            (directory / "bridge.py").write_text(
                "started = False\nstopped = False\n"
                "def start():\n    global started\n    started = True\n"
                "def stop():\n    global stopped\n    stopped = True\n", encoding="utf-8")
            for reported_path in (native_path, directory):
                with self.subTest(load_path=str(reported_path)):
                    plugin = types.ModuleType("native_namespace_without_file")
                    exec(compile(source.read_bytes(), str(source), "exec"), plugin.__dict__)
                    self.assertNotIn("__file__", plugin.__dict__)
                    queue, warnings, removed, path_calls = [], [], [], []
                    def load_path():
                        path_calls.append(True)
                        return str(reported_path)
                    cmds = types.SimpleNamespace(about=lambda **kw: False, warning=warnings.append)
                    maya = types.ModuleType("maya")
                    maya.cmds = cmds
                    maya.utils = types.SimpleNamespace(executeDeferred=queue.append)
                    maya_api = types.ModuleType("maya.api")
                    maya_api.OpenMaya = types.SimpleNamespace(
                        MFnPlugin=lambda *args: types.SimpleNamespace(loadPath=load_path),
                        MSceneMessage=types.SimpleNamespace(kMayaExiting=1, addCallback=lambda *args: 99),
                        MMessage=types.SimpleNamespace(removeCallback=removed.append))
                    with patch.dict(sys.modules, {"maya": maya, "maya.api": maya_api}):
                        plugin.initializePlugin(None)
                        self.assertIsNone(plugin._bridge)
                        self.assertEqual(len(queue), 1)
                        queue.pop()()
                        self.assertEqual(warnings, [])
                        self.assertEqual(path_calls, [True])
                        bridge = plugin._bridge
                        self.assertTrue(bridge.started)
                        self.assertEqual(Path(bridge.__file__), directory / "bridge.py")
                        plugin.uninitializePlugin(None)
                        self.assertTrue(bridge.stopped)
                        self.assertIsNone(plugin._bridge_path)
                        self.assertEqual(removed, [99])

    def test_unload_cancels_deferred_start_and_batch_does_not_listen(self):
        spec = importlib.util.spec_from_file_location("test_native_plugin", ROOT / "maya" / "bubble_maya_plugin.py")
        plugin = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(plugin)
        queue, removed = [], []
        cmds = types.SimpleNamespace(about=lambda **kw: False)
        utils = types.SimpleNamespace(executeDeferred=queue.append)
        api = types.SimpleNamespace(MFnPlugin=lambda *a: types.SimpleNamespace(loadPath=lambda: str(ROOT / "maya" / "bubble_maya_plugin.py")),
            MSceneMessage=types.SimpleNamespace(kMayaExiting=1, addCallback=lambda *a: 99),
            MMessage=types.SimpleNamespace(removeCallback=removed.append))
        maya = types.ModuleType("maya")
        maya.cmds, maya.utils = cmds, utils
        maya_api = types.ModuleType("maya.api")
        maya_api.OpenMaya = api
        with patch.dict(sys.modules, {"maya": maya, "maya.api": maya_api}):
            plugin.initializePlugin(None)
            self.assertEqual(len(queue), 1)
            plugin.uninitializePlugin(None)
            queue.pop()()
            self.assertIsNone(plugin._bridge)
            self.assertEqual(removed, [99])
            # An old callback may still be queued after unload/reload. Only one
            # listener may be started; the exiting callback also cancels work.
            plugin.initializePlugin(None)
            plugin.uninitializePlugin(None)
            plugin.initializePlugin(None)
            started, stopped = [], []
            bridge = types.SimpleNamespace(start=lambda: started.append(True), stop=lambda: stopped.append(True))
            fake_spec = types.SimpleNamespace(loader=types.SimpleNamespace(exec_module=lambda module: None))
            with patch.object(plugin.importlib.util, "spec_from_file_location", return_value=fake_spec), patch.object(plugin.importlib.util, "module_from_spec", return_value=bridge):
                for callback in queue:
                    callback()
                self.assertEqual(started, [True])
                plugin._stop()
                plugin._start()
                self.assertEqual(started, [True])
                self.assertEqual(stopped, [True])
            plugin.uninitializePlugin(None)
            queue.clear()
            cmds.about = lambda **kw: True
            plugin.initializePlugin(None)
            self.assertEqual(queue, [])
            plugin.uninitializePlugin(None)


if __name__ == "__main__":
    unittest.main()
