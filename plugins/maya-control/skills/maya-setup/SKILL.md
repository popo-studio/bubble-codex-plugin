---
name: maya-setup
description: Set up or troubleshoot the Bubble Maya local bridge and MCP connection, including locating the bundled Maya script and verifying a harmless scene query.
---

# Connect Bubble Maya

Read `../../README.md` for the current instructions. Resolve the plugin root from this skill's actual file location, including when installed in a versioned cache. Do not assume the source checkout path is still the installed path.

1. Verify `uv` is on the Codex process PATH and a separate Python 3.10+ is available. The bridge runs inside Maya; the MCP server runs externally with its own dependencies.
2. Give the user a Python Script Editor snippet that adds the absolute `<plugin-root>/maya` directory to `sys.path`, imports `bubble_maya_bridge`, and calls `start()`. Use a raw string or forward slashes on Windows. They can drag the selected snippet to a Maya shelf for reuse.
3. Do not install third-party Python packages into Maya or modify `userSetup.py` as part of ordinary setup. No permanent startup behavior is required.
4. Once the user has run the snippet in Maya, call `maya_list_sessions`, `maya_status`, then `maya_scene_info`. A verified Maya version, PID, and scene name establish a connection. A successful plugin installation alone does not.
5. If tools have not loaded after installation, report that a new chat or app reload may be needed; do not recreate the plugin. If multiple Maya sessions are present, identify the target before acting.
6. Explain `bubble_maya_bridge.stop()` for shutdown. Session tokens stay in the user's local profile and must not be shared, logged, or committed.

Only report the connection as working after a harmless live query succeeds. An unavailable Maya GUI or licensing error is a verification limitation, not a passing integration test.
