# Bubble Photoshop 0.2.1

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
