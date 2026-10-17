"""Portable MCP entrypoint, independent from application Python."""
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from client import request
from discovery import discover_sessions
from installation import installation_status, install_bridge, uninstall_bridge

mcp = FastMCP("Bubble Unreal Engine Control")
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
SCRIPT = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True)
INSTALL = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)


@mcp.tool(annotations=READ)
def unreal_installation_status(project_path: str | None = None) -> dict:
    """Preview local bridge installation and ownership conflicts without writes. Explicit existing .uproject file or directory required; affects only that project, never rewrites .uproject."""
    return installation_status(project_path)


@mcp.tool(annotations=INSTALL)
def unreal_install_bridge(project_path: str | None = None, confirmed: bool = False) -> dict:
    """Install/update stable owned application bridge files after explicit user consent. Default false is a read-only preview. Show exact paths and automatic startup behavior before asking consent; set true only when authorized. Explicit existing .uproject file or directory required; affects only that project, never rewrites .uproject. Then remind user to save work and restart; optional returned Python code loads the current session when Python is enabled. Never restarts the application or changes scenes automatically."""
    return install_bridge(project_path, confirmed)


@mcp.tool(annotations=INSTALL)
def unreal_uninstall_bridge(project_path: str | None = None, confirmed: bool = False) -> dict:
    """Preview removal by default; true requires user consent. Remove only owned unmodified files; preserve unrelated/generated files and refuse edited files. Restart the application to stop an existing listener. Explicit existing .uproject file or directory required; affects only that project, never rewrites .uproject."""
    return uninstall_bridge(project_path, confirmed)


@mcp.tool(annotations=READ)
def unreal_list_sessions(scene: str | None = None) -> dict:
    """Read live filename, full path, dirty state, version and PID of bridge-discovered sessions. Exact filename/stem/path matches only. Also matches exact .uproject filename/stem/path or Unreal map package name; duplicate maps/projects remain ambiguous. Matching is read-only; ambiguous, unsaved or unavailable instances require a numbered choice. Keep chosen PID and recheck scene before writes. Never silently fall back to another process."""
    return discover_sessions(scene)


@mcp.tool(annotations=READ)
def unreal_status(pid: int | None = None) -> dict:
    """Check the selected bridge; omit PID only when exactly one discovered instance exists."""
    return request("status", pid=pid, timeout=5)


@mcp.tool(annotations=READ)
def unreal_scene_info(pid: int | None = None) -> dict:
    """Read current scene/map path, project, dirty state and selection without changing them."""
    return request("scene_info", pid=pid)


@mcp.tool(annotations=READ)
def unreal_inspect_scene(pid: int | None = None, package: str | None = None) -> dict:
    """Checks direct hard/soft Asset Registry dependencies of saved current map or explicit /Game package. Unresolved entries are warnings, not proof of missing files; excludes transitive and external files. Read-only; never loads, repairs or saves files."""
    return request("inspect_scene", {"package": package}, pid)


@mcp.tool(annotations=SCRIPT)
def unreal_execute_python(code: str, pid: int | None = None, timeout: float = 30) -> dict:
    """Execute user-authorized Python with full user privileges on the application main thread. unreal is available; assign result for output. Captures Python stdout/stderr. Changes may already exist on failure/timeout, so never retry automatically or switch instances. This is not a sandbox. timeout is at most 120 seconds."""
    return request("execute_python", {"code": code}, pid, timeout)


if __name__ == "__main__":
    mcp.run(transport="stdio")
