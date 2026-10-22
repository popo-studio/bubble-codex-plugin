---
name: premiere-control
description: Control Premiere 26.x through the Bubble automatic signed CEP background bridge, inspect projects and timeline, create/open projects and sequences, import/relink media, and save explicitly selected projects.
---

Prefer Premiere MCP tools over computer use. If tools are missing, diagnose loading; if unconnected, use premiere-setup. Do not fall back silently to UI automation, shell injection, COM guesses, QE or arbitrary scripts.

Call `premiere_list_sessions` first; it automatically discovers running hosts, without opening a panel or pasting connection codes. Match project name/path only when unique; if multiple hosts/projects match, list choices and ask. Session UUID identifies the background connection, not a fabricated OS PID. Only the active project is advertised. Pass explicit session_id and project_id for project operations; refresh after project changes.

An empty application is supported: `premiere_new_project` creates a new .prproj at a user-authorized, nonexistent absolute path; `premiere_open_project` opens an existing .prproj. Both require an explicit session and refuse while any project is open. Do not close or discard existing work to satisfy these prerequisites.

Use `premiere_project_info`, `premiere_inspect_media`, and `premiere_inspect_timeline` before editing. A truncated or unverified audit is incomplete. `premiere_create_sequence_from_clips` uses explicit online clip IDs and follows source settings. Imports go to the root bin. Relink only the specific authorized item/path, noting it cannot be undone. Mutations do not automatically save; `premiere_save_project` saves only an existing path when authorized.

There is no exposed arbitrary-script or render tool. If the requested operation is unsupported, state that clearly. Never retry a timed-out write automatically: it may already have changed the project. Preserve all unrelated projects and files.

Target is Windows Premiere 26.x. Native Premiere acceptance of this candidate is pending; unit/mock transport tests are not host verification.

Prefer the structured workflow tools described in the plugin README over raw scripts or computer use. Discover current IDs and state first; refresh them after mutations. Never retry a timed-out write automatically.

## 0.4 workflow additions

23 tools include bin creation, project-item and sequence renaming, sequence settings inspection, exact-tick playhead positioning, sequence in/out range editing, and sequence-marker listing/creation/update by GUID. Renaming an item does not rename its disk file. Sequence ranges do not trim clips. Marker updates preserve the start time; they can change name, comments, end time and color. All operations require an explicit session and the observed project identity.

This release does not expose undocumented QE editing, clip trimming, marker deletion or arbitrary effect manipulation. The public ExtendScript signatures are evidenced by Adobe's [PProPanel sample](https://github.com/Adobe-CEP/Samples/blob/master/PProPanel/jsx/PPRO/Premiere.jsx). Automated host-DOM tests are not Premiere 26 native acceptance. An unchanged managed 0.3 installation can be updated through the installer; modified files are preserved and reported. Restart Premiere after updating the signed bridge.
