"""Opt-in native Photoshop workflow test via installed Codex MCP tools only."""
import argparse
import json
from pathlib import Path
import struct
import uuid
from codex_plugin_smoke import AppServer, ROOT, plugin_read
from photoshop_document_acceptance import payload


def refusal(response, message):
    assert not response.get("isError"), response
    data = response.get("structuredContent")
    if not isinstance(data, dict):
        data = json.loads(next(c["text"] for c in response["content"] if c["type"] == "text"))
    assert data.get("ok") is False and message in data.get("error", {}).get("message", ""), data


def run(binary, catalog):
    server = AppServer(binary)
    thread = None
    sid = None
    owned = set()
    original = None
    output = ROOT / ".test-runtime" / ("PSWorkflow_" + uuid.uuid4().hex)
    output.mkdir(parents=True)
    try:
        server.initialize()
        server.request("plugin/install", {"marketplacePath": str(catalog), "pluginName": "photoshop-control"}, timeout=120)
        detail = plugin_read(server, catalog, "photoshop-control")
        assert detail["summary"]["localVersion"] == "0.3.0"
        thread = server.request("thread/start", {
            "cwd": str(ROOT), "ephemeral": True, "sandbox": "read-only", "approvalPolicy": "never",
        }, timeout=120)["thread"]["id"]
        status = server.request("mcpServerStatus/list", {
            "threadId": thread, "serverName": "photoshop", "detail": "toolsAndAuthOnly",
        }, timeout=120)
        row = next(r for r in status["data"] if r["name"] == "photoshop")
        assert not row.get("toolsError") and len(row["tools"]) == 23, row
        assert row["pluginId"] == detail["summary"]["id"]

        def raw(tool, **arguments):
            return server.request("mcpServer/tool/call", {
                "threadId": thread, "server": "photoshop", "tool": "photoshop_" + tool,
                "arguments": arguments,
            }, timeout=120)

        def call(tool, **arguments):
            return payload(raw(tool, **arguments))["data"]

        sessions = payload(raw("list_sessions"))
        sid = sessions["selection"]["selected"]
        assert sid, sessions
        original = call("scene_info", session_id=sid)
        doc = call("create_document", session_id=sid, width=512, height=512, name=output.name)
        did = doc["id"]
        owned.add(did)

        def op(tool, **arguments):
            call("activate_document", session_id=sid, document_id=did)
            return call(tool, session_id=sid, document_id=did, **arguments)

        def inspect():
            return op("inspect_document")

        def flat(rows):
            result = []
            for row in rows:
                result.append(row)
                result.extend(flat(row.get("layers", [])))
            return result

        # Filled out against the tool schemas; every operation targets our new document.
        pixel = op("create_layer", kind="pixel", name="Paint")
        text = op("create_layer", kind="text", name="Caption", text="Bubble test", font_size=24)
        group = op("create_layer", kind="group", name="Group")
        text_id = text["layer_id"]
        op("update_layer", layer_id=text_id, name="Title", text="Verified", opacity=65, visible=False)
        layers = flat(inspect()["layers"])
        title = next(l for l in layers if l["layer_id"] == text_id)
        assert title["name"] == "Title" and title["visible"] is False and abs(title["opacity"] - 65) < 0.2, title
        assert title["text"] == "Verified", title
        op("update_layer", layer_id=text_id, text="Still hidden")
        title = next(l for l in flat(inspect()["layers"]) if l["layer_id"] == text_id)
        assert title["text"] == "Still hidden" and title["visible"] is False, title
        op("update_layer", layer_id=text_id, visible=True)
        op("select_layer", layer_id=text_id)
        assert inspect()["active_layer_id"] == text_id
        op("translate_layer", layer_id=text_id, x=10, y=12)
        duplicate = op("duplicate_layer", layer_id=text_id)
        duplicate_id = duplicate["layer_id"]
        op("delete_layer", layer_id=duplicate_id)
        assert duplicate_id not in [l["layer_id"] for l in flat(inspect()["layers"])]
        print("PASS real pixel/text/group layers, edit/select/translate/duplicate/delete", flush=True)
        op("resize_image", width=256, height=256)
        assert inspect()["width"] == inspect()["height"] == 256
        op("resize_canvas", width=300, height=280)
        assert (inspect()["width"], inspect()["height"]) == (300, 280)
        op("crop_document", left=0, top=0, right=200, bottom=180)
        op("rotate_document", angle=90)
        assert (inspect()["width"], inspect()["height"]) == (180, 200)
        print("PASS real resize/image canvas/crop/rotation dimensions", flush=True)
        refused_close = raw("close_document", session_id=sid, document_id=did)
        refusal(refused_close, "unsaved changes")
        assert inspect()["id"] == did
        psd, png, jpg = [output / ("result" + ext) for ext in (".psd", ".png", ".jpg")]
        op("save_document", path=str(psd))
        assert psd.read_bytes()[:4] == b"8BPS"
        before = inspect()
        op("export_document", path=str(png), format="png")
        op("export_document", path=str(jpg), format="jpeg")
        after = inspect()
        assert before == after, "Export changed source document/layers"
        png_bytes = png.read_bytes()
        assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"
        assert struct.unpack(">II", png_bytes[16:24]) == (180, 200)
        assert jpg.read_bytes()[:2] == b"\xff\xd8"
        print("PASS real PSD/PNG/JPEG output; export preserves source document", flush=True)
        existing = psd.read_bytes()
        refused = raw("save_document", session_id=sid, document_id=did, path=str(psd))
        refusal(refused, "Output already exists")
        assert psd.read_bytes() == existing
        op("close_document")
        owned.remove(did)
        reopened = call("open_file", session_id=sid, path=str(psd))
        owned.add(reopened["id"])
        assert (reopened["width"], reopened["height"]) == (180, 200)
        print("PASS overwrite refusal and saved document close/reopen", flush=True)
    finally:
        try:
            if sid and original is not None:
                for did in list(owned):
                    call("activate_document", session_id=sid, document_id=did)
                    call("close_document", session_id=sid, document_id=did, discard_changes=True)
                    owned.remove(did)
                if original["active_document_id"] is not None:
                    call("activate_document", session_id=sid, document_id=original["active_document_id"])
                after = call("scene_info", session_id=sid)
                assert sorted(d["id"] for d in after["documents"]) == sorted(d["id"] for d in original["documents"])
                print("PASS original documents preserved; owned fixtures closed", flush=True)
            if thread:
                server.request("thread/unsubscribe", {"threadId": thread})
        finally:
            server.close()
    print("PASS real Codex workflow; output: " + str(output), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", required=True)
    parser.add_argument("--codex", required=True)
    parser.add_argument("--catalog", type=Path, default=ROOT / ".agents/plugins/marketplace.json")
    args = parser.parse_args()
    run(args.codex, args.catalog)
