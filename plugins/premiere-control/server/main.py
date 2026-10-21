"""Premiere Pro 26.x signed CEP integration; stdio only."""
import atexit
import threading
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from broker import Broker, failure
from installation import installation_status, install_bridge, uninstall_bridge

mcp = FastMCP("Bubble Premiere Pro")
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)
_broker = None
_lock = threading.Lock()


def broker():
    global _broker
    with _lock:
        if _broker is None:
            _broker = Broker()
            atexit.register(_broker.close)
        return _broker


def call(operation, args, session_id, timeout=30):
    if _broker is None:
        return failure("not_paired", "Generate a pairing code and connect the Premiere CEP panel first")
    return _broker.request(operation, args, session_id, timeout)


@mcp.tool(annotations=READ)
def premiere_installation_status(package_path: str | None = None) -> dict:
    """Inspect installer availability and installation plan without changing Adobe or project files."""
    return installation_status(package_path)


@mcp.tool(annotations=WRITE)
def premiere_install_bridge(confirmed: bool = False, package_path: str | None = None) -> dict:
    """Preview by default. With explicit user authorization, install a the bundled signed CEP release in the current user extension folder.
    Requires Premiere 26.x. Never copy code into an editor. Installation success
    does not prove host loading. Updates use the same plugin ID. Does not restart Premiere."""
    return install_bridge(confirmed, package_path)


@mcp.tool(annotations=WRITE)
def premiere_uninstall_bridge(confirmed: bool = False) -> dict:
    """Preview by default; confirmed removal deletes only exact managed signed extension files.
    Removing the Codex plugin does not remove the CEP extension. Close its panel to disconnect immediately."""
    return uninstall_bridge(confirmed)


@mcp.tool(annotations=READ)
def premiere_pairing_code() -> dict:
    """Start this chat's local broker and return a private pairing code for the Bubble Premiere panel.
    Only call when the user requests connection; do not log or share the code. No script copying required.
    Panel credentials stay in memory; reconnect after MCP/chat restarts. Separate chats do not steal connections."""
    return broker().pairing()


@mcp.tool(annotations=READ)
def premiere_list_sessions(project: str | None = None) -> dict:
    """List paired panels by UUID with active project name/path/ID. Only the active project is advertised.
    Exact filename/stem/path matching; ambiguous results require user selection. Host PID is not guessed.
    Recheck chosen project ID before writes. No automatic switching or retries."""
    if _broker is None:
        return {"ok": True, "data": [], "selection": {"status": "unspecified", "selected": None, "matches": []},
                "note": "No panel paired with this chat"}
    return _broker.sessions(project)


@mcp.tool(annotations=READ)
def premiere_project_info(project_id: str, session_id: str | None = None) -> dict:
    """Read selected active project's name/path and up to 1000 sequence names/IDs. Rejects project switches."""
    return call("project_info", {"project_id": project_id}, session_id)


@mcp.tool(annotations=READ)
def premiere_inspect_media(project_id: str, session_id: str | None = None) -> dict:
    """Inspect up to 1000 project bin items and Adobe-reported offline state, preserving errors as unverified.
    This is not a full filesystem/sequence completeness audit or a timeline effects audit."""
    return call("inspect_media", {"project_id": project_id}, session_id)


@mcp.tool(annotations=WRITE)
def premiere_import_files(project_id: str, paths: list[str], session_id: str | None = None) -> dict:
    """Import 1–100 authorized paths into selected project root bin. Modifies project without saving.
    Rejects changed active project; no automatic retry after timeout because partial changes may exist."""
    return call("import_files", {"project_id": project_id, "paths": paths}, session_id)


@mcp.tool(annotations=WRITE)
def premiere_relink_media(project_id: str, item_id: str, path: str, session_id: str | None = None) -> dict:
    """Relink exactly one chosen media item, keeping Adobe compatibility checks. This operation is not
    undoable in Adobe; obtain user authorization for the exact item/path. Does not save the project."""
    return call("relink_media", {"project_id": project_id, "item_id": item_id, "path": path}, session_id)


@mcp.tool(annotations=WRITE)
def premiere_save_project(project_id: str, session_id: str | None = None) -> dict:
    """Save the explicitly authorized selected project to its existing path; refuses unsaved projects."""
    return call("save_project", {"project_id": project_id}, session_id)


@mcp.tool(annotations=WRITE)
def premiere_new_project(path: str, session_id: str) -> dict:
    """Create a project at a new absolute .prproj path only when no project is open. Never overwrites.
    Writes a new project file; requires authorization for that path. Does not close or discard existing work."""
    return call("new_project", {"path": path}, session_id)


@mcp.tool(annotations=WRITE)
def premiere_open_project(path: str, session_id: str) -> dict:
    """Open an existing .prproj only when no project is open; preserves Adobe conversion/offline warnings.
    Does not close, save, or discard existing work. Inspect after timeouts; never replay automatically."""
    return call("open_project", {"path": path}, session_id)


@mcp.tool(annotations=READ)
def premiere_inspect_timeline(project_id: str, sequence_id: str, session_id: str | None = None) -> dict:
    """Inspect up to 1000 video/audio timeline clips with stable IDs and exact tick strings. No effects audit."""
    return call("inspect_timeline", {"project_id": project_id, "sequence_id": sequence_id}, session_id)


@mcp.tool(annotations=WRITE)
def premiere_create_sequence_from_clips(project_id: str, name: str, item_ids: list[str], session_id: str | None = None) -> dict:
    """Create a sequence from 1-100 chosen online source clip IDs in order; settings follow source media.
    Requires authorization for project and clips. Does not save; never retry a timed-out mutation."""
    return call("create_sequence_from_clips", {"project_id": project_id, "name": name, "item_ids": item_ids}, session_id)


if __name__ == "__main__":
    mcp.run(transport="stdio")
