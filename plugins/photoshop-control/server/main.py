"""Photoshop UXP tools; no ExtendScript, arbitrary eval or automatic host install."""
import atexit
import threading
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from broker import Broker, failure
from installation import installation_status, install_bridge, uninstall_bridge

mcp = FastMCP("Bubble Photoshop Control")
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True)
_broker = None
_lock = threading.Lock()

def broker():
    global _broker
    with _lock:
        if _broker is None:
            _broker = Broker("photoshop")
            atexit.register(_broker.close)
        return _broker

def call(operation, args, session_id, timeout):
    if _broker is None:
        return failure("not_paired", "Generate a pairing code and connect the Photoshop UXP panel first")
    return _broker.request(operation, args, session_id, timeout)

@mcp.tool(annotations=READ)
def photoshop_installation_status(package_path: str | None = None) -> dict:
    """Inspect Photoshop/Adobe installer and optional absolute .ccx package_path. Does not install or launch applications."""
    return installation_status(package_path)

@mcp.tool(annotations=WRITE)
def photoshop_install_bridge(confirmed: bool = False, package_path: str | None = None) -> dict:
    """Preview official UXP installation with the included candidate CCX, or optional absolute package_path for a release-matching CCX. Packaging is not native Adobe validation; confirmed=True only after user authorizes displayed package/Adobe installation changes. Adobe may show confirmation. Never auto-restart Photoshop or silently enable developer mode. This is separate from Codex plugin installation."""
    return install_bridge(confirmed=confirmed, package_path=package_path)

@mcp.tool(annotations=WRITE)
def photoshop_uninstall_bridge(confirmed: bool = False) -> dict:
    """Preview removal through Adobe's official installer. True only with user authorization. Does not close Photoshop/documents. Close/disconnect panel to end a live connection. Codex plugin removal alone does not uninstall the Adobe panel."""
    return uninstall_bridge(confirmed=confirmed)

@mcp.tool(annotations=READ)
def photoshop_pairing() -> dict:
    """Get a private connection code for this Codex process. User opens Bubble Photoshop panel and pastes code, then Connect. This is a credential, not executable code; never place it in logs or external messages. Keep panel open; reconnect after MCP restarts. No host changes."""
    return broker().pairing()

@mcp.tool(annotations=READ)
def photoshop_list_sessions(document: str | None = None) -> dict:
    """List paired Photoshop panels and open document names/paths/IDs. Optional exact filename/stem/full path match; ambiguous matches require user choice. Session UUID is panel identity, not OS PID. Only paired panels are visible; never guess another instance. Retain selected session_id and document_id and recheck before writing."""
    if _broker is None:
        return {"ok":True, "data":[], "selection":{"status":"unspecified", "selected":None, "matches":[]}, "note":"No panel paired with this Codex process"}
    return _broker.sessions(document)

@mcp.tool(annotations=READ)
def photoshop_scene_info(session_id: str | None = None) -> dict:
    """Read paired Photoshop version, all open documents and active document. Omit session only if exactly one exists."""
    return call("scene_info", {}, session_id, 10)

@mcp.tool(annotations=READ)
def photoshop_inspect_document(document_id: int, session_id: str | None = None) -> dict:
    """Read document properties and bounded layer inventory (up to 2000 layers). Does NOT verify missing fonts, linked smart objects or other dependencies. Explicit document ID prevents active-document guessing."""
    return call("inspect_scene", {"document_id":document_id}, session_id, 15)

@mcp.tool(annotations=WRITE)
def photoshop_batch_play(commands: list[dict], document_id: int, session_id: str | None = None, timeout: float = 30) -> dict:
    """Run 1–100 user-authorized Photoshop batchPlay descriptors in executeAsModal. Selected document must still be active at execution. Descriptors are powerful and may affect other documents/application state; the ID check is not a sandbox. Explain target and destructive/save/export changes before execution. No arbitrary JS/eval/ExtendScript. File access remains subject to UXP permissions/tokens; raw paths are not guaranteed accepted. Never retry automatically after failure/timeout: partial changes may exist. timeout in (0,120]."""
    return call("batch_play", {"commands":commands,"document_id":document_id}, session_id, timeout)

if __name__ == "__main__":
    mcp.run(transport="stdio")
