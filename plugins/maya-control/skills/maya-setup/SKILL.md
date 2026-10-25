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
5. After restart, call `maya_list_sessions` for live scene names. If the user gives a filename or path, pass it as `scene` and use a unique verified match. Otherwise, when multiple instances exist, present a numbered list led by filenames and distinguishing folders/versions, then let the user choose by number or name. Show unavailable records as unavailable; do not silently fall back. Users should not need to know a PID. Internally retain the selected explicit PID, verify it with `maya_status` and `maya_scene_info`, and do not switch processes after a failure. Follow `../maya-control/SKILL.md` for duplicate names and unsaved scenes.

## Optional: connect without restarting

Only provide code if the user opts out of restarting or explicitly wants temporary setup. After installation, use the exact `no_restart_code` returned by the installer; it loads the installed copy and must not depend on the Codex cache version. Ask the user to run it in Maya's Script Editor **Python** tab, then verify the live session.

If they decline installation entirely but want a temporary connection, resolve the plugin root from this skill's actual file location and supply the legacy snippet adding `<plugin-root>/maya` to `sys.path`, importing `bubble_maya_bridge`, and calling `start()`. Explain that this temporary connection ends with Maya and does not enable automatic startup.

## Update, removal, and errors

- Updating the Codex plugin does not silently update Maya's installed files. Preview the runtime update, honor user consent, and recommend restarting Maya to load the new version. Do not hot-reload a running bridge automatically.
- The installation belongs to a Maya version's user profile, not to one PID: all future Maya 2027 instances using that profile load the installed runtime. Install/update/removal does not stop other running instances. Explain this scope when relevant; never restart or close any instance automatically.
- For removal, preview `maya_uninstall_bridge` with `confirmed=false`, then act with `confirmed=true` only when removal is authorized. Remove only owned installation files and the managed startup block. Preserve other startup code and backups. A running bridge may remain until Maya exits.
- Report conflicts or edited managed files as conflicts. Never bypass the installer's ownership checks or delete unrelated folders to force a reinstall.
- Maya security settings can restrict startup scripts or ask the user to approve plugin code. Explain any observed prompt; do not weaken their security preferences.
- Verify `uv` and a separate Python 3.10+ if the MCP server cannot start. Do not install packages into Maya's Python.
- If tools have not loaded after a plugin update, reload the plugin or open a new chat as appropriate. Do not recreate the plugin to refresh it.
- Keep discovery-file tokens private. An installation preview, successful copy, or standalone test does not prove an interactive Maya connection.

## 更新与完整卸载

用户请求更新/检查版本时，即使已经连接，也要调用 `maya_installation_status`，核对软件版本或明确项目路径、`installed_version`、`available_version` 和实际 changes。先展示差异；得到用户同意后才用 `maya_install_bridge(confirmed=true)` 更新。没有文件变化不重复安装。安装记录是磁盘状态，不能证明运行中的旧桥接已重新加载；提示保存工作并重启，或使用本软件明确支持的刷新方式，然后重新发现原目标实例。

GitHub 推送只发布源码。Codex 端需刷新已注册的 Git 插件市场，随后重新加载聊天/必要时重启 Codex；不要假定现有 MCP 进程已经更新，也不要把插件市场更新当作软件端桥接已更新。

用户说“卸载插件”但范围不明时，区分只移除 Codex 集成与完整移除软件接入。完整移除应先在插件工具仍可用时预览并授权 `maya_uninstall_bridge`，提醒重启/刷新停止已加载的桥接，再移除 Codex 插件。保留用户改动、备份和其他文件。软件端卸载授权不自动扩展到其他项目或软件版本。

若旧版 Codex 缓存删除报 Windows 拒绝访问，定位明确属于该插件旧缓存的 MCP 进程；获得停止这些连接的授权后再停止并重试卸载。不要终止 Maya/其他创作软件、所有 Python 进程，或删除整个 Codex 缓存。卸载 Codex 插件不会自动删除软件端配置。


Current bridge payload is 0.4.0; this release adds structured workflow operations. After installing/updating, verify `maya_status` reports bridge_version `0.4.0` before using new tools. A still-running older bridge needs one restart or the returned authorized no-restart bootstrap; do not replace user scenes. Codex package update alone does not reload the host payload.
