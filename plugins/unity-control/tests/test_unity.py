import json
import os
from pathlib import Path
import socketserver
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
import client
import discovery
import installation


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name) / "A project"
        (self.project / "Assets").mkdir(parents=True)
        (self.project / "ProjectSettings").mkdir()
        (self.project / "ProjectSettings/ProjectVersion.txt").write_text("m_EditorVersion: 6000.1.0f1\n")
        (self.project / "Packages").mkdir()
        self.original = b'{"dependencies": {"com.example.keep": "1.0.0"}}\r\n'
        (self.project / "Packages/manifest.json").write_bytes(self.original)
        self.target = self.project / "Packages" / installation.PACKAGE

    def install(self):
        result = installation.install_bridge(str(self.project), True)
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["applied"])

    def test_preview_never_writes(self):
        before = sorted(str(p.relative_to(self.project)) for p in self.project.rglob("*"))
        result = installation.install_bridge(str(self.project))
        self.assertTrue(result["requires_confirmation"])
        self.assertFalse(result["applied"])
        self.assertEqual(before, sorted(str(p.relative_to(self.project)) for p in self.project.rglob("*")))

    def test_install_idempotent_uninstall_preserves_unrelated_files(self):
        self.install()
        self.assertEqual((self.project / "Packages/manifest.json").read_bytes(), self.original)
        self.assertEqual(installation.installation_status(str(self.project))["changes"], [])
        (self.target / "Editor/user.cs").write_text("// user code")
        (self.target / "package.json.meta").write_text("generated metadata")
        result = installation.uninstall_bridge(str(self.project))
        self.assertTrue(result["installed"])
        self.assertFalse(result["applied"])
        result = installation.uninstall_bridge(str(self.project), True)
        self.assertTrue(result["ok"], result)
        self.assertFalse(result["installed"])
        self.assertEqual((self.target / "Editor/user.cs").read_text(), "// user code")
        self.assertTrue((self.target / "package.json.meta").exists())
        self.assertEqual((self.project / "Packages/manifest.json").read_bytes(), self.original)
        self.assertFalse(installation.install_bridge(str(self.project), True)["ok"])

    def test_reinstall_after_generated_meta_remains(self):
        self.install()
        (self.target / "package.json.meta").write_text("generated metadata")
        installation.uninstall_bridge(str(self.project), True)
        self.install()

    def test_uninstall_after_project_version_change(self):
        self.install()
        version = self.project / "ProjectSettings/ProjectVersion.txt"
        version.write_text("m_EditorVersion: 7000.0.0f1\n")
        self.assertFalse(installation.install_bridge(str(self.project), True)["ok"])
        result = installation.uninstall_bridge(str(self.project), True)
        self.assertTrue(result["ok"], result)
        self.assertFalse((self.target / "package.json").exists())
        self.assertEqual(version.read_text(), "m_EditorVersion: 7000.0.0f1\n")

    def test_uninstall_preserves_later_declared_dependency_and_warns(self):
        self.install()
        manifest = self.project / "Packages/manifest.json"
        original = json.dumps({"dependencies": {installation.PACKAGE: "file:elsewhere"}})
        manifest.write_text(original)
        preview = installation.uninstall_bridge(str(self.project))
        self.assertTrue(preview["ok"], preview)
        self.assertIn("may load", preview["warning"])
        self.assertTrue((self.target / "package.json").exists())
        result = installation.uninstall_bridge(str(self.project), True)
        self.assertTrue(result["ok"], result)
        self.assertIn("may load", result["warning"])
        self.assertEqual(manifest.read_text(), original)
        self.assertFalse((self.target / "package.json").exists())

    def test_modified_owned_file_blocks_update_and_uninstall(self):
        self.install()
        file = self.target / "Editor/BubbleUnityBridge.cs"
        file.write_text("// user modified")
        for operation in (installation.install_bridge, installation.uninstall_bridge):
            result = operation(str(self.project), True)
            self.assertFalse(result["ok"])
            self.assertEqual(file.read_text(), "// user modified")

    def test_malformed_manifest_does_not_delete_arbitrary_paths(self):
        self.install()
        owned = self.target / installation.MANIFEST
        value = json.loads(owned.read_text())
        value["files"]["../../manifest.json"] = installation._digest(self.original)
        owned.write_text(json.dumps(value))
        self.assertFalse(installation.uninstall_bridge(str(self.project), True)["ok"])
        self.assertEqual((self.project / "Packages/manifest.json").read_bytes(), self.original)

    def test_invalid_project_version_confirmation_and_dependency(self):
        self.assertFalse(installation.install_bridge("relative", True)["ok"])
        self.assertFalse(installation.install_bridge(str(self.project), "true")["ok"])
        version = self.project / "ProjectSettings/ProjectVersion.txt"
        version.write_text("m_EditorVersion: 2022.3.1f1")
        self.assertFalse(installation.install_bridge(str(self.project), True)["ok"])
        version.write_text("m_EditorVersion: 6000.1.0f1")
        (self.project / "Packages/manifest.json").write_text(json.dumps({"dependencies": {installation.PACKAGE: "file:elsewhere"}}))
        self.assertFalse(installation.install_bridge(str(self.project), True)["ok"])
        self.assertFalse(self.target.exists())

    def test_partial_io_failure_rolls_back_owned_files(self):
        original_write = installation._atomic_write
        calls = []
        def fail_once(path, data):
            calls.append(path)
            if len(calls) == 2:
                raise OSError("simulated disk error")
            original_write(path, data)
        with patch.object(installation, "_atomic_write", side_effect=fail_once):
            result = installation.install_bridge(str(self.project), True)
        self.assertFalse(result["ok"])
        self.assertFalse(any((self.target / name).exists() for name in (*installation.FILES, installation.MANIFEST)))
        self.install()

    def test_junction_rejected_cloud_placeholder_allowed(self):
        real_lstat = Path.lstat
        target = self.project / "Packages"
        class Info:
            st_mode = 0o40755
            st_file_attributes = 0x400
            st_reparse_tag = 0xA0000003
        def fake_lstat(path, *args, **kwargs):
            return Info() if path == target else real_lstat(path, *args, **kwargs)
        with patch.object(Path, "lstat", fake_lstat):
            self.assertFalse(installation.install_bridge(str(self.project))["ok"])
            Info.st_reparse_tag = 0x9000301A
            self.assertTrue(installation.install_bridge(str(self.project))["ok"])


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.metadata = [{"pid": 1, "token": "secret-one", "unity_version": "6000.1"}, {"pid": 2, "token": "secret-two", "unity_version": "6000.1"}]
        self.data = {
            1: {"ok": True, "data": {"path": "Assets/Scenes/Main.unity", "project": "D:/Projects/One", "project_name": "One", "modified": True, "scenes": [{"path": "Assets/Scenes/Additive.unity"}]}},
            2: {"ok": True, "data": {"path": "Assets/Scenes/Other.unity", "project": "D:/Projects/Two", "project_name": "Two", "scenes": []}},
        }
        one = patch.object(discovery, "sessions", return_value=self.metadata)
        two = patch.object(discovery, "request", side_effect=lambda op, pid, timeout: self.data[pid])
        one.start(); two.start()
        self.addCleanup(one.stop); self.addCleanup(two.stop)

    def test_names_full_paths_project_and_additive_scene_match(self):
        for query in ["MAIN.UNITY", "Main", "D:/Projects/One/Assets/Scenes/Main.unity", "One", "D:/Projects/One", "Additive.unity"]:
            result = discovery.discover_sessions(query)
            self.assertEqual(result["selection"]["selected_pid"], 1, query)
            self.assertNotIn("secret", json.dumps(result))
            self.assertIn("One / Main.unity", result["data"][0]["display_label"])

    def test_no_partial_match_or_wrong_full_path_fallback(self):
        for query in ["Ma", "D:/other/Main.unity", "*.unity"]:
            self.assertEqual(discovery.discover_sessions(query)["selection"]["status"], "not_found")

    def test_duplicate_and_unreachable_never_auto_select(self):
        self.data[2]["data"]["path"] = "Assets/Scenes/Main.unity"
        self.assertEqual(discovery.discover_sessions("Main")["selection"]["status"], "ambiguous")
        self.data[2] = {"ok": False}
        self.assertEqual(discovery.discover_sessions("Main")["selection"]["status"], "incomplete")
        self.assertIsNone(discovery.discover_sessions("Main")["selection"]["selected_pid"])

    def test_unsaved_label_and_no_implicit_selection(self):
        self.data[1]["data"]["path"] = ""
        result = discovery.discover_sessions()
        self.assertEqual(result["data"][0]["scene_name"], "未保存场景")
        self.assertIsNone(result["selection"]["selected_pid"])


class ClientSocketTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {"BUBBLE_UNITY_SESSION_DIR": self.temp.name})
        self.env.start(); self.addCleanup(self.env.stop)
        self.received = []
        received = self.received
        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                data = json.loads(self.rfile.readline())
                received.append(data)
                self.wfile.write(json.dumps({"ok": data["token"] == self.server.token, "data": {"pid": self.server.pid}}).encode() + b"\n")
        self.servers = []
        for pid in (111, 222):
            server = socketserver.TCPServer(("127.0.0.1", 0), Handler)
            server.pid, server.token = pid, str(pid) * 24
            self.servers.append(server)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
            (Path(self.temp.name) / (str(pid) + ".json")).write_text(json.dumps({"protocol": 1, "pid": pid, "port": server.server_address[1], "host": "127.0.0.1", "token": server.token}))

    def test_multi_instance_requires_pid_and_routes_exactly_once(self):
        self.assertEqual(client.request("status")["error"]["code"], "session_selection")
        self.assertEqual(self.received, [])
        self.assertEqual(client.request("status", pid=222)["data"]["pid"], 222)
        self.assertEqual(len(self.received), 1)
        self.assertEqual(self.received[0]["token"], self.servers[1].token)
        self.assertGreater(self.received[0]["expires_at"], 0)

    def test_unknown_pid_never_falls_back_and_metadata_redacts_token(self):
        self.assertEqual(client.request("status", pid=999)["error"]["code"], "session_selection")
        self.assertEqual(self.received, [])
        self.assertNotIn(self.servers[0].token, json.dumps(client.list_sessions()))

    def test_invalid_timeout_does_not_send(self):
        for timeout in (True, 0, -1, 121, float("nan"), float("inf")):
            self.assertEqual(client.request("status", pid=111, timeout=timeout)["error"]["code"], "invalid_timeout")
        self.assertEqual(self.received, [])


if __name__ == "__main__":
    unittest.main()
