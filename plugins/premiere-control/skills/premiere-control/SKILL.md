---
name: premiere-control
description: Inspect Premiere Pro 25.6+ projects and offline media, import or relink selected media, and save an explicitly chosen project.
---

# Bubble Premiere Pro control

First list sessions. Match exact filename, stem or full path; if ambiguous,
incomplete or unsaved, present the panels and ask the user to choose. Retain the
session UUID and project ID. Never choose a first item or move silently to a
different panel. Only active projects are advertised, not all open projects.

`premiere_project_info` lists sequences; `premiere_inspect_media` reports up to
1000 bin items, offline media and unverified host errors. Offline reporting is
Adobe's judgment, not a frame completeness check, effect audit or package-ready
dependency manifest. Keep truncation/errors visible.

`premiere_import_files` modifies the selected project root bin without saving.
`premiere_relink_media` changes exactly one selected media item and is not
undoable in Adobe. Confirm the exact target/path when not already authorized.
`premiere_save_project` writes the existing project path only on a save request.
Before any write, re-read project identity and verify the intended target.

The first version has explicit supported operations; arbitrary JavaScript,
ExtendScript, QE, timeline editing and rendering are not exposed. Do not invent
tool support or bypass the UXP integration with hidden host APIs.

Timeout/disconnect may follow partial host changes. Never automatically retry a
write. Inspect the selected project state before deciding the next action.
