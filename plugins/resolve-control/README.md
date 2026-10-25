# Bubble DaVinci Resolve

Windows local Codex plugin for the official external Python API in **DaVinci Resolve Studio 21+**. Version 0.1.0. No Resolve-side bridge, startup file or copied console code is installed.

## Requirements and connection

- Install and open Resolve Studio normally. The free edition does not provide the external scripting workflow used here.
- In Resolve Preferences > System > General, set **External scripting using: Local**. Restart if Resolve requests it. The plugin does not enable this setting automatically and never requests Network mode.
- The official SDK module normally resides in `%PROGRAMDATA%/Blackmagic Design/DaVinci Resolve/Support/Developer/Scripting/Modules/DaVinciResolveScript.py`; `RESOLVE_SCRIPT_API` can explicitly select an absolute official Scripting directory. Native `fusionscript.dll` is loaded from the running Resolve executable's directory.
- The locked launcher uses 64-bit Python 3.10/3.11 (`>=3.10,<3.12`) to avoid legacy SDK wrappers depending on `imp`, removed in Python 3.12. Actual SDK/native ABI compatibility must be checked with the installed Resolve release. No SDK is redistributed.
- After prerequisites are satisfied, calls connect automatically to the already running application. No application is launched by this plugin.

The API does not document arbitrary PID selection. Multiple Resolve processes are displayed but all native calls are refused until the user keeps only the intended instance open. Session IDs combine PID and creation time; process identity is checked before and after SDK loading and immediately before edits. Project unique IDs prevent silently acting in a different current project. These checks are not a lock against simultaneous UI changes; keep the selected project stable while executing an operation.

## Tools

20 MCP tools provide setup/lifecycle status, sessions, current project/settings/timelines, selected-bin clips and subfolders, timeline tracks/clips/markers/settings, render queue/presets/format/codec/mode, literal missing-media checks, project creation/open/save, media import/move, timeline creation/selection, bin creation, marker creation, render setting changes and explicitly authorized external Python.

Writes default to preview (`confirmed=false`). Create/open project refuses whenever a project is already open because unsaved state cannot safely be inferred; no project is silently closed. It operates in the user's current library folder. Project save uses its existing library. Import and timeline creation leave the selected destination bin active; Resolve may activate a newly created timeline. Media moves do not move source files on disk. Markers use timeline-relative frame offsets. Structured render tools never add jobs or start rendering/exporting.

Queries are bounded to 1000 items and report truncation. Media checks cover one bin, not recursive dependencies; image-sequence patterns, generated clips and unavailable paths remain unresolved. Render queries do not invent an undocumented `GetRenderSettings` API or claim every Deliver UI option is readable. Unsupported native methods return explicit capability errors.

Python runs externally with full user privileges via the official API. It receives `resolve` and `project`; assign `result`, and stdout is limited to 64 KiB. The worker runs outside the removable plugin directory and is replaced per request. Request size is limited to 256 KiB, code to 128 KiB and response to 2 MiB; calls time out after at most 120 seconds. Stopping a worker does not undo SDK work already dispatched. Never automatically repeat a timed-out/failed mutation.

## Updates and removal

Refresh/reinstall the Codex plugin to update. Versioned uv environments and worker-source snapshots live outside the installed package, avoiding DLL/cache locks on plugin uninstall. There are no software-side bridge files to update or remove. The install/uninstall compatibility tools are read-only lifecycle explanations; uninstall in Codex. The vendor SDK and external scripting preference are preserved.

## Verification and acceptance

Run `uv run --locked --directory plugins/resolve-control python -m unittest discover -s tests -v` and `uv run --locked --directory plugins/resolve-control python tests/stdio_smoke.py`.

The tests use native SDK doubles for project guards, closed/restarted/multiple processes, previews, query bounds, marker collisions and read/write behavior, plus real MCP stdio startup/tool discovery/lifecycle calls. **Resolve is not installed on the development machine; actual Resolve 21 connection, native DLL/Python compatibility and UI operations remain unverified.** Install Studio, enable Local scripting and first verify project_info on a disposable project. Then preview/create a bin and marker, verify their targets, save only when requested, and finally verify Codex uninstall. Production rendering is not part of automated tests.

## API provenance

- [Blackmagic product page: current Resolve generation](https://www.blackmagicdesign.com/products/davinciresolve)
- [Blackmagic staff: external scripting requires Studio](https://forum.blackmagicdesign.com/viewtopic.php?f=21&t=204977)
- [Blackmagic official features guide: developer documentation location](https://documents.blackmagicdesign.com/SupportNotes/DaVinci_Resolve_20.2_New_Features_Guide.pdf)
- Authoritative installed reference: Help > Documentation > Developer > Scripting > README.txt. No local copy was available on the development machine. Existing SDK methods were cross-checked against the publicly mirrored vendor README dated 24 July 2026 at [resolve-scripts documentation mirror](https://github.com/thatcherfreeman/resolve-scripts/blob/main/Documentation/scripting_documentation.txt); this mirror is not a Blackmagic-hosted distribution. Runtime capability checks remain mandatory. No claim is made of latest patch-level native certification.
