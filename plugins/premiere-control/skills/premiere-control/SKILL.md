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
