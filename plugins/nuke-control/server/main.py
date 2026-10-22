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




@mcp.tool(annotations=READ)
def nuke_scene_state(pid: int | None = None) -> dict:
    """Read structural scene snapshot, dirty status and render configuration. Snapshot is not a full attribute revision; read target values immediately before edits."""
    return request('structured_state', {}, pid)


@mcp.tool(annotations=SCRIPT)
def nuke_scene_file(action: str, pid: int, expected_snapshot: str, path: str = '', discard_changes: bool = False, overwrite: bool = False) -> dict:
    """New/open/save scene. Explicit PID and fresh scene_state snapshot required. Save before new/open; discard_changes=true only with explicit user authorization. Existing output requires overwrite=true. Opening a user-authorized project may run application/plugin callbacks. Never retry after timeout/error."""
    return request('structured_file', dict(action=action,pid=pid,expected_snapshot=expected_snapshot,path=path,discard_changes=discard_changes,overwrite=overwrite), pid)


@mcp.tool(annotations=READ)
def nuke_query_nodes(pid: int | None = None, selected: bool = False, node_type: str = '', parent: str = '', limit: int = 200) -> dict:
    """Inspect bounded node/object list with exact paths and types. Inspects the current scene. Returns truncation flag. Use exact returned paths for changes."""
    return request('structured_query',dict(selected=selected,node_type=node_type,parent=parent,limit=limit),pid)


@mcp.tool(annotations=SCRIPT)
def nuke_create_node(kind: str, name: str, pid: int, expected_snapshot: str, parent: str = '') -> dict:
    """Create a named object/node using native commands. Supported stock types: Read, Write, Constant, CheckerBoard2, Blur, Grade, Merge2, Transform, Crop, Reformat, Shuffle2, Dot, BackdropNode. Custom host node creation can run native callbacks. No implicit overwrite."""
    return request('structured_create',dict(kind=kind,name=name,pid=pid,expected_snapshot=expected_snapshot,parent=parent),pid)


@mcp.tool(annotations=SCRIPT)
def nuke_edit_node(action: str, node: str, pid: int, expected_snapshot: str, name: str = '', values: dict | None = None, confirm_delete: bool = False) -> dict:
    """Edit exact node: rename, delete or graph position with x/y. Root is reserved for scene-file/timeline tools. Delete requires user-authorized confirm_delete=true. Locked/referenced assets are protected. Structural guard does not detect every property edit; read target first."""
    return request('structured_edit',dict(action=action,node=node,pid=pid,expected_snapshot=expected_snapshot,name=name,values=values,confirm_delete=confirm_delete),pid)


@mcp.tool(annotations=SCRIPT)
def nuke_select_nodes(nodes: list[str], pid: int, expected_snapshot: str) -> dict:
    """Replace selection with exact node paths (empty list clears). Does not fall back to current selection or another process."""
    return request('structured_selection',dict(nodes=nodes,pid=pid,expected_snapshot=expected_snapshot),pid)


@mcp.tool(annotations=SCRIPT)
def nuke_node_attribute(node: str, attribute: str, pid: int, action: str = 'get', expected_snapshot: str = '', value: str | float | int | bool | list | None = None, expected_value: str | float | int | bool | list | None = None) -> dict:
    """Read/set a Nuke knob. Set requires fresh snapshot and exact expected_value from get; refuses animated/connected/locked values. No button/script knob execution. Supports scalar/vector values."""
    return request('structured_attribute',dict(node=node,attribute=attribute,pid=pid,action=action,expected_snapshot=expected_snapshot,value=value,expected_value=expected_value),pid)


@mcp.tool(annotations=SCRIPT)
def nuke_node_connections(node: str, pid: int, action: str = 'get', expected_snapshot: str = '', source: str = '', target: str = '', index: int = 0, expected_input: str | None = None) -> dict:
    """Read/connect/disconnect exact nodes. Use source path, input index and expected_input (null for empty). Set requires PID + fresh snapshot. Never follows current selection."""
    return request('structured_connections',dict(node=node,pid=pid,action=action,expected_snapshot=expected_snapshot,source=source,target=target,index=index,expected_input=expected_input),pid)


@mcp.tool(annotations=SCRIPT)
def nuke_timeline(pid: int, action: str = 'get', expected_snapshot: str = '', start: float = 1, end: float = 100, frame: float = 1) -> dict:
    """Read or set playback frame range and current frame, without rendering. Set requires fresh structural snapshot. Does not change FPS or retime animation."""
    return request('structured_timeline',dict(pid=pid,action=action,expected_snapshot=expected_snapshot,start=start,end=end,frame=frame),pid)


if __name__ == "__main__":
    mcp.run(transport="stdio")
