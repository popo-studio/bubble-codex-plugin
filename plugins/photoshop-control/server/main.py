"""Photoshop tools through the existing Windows COM automation server."""
import json
import atexit
import tempfile
from pathlib import Path
import subprocess
import sys
import time
from typing import Literal
from pydantic import StrictInt, StrictFloat, StrictBool
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from native import discover, installations, failure, select

# A running server must survive package update/removal. Snapshot only owned Python
# source at startup into an external temporary directory, never into the plugin.
_worker_runtime = tempfile.TemporaryDirectory(prefix="bubble-photoshop-worker-")
atexit.register(_worker_runtime.cleanup)
for _name in ("native.py", "worker.py", "operations.py", "advanced.py"):
    (Path(_worker_runtime.name) / _name).write_bytes(Path(__file__).with_name(_name).read_bytes())
_worker_path = str(Path(_worker_runtime.name) / "worker.py")

mcp = FastMCP("Bubble Photoshop Control")
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True)


def call(operation, session_id=None, timeout=20, **kwargs):
    if not 0 < timeout <= 120:
        return failure("invalid_timeout", "timeout must be in (0, 120]")
    try:
        selected = select(discover(), session_id)
        request = {"operation":operation, "session_id":selected["session_id"], "expires_at":time.time()+timeout, **kwargs}
        result = subprocess.run([sys.executable, "-B", _worker_path], input=json.dumps(request), capture_output=True, text=True, timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
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


@mcp.tool(annotations=WRITE)
def photoshop_create_document(session_id: str, width: StrictInt, height: StrictInt, name: str = "Untitled", resolution: StrictFloat = 72, mode: Literal["RGB", "grayscale"] = "RGB", background: Literal["white", "transparent"] = "white", timeout: float = 30) -> dict:
    """Create and activate an unsaved document in the explicitly selected session, including when no documents exist. Width/height are 1–30000 pixels, at most 100 million pixels total; resolution 1–1200 ppi. RGB/grayscale, white/transparent only. Returns document ID; never saves or overwrites a file. Do not retry automatically after errors/timeouts."""
    return call("create_document", session_id, timeout, width=width, height=height, name=name, resolution=resolution, mode=mode, background=background)


@mcp.tool(annotations=WRITE)
def photoshop_open_file(path: str, session_id: str, timeout: float = 30) -> dict:
    """Open/activate an absolute existing PSD/PSB or supported raster image in the explicitly selected session, even with no open documents. Script files and unsupported formats are rejected. Does not save/overwrite files. Photoshop may require format/profile interaction; timeout does not cancel its operation. Never auto-retry."""
    return call("open_file", session_id, timeout, path=path)


@mcp.tool(annotations=WRITE)
def photoshop_activate_document(document_id: StrictInt, session_id: str, timeout: float = 20) -> dict:
    """Activate the explicitly chosen existing document ID within the selected session and return its properties. Does not save/close documents. Use before JSX when its intended document is not active; never substitute another document."""
    return call("activate_document", session_id, timeout, document_id=document_id)


@mcp.tool(annotations=WRITE)
def photoshop_save_document(document_id: StrictInt, session_id: str, path: str, overwrite: StrictBool = False, timeout: float = 30) -> dict:
    """Save the active selected document as a layered PSD at an absolute path. Changes this document's associated save path. Parent directory must exist. Existing file overwrite requires explicit authorization and overwrite=True; default refuses. No automatic retry."""
    return call("save_document",session_id,timeout,document_id=document_id,path=path,overwrite=overwrite)


@mcp.tool(annotations=WRITE)
def photoshop_export_document(document_id: StrictInt, session_id: str, path: str, format: Literal["png","jpeg"] = "png", quality: StrictInt = 10, overwrite: StrictBool = False, timeout: float = 30) -> dict:
    """Export an RGB 8-bit PNG or JPEG from a temporary duplicate; source document/layers are preserved. JPEG quality 0–12; only duplicate is flattened. Absolute matching extension, existing parent and explicit overwrite authorization required. Finally closes duplicate and restores source active document. No retry after errors/timeouts."""
    return call("export_document",session_id,timeout,document_id=document_id,path=path,format=format,quality=quality,overwrite=overwrite)


@mcp.tool(annotations=WRITE)
def photoshop_close_document(document_id: StrictInt, session_id: str, discard_changes: StrictBool = False, timeout: float = 20) -> dict:
    """Close the selected active document. Refuse unsaved changes unless the user authorized discarding them and discard_changes=True. Does not save automatically or quit Photoshop."""
    return call("close_document",session_id,timeout,document_id=document_id,discard_changes=discard_changes)


@mcp.tool(annotations=WRITE)
def photoshop_resize_image(document_id: StrictInt, session_id: str, width: StrictInt, height: StrictInt, resolution: StrictFloat | None = None, timeout: float = 30) -> dict:
    """Resample selected active image with bicubic interpolation to explicit pixel dimensions (1–30000; max 100 million pixels). Optional resolution 1–1200 ppi; omitted preserves it. Does not save."""
    return call("resize_image",session_id,timeout,document_id=document_id,width=width,height=height,resolution=resolution)


@mcp.tool(annotations=WRITE)
def photoshop_resize_canvas(document_id: StrictInt, session_id: str, width: StrictInt, height: StrictInt, anchor: Literal["center","top_left","top","top_right","left","right","bottom_left","bottom","bottom_right"] = "center", timeout: float = 30) -> dict:
    """Change active selected canvas pixel dimensions without resampling. Shrinking crops content; explain before use. Width/height 1–30000, max 100 million pixels. Explicit anchor controls placement. Does not save."""
    return call("resize_canvas",session_id,timeout,document_id=document_id,width=width,height=height,anchor=anchor)


@mcp.tool(annotations=WRITE)
def photoshop_crop_document(document_id: StrictInt, session_id: str, left: StrictFloat, top: StrictFloat, right: StrictFloat, bottom: StrictFloat, timeout: float = 30) -> dict:
    """Crop selected active document to finite pixel bounds within the current canvas. Right>left, bottom>top; changes may remove content. Does not save."""
    return call("crop_document",session_id,timeout,document_id=document_id,left=left,top=top,right=right,bottom=bottom)


@mcp.tool(annotations=WRITE)
def photoshop_rotate_document(document_id: StrictInt, session_id: str, angle: StrictFloat, timeout: float = 30) -> dict:
    """Rotate selected active canvas by finite angle -360..360 degrees, using Photoshop's rotateCanvas. May change dimensions/resample content. Does not save."""
    return call("rotate_document",session_id,timeout,document_id=document_id,angle=angle)


@mcp.tool(annotations=WRITE)
def photoshop_create_layer(document_id: StrictInt, session_id: str, kind: Literal["pixel","group","text"] = "pixel", name: str = "Layer", text: str = "Text", font_size: StrictFloat = 48, timeout: float = 20) -> dict:
    """Create a pixel layer, group or text layer in selected active document. Text size is points (1–1296); returns stable layer_id. No implicit document selection or save."""
    return call("create_layer",session_id,timeout,document_id=document_id,kind=kind,name=name,text=text,font_size=font_size)


@mcp.tool(annotations=WRITE)
def photoshop_update_layer(document_id: StrictInt, session_id: str, layer_id: StrictInt, name: str | None = None, visible: StrictBool | None = None, opacity: StrictFloat | None = None, text: str | None = None, font_size: StrictFloat | None = None, timeout: float = 20) -> dict:
    """Update an explicit stable layer ID belonging to active selected document. At least one property required: name, visible, opacity 0–100, text contents or font_size 1–1296 points (text layers only). Does not save."""
    return call("update_layer",session_id,timeout,document_id=document_id,layer_id=layer_id,name=name,visible=visible,opacity=opacity,text=text,font_size=font_size)


@mcp.tool(annotations=WRITE)
def photoshop_duplicate_layer(document_id: StrictInt, session_id: str, layer_id: StrictInt, name: str | None = None, timeout: float = 20) -> dict:
    """Duplicate the explicit layer within the selected active document; optional new name. Returns a new stable layer_id. Does not save."""
    return call("duplicate_layer",session_id,timeout,document_id=document_id,layer_id=layer_id,name=name)


@mcp.tool(annotations=WRITE)
def photoshop_delete_layer(document_id: StrictInt, session_id: str, layer_id: StrictInt, timeout: float = 20) -> dict:
    """Delete the explicitly authorized layer ID from the selected active document. Destructive; never infer layer identity from index or current selection. Does not save."""
    return call("delete_layer",session_id,timeout,document_id=document_id,layer_id=layer_id)


@mcp.tool(annotations=WRITE)
def photoshop_translate_layer(document_id: StrictInt, session_id: str, layer_id: StrictInt, x: StrictFloat, y: StrictFloat, timeout: float = 20) -> dict:
    """Translate explicit layer by x/y pixel offsets (-30000..30000) inside the active selected document. Does not resize or save; locked/background layers may reject changes."""
    return call("translate_layer",session_id,timeout,document_id=document_id,layer_id=layer_id,x=x,y=y)


@mcp.tool(annotations=WRITE)
def photoshop_select_layer(document_id: StrictInt, session_id: str, layer_id: StrictInt, timeout: float = 20) -> dict:
    """Select the explicit stable layer ID belonging to the active selected document. Does not change document selection, content, or save."""
    return call("select_layer",session_id,timeout,document_id=document_id,layer_id=layer_id)


@mcp.tool(annotations=READ)
def photoshop_selection_info(document_id: StrictInt, session_id: str) -> dict:
    """Read whether selected active document has a selection and its pixel bounds. Bounds do not describe shape or feathering. Does not change selection or channels."""
    return call("selection_info",session_id,20,document_id=document_id)


@mcp.tool(annotations=WRITE)
def photoshop_selection(document_id: StrictInt, session_id: str, action: Literal["all","deselect","invert","rectangle","ellipse","expand","contract","feather"], mode: Literal["replace","add","subtract","intersect"] = "replace", left: StrictFloat | None = None, top: StrictFloat | None = None, right: StrictFloat | None = None, bottom: StrictFloat | None = None, amount: StrictInt | None = None, timeout: float = 20) -> dict:
    """Modify selected active document selection. Rectangle supports replace/add/subtract/intersect with explicit pixel bounds; ellipse currently replace only. Expand/contract/feather require an existing selection and integer amount 1–500 pixels. Returns selection bounds. Does not paint or save."""
    return call("selection",session_id,timeout,document_id=document_id,action=action,mode=mode,left=left,top=top,right=right,bottom=bottom,amount=amount)


@mcp.tool(annotations=WRITE)
def photoshop_fill_selection(document_id: StrictInt, session_id: str, layer_id: StrictInt, color: str, opacity: StrictFloat = 100, timeout: float = 30) -> dict:
    """Fill existing selection on the exact normal pixel layer using #RRGGBB and opacity 0–100. Explicitly selects only this layer and RGB/grayscale component channels, never a mask. Use selection all for whole-image fill. Destructive; no implicit rasterization, unlocking, or save."""
    return call("fill_selection",session_id,timeout,document_id=document_id,layer_id=layer_id,color=color,opacity=opacity)


@mcp.tool(annotations=WRITE)
def photoshop_layer_mask(document_id: StrictInt, session_id: str, layer_id: StrictInt, action: Literal["create","enable","disable","delete","apply"], mode: Literal["reveal_all","hide_all","reveal_selection","hide_selection"] = "reveal_all", timeout: float = 30) -> dict:
    """Manage the exact layer's raster mask (not vector masks). Create refuses existing masks; selection modes require a selection. Enable/disable preserve mask; delete discards it; apply destructively applies to normal pixel layer only. Explicitly selects one layer and returns to component pixel channels. Does not save."""
    return call("layer_mask",session_id,timeout,document_id=document_id,layer_id=layer_id,action=action,mode=mode)


@mcp.tool(annotations=WRITE)
def photoshop_adjust_color(document_id: StrictInt, session_id: str, layer_id: StrictInt, adjustment: Literal["brightness_contrast","levels","invert","desaturate"], brightness: StrictInt = 0, contrast: StrictInt = 0, input_black: StrictInt = 0, input_white: StrictInt = 255, gamma: StrictFloat = 1, output_black: StrictInt = 0, output_white: StrictInt = 255, timeout: float = 30) -> dict:
    """Destructively adjust exact normal pixel layer (8/16-bit RGB/grayscale), respecting current selection. Explicitly selects only this layer and component channels; masks untouched. Brightness/contrast -100..100, levels 0..255 ordered endpoints and gamma .1..9.99. No automatic rasterization or adjustment-layer creation; no save."""
    return call("adjust_color",session_id,timeout,document_id=document_id,layer_id=layer_id,adjustment=adjustment,brightness=brightness,contrast=contrast,input_black=input_black,input_white=input_white,gamma=gamma,output_black=output_black,output_white=output_white)


@mcp.tool(annotations=WRITE)
def photoshop_apply_filter(document_id: StrictInt, session_id: str, layer_id: StrictInt, filter: Literal["gaussian_blur","unsharp_mask","median"], radius: StrictFloat = 1, amount: StrictFloat = 100, threshold: StrictInt = 0, timeout: float = 30) -> dict:
    """Destructively filter exact normal pixel layer, respecting selection. Gaussian/unsharp radius .1–250 px; unsharp amount 1–500%, threshold 0–255; median radius integer 1–100px. Selects one layer and component channels, never the mask. No implicit rasterization/smart-filter conversion or save."""
    return call("apply_filter",session_id,timeout,document_id=document_id,layer_id=layer_id,filter=filter,radius=radius,amount=amount,threshold=threshold)


@mcp.tool(annotations=WRITE)
def photoshop_smart_object(document_id: StrictInt, session_id: str, layer_id: StrictInt, action: Literal["convert","replace_contents"], path: str | None = None, timeout: float = 30) -> dict:
    """Convert one normal pixel layer to a smart object, or replace a verified embedded object's contents with absolute existing PNG/JPEG/TIFF/BMP. Linked/unknown objects are refused. Replacement also refuses if any other smart-object layer exists in any open document, because copied embedded objects may share contents; error lists other document/layer IDs. Selects exactly one layer; returns current stable ID because conversion can change it. Does not edit original source file or save document; no automatic retry."""
    return call("smart_object",session_id,timeout,document_id=document_id,layer_id=layer_id,action=action,path=path)


if __name__ == "__main__":
    mcp.run(transport="stdio")
