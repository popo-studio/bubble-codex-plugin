---
name: blender-control
description: Control a connected Blender instance through structured tools and authorized Python, with explicit instance and scene selection.
---

Use this plugin first for Blender tasks; do not switch to computer use merely because a scene is empty. List sessions, select by exact file/path or ask the user when multiple/ambiguous instances exist. Do not route writes by current foreground window. If disconnected, use blender-setup.

Read blender_scene_state and target objects immediately before every mutation. Pass explicit PID and expected_snapshot. The structural fingerprint is not a full edit revision; pause for a new inspection after intervening edits or any failure. Use structured creation/edit/material/camera/light/timeline/render settings tools where supported. Transforms are local and rotations radians. Material edits are non-node only; inspect before assuming renderer appearance.

Never delete objects, discard dirty scenes, overwrite files or execute Python without user intent covering the action. Opening files can invoke application callbacks even with embedded Python disabled. Render-settings changes do not authorize actual rendering. Python escape hatch has full user privileges and requires explicit PID/snapshot; use only for the requested unsupported operation. Never retry a timed-out write automatically; inspect the selected instance to establish its outcome first.

Do not claim completeness for asset sequences/UDIM/caches/fonts. Report tested Blender version;4.5.3 native evidence does not establish5.2 native compatibility.

For scene organization use `blender_collection` to list/create/rename/link/unlink. Link destination first before unlinking source; never remove the last current-scene membership. Empty collection name/parent means scene root. Use `blender_parent_object` for safe parenting, empty parent to detach; it preserves world matrix and rejects ambiguous/animated/locked/shared-scene targets. Every write still needs selected PID and fresh snapshot.
