"""MCP stdio entrypoint; deployed plugins start through the versioned launcher."""
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from client import request
from discovery import discover_sessions
from installation import installation_status, install_bridge, uninstall_bridge

mcp = FastMCP("Bubble Nuke Control")
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
SCRIPT = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True)
INSTALL = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)


@mcp.tool(annotations=READ)
def nuke_installation_status(nuke_version: str = "15.1") -> dict:
    """Read-only inspection of user-level Nuke installation, paths, conflicts and proposed changes. Works with Nuke closed. Honors BUBBLE_NUKE_USER_DIR; supports Nuke15.1 only."""
    return installation_status(nuke_version)


@mcp.tool(annotations=INSTALL)
def nuke_install_bridge(nuke_version: str = "15.1", confirmed: bool = False) -> dict:
    """Install/update a Nuke Python bridge and managed menu.py startup block. Default false previews without writes. Set confirmed=true only after the user has authorized these persistent file changes and automatic local bridge startup; a general inquiry is not consent. Preserves other startup code and backs it up. Then ask user to restart Nuke, or offer returned code for current-session loading. Never restarts Nuke or changes scenes."""
    return install_bridge(nuke_version, confirmed)


@mcp.tool(annotations=INSTALL)
def nuke_uninstall_bridge(nuke_version: str = "15.1", confirmed: bool = False) -> dict:
    """Remove only owned unmodified Nuke runtime files and exact managed startup block. Default false previews without writes. Set true only with user consent to removal. Preserves unrelated files and backups; refuses conflicts. Restart Nuke to stop the already running bridge. Does not uninstall the Codex plugin."""
    return uninstall_bridge(nuke_version, confirmed)


@mcp.tool(annotations=READ)
def nuke_list_sessions(scene: str | None = None) -> dict:
    """List readable live Nuke scenes, filenames/full paths, unsaved/modified status and version. Optional scene matches an exact filename, extensionless stem or full path (case-insensitive); only unique complete results return selected_pid. Duplicate/unsaved/unreachable scenes require user choice; never guess or use partial-name matches. Only bridge-discovered processes appear. Read-only; retains no selection. Keep the chosen PID and recheck its scene before writes."""
    return discover_sessions(scene)


@mcp.tool(annotations=READ)
def nuke_status(pid: int | None = None) -> dict:
    """Check an interactive Nuke bridge. Omit pid only when exactly one session exists."""
    return request("status", pid=pid, timeout=5)


@mcp.tool(annotations=READ)
def nuke_scene_info(pid: int | None = None) -> dict:
    """Read current script/scene path, dirty state, application version and selection."""
    return request("scene_info", pid=pid)


@mcp.tool(annotations=READ)
def nuke_inspect_scene(pid: int | None = None) -> dict:
    """Read-only external file reference audit. Reports local paths, missing files and unverified expressions. Sequence existence means any matching frame, not completeness."""
    return request("inspect_scene", {}, pid)


@mcp.tool(annotations=SCRIPT)
def nuke_execute_python(code: str, pid: int | None = None, timeout: float = 30) -> dict:
    """Execute Python on Nuke's main thread with full user privileges. nuke is available; assign result for a return value. Captures Python stdout/stderr. May edit files/scenes or access network; run only user-authorized code. No automatic retries on timeout/error; partial changes may already exist. timeout <=120 seconds."""
    return request("execute_python", {"code": code}, pid, timeout)


if __name__ == "__main__":
    mcp.run(transport="stdio")
