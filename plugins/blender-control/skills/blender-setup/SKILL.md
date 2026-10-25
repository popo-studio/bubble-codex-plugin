---
name: blender-setup
description: Preview, install, update, remove or diagnose the user-scoped automatic Blender bridge.
---

First call blender_list_sessions and blender_installation_status. Explain the exact user scripts path and owned startup/runtime files before installing. Installation/update/uninstall defaults to preview; set confirmed=true only when the user has authorized those persistent changes. Choose the actual installed Blender profile, not automatically the newest guessed version. Standard Windows profile is APPDATA/Blender Foundation/Blender/<version>/scripts; custom directory should match bpy.utils.user_resource('SCRIPTS') or BLENDER_USER_SCRIPTS.

After installation ask user to save work and restart Blender; future GUI startups connect automatically. Offer returned code only if they prefer no restart. Never change Blender preferences, install another Blender version or run an installer just to connect. Factory-startup/background modes do not automatically load this GUI bridge. Multiple versions/profiles require explicit selection.

For updates compare available vs installed bridge version. Uninstall bridge before uninstalling Codex plugin if the user wants full removal. Modified/unknown files are preserved; explain conflicts, do not bypass ownership hashes or remove unrelated files. Already running bridges stop after Blender restarts; do not terminate user processes. A stale install lock needs inspection before removal. Check connected versions and clearly separate native4.5.3 verification from untested5.2.
