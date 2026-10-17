---
name: maya-setup
description: Install, update, uninstall, or troubleshoot the Bubble Maya bridge with user consent. Default to automatic connection after Maya restarts; offer a Script Editor snippet only when the user wants to connect without restarting.
---

# Set up Bubble Maya

Read `../../README.md` when details are needed. Use the bundled installation tools; do not manually patch Maya preferences or copy files into a guessed directory. Maya 2027 is the supported target.

## Default: install, then restart

1. Check `maya_installation_status` and `maya_list_sessions`. If the intended session already responds, query `maya_status` and `maya_scene_info` and continue the user's work. Do not reinstall unnecessarily.
2. For an absent or outdated installation, call `maya_install_bridge` with `confirmed=false` to get a read-only preview. Show the target version, installation directory, and startup-file change in plain language. Explain that the bridge will start automatically with Maya and listens only on this machine.
3. Obtain the user's permission to install and enable that startup behavior before calling `confirmed=true`. Existing explicit consent for these displayed changes is sufficient; do not ask twice. Installing the Codex plugin alone is not permission to change Maya startup files. Previewing must never write files.
4. On success, tell the user: “安装完成。请保存场景并重启 Maya，之后会自动连接。” Do not close, restart, or save Maya for them. Distinguish files installed from a live connection verified.
5. After restart, call `maya_list_sessions`, `maya_status`, and `maya_scene_info`. Verify the target PID/version/scene before claiming that the connection works. If multiple sessions exist, identify the intended one.

## Optional: connect without restarting

Only provide code if the user opts out of restarting or explicitly wants temporary setup. After installation, use the exact `no_restart_code` returned by the installer; it loads the installed copy and must not depend on the Codex cache version. Ask the user to run it in Maya's Script Editor **Python** tab, then verify the live session.

If they decline installation entirely but want a temporary connection, resolve the plugin root from this skill's actual file location and supply the legacy snippet adding `<plugin-root>/maya` to `sys.path`, importing `bubble_maya_bridge`, and calling `start()`. Explain that this temporary connection ends with Maya and does not enable automatic startup.

## Update, removal, and errors

- Updating the Codex plugin does not silently update Maya's installed files. Preview the runtime update, honor user consent, and recommend restarting Maya to load the new version. Do not hot-reload a running bridge automatically.
- For removal, preview `maya_uninstall_bridge` with `confirmed=false`, then act with `confirmed=true` only when removal is authorized. Remove only owned installation files and the managed startup block. Preserve other startup code and backups. A running bridge may remain until Maya exits.
- Report conflicts or edited managed files as conflicts. Never bypass the installer's ownership checks or delete unrelated folders to force a reinstall.
- Maya security settings can restrict startup scripts or ask the user to approve plugin code. Explain any observed prompt; do not weaken their security preferences.
- Verify `uv` and a separate Python 3.10+ if the MCP server cannot start. Do not install packages into Maya's Python.
- If tools have not loaded after a plugin update, reload the plugin or open a new chat as appropriate. Do not recreate the plugin to refresh it.
- Keep discovery-file tokens private. An installation preview, successful copy, or standalone test does not prove an interactive Maya connection.
