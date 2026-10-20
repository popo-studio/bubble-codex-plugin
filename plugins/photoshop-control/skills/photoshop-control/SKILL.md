---
name: photoshop-control
description: Connect a paired Photoshop 26.2+ UXP panel, inspect open documents and layers, and execute user-authorized Photoshop batchPlay actions.
---

# Bubble Photoshop

Use `photoshop_list_sessions` first. Only panels explicitly connected to this Codex process appear. A session UUID identifies a panel, not an OS PID; do not claim all running Photoshop instances are discovered.

If disconnected, use the setup skill. Match the user's exact document name or full path and retain both session_id and document_id. Multiple matches, unsaved documents, incomplete results or changed targets require user choice. Never silently choose the first panel or active document.

Read `photoshop_scene_info` before changes. `photoshop_inspect_document` lists document properties and layers only; it does not verify linked smart objects, missing fonts or external file dependencies. Preserve this limitation in reports.

Use `photoshop_batch_play` only for the user's requested actions. Explain which document and file/export/delete effects will occur. Descriptors have broad Photoshop privileges: the active document ID guard is not a sandbox for descriptors addressing other documents/application settings. User must select the intended document in Photoshop; do not auto-switch to another document. Do not execute arbitrary JavaScript or ExtendScript: this release accepts action descriptors, not code.

For uncertain descriptor syntax consult official Photoshop UXP batchPlay documentation. File operations are subject to UXP permission and file-token requirements; do not claim raw paths automatically grant access. No broad filesystem permission is requested by this release. If file access is unavailable, explain it rather than bypassing UXP.

Never retry mutations automatically after timeout or error. Changes may have partially completed. Read current state and report uncertainty before another explicit user-authorized attempt.

Connection codes are private credentials. Show only to the requesting user for entry in the panel; never add them to repository files, logs, screenshots or external messages. Keep the panel open; closing it or restarting the MCP process requires reconnection. No background/restart persistence is promised.
