"""Validate packages with Codex's own loader, optionally its installed MCP runtime.

Read-only package parsing is the default. Set CODEX_BIN (or --codex) to the
desktop app's bundled executable, not an unrelated older CLI on PATH.
--install explicitly permits real Codex plugin installation. Existing plugins
remain installed and updated; plugins absent before this test are uninstalled
through Codex in finally. Software-side bridges are never installed or changed.
The test creates only an ephemeral runtime thread and never starts a model turn.
"""
import argparse
from collections import deque
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import tempfile
import threading
import time


ROOT = Path(__file__).resolve().parents[1]


class AppServer:
    def __init__(self, binary):
        self.messages = queue.Queue()
        self.errors = deque(maxlen=100)
        self.sequence = 0
        self.process = subprocess.Popen(
            [binary, "app-server", "--stdio"], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace", cwd=ROOT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()

    def _read_stdout(self):
        for line in self.process.stdout:
            try:
                self.messages.put(json.loads(line))
            except json.JSONDecodeError:
                self.errors.append("Non-JSON app-server output")
        self.messages.put({"eof": True})

    def _read_stderr(self):
        for line in self.process.stderr:
            self.errors.append(line.rstrip())

    def send(self, message):
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()

    def request(self, method, params, timeout=60):
        self.sequence += 1
        request_id = self.sequence
        self.send({"id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        while True:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Codex {method} did not answer within {timeout}s")
            try:
                row = self.messages.get(timeout=max(0.01, deadline - time.monotonic()))
            except queue.Empty:
                raise TimeoutError(f"Codex {method} did not answer within {timeout}s") from None
            if row.get("eof"):
                raise RuntimeError(f"Codex exited during {method}")
            if "method" in row and "id" in row:
                # A smoke test must never accept an unexpected approval or
                # elicitation request, including from unrelated enabled plugins.
                self.send({"id": row["id"], "error": {
                    "code": -32601, "message": "Not supported by the smoke test client"}})
                continue
            if row.get("id") != request_id:
                continue
            if "error" in row:
                raise RuntimeError(f"{method}: {row['error']}")
            return row["result"]

    def initialize(self):
        result = self.request("initialize", {
            "clientInfo": {"name": "bubble-plugin-regression", "version": "1.0"},
            "capabilities": {"experimentalApi": True},
        })
        self.send({"method": "initialized"})
        return result

    def close(self):
        # Closing our own stdio lets app-server release its thread/MCP resources.
        if self.process.poll() is None:
            self.process.stdin.close()
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)


def plugin_read(server, catalog, name):
    return server.request("plugin/read", {
        "marketplacePath": str(catalog), "pluginName": name,
    })["plugin"]


def assert_session_result(response, app):
    """Check the application result without exposing scene paths or tokens."""
    assert isinstance(response.get("content"), list), (app, "missing MCP content")
    assert not response.get("isError"), (app, "MCP tool reported an error")
    payload = response.get("structuredContent")
    if not isinstance(payload, dict):
        payload = None
        for item in response["content"]:
            if item.get("type") == "text":
                try:
                    candidate = json.loads(item.get("text", ""))
                except (json.JSONDecodeError, TypeError):
                    continue
                if isinstance(candidate, dict):
                    payload = candidate
                    break
    assert isinstance(payload, dict), (app, "missing application result")
    assert payload.get("ok") is True, (app, "session discovery failed")
    assert isinstance(payload.get("data"), list), (app, "invalid session list")


def check_loader(server, catalog, entries, workspace):
    details = {}
    for entry in entries:
        name = entry["name"]
        expected = name.removesuffix("-control")
        detail = plugin_read(server, catalog, name)
        assert detail["mcpServers"] == [expected], (name, detail["mcpServers"])
        assert len(detail["skills"]) >= 2, name
        details[name] = detail
        print(f"PASS {name}: Codex discovered {expected} MCP and skills", flush=True)

    # Reproduce the released failure with the real loader, not a hand-written
    # JSON validator or an MCP SDK which bypasses plugin path restrictions.
    negative = workspace / "legacy-cwd"
    package = negative / "plugins/maya-control"
    shutil.copytree(ROOT / "plugins/maya-control", package, ignore=shutil.ignore_patterns(
        ".venv", "__pycache__", "*.pyc", ".test-runtime", ".cache", "dist"))
    for filename in ("mcp.json", ".mcp.json"):
        path = package / filename
        content = json.loads(path.read_text(encoding="utf-8"))
        for config in content["mcpServers"].values():
            config["cwd"] = "/"
        path.write_text(json.dumps(content), encoding="utf-8")
    negative_catalog = negative / ".agents/plugins/marketplace.json"
    negative_catalog.parent.mkdir(parents=True)
    negative_catalog.write_text(json.dumps({
        "name": "bubble-cwd-regression", "plugins": [next(e for e in entries if e["name"] == "maya-control")],
    }), encoding="utf-8")
    rejected = plugin_read(server, negative_catalog, "maya-control")
    assert rejected["mcpServers"] == [], rejected["mcpServers"]
    assert len(rejected["skills"]) >= 2
    print("PASS legacy cwd=/ control: Codex reproduces skills-only loading", flush=True)
    return details


def check_installed_runtime(server, catalog, entries, details, workspace):
    added = []
    ephemeral_id = None
    try:
        for entry in entries:
            name = entry["name"]
            summary = details[name]["summary"]
            # Register cleanup before the request in case installation partially
            # succeeds and the response is lost. Existing installs are preserved.
            if not summary["installed"]:
                added.append(summary["id"])
            server.request("plugin/install", {
                "marketplacePath": str(catalog), "pluginName": name,
            }, timeout=120)
            installed = plugin_read(server, catalog, name)
            assert installed["summary"]["installed"], name
            expected_version = json.loads((ROOT / "plugins" / name / "plugin.json").read_text(encoding="utf-8"))["version"]
            assert installed["summary"]["localVersion"] == expected_version, (name, "wrong installed version")
            print(f"PASS {name}: Codex installation", flush=True)

        thread = server.request("thread/start", {
            "cwd": str(workspace), "ephemeral": True,
            "sandbox": "read-only", "approvalPolicy": "never",
        }, timeout=120)
        ephemeral_id = thread["thread"]["id"]
        for entry in entries:
            name = entry["name"]
            app = name.removesuffix("-control")
            status = server.request("mcpServerStatus/list", {
                "threadId": ephemeral_id, "serverName": app,
                "detail": "toolsAndAuthOnly",
            }, timeout=120)
            row = next((r for r in status["data"] if r["name"] == app), None)
            assert row is not None, (app, "not registered")
            assert row.get("pluginId") == details[name]["summary"]["id"], (app, "wrong plugin source")
            assert not row.get("toolsError"), (app, row.get("toolsError"))
            tool = f"{app}_list_sessions"
            tools = row["tools"]
            assert any(t.get("name") == tool for t in tools.values()), (app, list(tools))
            response = server.request("mcpServer/tool/call", {
                "threadId": ephemeral_id, "server": app, "tool": tool, "arguments": {},
            }, timeout=60)
            assert_session_result(response, app)
            print(f"PASS {name}: Codex listed {len(tools)} tools and called {tool}", flush=True)
    finally:
        # Exercise official uninstall while the test runtime may still hold its
        # MCP connections. Never manually delete real installed package files.
        cleanup_errors = []
        for plugin_id in reversed(added):
            try:
                server.request("plugin/uninstall", {"pluginId": plugin_id}, timeout=60)
                name = plugin_id.split("@", 1)[0]
                assert not plugin_read(server, catalog, name)["summary"]["installed"], (name, "still installed after uninstall")
                print(f"RESTORED previously absent plugin: {plugin_id}", flush=True)
            except Exception as exc:
                cleanup_errors.append(f"{plugin_id}: {exc}")
        if ephemeral_id:
            try:
                server.request("thread/unsubscribe", {"threadId": ephemeral_id})
            except Exception as exc:
                cleanup_errors.append(f"ephemeral thread cleanup: {exc}")
        if cleanup_errors:
            raise RuntimeError("Cleanup needs attention: " + "; ".join(cleanup_errors))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex", default=os.environ.get("CODEX_BIN") or shutil.which("codex"))
    parser.add_argument("--install", action="store_true", help="Explicitly allow real Codex install/update and cleanup")
    args = parser.parse_args()
    if not args.codex:
        parser.error("Set CODEX_BIN or --codex to the desktop's bundled Codex executable")
    catalog = ROOT / ".agents/plugins/marketplace.json"
    entries = json.loads(catalog.read_text(encoding="utf-8"))["plugins"]
    parent = ROOT / ".test-runtime"
    parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="codex-plugin-", dir=parent) as temporary:
        workspace = Path(temporary)
        server = AppServer(args.codex)
        try:
            server.initialize()
            details = check_loader(server, catalog, entries, workspace)
            if args.install:
                check_installed_runtime(server, catalog, entries, details, workspace)
        finally:
            server.close()


if __name__ == "__main__":
    main()
