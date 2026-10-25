"""Read-only Bubble plugin diagnostic tools."""
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
import diagnostics as d

mcp = FastMCP("Bubble Plugin Doctor")
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)


@mcp.tool(annotations=READ)
def doctor_status() -> dict:
    """Check this diagnostic server and runtime; no files modified or software started."""
    return d.status()


@mcp.tool(annotations=READ)
def doctor_inventory(codex_home: str | None = None, source_root: str | None = None) -> dict:
    """Inspect bounded Bubble cache directories and optionally compare a local marketplace source. Cache presence is not enabled/installed/runtime state. Does not read credentials or raw Codex config, query GitHub, or execute package code."""
    return d.inventory(codex_home, source_root)


@mcp.tool(annotations=READ)
def doctor_check_package(package_path: str) -> dict:
    """Check an exact absolute Bubble package directory for manifest/MCP parity, missing launch files, unsupported cwd and in-package .venv. Static checks do not prove tools loaded."""
    return d.package_check(package_path)


@mcp.tool(annotations=READ)
def doctor_capabilities(package_path: str) -> dict:
    """List statically declared tool names, descriptions, parameters and read/write hints in one exact Bubble package. Reports duplicate names and package issues without importing or executing its code. Does not prove runtime loading or native software support."""
    return d.capabilities(package_path)


@mcp.tool(annotations=READ)
def doctor_check_bridge(app: str, runtime_directory: str) -> dict:
    """Read ownership metadata and verify hashes in an explicit installed runtime directory. app: maya/nuke/houdini/max/unreal/unity/blender. For Blender pass user scripts directory. Reports modified/missing files; does not inspect startup scripts or prove loaded version. For complete checks use the owning plugin's installation_status."""
    return d.bridge_check(app, runtime_directory)


@mcp.tool(annotations=READ)
def doctor_list_sessions(app: str, session_directory: str | None = None, probe: bool = True) -> dict:
    """Inspect one DCC's bridge registry and optionally send read-only scene_info to validated loopback endpoints. At most 16 probes, bounded time/output. Tokens never returned. Multiple instances require user selection; no automatic selection or reconnection."""
    return d.sessions(app, session_directory, probe)


@mcp.tool(annotations=READ)
def doctor_check_log(log_path: str) -> dict:
    """Classify known startup errors from the last 256 KiB of one explicitly selected local log. Returns fixed clues only, never raw logs/secrets. No scan of unrelated logs."""
    return d.log_check(log_path)


@mcp.tool(annotations=READ)
def doctor_repair_guidance(plugin_name: str, action: str = "repair") -> dict:
    """Return a concrete workflow for repair/update/uninstall using supported Codex/owning-plugin tools. Does not execute it. Select exact profile/project and obtain authorization for displayed changes before mutations."""
    return d.guidance(plugin_name, action)


if __name__ == "__main__":
    mcp.run(transport="stdio")
