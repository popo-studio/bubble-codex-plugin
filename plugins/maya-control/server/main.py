"""MCP stdio entrypoint: uv run --directory <plugin-root> server/main.py."""
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from client import list_sessions, request

mcp = FastMCP("Bubble Maya Control")
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
SCRIPT = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True)


@mcp.tool(annotations=READ)
def maya_list_sessions() -> dict:
    """List local Maya bridge sessions without exposing authentication secrets. Files may be stale."""
    return list_sessions()


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


if __name__ == "__main__":
    mcp.run(transport="stdio")
