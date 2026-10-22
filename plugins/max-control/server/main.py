"""Portable MCP entrypoint, independent from application Python."""
from typing import Literal
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from client import request
from discovery import discover_sessions
from installation import installation_status, install_bridge, uninstall_bridge

mcp = FastMCP("Bubble 3ds Max Control")
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
SCRIPT = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True)
INSTALL = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)


@mcp.tool(annotations=READ)
def max_installation_status(startup_directory: str | None = None) -> dict:
    """Preview local bridge installation and ownership conflicts without writes. Absolute user startup scripts directory; a unique existing profile can be detected when omitted."""
    return installation_status(startup_directory)


@mcp.tool(annotations=INSTALL)
def max_install_bridge(startup_directory: str | None = None, confirmed: bool = False) -> dict:
    """Install/update stable owned application bridge files after explicit user consent. Default false is a read-only preview. Show exact paths and automatic startup behavior before asking consent; set true only when authorized. Absolute user startup scripts directory; a unique existing profile can be detected when omitted. Then remind user to save work and restart; optional returned Python code loads the current session when Python is enabled. Never restarts the application or changes scenes automatically."""
    return install_bridge(startup_directory, confirmed)


@mcp.tool(annotations=INSTALL)
def max_uninstall_bridge(startup_directory: str | None = None, confirmed: bool = False) -> dict:
    """Preview removal by default; true requires user consent. Remove only owned unmodified files; preserve unrelated/generated files and refuse edited files. Restart the application to stop an existing listener. Absolute user startup scripts directory; a unique existing profile can be detected when omitted."""
    return uninstall_bridge(startup_directory, confirmed)


@mcp.tool(annotations=READ)
def max_list_sessions(scene: str | None = None) -> dict:
    """Read live filename, full path, dirty state, version and PID of bridge-discovered sessions. Exact filename/stem/path matches only.  Matching is read-only; ambiguous, unsaved or unavailable instances require a numbered choice. Keep chosen PID and recheck scene before writes. Never silently fall back to another process."""
    return discover_sessions(scene)


@mcp.tool(annotations=READ)
def max_status(pid: int | None = None) -> dict:
    """Check the selected bridge; omit PID only when exactly one discovered instance exists."""
    return request("status", pid=pid, timeout=5)


@mcp.tool(annotations=READ)
def max_scene_info(pid: int | None = None) -> dict:
    """Read current scene/map path, project, dirty state and selection without changing them."""
    return request("scene_info", pid=pid)


@mcp.tool(annotations=READ)
def max_inspect_scene(pid: int | None = None) -> dict:
    """Checks Bitmaptexture maps and top-level scene XRefs; excludes third-party renderer maps/caches and sequence completeness. Read-only; never loads, repairs or saves files."""
    return request("inspect_scene", {}, pid)


@mcp.tool(annotations=SCRIPT)
def max_execute_python(code: str, pid: int | None = None, timeout: float = 30) -> dict:
    """Execute user-authorized Python with full user privileges on the application main thread. rt (pymxs.runtime) is available; assign result for output. Captures Python stdout/stderr. Changes may already exist on failure/timeout, so never retry automatically or switch instances. This is not a sandbox. timeout is at most 120 seconds."""
    return request("execute_python", {"code": code}, pid, timeout)


@mcp.tool(annotations=SCRIPT)
def max_execute_maxscript(code: str, pid: int | None = None, timeout: float = 30) -> dict:
    """Execute authorized MAXScript on the main thread with full user privileges. Return its result. Listener output may not be captured. No retries on timeout/error because partial changes may exist."""
    return request("execute_maxscript", {"code": code}, pid, timeout)



@mcp.tool(annotations=READ)
def max_list_objects(pid: int, limit: int = 1000) -> dict:
    """List explicit object IDs/hierarchy/transforms and scene_token in the selected instance; bounded 1..5000. Refresh after scene switch/reload. Prefer structured tools over scripts."""
    return request("list_objects", {"limit": limit}, pid)

@mcp.tool(annotations=READ)
def max_inspect_object(object_id: int, expected_scene: str, pid: int) -> dict:
    """Read exact object's class/components/material metadata. expected_scene is scene_token from list_objects, not a filename."""
    return request("inspect_object", {"object_id": object_id, "expected_scene": expected_scene}, pid)

@mcp.tool(annotations=SCRIPT)
def max_object_action(action: Literal["create", "select", "duplicate", "rename", "delete", "transform"], expected_scene: str, pid: int, object_id: int | None = None, kind: str = "box", name: str | None = None, position: list[float] | None = None, scale: list[float] | None = None) -> dict:
    """Edit one explicit object on main thread. scene_token required. Create primitives; select/duplicate/rename/delete by ID; transform position/scale only. No automatic save. Deletion needs user authorization; timeout/partial error must not be retried. List objects after scene changes. Coordinates follow host world position/local scale conventions."""
    return request("object_action", dict(action=action, expected_scene=expected_scene, object_id=object_id, kind=kind, name=name, position=position, scale=scale), pid)

@mcp.tool(annotations=SCRIPT)
def max_scene_action(action: Literal["new", "open", "save"], expected_scene: str, pid: int, path: str | None = None, overwrite: bool = False) -> dict:
    """Explicit new/open/save in selected instance. New/open refuses ANY dirty affected scene; never discards or saves implicitly. Save requires explicit target and overwrite authorization for existing files. Use absolute .max path. expected_scene is latest scene_token."""
    return request("scene_action", dict(action=action, expected_scene=expected_scene, path=path, overwrite=overwrite), pid, 60)

@mcp.tool(annotations=READ)
def max_settings(pid: int) -> dict:
    """Inspect render/editor configuration and asset metadata without modifying settings or starting a render/build."""
    return request("settings", {}, pid)


if __name__ == "__main__":
    mcp.run(transport="stdio")
