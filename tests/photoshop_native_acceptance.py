"""Opt-in real Windows Photoshop + Codex installation acceptance.

Creates and closes only its own unsaved test document. Requires an already open
Photoshop and --run. Does not install Adobe components or change registrations.
"""
import argparse
from contextlib import nullcontext
import json
import os
from pathlib import Path
import sys
import uuid

from codex_plugin_smoke import AppServer, ROOT, plugin_read


def payload(response):
    assert not response.get("isError"), response
    value = response.get("structuredContent")
    if not isinstance(value, dict):
        value = next(json.loads(c["text"]) for c in response["content"] if c["type"] == "text")
    assert value.get("ok"), value
    return value


def run(binary):
    import pythoncom
    import win32com.client.dynamic
    sys.path.insert(0, str(ROOT / "plugins/photoshop-control/server"))
    import native
    candidates = [s for s in native.discover() if s["status"] == "available" and s["version"].startswith("26.")]
    assert len(candidates) == 1, "Need exactly one available PS 2025 instance"
    selected = candidates[0]
    before_reg = native.installations()
    pythoncom.CoInitialize()
    app = win32com.client.dynamic.Dispatch(
        pythoncom.GetActiveObject(selected["prog_id"]).QueryInterface(pythoncom.IID_IDispatch))
    assert os.path.normcase(os.path.abspath(str(app.Path))) == os.path.normcase(os.path.dirname(selected["executable"]))
    assert str(app.Version).split(".")[:2] == selected["version"].split(".")[:2]
    native.select(native.discover(), selected["session_id"])
    token = "BubbleNativeAcceptance_" + uuid.uuid4().hex
    doc_id = None
    installed_by_test = False
    thread_id = None
    original_active = None
    server = AppServer(binary)
    catalog = ROOT / ".agents/plugins/marketplace.json"
    try:
        server.initialize()
        detail = plugin_read(server, catalog, "photoshop-control")
        assert not detail["summary"]["installed"], "Uninstall existing PS Codex plugin first; acceptance must verify clean lifecycle"
        installed_by_test = True
        server.request("plugin/install", {"marketplacePath": str(catalog), "pluginName": "photoshop-control"}, timeout=120)
        detail = plugin_read(server, catalog, "photoshop-control")
        assert detail["summary"]["installed"] and detail["summary"]["localVersion"] == "0.2.0", detail["summary"]
        print("PASS actual Codex install 0.2.0", flush=True)
        with nullcontext(str(ROOT)) as workspace:
            thread_id = server.request("thread/start", {
                "cwd": workspace, "ephemeral": True, "sandbox": "read-only", "approvalPolicy": "never",
            }, timeout=120)["thread"]["id"]
            status = server.request("mcpServerStatus/list", {
                "threadId": thread_id, "serverName": "photoshop", "detail": "toolsAndAuthOnly",
            }, timeout=120)
            row = next(r for r in status["data"] if r["name"] == "photoshop")
            assert not row.get("toolsError") and len(row["tools"]) == 7, row
            assert row["pluginId"] == detail["summary"]["id"]
            def call(tool, **arguments):
                return payload(server.request("mcpServer/tool/call", {
                    "threadId": thread_id, "server": "photoshop", "tool": tool, "arguments": arguments,
                }, timeout=120))
            sessions = call("photoshop_list_sessions")
            assert any(s["session_id"] == selected["session_id"] and s["status"] == "available" for s in sessions["data"]), sessions
            original = call("photoshop_scene_info", session_id=selected["session_id"])["data"]
            original_ids = sorted(d["id"] for d in original["documents"])
            original_active = original["active_document_id"]
            print("PASS installed MCP connects real Photoshop " + original["version"], flush=True)
            doc_id = int(app.DoJavaScript(
                'app.documents.add(UnitValue(16,"px"),UnitValue(16,"px"),72,' + json.dumps(token) + ').id;'))
            inspected = call("photoshop_inspect_document", session_id=selected["session_id"], document_id=doc_id)["data"]
            assert inspected["name"] == token and inspected["width"] == 16, inspected
            result = call("photoshop_execute_script", session_id=selected["session_id"], document_id=doc_id,
                          code='app.activeDocument.activeLayer.name="Bubble verified";app.activeDocument.activeLayer.name;')
            assert result["data"] == "Bubble verified", result
            inspected = call("photoshop_inspect_document", session_id=selected["session_id"], document_id=doc_id)["data"]
            assert inspected["layers"][0]["name"] == "Bubble verified", inspected
            print("PASS real temporary document inspect / execute / read-back", flush=True)
            close_fixture(app, doc_id, token)
            doc_id = None
            restore_active(app, original_active)
            after = call("photoshop_scene_info", session_id=selected["session_id"])["data"]
            assert sorted(d["id"] for d in after["documents"]) == original_ids
            print("PASS temporary document closed without save; original document IDs preserved", flush=True)
    finally:
        try:
            if doc_id is not None:
                close_fixture(app, doc_id, token)
            restore_active(app, original_active)
        finally:
            try:
                if installed_by_test:
                    server.request("plugin/uninstall", {"pluginId": detail["summary"]["id"]}, timeout=120)
                    assert not plugin_read(server, catalog, "photoshop-control")["summary"]["installed"]
                    print("PASS official Codex uninstall", flush=True)
                if thread_id:
                    server.request("thread/unsubscribe", {"threadId": thread_id})
                assert native.installations() == before_reg
                print("PASS native registration unchanged", flush=True)
            finally:
                server.close()
                pythoncom.CoUninitialize()


def close_fixture(app, doc_id, token):
    result = app.DoJavaScript(
        '(function(){for(var i=0;i<app.documents.length;i++){var d=app.documents[i];'
        f'if(d.id==={doc_id}&&d.name==={json.dumps(token)})'
        '{d.close(SaveOptions.DONOTSAVECHANGES);return "closed";}}return "missing";})();')
    assert result == "closed", "Own fixture cleanup needs attention"


def restore_active(app, doc_id):
    if doc_id is not None:
        result = app.DoJavaScript(
            '(function(){for(var i=0;i<app.documents.length;i++){var d=app.documents[i];'
            f'if(d.id==={doc_id})'
            '{app.activeDocument=d;return "restored";}}return "missing";})();')
        assert result == "restored", "Original active document no longer exists"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", required=True)
    parser.add_argument("--codex", required=True)
    args = parser.parse_args()
    run(args.codex)
