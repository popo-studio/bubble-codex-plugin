"""Opt-in real Codex MCP acceptance from zero PS documents; no direct COM/UI."""
import argparse
import json
import uuid
from pathlib import Path
from codex_plugin_smoke import AppServer, ROOT, plugin_read


def payload(response):
    assert not response.get("isError"), response
    value = response.get("structuredContent")
    if not isinstance(value, dict):
        value = next(json.loads(c["text"]) for c in response["content"] if c["type"] == "text")
    assert value.get("ok"), value
    return value


def run(binary, catalog):
    server = AppServer(binary)
    thread_id = None
    sid = None
    owned = set()
    started_empty = False
    token = "Bubble512_" + uuid.uuid4().hex
    output = ROOT / ".test-runtime" / (token + ".psd")
    output.parent.mkdir(exist_ok=True)
    assert not output.exists()
    try:
        server.initialize()
        server.request("plugin/install", {"marketplacePath": str(catalog), "pluginName": "photoshop-control"}, timeout=120)
        detail = plugin_read(server, catalog, "photoshop-control")
        assert detail["summary"]["installed"] and detail["summary"]["localVersion"] == "0.2.1", detail["summary"]
        print("PASS actual Codex install 0.2.1", flush=True)
        thread_id = server.request("thread/start", {
            "cwd": str(ROOT), "ephemeral": True, "sandbox": "read-only", "approvalPolicy": "never",
        }, timeout=120)["thread"]["id"]
        status = server.request("mcpServerStatus/list", {
            "threadId": thread_id, "serverName": "photoshop", "detail": "toolsAndAuthOnly",
        }, timeout=120)
        row = next(r for r in status["data"] if r["name"] == "photoshop")
        assert not row.get("toolsError") and len(row["tools"]) == 10, row
        assert row["pluginId"] == detail["summary"]["id"]

        def call(tool, **arguments):
            return payload(server.request("mcpServer/tool/call", {
                "threadId": thread_id, "server": "photoshop", "tool": tool, "arguments": arguments,
            }, timeout=120))

        sessions = call("photoshop_list_sessions")
        sid = sessions["selection"]["selected"]
        assert sid, sessions
        original = call("photoshop_scene_info", session_id=sid)["data"]
        assert original["documents"] == [], "Save/close existing documents before zero-document acceptance"
        started_empty = True
        print("PASS real Photoshop starts with zero documents", flush=True)
        created = call("photoshop_create_document", session_id=sid, width=512, height=512, name=token)["data"]
        owned.add(created["id"])
        doc_id = created["id"]
        inspected = call("photoshop_inspect_document", session_id=sid, document_id=doc_id)["data"]
        assert inspected["width"] == inspected["height"] == 512 and inspected["name"] == token, inspected
        print("PASS plugin creates and reads back 512x512 document", flush=True)
        other = call("photoshop_create_document", session_id=sid, width=16, height=16, name=token + "_activation")["data"]
        owned.add(other["id"])
        call("photoshop_activate_document", session_id=sid, document_id=doc_id)
        assert call("photoshop_scene_info", session_id=sid)["data"]["active_document_id"] == doc_id
        code = 'app.activeDocument.saveAs(new File(' + json.dumps(output.as_posix()) + '),new PhotoshopSaveOptions(),true,Extension.LOWERCASE);true;'
        assert call("photoshop_execute_script", session_id=sid, document_id=doc_id, code=code)["data"] is True
        assert output.is_file()
        close_owned(call, sid, doc_id)
        owned.remove(doc_id)
        reopened = call("photoshop_open_file", session_id=sid, path=str(output))["data"]
        owned.add(reopened["id"])
        assert reopened["width"] == reopened["height"] == 512
        assert Path(reopened["path"]).resolve() == output.resolve(), reopened
        print("PASS plugin activates explicit document, saves own PSD, closes and opens file", flush=True)
    finally:
        try:
            if sid and started_empty:
                for doc_id in list(owned):
                    close_owned(call, sid, doc_id)
                    owned.remove(doc_id)
                assert call("photoshop_scene_info", session_id=sid)["data"]["documents"] == []
                print("PASS plugin cleanup; zero documents restored", flush=True)
            if thread_id:
                server.request("thread/unsubscribe", {"threadId": thread_id})
        finally:
            server.close()
    print("PASS all real acceptance steps used installed plugin tools; plugin retained", flush=True)


def close_owned(call, sid, doc_id):
    call("photoshop_activate_document", session_id=sid, document_id=doc_id)
    call("photoshop_execute_script", session_id=sid, document_id=doc_id,
         code="app.activeDocument.close(SaveOptions.DONOTSAVECHANGES);true;")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", required=True)
    parser.add_argument("--codex", required=True)
    parser.add_argument("--catalog", type=Path, default=ROOT / ".agents/plugins/marketplace.json")
    args = parser.parse_args()
    run(args.codex, args.catalog)
