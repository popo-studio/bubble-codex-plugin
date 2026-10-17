"""MCP stdio entrypoint; deployed plugins start through the versioned launcher."""
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from client import request
from discovery import discover_sessions
from installation import installation_status, install_bridge, uninstall_bridge

mcp = FastMCP("Bubble Houdini Control")
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
SCRIPT = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True)
INSTALL = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)


@mcp.tool(annotations=READ)
def houdini_installation_status(houdini_version: str = "20.5") -> dict:
    """Read-only inspection of user-level Houdini installation, paths, conflicts and proposed changes. Works with Houdini closed. Honors HOUDINI_USER_PREF_DIR; supports Houdini20.5 only."""
    return installation_status(houdini_version)


@mcp.tool(annotations=INSTALL)
def houdini_install_bridge(houdini_version: str = "20.5", confirmed: bool = False) -> dict:
    """Install/update a Houdini Python bridge and managed uiready.py startup block. Default false previews without writes. Set confirmed=true only after the user has authorized these persistent file changes and automatic local bridge startup; a general inquiry is not consent. Preserves other startup code and backs it up. Then ask user to restart Houdini, or offer returned code for current-session loading. Never restarts Houdini or changes scenes."""
    return install_bridge(houdini_version, confirmed)


@mcp.tool(annotations=INSTALL)
def houdini_uninstall_bridge(houdini_version: str = "20.5", confirmed: bool = False) -> dict:
    """Remove only owned unmodified Houdini runtime files and exact managed startup block. Default false previews without writes. Set true only with user consent to removal. Preserves unrelated files and backups; refuses conflicts. Restart Houdini to stop the already running bridge. Does not uninstall the Codex plugin."""
    return uninstall_bridge(houdini_version, confirmed)


@mcp.tool(annotations=READ)
def houdini_list_sessions(scene: str | None = None) -> dict:
    """List readable live Houdini scenes, filenames/full paths, unsaved/modified status and version. Optional scene matches an exact filename, extensionless stem or full path (case-insensitive); only unique complete results return selected_pid. Duplicate/unsaved/unreachable scenes require user choice; never guess or use partial-name matches. Only bridge-discovered processes appear. Read-only; retains no selection. Keep the chosen PID and recheck its scene before writes."""
    return discover_sessions(scene)


@mcp.tool(annotations=READ)
def houdini_status(pid: int | None = None) -> dict:
    """Check an interactive Houdini bridge. Omit pid only when exactly one session exists."""
    return request("status", pid=pid, timeout=5)


@mcp.tool(annotations=READ)
def houdini_scene_info(pid: int | None = None) -> dict:
    """Read current script/scene path, dirty state, application version and selection."""
    return request("scene_info", pid=pid)


@mcp.tool(annotations=READ)
def houdini_inspect_scene(pid: int | None = None) -> dict:
    """Read-only external file reference audit. Reports local paths, missing files and unverified expressions. Sequence existence means any matching frame, not completeness."""
    return request("inspect_scene", {}, pid)


@mcp.tool(annotations=SCRIPT)
def houdini_execute_python(code: str, pid: int | None = None, timeout: float = 30) -> dict:
    """Execute Python on Houdini's main thread with full user privileges. hou is available; assign result for a return value. Captures Python stdout/stderr. May edit files/scenes or access network; run only user-authorized code. No automatic retries on timeout/error; partial changes may already exist. timeout <=120 seconds."""
    return request("execute_python", {"code": code}, pid, timeout)


if __name__ == "__main__":
    mcp.run(transport="stdio")
