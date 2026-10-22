# Bubble Photoshop 0.5.0

Windows Photoshop control through its native COM automation. Install this plugin in Codex, open Photoshop normally, and list sessions. **No Creative Cloud Desktop, UPIA, UXP Developer Tool, CCX, panel, pairing code, or Photoshop-side files are required.** The plugin never changes Adobe licensing, security, COM registration, startup or user documents during setup.

## Requirements and boundaries

- Windows; an existing supported Photoshop installation with its native, version-specific COM registration. Native target tested: Photoshop 2025 / 26.2.0. Other versions are not implied tested.
- Codex and `uv` use a locked external Python environment with `mcp` and Windows-only `pywin32`. No virtual environment is created in the deployed package.
- Open Photoshop yourself. Discovery and requests never launch it. Only an existing COM object is used.
- Different registered installations can be listed and explicitly selected. Two processes from the **same executable cannot be independently routed through COM** and are refused. Close extra instances yourself before connecting.
- Native JSX is different from UXP batchPlay. There is no batchPlay API in this package.

## Tools

| Tool | Behavior |
| --- | --- |
| photoshop_installation_status | Read registered installations and zero-install requirements |
| photoshop_install_bridge | Compatibility status alias; writes no software files |
| photoshop_uninstall_bridge | Reports no native bridge files to remove |
| photoshop_list_sessions | List exact process identities, versions and documents |
| photoshop_scene_info | Read document IDs and active document |
| photoshop_inspect_document | Read a selected document and up to 2000 layers |
| photoshop_create_document | Create and activate a new unsaved RGB/grayscale document, including from an empty session |
| photoshop_open_file | Open and activate an absolute existing PSD/PSB or supported raster image; scripts rejected |
| photoshop_activate_document | Activate an explicit existing document ID |
| photoshop_save_document | Save active selected document as layered PSD; overwrite defaults false |
| photoshop_export_document | Export PNG/JPEG from a temporary duplicate, preserving the source |
| photoshop_close_document | Close selected document; refuse dirty documents unless discard is authorized |
| photoshop_resize_image / resize_canvas | Resize pixels or canvas with explicit pixel units |
| photoshop_crop_document / rotate_document | Crop pixel bounds or rotate the selected document |
| photoshop_create_layer / update_layer | Create pixel/group/text layers; edit properties and text size in points |
| photoshop_duplicate_layer / delete_layer | Duplicate or delete by stable layer ID |
| photoshop_translate_layer / select_layer | Move by pixel offsets or select an explicit layer |
| photoshop_selection_info / selection | Read and modify pixel selections, including rectangle modes and ellipse replace |
| photoshop_fill_selection | Fill selected normal-layer pixels with explicit RGB color |
| photoshop_layer_mask | Create, enable, disable, delete or apply a raster layer mask |
| photoshop_adjust_color | Destructive brightness/contrast, levels, invert or desaturate |
| photoshop_apply_filter | Destructive Gaussian blur, unsharp mask or median |
| photoshop_smart_object | Convert a normal pixel layer or replace verified embedded contents |
| photoshop_execute_script | Execute user-authorized JSX with explicit session and active document ID |

Scripts can affect Photoshop and files beyond the selected document. The ID guard is not a sandbox. Use create_document or open_file when the session is empty; use activate_document to select the intended existing document before JSX. Script execution itself retains its active-document guard. These native tools are preferred to UI automation. Each operation runs in a bounded worker. A timeout stops the worker but may not cancel the Photoshop operation: never automatically retry.

## Install, update and uninstall

Install/update the Codex plugin from the Bubble marketplace. No additional Photoshop bridge install or restart is normally necessary. Remove the Codex plugin to remove the integration; Adobe's built-in COM support belongs to Photoshop and is left intact. Native mode does not remove legacy UXP panels installed separately. No invented enable-file or installation receipt is used.

## Validation

`tests/test_native.py` checks routing and failure handling. `tests/stdio_smoke.py` performs **real MCP stdio to the running Photoshop COM object**, reads documents/layers and reports actual version. It needs a running Photoshop and has no simulated host. Actual Codex installation/removal is covered by the repository acceptance harness; see root `VALIDATION.md` for observed results and limits.

## References

- [Adobe Photoshop scripting](https://helpx.adobe.com/photoshop/using/scripting.html)
- [Microsoft GetActiveObject](https://learn.microsoft.com/en-us/dotnet/fundamentals/runtime-libraries/system-runtime-interopservices-marshal-getactiveobject)

Software icon provenance: `assets/`.

## Standard editing safeguards

All edits require the explicit session and active document ID. Inspect returns stable `layer_id` and `active_layer_id`, including background ID zero where Photoshop exposes it; never use layer indices as identity. Layer IDs must resolve inside that document. Layer locking/native restrictions remain enforced by Photoshop.

Save changes the current document path to a layered PSD. Export converts only a temporary duplicate to RGB 8-bit; JPEG flattens only that duplicate, which is closed in finally while the original is restored active. Absolute output paths need an existing parent directory and matching extension. Existing output is refused unless `overwrite=True` is explicitly authorized, with checks in Python and immediately before native save. These checks do not promise atomic exclusion against another program concurrently writing the same path.

A running MCP server snapshots its worker source into an owned external temporary directory at startup. Updating/removing the package does not break that server's workers. The snapshot is cleaned up when the server exits; no source/worker files are installed into Photoshop.

## Selections, masks and pixel operations

Selection tools report bounds, not an exact shape serialization. Rectangle supports replace/add/subtract/intersect; ellipse supports replace. Expand/contract/feather take whole pixel amounts. Fill requires an explicit selection: request `all` first for a full-image fill.

Fill, adjustments and filters target **normal pixel layers and RGB/grayscale component channels**, not whatever mask channel was previously active. They select exactly one layer by ID, clear layer multiselection, and leave component channels active. Current pixel selection is respected. No automatic rasterization, unlocking, color-mode conversion or saving occurs. Supported pixel depth is 8/16 bit; Photoshop may impose further native restrictions.

Raster masks support reveal/hide all or current selection, enable/disable, delete without applying, and destructive apply to a normal pixel layer. Existing masks are never silently replaced. Vector masks and painting directly into a mask are outside these tools. Inspection returns raster-mask presence/enabled state, smart-object state and selection bounds.

Smart conversion returns the new stable layer ID. Replacement requires a verified embedded object (`smart_object_linked=false`) and an existing PNG/JPEG/TIFF/BMP. Linked or unknown objects, script/PDF/raw/PSD replacement sources and automatic editing of embedded contents are not supported in this release. No external linked source is modified.

Hue/saturation, AI filters, neural filters, adjustment layers and smart filters are not claimed by these standard tools. The bounded authorized JSX tool remains available for separately requested operations.

Smart-object replacement safety limit: native testing confirmed that ordinary duplicates can share embedded contents, so replacing one may also change its twin. Until reliable independent-content identity is available, replacement refuses when **any other smart-object layer exists in any open document**, including nested groups, linked objects or unrelated smart objects. The error lists document/layer IDs. This deliberately conservative check runs before selection/channel changes or replacement. Never delete, close, unlink, or independently copy user objects to bypass it without an explicit user request. Conversion itself remains available.

## 0.5 workflow additions

39 structured tools include document duplication, layer scale/rotation and relative ordering, blend modes, exact-font text styling, history inspection/restoration, and named alpha-channel selection storage/loading. History restoration requires the complete observed history snapshot; inspect again after any change. Alpha names never overwrite existing channels. Text styling preserves visibility and unrelated text properties. Locked/background/linked layers are refused where the operation cannot be isolated safely.

Existing adjustment/filter tools additionally expose RGB color balance, motion blur, noise and sharpening. These operate on the selected normal pixel layer, with the existing channel and lock guards. They do not create adjustment layers or bypass unsupported modes. Photoshop native acceptance is reported separately from DOM simulations.

History snapshots compare document ID, action names and active index, not persistent history-state identity. An undo followed by a same-named action can reproduce that fingerprint. Read immediately before restoring with no intervening edits; never present this guard as a full revision check.
