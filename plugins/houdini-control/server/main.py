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




@mcp.tool(annotations=READ)
def houdini_scene_state(pid: int | None = None) -> dict:
    """Read structural scene snapshot, dirty status and render configuration. Snapshot is not a full attribute revision; read target values immediately before edits."""
    return request('structured_state', {}, pid)


@mcp.tool(annotations=SCRIPT)
def houdini_scene_file(action: str, pid: int, expected_snapshot: str, path: str = '', discard_changes: bool = False, overwrite: bool = False) -> dict:
    """New/open/save scene. Explicit PID and fresh scene_state snapshot required. Save before new/open; discard_changes=true only with explicit user authorization. Existing output requires overwrite=true. Opening a user-authorized project may run application/plugin callbacks. Never retry after timeout/error."""
    return request('structured_file', dict(action=action,pid=pid,expected_snapshot=expected_snapshot,path=path,discard_changes=discard_changes,overwrite=overwrite), pid)


@mcp.tool(annotations=READ)
def houdini_query_nodes(pid: int | None = None, selected: bool = False, node_type: str = '', parent: str = '', limit: int = 200) -> dict:
    """Inspect bounded node/object list with exact paths and types. Parent defaults /obj. Returns truncation flag. Use exact returned paths for changes."""
    return request('structured_query',dict(selected=selected,node_type=node_type,parent=parent,limit=limit),pid)


@mcp.tool(annotations=SCRIPT)
def houdini_create_node(kind: str, name: str, pid: int, expected_snapshot: str, parent: str = '') -> dict:
    """Create a named object/node using native commands. Exact Houdini node type; parent defaults /obj. Custom host node creation can run native callbacks. No implicit overwrite."""
    return request('structured_create',dict(kind=kind,name=name,pid=pid,expected_snapshot=expected_snapshot,parent=parent),pid)


@mcp.tool(annotations=SCRIPT)
def houdini_edit_node(action: str, node: str, pid: int, expected_snapshot: str, name: str = '', values: dict | None = None, confirm_delete: bool = False) -> dict:
    """Edit exact node: rename, duplicate, delete, position x/y or flags bypass/display/render. Delete requires user-authorized confirm_delete=true. Locked/referenced assets are protected. Structural guard does not detect every property edit; read target first."""
    return request('structured_edit',dict(action=action,node=node,pid=pid,expected_snapshot=expected_snapshot,name=name,values=values,confirm_delete=confirm_delete),pid)


@mcp.tool(annotations=SCRIPT)
def houdini_select_nodes(nodes: list[str], pid: int, expected_snapshot: str) -> dict:
    """Replace selection with exact node paths (empty list clears). Does not fall back to current selection or another process."""
    return request('structured_selection',dict(nodes=nodes,pid=pid,expected_snapshot=expected_snapshot),pid)


@mcp.tool(annotations=SCRIPT)
def houdini_node_attribute(node: str, attribute: str, pid: int, action: str = 'get', expected_snapshot: str = '', value: str | float | int | bool | list | None = None, expected_value: str | float | int | bool | list | None = None) -> dict:
    """Read/set a Houdini scalar parameter. Set requires fresh snapshot and exact expected_value from get; refuses animated/connected/locked values. No button/script knob execution. Use scalar component names such as tx."""
    return request('structured_attribute',dict(node=node,attribute=attribute,pid=pid,action=action,expected_snapshot=expected_snapshot,value=value,expected_value=expected_value),pid)


@mcp.tool(annotations=SCRIPT)
def houdini_node_connections(node: str, pid: int, action: str = 'get', expected_snapshot: str = '', source: str = '', target: str = '', index: int = 0, expected_input: str | None = None) -> dict:
    """Read/connect/disconnect exact nodes. Use source path, input index and expected_input (null for empty). Set requires PID + fresh snapshot. Never follows current selection."""
    return request('structured_connections',dict(node=node,pid=pid,action=action,expected_snapshot=expected_snapshot,source=source,target=target,index=index,expected_input=expected_input),pid)


@mcp.tool(annotations=SCRIPT)
def houdini_timeline(pid: int, action: str = 'get', expected_snapshot: str = '', start: float = 1, end: float = 100, frame: float = 1) -> dict:
    """Read or set playback frame range and current frame, without rendering. Set requires fresh structural snapshot. Does not change FPS or retime animation."""
    return request('structured_timeline',dict(pid=pid,action=action,expected_snapshot=expected_snapshot,start=start,end=end,frame=frame),pid)



@mcp.tool(annotations=SCRIPT)
def houdini_keyframes(node: str, attribute: str, pid: int, action: str = 'get', expected_snapshot: str = '', expected_keys: str = '', frame: float = 1, value: float = 0, overwrite: bool = False, confirm_delete: bool = False) -> dict:
    """Get/set/delete keys of one exact numeric scalar Houdini parm (such as tx). Mutations require fresh scene snapshot and key revision from get. Existing keys require overwrite; deletion requires confirm_delete. Locked/referenced parms and custom expressions are protected. New keys use linear Hscript interpolation."""
    return request('structured_keyframes',dict(node=node,attribute=attribute,pid=pid,action=action,expected_snapshot=expected_snapshot,expected_keys=expected_keys,frame=frame,value=value,overwrite=overwrite,confirm_delete=confirm_delete),pid)


@mcp.tool(annotations=SCRIPT)
def houdini_graph_transfer(action: str, path: str, pid: int, expected_snapshot: str, nodes: list[str] | None = None, parent: str = '/obj', overwrite: bool = False) -> dict:
    """Import/export a native .cpio network snippet containing explicit immediate child nodes of an editable parent. Import returns actual created paths. Absolute paths, explicit export targets and overwrite consent required. Import executes native file content and may run callbacks: trusted user-authorized files only. No automatic retry after partial failure. Does not bundle external assets."""
    return request('structured_transfer',dict(action=action,path=path,pid=pid,expected_snapshot=expected_snapshot,nodes=nodes,parent=parent,overwrite=overwrite),pid)


@mcp.tool(annotations=SCRIPT)
def houdini_network_box(parent: str, pid: int, action: str = 'get', expected_snapshot: str = '', name: str = '', nodes: list[str] | None = None, comment: str = '') -> dict:
    """List/create a network box or add/remove explicit immediate child nodes. Create accepts comment. Mutation requires fresh scene snapshot; refuses silently moving nodes from another box. Remove only unboxes nodes, never deletes them. No automatic cooking/rendering."""
    return request('structured_network_box',dict(parent=parent,pid=pid,action=action,expected_snapshot=expected_snapshot,name=name,nodes=nodes,comment=comment),pid)


if __name__ == "__main__":
    mcp.run(transport="stdio")
