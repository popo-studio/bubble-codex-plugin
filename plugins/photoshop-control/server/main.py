"""Photoshop tools through the existing Windows COM automation server."""
import json
from pathlib import Path
import subprocess
import sys
import time
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from native import discover, installations, failure, select

mcp = FastMCP("Bubble Photoshop Control")
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True)


def call(operation, session_id=None, timeout=20, **kwargs):
    if not 0 < timeout <= 120:
        return failure("invalid_timeout", "timeout must be in (0, 120]")
    try:
        selected = select(discover(), session_id)
        request = {"operation":operation, "session_id":selected["session_id"], "expires_at":time.time()+timeout, **kwargs}
        result = subprocess.run([sys.executable, "-B", str(Path(__file__).with_name("worker.py"))], input=json.dumps(request), capture_output=True, text=True, timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode:
            return failure("worker_failed", "COM worker failed; operation may have partially executed. Do not retry automatically. " + result.stderr[-2000:])
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        return failure("timeout_outcome_unknown", "Worker timed out and was stopped. Photoshop may still be executing or may have completed the request. Inspect state before any retry; never retry automatically.")
    except Exception as exc:
        return failure("connection_error", str(exc))


@mcp.tool(annotations=READ)
def photoshop_installation_status() -> dict:
    """Read version-specific native COM registrations. Windows only. Does not install, launch, or change Photoshop. No Creative Cloud, UPIA, developer tools or PS-side bridge needed."""
    return {"ok":True,"data":{"platform":sys.platform,"installations":installations(),"transport":"Windows native COM","software_bridge_required":False,"software_files_installed":[],"note":"Install the Codex plugin and open Photoshop normally. Existing native COM registration is required; no registration or software installation is performed."}}


@mcp.tool(annotations=READ)
def photoshop_install_bridge(confirmed: bool = False) -> dict:
    """Compatibility/status tool: native COM requires no Photoshop-side bridge installation. Never creates an installation receipt or modifies Photoshop files."""
    return photoshop_installation_status()


@mcp.tool(annotations=READ)
def photoshop_uninstall_bridge(confirmed: bool = False) -> dict:
    """Native COM mode installs no Photoshop files. Remove the Codex plugin to remove its tools; native Photoshop registration belongs to Adobe and is never deleted. Legacy UXP panels, if manually installed, are not removed by this tool."""
    return {"ok":True,"data":{"removed_files":[],"software_bridge_required":False,"note":"No Photoshop-side files were installed by native COM mode. Uninstall Bubble Photoshop in Codex. Any separately installed legacy UXP panel requires its own original uninstall route."}}


@mcp.tool(annotations=READ)
def photoshop_list_sessions(document: str | None = None) -> dict:
    """List running Photoshop processes without launching any. Probe documents only through existing exact-version COM objects. Use session_id for all later operations. Multiple processes using the same executable are unrouteable and must be resolved by the user. document optionally matches exact path/name/stem; ambiguous or unavailable sessions prevent silent selection."""
    try:
        rows = discover()
        for row in rows:
            if row["status"] == "available":
                info = call("scene_info", row["session_id"])
                if info.get("ok"):
                    row.update(info["data"])
                else:
                    row["status"] = "unavailable"
                    row["error"] = info.get("error")
        matches = []
        for row in rows:
            if row["status"] != "available":
                continue
            if document is None or any(document.casefold() in {str(d.get("name", "")).casefold(),str(d.get("path", "")).casefold(),Path(d.get("name", "")).stem.casefold()} for d in row.get("documents", [])):
                matches.append(row["session_id"])
        blocked = any(row["status"] != "available" for row in rows)
        status = "incomplete" if blocked else "unique" if len(matches)==1 else "ambiguous" if matches else "none"
        return {"ok":True,"data":rows,"selection":{"status":status,"selected":matches[0] if status=="unique" else None,"matches":matches}}
    except Exception as exc:
        return failure("discovery_failed", str(exc))


@mcp.tool(annotations=READ)
def photoshop_scene_info(session_id: str | None = None) -> dict:
    """Read existing Photoshop version, open document IDs/names/paths and active document. Never launches Photoshop. Omit session only if exactly one running process is safely addressable."""
    return call("scene_info", session_id)


@mcp.tool(annotations=READ)
def photoshop_inspect_document(document_id: int, session_id: str | None = None) -> dict:
    """Read explicit document properties and up to 2000 layers without changing selection. Does not audit fonts, linked objects or all file dependencies."""
    return call("inspect_document", session_id, document_id=document_id)


@mcp.tool(annotations=WRITE)
def photoshop_execute_script(code: str, document_id: int, session_id: str, timeout: float = 30) -> dict:
    """Execute user-authorized ExtendScript/JSX via native DoJavaScript. Requires explicit session and currently active document ID. This check is not a sandbox: code can change any document, save/export/delete files or application state. Explain intended target and writes first. Never auto-retry after any failure/timeout, since effects may already exist. No UXP/batchPlay. timeout in (0,120]."""
    return call("execute_script", session_id, timeout, document_id=document_id, code=code)


if __name__ == "__main__":
    mcp.run(transport="stdio")
