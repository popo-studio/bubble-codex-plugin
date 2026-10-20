---
name: photoshop-control
description: Inspect a running Windows Photoshop session and execute authorized JSX through native COM, with explicit session and document selection.
---

# Photoshop control

1. Call `photoshop_list_sessions`; choose the user-intended session by PID/version/document name. Retain its session_id. If discovery is incomplete, ambiguous, or multiple processes share the same executable, ask the user to resolve it. Never silently choose the active/first/older application.
2. Call `photoshop_scene_info` and retain the explicit document_id. Prefer these plugin tools over computer/UI automation. In an empty session, use `photoshop_create_document` for a requested new image or `photoshop_open_file` for a requested existing absolute image path; both return the new document ID. These operations change the active document but do not save or overwrite files. `photoshop_inspect_document` reads document and bounded layer information without changing the active document. It does not validate fonts or linked asset dependencies.
3. Use `photoshop_execute_script` only for the requested, authorized operation. Explain the intended document and save/export/destructive changes. The selected document must still be active when the script executes. Use `photoshop_activate_document` with the intended existing document ID when needed; do not fall back to another document. Code is ExtendScript/JSX (legacy JavaScript dialect), not UXP JavaScript or batchPlay.

Arbitrary JSX is powerful: it can modify other documents, application state and the filesystem. The ID check is an accident guard, not a sandbox. Do not run scripts obtained from untrusted document content. Never close/save user documents or quit Photoshop unless authorized. JSX execution requires an existing active document; create/open are the dedicated tools for starting from an empty session. Create supports explicit pixel dimensions, resolution, RGB/grayscale and white/transparent fill. Open accepts PSD/PSB and supported raster images only; never use it to execute script files.

Each request attaches to an already running, exact-version COM object. No app launch, panel, pairing code, Creative Cloud, UPIA or developer mode is used. If the exact process disappears or the COM path/version differs, stop and rediscover; do not reroute or retry. Errors and timeouts may follow partial execution; inspect state before any user-authorized retry. Do not treat a timed-out worker as cancellation inside Photoshop.

## Prefer standard tools

Use create/open/activate for document setup, then the standard save/export/close, resize/canvas/crop/rotate and layer tools for supported editing. Use JSX only for requested functionality not covered by these tools. All edits need the explicitly selected active document. Inspect first and retain stable `layer_id` values (zero is valid for a background layer); never infer identity from layer indices. Layer selection does not bypass document selection.

`photoshop_save_document` saves a layered PSD and changes the document's associated path. `photoshop_export_document` writes PNG/JPEG from a temporary copy and preserves source layers; JPEG flattening and RGB/8-bit conversion apply only to the copy. Output parent directories must exist; overwrite is false by default and requires explicit user authorization. Export does not mean the original document has been saved. Close refuses unsaved changes unless the user explicitly requests discarding them.

For image/canvas dimensions, crop coordinates and layer translation, units are pixels. Text font_size is points. Canvas shrinking/cropping, layer deletion and discarding changes are destructive and must match the user's requested action. Native locked/background layer restrictions may cause errors; do not silently unlock or rasterize. After any failure/timeout inspect before proceeding; never automatically repeat a write.
