import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import socket
import subprocess
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
import configuration as cfg
from native import Manager, local_http, redactor


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {"BUBBLE_CINEMA4D_CONFIG_DIR": str(self.root / "registry")})
        self.env.start()
        self.source = self.root / "export.json"
        self.write({"url": "http://127.0.0.1:12345/vendor-mcp", "headers": {"Authorization": "Bearer SECRET"}})

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def write(self, entry):
        self.source.write_text(json.dumps({"mcpServers": {"Cinema4D": entry}}), encoding="utf-8")

    def register(self):
        p = cfg.change("register", "studio", str(self.source), "Cinema4D")
        return cfg.change("register", "studio", str(self.source), "Cinema4D", True, p["revision"], p["config_hash"])

    def test_preview_has_no_writes_or_secrets(self):
        p = cfg.change("register", "studio", str(self.source), "Cinema4D")
        self.assertFalse(cfg.registry_path().exists())
        self.assertNotIn("SECRET", json.dumps(p))

    def test_redaction_covers_query_argv_flag_values_and_dictionary_keys(self):
        scrub = redactor({"headers": {"Authorization": "Bearer HEADSECRET"}, "args": ["--token=ARGSECRET", "--secret", "NEXTSECRET"], "url": "http://localhost/mcp?token=QUERYSECRET"})
        text = json.dumps(scrub({"ARGSECRET": ["HEADSECRET", "NEXTSECRET", "QUERYSECRET"]}))
        for secret in ("ARGSECRET", "HEADSECRET", "NEXTSECRET", "QUERYSECRET"):
            self.assertNotIn(secret, text)

    def test_register_stores_reference_only_remove_preserves_export(self):
        before = self.source.read_bytes()
        self.register()
        self.assertNotIn("SECRET", cfg.registry_path().read_text())
        p = cfg.change("remove", "studio")
        cfg.change("remove", "studio", confirmed=True, expected_revision=p["revision"])
        self.assertEqual(cfg.status()["connections"], [])
        self.assertEqual(before, self.source.read_bytes())

    def test_missing_preview_denied(self):
        with self.assertRaises(ValueError):
            cfg.change("register", "studio", str(self.source), "Cinema4D", True)
        self.assertFalse(cfg.registry_path().exists())

    def test_changed_export_requires_new_preview(self):
        self.register()
        self.write({"url": "http://localhost:12346/mcp"})
        with self.assertRaisesRegex(ValueError, "changed"):
            cfg.load_connection("studio")

    def test_stale_registry_preview(self):
        p = cfg.change("register", "second", str(self.source), "Cinema4D")
        self.register()
        with self.assertRaisesRegex(ValueError, "stale"):
            cfg.change("register", "second", str(self.source), "Cinema4D", True, p["revision"], p["config_hash"])

    def test_unknown_owner_preserved(self):
        cfg.registry_path().parent.mkdir()
        cfg.registry_path().write_text('{"owner":"somebody-else"}')
        with self.assertRaises(ValueError):
            self.register()
        self.assertEqual(cfg.registry_path().read_text(), '{"owner":"somebody-else"}')

    def test_remote_urls_and_unknown_fields_rejected(self):
        for url in ["http://example.com/mcp", "file:///mcp", "http://127.0.0.1.evil.com/", "http://user:pass@localhost/mcp"]:
            self.write({"url": url})
            with self.subTest(url=url), self.assertRaises(ValueError):
                self.register()
        self.write({"url": "http://localhost/mcp", "tokenFile": "unknown-mechanism"})
        with self.assertRaises(ValueError):
            self.register()

    def test_sse_and_http_and_stdio_configs(self):
        for entry in [{"url": "http://[::1]:12345/sse", "type": "sse"}, {"url": "http://localhost/mcp", "type": "http"}, {"command": sys.executable, "args": ["native-helper.py"], "type": "stdio"}]:
            self.write(entry)
            self.register()

    def test_lock_conflict_preserves_registry(self):
        self.register()
        before = cfg.registry_path().read_bytes()
        cfg.registry_path().with_suffix(".lock").write_text("other transaction")
        with self.assertRaises(FileExistsError):
            self.register()
        self.assertEqual(before, cfg.registry_path().read_bytes())


class NativeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {"BUBBLE_CINEMA4D_CONFIG_DIR": str(root / "registry")})
        self.env.start()
        self.source = root / "native.json"
        self.source.write_text(json.dumps({"mcpServers": {"native": {"command": sys.executable, "args": [str(ROOT / "tests" / "fixture_native.py")], "env": {"TOKEN": "SECRET-CREDENTIAL-DO-NOT-PRINT"}}}}))
        p = cfg.change("register", "studio", str(self.source), "native")
        cfg.change("register", "studio", str(self.source), "native", True, p["revision"], p["config_hash"])
        self.manager = Manager()

    async def asyncTearDown(self):
        for sid in list(self.manager.sessions):
            await self.manager.disconnect(sid)
        self.env.stop()
        self.temp.cleanup()

    async def connect(self):
        result = await self.manager.connect("studio", True)
        self.assertIn("session_id", result, result)
        return result["session_id"]

    async def test_real_stdio_native_discovery_call_replay_and_disconnect(self):
        with self.assertRaises(ValueError):
            await self.manager.connect("studio")
        sid = await self.connect()
        with self.assertRaises(ValueError):
            await self.manager.call(sid, "fixture_echo", {}, "request-1", True)
        tools = await self.manager.tools(sid)
        self.assertIn("fixture_echo", [x["name"] for x in tools["tools"]])
        with self.assertRaises(ValueError):
            await self.manager.call(sid, "fixture_echo", {"value": "hello"}, "request-1")
        result = await self.manager.call(sid, "fixture_echo", {"value": "hello"}, "request-1", True)
        self.assertIn("hello", json.dumps(result))
        with self.assertRaisesRegex(ValueError, "already submitted"):
            await self.manager.call(sid, "fixture_echo", {"value": "hello"}, "request-1", True)
        with self.assertRaises(ValueError):
            await self.manager.connect("studio", True)
        await self.manager.disconnect(sid)
        with self.assertRaises(ValueError):
            await self.manager.tools(sid)

    async def test_timeout_closes_session_without_replay(self):
        sid = await self.connect()
        await self.manager.tools(sid)
        result = await self.manager.call(sid, "fixture_slow", {}, "slow-request", True, 1)
        self.assertIn("timed out", result["error"])
        with self.assertRaises(ValueError):
            await self.manager.call(sid, "fixture_echo", {}, "next-request", True)

    async def test_errors_and_known_credentials_not_returned(self):
        sid = await self.connect()
        await self.manager.tools(sid)
        result = await self.manager.call(sid, "fixture_error", {}, "error-request", True)
        self.assertNotIn("SECRET", json.dumps(result))
        result = await self.manager.call(sid, "fixture_echo", {"value": "SECRET-CREDENTIAL-DO-NOT-PRINT"}, "secret-request", True)
        self.assertNotIn("SECRET", json.dumps(result))

    async def test_changed_config_blocks_existing_session(self):
        sid = await self.connect()
        self.source.write_text(self.source.read_text() + " ")
        with self.assertRaises(ValueError):
            await self.manager.tools(sid)

    async def test_resources_require_discovery_and_exact_session_uri(self):
        sid=await self.connect()
        with self.assertRaises(ValueError):
            await self.manager.read_resource(sid,'file:///arbitrary/path')
        resources=await self.manager.resources(sid)
        self.assertEqual([r['uri'] for r in resources['resources']],['fixture://scene'])
        result=await self.manager.read_resource(sid,'fixture://scene')
        self.assertIn('Fixture scene',json.dumps(result))
        self.assertNotIn('SECRET',json.dumps(result))
        with self.assertRaises(ValueError):
            await self.manager.read_resource(sid,'https://example.com/scene')

    async def test_schema_validation_precedes_submit_and_does_not_break_session(self):
        sid=await self.connect();await self.manager.tools(sid)
        for args in ({},{'value':123}):
            with self.assertRaisesRegex(ValueError,'no call submitted'):
                await self.manager.call(sid,'fixture_echo',args,'schema-request',True)
        self.assertNotIn('schema-request',self.manager.used_requests)
        tool=self.manager.sessions[sid].tools['fixture_echo'];original=tool.inputSchema
        tool.inputSchema={'$ref':'https://127.0.0.1:1/must-not-fetch'}
        with self.assertRaisesRegex(ValueError,'no call submitted'):
            await self.manager.call(sid,'fixture_echo',{'value':'secret'},'schema-request',True)
        tool.inputSchema=original
        result=await self.manager.call(sid,'fixture_echo',{'value':'valid'},'schema-request',True)
        self.assertIn('valid',json.dumps(result))

    async def test_concurrent_connect_rejected_before_initialization(self):
        first = asyncio.create_task(self.manager.connect("studio", True))
        await asyncio.sleep(0)
        with self.assertRaisesRegex(ValueError, "initializing"):
            await self.manager.connect("studio", True)
        self.assertIn("session_id", await first)

    async def test_reconnect_does_not_reset_request_ids(self):
        sid = await self.connect()
        await self.manager.tools(sid)
        await self.manager.call(sid, "fixture_echo", {"value": "once"}, "once-request", True)
        await self.manager.disconnect(sid)
        new_sid = await self.connect()
        await self.manager.tools(new_sid)
        with self.assertRaisesRegex(ValueError, "already submitted"):
            await self.manager.call(new_sid, "fixture_echo", {"value": "once"}, "once-request", True)

    async def test_http_client_disables_redirects_and_proxy_environment(self):
        async with local_http() as client:
            self.assertFalse(client.follow_redirects)
            self.assertFalse(client.trust_env)


class HTTPTests(NativeTests):
    """The same lifecycle contracts over a real loopback Streamable HTTP server."""
    async def asyncSetUp(self):
        await super().asyncSetUp()
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        self.process = subprocess.Popen([sys.executable, str(ROOT / "tests" / "fixture_native.py"), "streamable-http", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.05):
                    break
            except OSError:
                await asyncio.sleep(0.05)
        else:
            self.process.terminate()
            self.process.wait(timeout=5)
            raise AssertionError("HTTP fixture did not start")
        self.source.write_text(json.dumps({"mcpServers": {"native": {"url": f"http://127.0.0.1:{port}/mcp", "headers": {"Authorization": "Bearer SECRET-CREDENTIAL-DO-NOT-PRINT"}}}}))
        p = cfg.change("register", "studio", str(self.source), "native")
        cfg.change("register", "studio", str(self.source), "native", True, p["revision"], p["config_hash"])

    async def asyncTearDown(self):
        await super().asyncTearDown()
        self.process.terminate()
        self.process.wait(timeout=5)

    async def test_server_disappears_session_not_silently_reconnected(self):
        sid = await self.connect()
        await self.manager.tools(sid)
        self.process.terminate()
        self.process.wait(timeout=5)
        result = await self.manager.call(sid, "fixture_echo", {"value": "one"}, "disconnected-request", True)
        self.assertIn("error", result)
        with self.assertRaises(ValueError):
            await self.manager.call(sid, "fixture_echo", {"value": "two"}, "fresh-request", True)


class SSETests(HTTPTests):
    async def asyncSetUp(self):
        await NativeTests.asyncSetUp(self)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        self.process = subprocess.Popen([sys.executable, str(ROOT / "tests" / "fixture_native.py"), "sse", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.05):
                    break
            except OSError:
                await asyncio.sleep(0.05)
        else:
            self.process.terminate()
            self.process.wait(timeout=5)
            raise AssertionError("SSE fixture did not start")
        self.source.write_text(json.dumps({"mcpServers": {"native": {"url": f"http://127.0.0.1:{port}/sse", "type": "sse", "headers": {"Authorization": "Bearer SECRET-CREDENTIAL-DO-NOT-PRINT"}}}}))
        p = cfg.change("register", "studio", str(self.source), "native")
        cfg.change("register", "studio", str(self.source), "native", True, p["revision"], p["config_hash"])


if __name__ == "__main__":
    unittest.main()
