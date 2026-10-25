"""Blender MCP tools; all host operations are dispatched to the Blender main thread."""
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from client import request
from discovery import discover_sessions
from installation import installation_status,install_bridge,uninstall_bridge

mcp=FastMCP('Bubble Blender Control')
READ=ToolAnnotations(readOnlyHint=True,destructiveHint=False,idempotentHint=True,openWorldHint=False)
WRITE=ToolAnnotations(readOnlyHint=False,destructiveHint=True,idempotentHint=False,openWorldHint=True)

@mcp.tool(annotations=READ)
def blender_installation_status(scripts_directory: str | None=None)->dict:
    """Preview exact Blender user scripts paths and ownership without writes. Choose installed version's directory; default only if one profile is present."""
    return installation_status(scripts_directory)

@mcp.tool(annotations=WRITE)
def blender_install_bridge(scripts_directory: str | None=None,confirmed: bool=False)->dict:
    """Install/update owned automatic Startup module after explicit user authorization. False previews. No prefs/add-on toggles. Save and restart Blender afterward; optional returned code loads current session."""
    return install_bridge(scripts_directory,confirmed)

@mcp.tool(annotations=WRITE)
def blender_uninstall_bridge(scripts_directory: str | None=None,confirmed: bool=False)->dict:
    """Remove only unchanged owned files; preserve other scripts/unknown files. False previews. Explicit authorization required. Restart Blender to stop already loaded bridge; Codex uninstall is separate."""
    return uninstall_bridge(scripts_directory,confirmed)

@mcp.tool(annotations=READ)
def blender_list_sessions(scene: str | None=None)->dict:
    """List live bridge sessions, PID and exact scene paths. Multiple/ambiguous matches require user choice; never guess an instance from a partial name."""
    return discover_sessions(scene)

@mcp.tool(annotations=READ)
def blender_status(pid: int | None=None)->dict:
    """Read bridge/application version. Omit PID only if exactly one registered instance exists."""
    return request('status',pid=pid,timeout=5)

@mcp.tool(annotations=READ)
def blender_scene_info(pid: int | None=None)->dict:
    """Read scene path/dirty flag, selection and current frame."""
    return request('scene_info',pid=pid)

@mcp.tool(annotations=READ)
def blender_scene_state(pid: int | None=None)->dict:
    """Read structural snapshot before each write. It is not a full property revision; inspect targets immediately before changing them."""
    return request('structured_state',pid=pid)

@mcp.tool(annotations=READ)
def blender_inspect_scene(pid: int | None=None)->dict:
    """Audit image/movie/sound/library paths without evaluating expressions. Packed assets marked separately; UDIM/sequences/caches/fonts completeness unverified."""
    return request('inspect_scene',pid=pid)

@mcp.tool(annotations=READ)
def blender_list_objects(pid: int | None=None,selected: bool=False,object_type: str='',limit: int=200)->dict:
    """Inspect exact object names/session IDs and local transforms in current scene. At most1000; reports truncation."""
    return request('structured_query',dict(selected=selected,object_type=object_type,limit=limit),pid)

@mcp.tool(annotations=WRITE)
def blender_scene_file(action: str,pid: int,expected_snapshot: str,path: str='',discard_changes: bool=False,overwrite: bool=False)->dict:
    """New/open/save .blend. Dirty scene replacement requires explicit discard authorization. Existing output requires overwrite. Open disables embedded scripts and keeps UI; host/plugin callbacks remain possible. No retries on timeout."""
    return request('structured_file',dict(action=action,pid=pid,expected_snapshot=expected_snapshot,path=path,discard_changes=discard_changes,overwrite=overwrite),pid)

@mcp.tool(annotations=WRITE)
def blender_create_object(kind: str,name: str,pid: int,expected_snapshot: str,vertices: list[list[float]] | None=None,faces: list[list[int]] | None=None)->dict:
    """Create named cube/mesh/empty/camera/point_light/sun_light/area_light using data API. Custom mesh max10000 vertices/faces; no current-selection dependence or auto render."""
    return request('structured_create',dict(kind=kind,name=name,pid=pid,expected_snapshot=expected_snapshot,vertices=vertices,faces=faces),pid)

@mcp.tool(annotations=WRITE)
def blender_edit_object(action: str,name: str,pid: int,expected_snapshot: str,new_name: str='',values: dict | None=None,confirm_delete: bool=False)->dict:
    """Rename/duplicate/delete/transform/visibility exact object. Transform local location/rotation_euler(radians)/scale vectors, refuses animated/constrained/locked targets. Delete needs user-authorized confirm_delete. Linked/overridden data protected."""
    return request('structured_edit',dict(action=action,name=name,pid=pid,expected_snapshot=expected_snapshot,new_name=new_name,values=values,confirm_delete=confirm_delete),pid)

@mcp.tool(annotations=WRITE)
def blender_select_objects(names: list[str],pid: int,expected_snapshot: str)->dict:
    """Replace selection by exact names in current view layer, first becomes active; empty clears. Max1000."""
    return request('structured_selection',dict(names=names,pid=pid,expected_snapshot=expected_snapshot),pid)

@mcp.tool(annotations=WRITE)
def blender_material(name: str,pid: int,action: str='get',expected_snapshot: str='',values: dict | None=None,object_name: str='')->dict:
    """Get/create/set/assign material. Basic non-node diffuse_color RGBA/roughness/metallic in0..1; node material editing refused. Assign appends unique slot and refuses shared object data. Writes require fresh snapshot."""
    return request('structured_material',dict(name=name,pid=pid,action=action,expected_snapshot=expected_snapshot,values=values,object_name=object_name),pid)

@mcp.tool(annotations=WRITE)
def blender_camera(name: str,pid: int,action: str='get',expected_snapshot: str='',values: dict | None=None)->dict:
    """Get/set lens,clip_start,clip_end; activate makes named camera scene camera. Reject shared/animated data edits. Explicit snapshot for writes."""
    return request('structured_camera',dict(name=name,pid=pid,action=action,expected_snapshot=expected_snapshot,values=values),pid)

@mcp.tool(annotations=WRITE)
def blender_light(name: str,pid: int,action: str='get',expected_snapshot: str='',values: dict | None=None)->dict:
    """Get/set light energy and RGB color0..1. Refuses shared/animated data edits. No rendering."""
    return request('structured_light',dict(name=name,pid=pid,action=action,expected_snapshot=expected_snapshot,values=values),pid)

@mcp.tool(annotations=WRITE)
def blender_timeline(pid: int,action: str='get',expected_snapshot: str='',values: dict | None=None)->dict:
    """Get/set integer frame_start/frame_end/frame_current/fps; does not retime keys or render."""
    return request('structured_timeline',dict(pid=pid,action=action,expected_snapshot=expected_snapshot,values=values),pid)

@mcp.tool(annotations=WRITE)
def blender_render_settings(pid: int,action: str='get',expected_snapshot: str='',values: dict | None=None)->dict:
    """Get/set resolution_x/y/percentage and supported engine. Does not render or set output paths. Unsupported engines fail explicitly."""
    return request('structured_render_settings',dict(pid=pid,action=action,expected_snapshot=expected_snapshot,values=values),pid)

@mcp.tool(annotations=WRITE)
def blender_execute_python(code: str,pid: int,expected_snapshot: str,timeout: float=30)->dict:
    """Execute user-authorized Python on mainthread, bpy available, assign result. Full user privileges, not sandboxed; may write files/network. ExplicitPID+snapshot. Never retry timed-out writes; partial changes may exist."""
    return request('execute_python',dict(code=code,pid=pid,expected_snapshot=expected_snapshot),pid,timeout)

if __name__=='__main__':mcp.run(transport='stdio')
