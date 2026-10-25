---
name: resolve-control
description: Inspect Resolve projects, media bins, timelines, markers and render queues, and perform explicitly authorized structured edits or external Python through the official SDK.
---

Discover with `resolve_list_sessions`, then query `resolve_project_info`. Retain exact session_id and project_id; use timeline/folder/media IDs returned by tools, not guessed names. Project-name selection is exact. When multiple processes are present, explain that the API cannot safely target a PID and ask the user to keep only the intended one open. Do not switch after stale/restarted/unavailable target errors.

Prefer structured tools. Read-only project/media/timeline/render queries do not switch projects, load files or start renders. Media queries cover one bin and at most 1000 items; timeline queries have a 1000-clip cap. Report truncation and unresolved paths. `resolve_missing_media` checks literal absolute paths only; generated media and image-sequence placeholders remain unresolved and are not proof of missing media. Render queries cannot expose all Deliver UI settings.

For writes, call with confirmed=false, present the concrete target/effects, then confirmed=true only within user-authorized scope. Existing authorization can cover the action; do not ask redundantly. Create/open project only if no project is open; never close or discard another project's work implicitly. The operation uses the current project library folder. If a project is open, ask the user to save/close it or explicitly authorize a separate workflow. Save_project saves only the selected current project.

Import_media imports explicitly selected files and leaves its destination bin active. Create_timeline creates empty or from ordered media IDs in one bin, leaves that bin active and may activate the created timeline. Select_timeline intentionally changes the active timeline. Move_media moves only media-pool entries, not disk files. Add_marker uses timeline-relative frame offsets (not absolute starting timecode) and refuses an occupied frame. Set_render_settings edits settings only; it never adds render jobs, renders or exports.

Use execute_python only for explicitly requested code or an operation the user has authorized. It runs in an external Python worker using official `resolve` and `project` proxy objects; it is not a sandbox or in-editor eval. Set `result` for a return value. Code can affect files and all projects with user privileges. Never use code to automatically render/export, delete/close projects, switch libraries or overwrite media unless specifically authorized. Do not bypass the selection guard through a second SDK connection. Keep the user's project stable while work runs; process/project prechecks do not provide a transaction or lock against concurrent manual edits.

On timeout, crash or write error, report that earlier changes may exist. Inspect state before considering another action. Never retry mutations automatically. Do not claim testing in a real Resolve host when only SDK test doubles were used.
