import hashlib
import json
import os
from pathlib import Path
import shutil
import socketserver
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
import diagnostics as d


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        (ROOT / ".test-runtime").mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / ".test-runtime")
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_status_and_bad_input(self):
        self.assertTrue(d.status()["ok"])
        self.assertFalse(d.package_check("relative")["ok"])
        self.assertFalse(d.sessions("unknown")["ok"])
        self.assertFalse(d.guidance("evil", "repair")["ok"])

    def test_adobe_guidance_uses_owning_connector_not_pid_registry(self):
        for app in ("premiere", "photoshop"):
            self.assertIn(app + "-control", d.status()["data"]["supported_plugins"])
            for action in ("repair", "update", "uninstall"):
                result = d.guidance(app + "-control", action)
                self.assertTrue(result["ok"])
                self.assertFalse(result["data"]["executed"])
                self.assertIn(app + "_list_sessions", " ".join(result["data"]["steps"]))
                if app == "photoshop":
                    self.assertIn("no Creative Cloud", " ".join(result["data"]["steps"]))
                if app == "premiere":
                    self.assertIn("automatic discovery", " ".join(result["data"]["steps"]))
                    self.assertNotIn("obtain a fresh pairing code", " ".join(result["data"]["steps"]))
            self.assertFalse(d.sessions(app)["ok"])

    def test_native_connectors_have_separate_guidance(self):
        for app in ('cinema4d','resolve'):
            self.assertIn(app+'-control',d.PLUGINS)
            with patch.object(d.socket,'create_connection',side_effect=AssertionError('No socket probing')):
                self.assertFalse(d.sessions(app)['ok'])
                text=' '.join(d.guidance(app+'-control','repair')['data']['steps'])
                self.assertIn(app+'_setup_status',text);self.assertIn(app+'_list_sessions',text)
                self.assertNotIn(app+'_install_bridge',text)
    def test_sequence_python313_is_standard(self):
        source=ROOT.parent/'sequence-check';target=self.root/'sequence'
        shutil.copytree(source,target,ignore=shutil.ignore_patterns('.venv','__pycache__','.test-runtime'))
        result=d.package_check(str(target));self.assertTrue(result['data']['healthy'],result)
        p=target/'mcp.json';v=json.loads(p.read_text(encoding='utf-8'));next(iter(v['mcpServers'].values()))['args'][2]='3.99';p.write_text(json.dumps(v))
        self.assertIn('nonstandard_launcher',d.package_check(str(target))['data']['issues'])
    def test_blender_bridge_receipt_relative_to_scripts_root(self):
        data=b'fixture';self.write('modules/bubble_blender_runtime/installation.json',{'owner':'bubble-blender-control','version':'0.1.0','files':{'startup/bubble_blender.py':hashlib.sha256(data).hexdigest()}})
        p=self.root/'startup/bubble_blender.py';p.parent.mkdir();p.write_bytes(data)
        self.assertTrue(d.bridge_check('blender',str(self.root))['data']['intact'])
        self.assertIn('blender',d.APPS)

    def test_current_package(self):
        result = d.package_check(str(ROOT))
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["data"]["healthy"], result)

    def test_static_capabilities_never_executes_source(self):
        target = self.root / 'package'
        shutil.copytree(ROOT, target, ignore=shutil.ignore_patterns('.venv', '__pycache__', '.test-runtime'))
        path = target / 'server/main.py'
        path.write_text('raise RuntimeError("must never execute")\n' + path.read_text(encoding='utf-8'), encoding='utf-8')
        result = d.capabilities(str(target))
        self.assertTrue(result['ok'], result)
        tools = {item['name']: item for item in result['data']['tools']}
        self.assertIn('doctor_capabilities', tools)
        self.assertTrue(tools['doctor_capabilities']['read_only_hint'])
        self.assertEqual(tools['doctor_capabilities']['parameters'], [{'name': 'package_path', 'required': True}])
        path.write_text(path.read_text(encoding='utf-8') + '\n@mcp.tool(name="doctor_status", annotations=READ)\ndef duplicate(): pass\n', encoding='utf-8')
        self.assertIn('duplicate_tool_name:doctor_status', d.capabilities(str(target))['data']['issues'])
        path.write_text('not valid Python(', encoding='utf-8')
        self.assertFalse(d.capabilities(str(target))['ok'])

    def test_after_effects_automatic_bridge_guidance(self):
        result = d.guidance('after-effects-control', 'uninstall')
        self.assertTrue(result['ok'])
        steps = ' '.join(result['data']['steps'])
        self.assertIn('after_effects_list_sessions', steps)
        self.assertIn('Multiple AE instances', steps)
        self.assertIn('after_effects_uninstall_bridge', steps)
        self.assertIn('Startup script', steps)
        self.assertNotIn('cannot be safely selected', steps)

    def test_detect_legacy_failure_and_version_drift(self):
        p = self.root / "package"
        shutil.copytree(ROOT, p, ignore=shutil.ignore_patterns(".venv", "__pycache__", ".test-runtime"))
        path = p / ".mcp.json"
        data = json.loads(path.read_text())
        data["mcpServers"]["doctor"]["cwd"] = "/"
        path.write_text(json.dumps(data))
        (p / ".venv").mkdir()
        legacy = p / ".codex-plugin/plugin.json"
        data = json.loads(legacy.read_text(encoding="utf-8"))
        data["version"] = "0.0.1"
        legacy.write_text(json.dumps(data))
        issues = d.package_check(str(p))["data"]["issues"]
        self.assertIn("mcp_config_mismatch", issues)
        self.assertIn("declared_cwd_may_prevent_loading", issues)
        self.assertIn("in_package_venv_may_block_uninstall", issues)
        self.assertIn("manifest_version_mismatch", issues)

    def test_cache_is_not_installation_state(self):
        dest = self.root / "plugins/cache/test-market/plugin-doctor/0.1.2"
        shutil.copytree(ROOT, dest, ignore=shutil.ignore_patterns(".venv", "__pycache__", ".test-runtime"))
        report = d.inventory(str(self.root), str(ROOT.parents[1]))
        self.assertTrue(report["ok"], report)
        row = report["data"]["cached_packages"][0]
        self.assertTrue(row["matches_source_version"])
        self.assertNotIn("installed", row)
        self.assertNotIn("enabled", row)
        self.assertEqual(d.inventory(str(self.root / "empty"))["data"]["cached_packages"], [])

    def test_corrupt_package(self):
        self.write("plugin.json", [])
        self.assertFalse(d.package_check(str(self.root))["ok"])

    def test_invalid_version_not_used_as_path(self):
        self.write('plugin.json', {'name': 'plugin-doctor', 'version': '../../outside'})
        self.write('.codex-plugin/plugin.json', {'name': 'plugin-doctor', 'version': '../../outside'})
        report = d.package_check(str(self.root))
        self.assertFalse(report['ok'])
        self.assertIn('Invalid package version', report['error']['message'])

    def test_inventory_global_bound(self):
        for version in ('0.1.0', '0.2.0'):
            (self.root / 'plugins/cache/test/plugin-doctor' / version).mkdir(parents=True)
        with patch.object(d, 'MAX_PACKAGES', 1):
            report = d.inventory(str(self.root))
        self.assertTrue(report['ok'])
        self.assertEqual(len(report['data']['cached_packages']), 1)
        self.assertTrue(report['data']['truncated'])

    def test_bridge_integrity_and_missing(self):
        content = b"test content"
        (self.root / "bridge.py").write_bytes(content)
        metadata = {"owner": "bubble-maya-control", "version": "0.2.6", "files": {"bridge.py": hashlib.sha256(content).hexdigest()}}
        self.write("installation.json", metadata)
        self.assertTrue(d.bridge_check("maya", str(self.root))["data"]["intact"])
        (self.root / "bridge.py").write_bytes(b"changed")
        self.assertEqual(d.bridge_check("maya", str(self.root))["data"]["files"][0]["status"], "modified")
        (self.root / "bridge.py").unlink()
        self.assertEqual(d.bridge_check("maya", str(self.root))["data"]["files"][0]["status"], "missing")

    def test_bridge_rejects_ownership_and_traversal(self):
        self.write("installation.json", {"owner": "someone-else", "files": {"file": "a"*64}})
        self.assertFalse(d.bridge_check("maya", str(self.root))["ok"])
        for name in ("../secret", "a/../../secret", "C:/secret", "a\\secret", ""):
            self.write("installation.json", {"owner": "bubble-maya-control", "files": {name: "a"*64}})
            self.assertFalse(d.bridge_check("maya", str(self.root))["ok"], name)

    def test_no_secret_log_output(self):
        path = self.root / "startup.log"
        path.write_text("token=SUPER_SECRET\nWarning: name '__file__' is not defined\nos error 5\n")
        report = d.log_check(str(path))
        self.assertEqual(len(report["data"]["findings"]), 2)
        self.assertNotIn("SUPER_SECRET", json.dumps(report))
        path.write_bytes(b"x" * (d.MAX_JSON+5))
        self.assertTrue(d.log_check(str(path))["data"]["tail_only"])

    def test_oversize_json_rejected(self):
        path = self.root / "large.json"
        path.write_bytes(b" " * (d.MAX_JSON+1))
        with self.assertRaises(ValueError):
            d.read_json(path)

    def test_fixed_operation_redaction_multisession(self):
        secret = "s" * 40
        seen = []
        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                request = json.loads(self.rfile.readline())
                seen.append(request)
                self.wfile.write(json.dumps({"ok": True, "data": {"path": "C:/"+secret+"/hero.ma", "modified": False, "token": secret}}).encode()+b"\n")
        with socketserver.TCPServer(("127.0.0.1", 0), Handler) as server:
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                for pid in (123, 456):
                    self.write(str(pid)+".json", {"protocol": 1, "pid": pid, "port": server.server_address[1], "host": "127.0.0.1", "token": secret})
                self.write("789.json", {"protocol":1,"pid":789,"port":80,"host":"external.example","token":secret})
                self.write("broken.json", [])
                report = d.sessions("maya", str(self.root))
                self.assertTrue(report["ok"], report)
                self.assertEqual(len(report["data"]), 2)
                self.assertEqual(report["invalid_records"], 2)
                self.assertTrue(all(r["status"] == "reachable" for r in report["data"]))
                self.assertNotIn(secret, json.dumps(report))
                self.assertEqual([r["operation"] for r in seen], ["scene_info", "scene_info"])
                self.assertTrue(all(r["arguments"] == {} for r in seen))
            finally:
                server.shutdown()
                worker.join()

    def test_guidance_never_executes(self):
        for name in d.PLUGINS:
            for action in ("repair", "update", "uninstall"):
                result = d.guidance(name, action)
                self.assertTrue(result["ok"])
                self.assertFalse(result["data"]["executed"])

    def test_symlink_refused(self):
        target = self.root / "target"
        target.mkdir()
        link = self.root / "link"
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError:
            self.skipTest("Symlink creation unavailable")
        with self.assertRaises(ValueError):
            d.absolute(link)


if __name__ == "__main__":
    unittest.main()
