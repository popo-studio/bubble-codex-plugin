"""MCP stdio entrypoint; deployed plugins start through the versioned launcher."""
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from client import request
from discovery import discover_sessions
from installation import installation_status, install_bridge, uninstall_bridge

mcp = FastMCP("Bubble Maya Control")
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
SCRIPT = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True)
INSTALL = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)


@mcp.tool(annotations=READ)
def maya_installation_status(maya_version: str = "2027") -> dict:
    """Read-only inspection of user-level Maya installation, paths, conflicts and proposed changes. Works with Maya closed. Honors MAYA_APP_DIR; supports Maya2027 only."""
    return installation_status(maya_version)


@mcp.tool(annotations=INSTALL)
def maya_install_bridge(maya_version: str = "2027", confirmed: bool = False) -> dict:
    """Install/update a native Maya plug-in and managed userSetup.py startup block. Default false previews without writes. Set confirmed=true only after the user has authorized these persistent file changes and automatic local bridge startup; a general inquiry is not consent. Preserves other startup code and backs it up. Then ask user to restart Maya, or offer returned code for current-session loading. Never restarts Maya or changes scenes."""
    return install_bridge(maya_version, confirmed)


@mcp.tool(annotations=INSTALL)
def maya_uninstall_bridge(maya_version: str = "2027", confirmed: bool = False) -> dict:
    """Remove only owned unmodified Maya runtime files and exact managed startup block. Default false previews without writes. Set true only with user consent to removal. Preserves unrelated files and backups; refuses conflicts. Restart Maya to stop the already running bridge. Does not uninstall the Codex plugin."""
    return uninstall_bridge(maya_version, confirmed)


@mcp.tool(annotations=READ)
def maya_list_sessions(scene: str | None = None) -> dict:
    """List readable live Maya scenes, filenames/full paths, unsaved/modified status and version. Optional scene matches an exact filename, extensionless stem or full path (case-insensitive); only unique complete results return selected_pid. Duplicate/unsaved/unreachable scenes require user choice; never guess or use partial-name matches. Only bridge-discovered processes appear. Read-only; retains no selection. Keep the chosen PID and recheck its scene before writes."""
    return discover_sessions(scene)


@mcp.tool(annotations=READ)
def maya_status(pid: int | None = None) -> dict:
    """Check an interactive Maya bridge. Omit pid only when exactly one session exists."""
    return request("status", pid=pid, timeout=5)


@mcp.tool(annotations=READ)
def maya_scene_info(pid: int | None = None) -> dict:
    """Read current scene path, dirty state, project, selection, units and node count."""
    return request("scene_info", pid=pid)


@mcp.tool(annotations=READ)
def maya_inspect_scene(pid: int | None = None, include_namespaces: bool = True) -> dict:
    """Read-only check of references, file textures (UDIM/sequences), unknown nodes and namespaces. Checks whether any tile/frame exists, not completeness; excludes plugin caches."""
    return request("inspect_scene", {"include_namespaces": include_namespaces}, pid)


@mcp.tool(annotations=SCRIPT)
def maya_execute_python(code: str, pid: int | None = None, timeout: float = 30) -> dict:
    """Execute Python on Maya's main thread with full user privileges. cmds/mel are available; assign result for a return value. Captures Python stdout/stderr. May edit files/scenes or access network; run only user-authorized code. No automatic retries on timeout/error; partial changes may already exist. timeout <=120 seconds."""
    return request("execute_python", {"code": code}, pid, timeout)


@mcp.tool(annotations=SCRIPT)
def maya_execute_mel(code: str, pid: int | None = None, timeout: float = 30) -> dict:
    """Execute MEL with full user privileges on Maya's main thread and return mel.eval result. MEL console output is not guaranteed captured. May modify files/scenes; run only authorized code. Never auto-retry a timeout/error: partial changes may exist. timeout <=120 seconds."""
    return request("execute_mel", {"code": code}, pid, timeout)




@mcp.tool(annotations=READ)
def maya_scene_state(pid: int | None = None) -> dict:
    """Read structural scene snapshot, dirty status and render configuration. Snapshot is not a full attribute revision; read target values immediately before edits."""
    return request('structured_state', {}, pid)


@mcp.tool(annotations=SCRIPT)
def maya_scene_file(action: str, pid: int, expected_snapshot: str, path: str = '', discard_changes: bool = False, overwrite: bool = False) -> dict:
    """New/open/save scene. Explicit PID and fresh scene_state snapshot required. Save before new/open; discard_changes=true only with explicit user authorization. Existing output requires overwrite=true. Opening a user-authorized project may run application/plugin callbacks. Never retry after timeout/error."""
    return request('structured_file', dict(action=action,pid=pid,expected_snapshot=expected_snapshot,path=path,discard_changes=discard_changes,overwrite=overwrite), pid)


@mcp.tool(annotations=READ)
def maya_query_nodes(pid: int | None = None, selected: bool = False, node_type: str = '', parent: str = '', limit: int = 200) -> dict:
    """Inspect bounded node/object list with exact paths and types. Inspects the current scene. Returns truncation flag. Use exact returned paths for changes."""
    return request('structured_query',dict(selected=selected,node_type=node_type,parent=parent,limit=limit),pid)


@mcp.tool(annotations=SCRIPT)
def maya_create_node(kind: str, name: str, pid: int, expected_snapshot: str, parent: str = '') -> dict:
    """Create a named object/node using native commands. Kinds: cube/sphere/plane/cylinder/locator/transform/camera. Custom host node creation can run native callbacks. No implicit overwrite."""
    return request('structured_create',dict(kind=kind,name=name,pid=pid,expected_snapshot=expected_snapshot,parent=parent),pid)


@mcp.tool(annotations=SCRIPT)
def maya_edit_node(action: str, node: str, pid: int, expected_snapshot: str, name: str = '', values: dict | None = None, confirm_delete: bool = False) -> dict:
    """Edit exact node: rename, duplicate, delete, or transform with translation/rotation/scale triples. Delete requires user-authorized confirm_delete=true. Locked/referenced assets are protected. Structural guard does not detect every property edit; read target first."""
    return request('structured_edit',dict(action=action,node=node,pid=pid,expected_snapshot=expected_snapshot,name=name,values=values,confirm_delete=confirm_delete),pid)


@mcp.tool(annotations=SCRIPT)
def maya_select_nodes(nodes: list[str], pid: int, expected_snapshot: str) -> dict:
    """Replace selection with exact node paths (empty list clears). Does not fall back to current selection or another process."""
    return request('structured_selection',dict(nodes=nodes,pid=pid,expected_snapshot=expected_snapshot),pid)


@mcp.tool(annotations=SCRIPT)
def maya_node_attribute(node: str, attribute: str, pid: int, action: str = 'get', expected_snapshot: str = '', value: str | float | int | bool | list | None = None, expected_value: str | float | int | bool | list | None = None) -> dict:
    """Read/set a Maya attribute. Set requires fresh snapshot and exact expected_value from get; refuses animated/connected/locked values. No button/script knob execution. Supports scalar numeric/string values."""
    return request('structured_attribute',dict(node=node,attribute=attribute,pid=pid,action=action,expected_snapshot=expected_snapshot,value=value,expected_value=expected_value),pid)


@mcp.tool(annotations=SCRIPT)
def maya_node_connections(node: str, pid: int, action: str = 'get', expected_snapshot: str = '', source: str = '', target: str = '', index: int = 0, expected_input: str | None = None) -> dict:
    """Read/connect/disconnect exact nodes. Source/target are exact plugs and never force-replace. Set requires PID + fresh snapshot. Never follows current selection."""
    return request('structured_connections',dict(node=node,pid=pid,action=action,expected_snapshot=expected_snapshot,source=source,target=target,index=index,expected_input=expected_input),pid)


@mcp.tool(annotations=SCRIPT)
def maya_timeline(pid: int, action: str = 'get', expected_snapshot: str = '', start: float = 1, end: float = 100, frame: float = 1) -> dict:
    """Read or set playback frame range and current frame, without rendering. Set requires fresh structural snapshot. Does not change FPS or retime animation."""
    return request('structured_timeline',dict(pid=pid,action=action,expected_snapshot=expected_snapshot,start=start,end=end,frame=frame),pid)


if __name__ == "__main__":
    mcp.run(transport="stdio")
