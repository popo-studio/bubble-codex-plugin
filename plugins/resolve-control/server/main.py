"""Bubble Resolve MCP. No Resolve dependency is imported into the MCP server."""
import atexit
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Literal
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import StrictBool, StrictInt
from native import discover, failure, sdk_path, select

_runtime = tempfile.TemporaryDirectory(prefix="bubble-resolve-worker-")
atexit.register(_runtime.cleanup)
for _name in ("worker.py", "native.py", "operations.py"):
    (Path(_runtime.name) / _name).write_bytes(Path(__file__).with_name(_name).read_bytes())
mcp = FastMCP("Bubble DaVinci Resolve")
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True)


def call(operation, session_id=None, timeout=30, **arguments):
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 0 < timeout <= 120:
        return failure("invalid_timeout", "Timeout must be finite and in (0,120]")
    try:
        selected = select(discover(), session_id)
        request = {"operation": operation, "session_id": selected["session_id"], "expires_at": time.time() + timeout, "arguments": arguments}
        payload = json.dumps(request, allow_nan=False)
        if len(payload.encode("utf-8")) > 262144:
            raise ValueError("Request exceeds 256 KiB")
        with tempfile.TemporaryDirectory(prefix="bubble-resolve-call-") as directory:
            reply = Path(directory) / "reply.json"
            result = subprocess.run([sys.executable, "-B", str(Path(_runtime.name) / "worker.py"), str(reply)], input=payload.encode("utf-8"), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if result.returncode or not reply.is_file():
                return failure("worker_failed", "SDK worker failed. Check Studio, 64-bit Python and Local scripting setting. A requested write may have completed; never retry automatically.")
            if reply.stat().st_size > 2 * 1024 * 1024:
                raise ValueError("Worker response exceeds 2 MiB")
            return json.loads(reply.read_text(encoding="utf-8"))
    except subprocess.TimeoutExpired:
        return failure("timeout_outcome_unknown", "Worker timed out and was stopped. Resolve may still finish an operation already sent. Inspect state; never automatically retry.")
    except Exception as exc:
        return failure("connection_error", str(exc))


@mcp.tool(annotations=READ)
def resolve_setup_status() -> dict:
    """Read-only prerequisites. Works without Resolve installed; never imports its native library, launches an app or writes preferences."""
    try:
        path = sdk_path()
        return {"ok": True, "data": {"platform": sys.platform, "supported_platform": sys.platform == "win32", "sdk_module": str(path), "sdk_module_present": path.is_file(),
                "software_bridge_required": False, "software_files_installed": [], "required_version": "DaVinci Resolve Studio 21+", "requires_external_scripting": "Local",
                "instructions": "Open Resolve Studio normally and enable Preferences > System > General > External scripting using: Local. Restart if Resolve requests it. After setup the plugin connects automatically; no copied code or host bridge is needed. Free edition is not supported for external scripting. No preferences were changed."}}
    except Exception as exc:
        return failure("setup_error", str(exc))


@mcp.tool(annotations=READ)
def resolve_install_bridge(confirmed: StrictBool = False) -> dict:
    """Compatibility/status only: this native mode installs no Resolve-side bridge and does not enable scripting or bypass Studio requirements."""
    return resolve_setup_status()


@mcp.tool(annotations=READ)
def resolve_uninstall_bridge(confirmed: StrictBool = False) -> dict:
    """Zero-install lifecycle: no Resolve files/settings to remove. Uninstall Bubble Resolve in Codex; SDK belongs to Blackmagic and is preserved."""
    return {"ok": True, "data": {"removed_files": [], "software_bridge_required": False, "note": "Remove Bubble Resolve in Codex. No Resolve-side files were installed, and the official SDK and preferences are not modified."}}


@mcp.tool(annotations=READ)
def resolve_list_sessions(project_name: str | None = None) -> dict:
    """List Resolve processes; exact project-name matching only. Multiple processes are listed but refused because the native API cannot target PID. Never launches Resolve."""
    try:
        found = discover()
        for row in found:
            if row["status"] == "available":
                response = call("project_info", row["session_id"])
                if response.get("ok"):
                    row.update(response["data"])
                else:
                    row.update(status="unavailable", error=response.get("error"))
        matching = [r["session_id"] for r in found if r["status"] == "available" and (project_name is None or str((r.get("project") or {}).get("name", "")).casefold() == project_name.casefold())]
        incomplete = any(r["status"] != "available" for r in found)
        return {"ok": True, "data": found, "selection": {"status": "incomplete" if incomplete else "unique" if len(matching) == 1 else "not_found",
                "selected": matching[0] if len(matching) == 1 and not incomplete else None}, "note": "Select a session_id; restarted processes invalidate it. Keep only the intended Resolve instance open when multiple processes are listed."}
    except Exception as exc:
        return failure("discovery_failed", str(exc))


@mcp.tool(annotations=READ)
def resolve_project_info(session_id: str | None = None) -> dict:
    """Read current project unique ID/name/settings, timelines and current library folder's project names. Never switches or opens projects."""
    return call("project_info", session_id)


@mcp.tool(annotations=READ)
def resolve_media_info(project_id: str, folder_id: str | None = None, session_id: str | None = None) -> dict:
    """Read up to 1000 media clips and immediate child bins in the selected folder (root by default). Reports truncation; not a full dependency audit."""
    return call("media_info", session_id, project_id=project_id, folder_id=folder_id)


@mcp.tool(annotations=READ)
def resolve_timeline_info(project_id: str, timeline_id: str, session_id: str | None = None) -> dict:
    """Read selected timeline tracks/clips/markers/settings without activating it. Up to 1000 clips; explicit unique IDs prevent same-name confusion."""
    return call("timeline_info", session_id, project_id=project_id, timeline_id=timeline_id)


@mcp.tool(annotations=READ)
def resolve_render_info(project_id: str, session_id: str | None = None) -> dict:
    """Read render queue/presets/current format+codec+mode/status. Does not add jobs, start rendering or export; not all Deliver UI settings are queryable."""
    return call("render_info", session_id, project_id=project_id)


@mcp.tool(annotations=WRITE)
def resolve_create_project(name: str, confirmed: StrictBool = False, session_id: str | None = None) -> dict:
    """Preview then create a project in the current library folder only when NO project is open. Never silently closes/saves/discards another project. Name must be unique."""
    return call("create_project", session_id, name=name, confirmed=confirmed)


@mcp.tool(annotations=WRITE)
def resolve_open_project(name: str, confirmed: StrictBool = False, session_id: str | None = None) -> dict:
    """Preview then open exact project name from current library folder. Refuses if any project is already open; save/close it manually first. No library/folder switching."""
    return call("open_project", session_id, name=name, confirmed=confirmed)


@mcp.tool(annotations=WRITE)
def resolve_save_project(project_id: str, confirmed: StrictBool = False, session_id: str | None = None) -> dict:
    """Preview then explicitly save the current project to its existing library. No Save As, export or overwrite of another project."""
    return call("save_project", session_id, project_id=project_id, confirmed=confirmed)


@mcp.tool(annotations=WRITE)
def resolve_import_media(project_id: str, folder_id: str, paths: list[str], confirmed: StrictBool = False, session_id: str | None = None) -> dict:
    """Preview then import explicit existing files into a selected bin; leaves destination bin active. Never imports directories recursively, relinks, deletes or copies source files. Resolve may group image frames."""
    return call("import_media", session_id, project_id=project_id, folder_id=folder_id, paths=paths, confirmed=confirmed)


@mcp.tool(annotations=WRITE)
def resolve_create_timeline(project_id: str, folder_id: str, name: str, media_ids: list[str] | None = None, confirmed: StrictBool = False, session_id: str | None = None) -> dict:
    """Preview then create an empty timeline or one from explicitly ordered media IDs in the selected bin. Unique name required. Leaves bin active; Resolve may activate new timeline. Never saves/renders."""
    return call("create_timeline", session_id, project_id=project_id, folder_id=folder_id, name=name, media_ids=media_ids, confirmed=confirmed)


@mcp.tool(annotations=WRITE)
def resolve_select_timeline(project_id: str, timeline_id: str, confirmed: StrictBool = False, session_id: str | None = None) -> dict:
    """Preview then activate exact timeline unique ID; never chooses by ambiguous names or switches project."""
    return call("select_timeline", session_id, project_id=project_id, timeline_id=timeline_id, confirmed=confirmed)


@mcp.tool(annotations=WRITE)
def resolve_move_media(project_id: str, folder_id: str, destination_folder_id: str, media_ids: list[str], confirmed: StrictBool = False, session_id: str | None = None) -> dict:
    """Preview then move explicitly identified media-pool entries between bins. Does not move/delete filesystem media or relink sources."""
    return call("move_media", session_id, project_id=project_id, folder_id=folder_id, destination_folder_id=destination_folder_id, media_ids=media_ids, confirmed=confirmed)


@mcp.tool(annotations=READ)
def resolve_missing_media(project_id: str, folder_id: str | None = None, session_id: str | None = None) -> dict:
    """Check literal absolute file paths from up to 1000 clips in one bin. Sequence/generated/empty paths remain unresolved; no relinking or complete offline verdict."""
    return call("missing_media", session_id, project_id=project_id, folder_id=folder_id)


@mcp.tool(annotations=WRITE)
def resolve_create_bin(project_id: str, folder_id: str, name: str, confirmed: StrictBool = False, session_id: str | None = None) -> dict:
    """Preview then create a media bin in an explicitly selected parent. Requires user authorization; duplicate names are refused. Does not save or switch project."""
    return call("create_bin", session_id, project_id=project_id, folder_id=folder_id, name=name, confirmed=confirmed)


@mcp.tool(annotations=WRITE)
def resolve_add_marker(project_id: str, timeline_id: str, frame: StrictInt, name: str, color: str = "Blue", note: str = "", duration: StrictInt = 1, confirmed: StrictBool = False, session_id: str | None = None) -> dict:
    """Preview then add a marker at a timeline-relative frame. Existing marker at that frame is never replaced. No implicit timeline switch or saving."""
    return call("add_marker", session_id, project_id=project_id, timeline_id=timeline_id, frame=frame, name=name, color=color, note=note, duration=duration, confirmed=confirmed)


@mcp.tool(annotations=WRITE)
def resolve_set_render_settings(project_id: str, settings: dict, confirmed: StrictBool = False, session_id: str | None = None) -> dict:
    """Preview then apply documented TargetDir/CustomName/frame-range/export flags/dimensions/frame-rate settings only. Does NOT queue/render/export. SDK validates values."""
    return call("set_render_settings", session_id, project_id=project_id, settings=settings, confirmed=confirmed)


@mcp.tool(annotations=WRITE)
def resolve_execute_python(project_id: str, code: str, confirmed: StrictBool = False, session_id: str | None = None, timeout: float = 30) -> dict:
    """Preview then execute explicitly authorized external Python with official resolve/project objects and full user privileges. Return result; stdout capped at 64KiB. Not an in-editor eval. Never auto-render/export/delete/close projects. Process and project checked before execution; concurrent manual edits are not locked. Errors/timeouts must never trigger automatic retry."""
    return call("execute_python", session_id, timeout=timeout, project_id=project_id, code=code, confirmed=confirmed)


@mcp.tool(annotations=WRITE)
def resolve_manage_timeline(project_id: str, timeline_id: str, action: Literal['rename','duplicate'], name: str, confirmed: StrictBool = False, session_id: str | None = None) -> dict:
    """Preview then rename/duplicate an exact timeline ID with a unique name. Duplicate returns a new ID; Resolve may activate it. Does not save, delete source, or render."""
    return call('manage_timeline',session_id,project_id=project_id,timeline_id=timeline_id,action=action,name=name,confirmed=confirmed)


@mcp.tool(annotations=WRITE)
def resolve_track_state(project_id: str, timeline_id: str, track_type: Literal['video','audio','subtitle'], index: StrictInt, name: str | None = None, enabled: StrictBool | None = None, locked: StrictBool | None = None, expected_state: dict | None = None, confirmed: StrictBool = False, session_id: str | None = None) -> dict:
    """Read one-based track name/enabled/locked/count. For edits pass exact fresh returned state plus requested fields and confirmed after preview. Fingerprint detects observed changes, not equal-state track replacement. No clip trimming/deletion or rendering; failures may leave partial field changes."""
    return call('track_state',session_id,project_id=project_id,timeline_id=timeline_id,track_type=track_type,index=index,name=name,enabled=enabled,locked=locked,expected_state=expected_state,confirmed=confirmed)


@mcp.tool(annotations=WRITE)
def resolve_delete_marker(project_id: str, timeline_id: str, frame: StrictInt, expected_marker: dict, confirmed: StrictBool = False, session_id: str | None = None) -> dict:
    """Preview then delete one timeline-relative marker frame only if its full timeline_info marker dictionary still matches. Never clears all markers or changes clips. Requires deletion intent; no save/render."""
    return call('delete_marker',session_id,project_id=project_id,timeline_id=timeline_id,frame=frame,expected_marker=expected_marker,confirmed=confirmed)


if __name__ == "__main__":
    mcp.run()
