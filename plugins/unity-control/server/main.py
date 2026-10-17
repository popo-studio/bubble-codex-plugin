"""Unity Editor MCP stdio entrypoint."""
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from client import request
from discovery import discover_sessions
from installation import installation_status, install_bridge, uninstall_bridge

mcp = FastMCP("Bubble Unity Control")
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
SCRIPT = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True)
INSTALL = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)


@mcp.tool(annotations=READ)
def unity_installation_status(project_path: str) -> dict:
    """Preview package paths, version, ownership conflicts and planned changes in an explicit absolute Unity 6 project path. No writes; works with Editor closed."""
    return installation_status(project_path)


@mcp.tool(annotations=INSTALL)
def unity_install_bridge(project_path: str, confirmed: bool = False) -> dict:
    """Install/update an embedded Editor-only package for this project. False previews; true requires the user's consent for these exact persistent project changes and automatic local bridge startup. Recommend saving work and restarting this Editor; optional Assets > Refresh and compilation can apply without restart. Never restarts Editor, edits scenes, or changes manifest.json."""
    return install_bridge(project_path, confirmed)


@mcp.tool(annotations=INSTALL)
def unity_uninstall_bridge(project_path: str, confirmed: bool = False) -> dict:
    """Preview or consentedly remove only owned unmodified package files. Preserves .meta/unrelated files and refuses modified owned files. Restart or refresh Editor afterward to stop loaded code. Codex plugin removal alone does not remove the project package."""
    return uninstall_bridge(project_path, confirmed)


@mcp.tool(annotations=READ)
def unity_list_sessions(scene: str | None = None) -> dict:
    """List live projects and loaded scenes. Optional exact scene filename/stem, full scene path, project folder name or full project path matches; no partial matching. Multiple, unsaved or unreachable sessions require a numbered user choice; retain explicit PID and recheck project/scene before writes. Selection never silently falls back after reload/disconnect."""
    return discover_sessions(scene)


@mcp.tool(annotations=READ)
def unity_status(pid: int | None = None) -> dict:
    """Read Editor version, project, loaded scenes and compile/import/play states. PID may be omitted only when exactly one discovery record exists. Bridge pauses in Play Mode and reconnects on returning to Edit Mode."""
    return request("status", pid=pid, timeout=5)


@mcp.tool(annotations=READ)
def unity_scene_info(pid: int | None = None) -> dict:
    """Read active and loaded scene paths, unsaved/dirty states, root counts, selection and project. Does not save, open or change scenes."""
    return request("scene_info", pid=pid)


@mcp.tool(annotations=READ)
def unity_inspect_scene(pid: int | None = None, max_objects: int = 5000) -> dict:
    """Read-only scan of loaded scenes for missing scripts and serialized missing object references, capped at max_objects 1..10000 and 5000 issues. Reports truncation. Excludes unloaded scenes, prefab assets, Addressables and external resource completeness. Requires idle Edit Mode."""
    return request("inspect_scene", {"max_objects": max_objects}, pid)


@mcp.tool(annotations=SCRIPT)
def unity_invoke_method(type_name: str, method_name: str, payload: str | None = None, pid: int | None = None, timeout: float = 30) -> dict:
    """Run an EXISTING compiled public static synchronous C# method on the Editor main thread with full user privileges. Exact fully qualified type required. If payload is omitted, method takes no arguments; otherwise one string argument. Returns void/string/primitive/enum; serialize structured results to a JSON string in the method. Not arbitrary C# eval; no Task/coroutine return. Only run user-authorized scripts, check idle Edit Mode and selected project first. Effects may continue after timeout; NEVER auto-retry. Console logs are not captured."""
    return request("invoke_method", {"type_name": type_name, "method_name": method_name, "with_payload": payload is not None, "payload": payload}, pid, timeout)


@mcp.tool(annotations=SCRIPT)
def unity_execute_menu(menu_path: str, pid: int | None = None, timeout: float = 30) -> dict:
    """Execute an explicitly authorized exact Unity Editor menu command in idle Edit Mode. May edit/save/delete project data, open dialogs, launch builds or quit Editor. Full user privileges; no sandbox. Returns dispatch acceptance, not completion of asynchronous work. Never retry automatically after timeout/disconnect."""
    return request("execute_menu", {"menu_path": menu_path}, pid, timeout)


if __name__ == "__main__":
    mcp.run(transport="stdio")
