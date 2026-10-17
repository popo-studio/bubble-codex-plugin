import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "maya"))
sys.path.insert(0, str(ROOT / "server"))
import bubble_maya_bridge as bridge
import client


class FakeCmds:
    def __init__(self, root):
        self.root = root

    def workspace(self, **kwargs):
        if kwargs.get("query"):
            return self.root
        return os.path.join(self.root, kwargs["expandName"])

    def ls(self, **kwargs):
        if kwargs.get("selection"):
            return ["|cube"]
        return {"reference": ["sharedReferenceNode", "ref1"], "file": ["texture1"], "unknown": ["badNode"]}.get(kwargs.get("type"), [])

    def file(self, **kwargs):
        return False if kwargs.get("modified") else "scene.ma"

    def about(self, **kwargs):
        return "2027"

    def referenceQuery(self, node, **kwargs):
        return False if kwargs.get("isLoaded") else "missing.ma"

    def getAttr(self, attr):
        return {"fileTextureName": "albedo.1001.exr", "computedFileTextureNamePattern": "albedo.<UDIM>.exr", "useFrameExtension": False}[attr.split(".")[-1]]

    def currentTime(self, **kwargs):
        return 1

    def currentUnit(self, **kwargs):
        return "film" if kwargs.get("time") else "cm"

    def namespaceInfo(self, **kwargs):
        return ["UI", "shared"]


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.pending, self.calls = [], []
        self.server = bridge.Bridge(self.dispatch, self.pending.append)

    def tearDown(self):
        self.server.server_close()

    def dispatch(self, operation, arguments):
        self.calls.append(operation)
        return arguments

    def request(self, **kwargs):
        return {"protocol": 1, "token": self.server.token, "operation": "status", "timeout": .02, "expires_at": time.time() + .02, **kwargs}

    def test_auth_rejected_before_dispatch(self):
        for token in (None, "wrong", "密钥"):
            self.assertEqual(self.server.invoke(self.request(token=token))["error"]["code"], "unauthorized")
        self.assertFalse(self.pending)

    def test_unknown_operation_and_invalid_timeout_rejected(self):
        for operation in ("delete_scene", [], {}):
            self.assertEqual(self.server.invoke(self.request(operation=operation))["error"]["code"], "invalid_operation")
        for timeout in (True, -1, 121, float("nan")):
            self.assertEqual(self.server.invoke(self.request(timeout=timeout))["error"]["code"], "invalid_request")
        self.assertFalse(self.pending)

    def test_failed_scheduling_cancels_any_queued_callback(self):
        def schedule(fn):
            self.pending.append(fn)
            raise RuntimeError("Maya shutting down")
        self.server.schedule_fn = schedule
        self.assertEqual(self.server.invoke(self.request())["error"]["code"], "scheduling_error")
        self.pending.pop()()
        self.assertFalse(self.calls)

    def test_queued_timeout_cancels_late_execution(self):
        reply = self.server.invoke(self.request())
        self.assertEqual(reply["error"]["code"], "queue_timeout")
        self.pending.pop()()
        self.assertFalse(self.calls)

    def test_request_expired_in_accept_backlog_does_not_dispatch(self):
        self.assertEqual(self.server.invoke(self.request(expires_at=time.time() - 1))["error"]["code"], "queue_timeout")
        self.assertFalse(self.pending)

    def test_running_timeout_is_uncertain(self):
        finished = threading.Event()
        def slow(*args):
            time.sleep(.1)
            finished.set()
        self.server.dispatch_fn = slow
        self.server.schedule_fn = lambda fn: threading.Thread(target=fn).start()
        reply = self.server.invoke(self.request())
        self.assertEqual(reply["error"]["code"], "execution_timeout")
        self.assertTrue(reply["error"]["execution_started"])
        self.assertTrue(finished.wait(1))

    def test_successful_dispatch(self):
        self.server.schedule_fn = lambda fn: fn()
        self.assertEqual(self.server.invoke(self.request(arguments={"value": 42})), {"ok": True, "data": {"value": 42}})

    def test_shutdown_cancels_pending_work(self):
        self.server.closed.set()
        self.server.schedule_fn = lambda fn: fn()
        self.assertEqual(self.server.invoke(self.request())["error"]["code"], "queue_timeout")
        self.assertFalse(self.calls)


class InspectionTests(unittest.TestCase):
    def test_patterns_and_literal_missing_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            cmds = FakeCmds(directory)
            for name in ("albedo.1001.exr", "anim.0001.exr", "tile.u1_v1.exr", "square[1].exr"):
                Path(directory, name).touch()
            for path in ("albedo.<UDIM>.exr", "anim.<f>.exr", "anim.####.exr", "anim.%04d.exr", "tile.<UVTILE>.exr", "square[1].exr"):
                self.assertTrue(bridge.path_status(path, cmds)["exists"], path)
            self.assertTrue(bridge.path_status("anim.0030.exr", cmds, sequence=True)["exists"])
            self.assertFalse(bridge.path_status("absent.<UDIM>.exr", cmds)["exists"])
            Path(directory, "backup.1_backup.exr").touch()
            self.assertFalse(bridge.path_status("backup.<f>.exr", cmds)["exists"])
            self.assertFalse(bridge.path_status("anim.###.exr", cmds)["exists"])

    def test_inspection_distinguishes_unloaded_and_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "albedo.1001.exr").touch()
            report = bridge.inspect_scene(FakeCmds(directory), include_namespaces=False)
            self.assertEqual(len(report["missing_references"]), 1)
            self.assertFalse(report["references"][0]["loaded"])
            self.assertEqual(report["missing_textures"], [])
            self.assertEqual(report["unknown_nodes"], ["badNode"])
            self.assertEqual(report["namespaces"], [])
            self.assertEqual(report["scene"]["selection"], ["|cube"])

    def test_script_result_output_and_error(self):
        maya = types.ModuleType("maya")
        maya.cmds, maya.mel = object(), types.SimpleNamespace(eval=lambda code: 7)
        with patch.dict(sys.modules, {"maya": maya}):
            result = bridge.dispatch("execute_python", {"code": "print('hello'); result = 6 * 7"})
            self.assertEqual(result["result"], 42)
            self.assertEqual(result["stdout"], "hello\n")
            result = bridge.dispatch("execute_python", {"code": "raise RuntimeError('oops')"})
            self.assertEqual(result["error"]["code"], "script_error")
            self.assertIn("RuntimeError: oops", result["error"]["traceback"])
            self.assertEqual(bridge.dispatch("execute_mel", {"code": "1 + 6"})["result"], 7)


class ClientIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"BUBBLE_MAYA_SESSION_DIR": self.directory.name})
        self.env.start()
        self.server = bridge.Bridge(lambda op, args: {"op": op, **args}, lambda fn: fn())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.metadata = {"protocol": 1, "pid": 123, "host": "127.0.0.1", "port": self.server.server_address[1], "token": self.server.token}
        Path(self.directory.name, "123.json").write_text(json.dumps(self.metadata), encoding="utf-8")

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.env.stop()
        self.directory.cleanup()

    def test_transport_and_secret_redaction(self):
        self.assertNotIn(self.server.token, json.dumps(client.list_sessions()))
        self.assertEqual(client.request("scene_info"), {"ok": True, "data": {"op": "scene_info"}})
        self.assertEqual(client.request("status", pid=123)["data"]["op"], "status")

    def test_remote_session_rejected(self):
        self.metadata["host"] = "192.168.1.1"
        Path(self.directory.name, "123.json").write_text(json.dumps(self.metadata))
        self.assertEqual(client.sessions(), [])

    def test_multiple_sessions_require_pid(self):
        Path(self.directory.name, "456.json").write_text(json.dumps({**self.metadata, "pid": 456}))
        self.assertEqual(client.request("status")["error"]["code"], "session_selection")
        self.assertTrue(client.request("status", pid=123)["ok"])

    def test_malformed_network_request_keeps_listener_alive(self):
        with socket.create_connection(self.server.server_address) as sock:
            sock.sendall(b"not-json\n")
            self.assertFalse(json.loads(sock.makefile("rb").readline())["ok"])
        self.assertTrue(client.request("status")["ok"])

    def test_size_limits_do_not_retry_execution(self):
        calls = []
        def large_result(op, args):
            calls.append(op)
            return "x" * bridge.MAX_MESSAGE
        self.server.dispatch_fn = large_result
        response = client.request("execute_python", {"code": "x" * bridge.MAX_MESSAGE})
        self.assertEqual(response["error"]["code"], "request_too_large")
        self.assertEqual(calls, [])
        response = client.request("execute_python", {"code": "result = large"})
        self.assertEqual(response["error"]["code"], "response_too_large")
        self.assertEqual(calls, ["execute_python"])


class MultiInstanceIntegrationTests(unittest.TestCase):
    """Two real loopback listeners model separate Maya processes, without Maya."""

    def setUp(self):
        runtime = ROOT / ".test-runtime"
        runtime.mkdir(exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(prefix="multi-maya-", dir=runtime)
        self.addCleanup(self.directory.cleanup)
        self.env = patch.dict(os.environ, {"BUBBLE_MAYA_SESSION_DIR": self.directory.name})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.servers, self.threads, self.metadata, self.calls = {}, {}, {}, {}
        for pid in (123, 456):
            self.calls[pid] = []
            def dispatch(operation, arguments, pid=pid):
                self.calls[pid].append((operation, arguments))
                return {"pid": pid, "operation": operation, "arguments": arguments}
            server = bridge.Bridge(dispatch, lambda fn: fn())
            self.servers[pid] = server
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            self.threads[pid] = worker
            worker.start()
            self.addCleanup(self.stop_instance, pid)
            self.metadata[pid] = {"protocol": 1, "pid": pid, "host": "127.0.0.1",
                                  "port": server.server_address[1], "token": server.token}
            self.write_metadata(pid, self.metadata[pid])

    def write_metadata(self, pid, value):
        Path(self.directory.name, "%s.json" % pid).write_text(json.dumps(value), encoding="utf-8")

    def stop_instance(self, pid):
        server = self.servers.pop(pid, None)
        if server is not None:
            server.closed.set()
            server.shutdown()
            server.server_close()
            self.threads.pop(pid).join(timeout=5)

    def test_explicit_pid_routes_all_operations_only_to_selected_instance(self):
        self.assertNotEqual(self.metadata[123]["port"], self.metadata[456]["port"])
        self.assertNotEqual(self.metadata[123]["token"], self.metadata[456]["token"])
        listing = client.list_sessions()
        self.assertEqual({item["pid"] for item in listing["data"]}, {123, 456})
        for value in self.metadata.values():
            self.assertNotIn(value["token"], json.dumps(listing))
        for operation, arguments in (("scene_info", {}),
                                     ("execute_python", {"code": "result = 'selected Maya'"}),
                                     ("execute_mel", {"code": 'print("selected Maya");'})):
            ambiguous = client.request(operation, arguments)
            self.assertEqual(ambiguous["error"]["code"], "session_selection")
        self.assertEqual(self.calls, {123: [], 456: []})
        for pid in (123, 456):
            other = 456 if pid == 123 else 123
            for operation, arguments in (("scene_info", {}),
                                         ("execute_python", {"code": "result = %s" % pid}),
                                         ("execute_mel", {"code": "print(%s);" % pid})):
                other_before = list(self.calls[other])
                selected_before = len(self.calls[pid])
                response = client.request(operation, arguments, pid=pid)
                self.assertEqual(response, {"ok": True, "data": {"pid": pid, "operation": operation, "arguments": arguments}})
                self.assertEqual(len(self.calls[pid]), selected_before + 1)
                self.assertEqual(self.calls[other], other_before)

    def test_other_instance_token_cannot_authorize_selected_instance(self):
        self.write_metadata(123, {**self.metadata[123], "token": self.metadata[456]["token"]})
        response = client.request("execute_python", {"code": "result = 42"}, pid=123)
        self.assertEqual(response["error"]["code"], "unauthorized")
        self.assertEqual(self.calls, {123: [], 456: []})
        self.assertEqual(client.request("scene_info", pid=456)["data"]["pid"], 456)
        self.assertEqual(self.calls[123], [])

    def test_closed_or_stale_selection_never_falls_back_to_live_instance(self):
        self.stop_instance(123)
        for pid in (123, 999):
            if pid == 999:
                self.write_metadata(pid, {**self.metadata[123], "pid": pid})
            response = client.request("execute_mel", {"code": 'print("must not reach survivor");'}, pid=pid)
            self.assertEqual(response["error"]["code"], "connection_error")
            self.assertFalse(response["error"]["execution_uncertain"])
            self.assertEqual(self.calls, {123: [], 456: []})
            self.assertEqual(client.request("scene_info")["error"]["code"], "session_selection")
        self.assertEqual(client.request("scene_info", pid=987)["error"]["code"], "session_selection")
        self.assertEqual(self.calls, {123: [], 456: []})
        self.assertEqual(client.request("scene_info", pid=456)["data"]["pid"], 456)
        self.assertEqual(self.calls[123], [])
        self.assertEqual(self.calls[456], [("scene_info", {})])


if __name__ == "__main__":
    unittest.main()
