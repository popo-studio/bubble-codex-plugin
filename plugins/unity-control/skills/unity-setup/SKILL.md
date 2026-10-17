---
name: unity-setup
description: Install or troubleshoot the Bubble Unity bridge in an explicitly selected Unity 6 project, with consent and project-aware session discovery.
---

# Unity setup

Use this skill to connect Unity Editor. Requires `uv` on PATH for the MCP server. Unity runtime uses only Unity's built-in Editor APIs. Supported target is Unity 6 (6000.x), developed against 6000.1.0f1 on Windows.

1. First call `unity_list_sessions`. A connected project needs no installation. If several Editors exist, display numbered **project name / scene filename / modified state / Unity version** rows with full project paths; let the user choose a row or name a file/project. The PID is for routing, not something the user needs to know. An exact unique filename, stem or full path may identify a session; duplicate/unsaved/unavailable rows need a choice. Never guess a process, use a partial name, silently switch, or fall back to another session after errors.
2. If no bridge is available, identify the exact existing project directory from the user or task context. Do not choose a recent project arbitrarily. Call `unity_installation_status(project_path)` or `unity_install_bridge(..., confirmed=False)` and explain the exact package path, supported version, automatic startup in this project's Editor, and persistent file changes. This is a project-level installation; it is not a global Unity Hub add-on.
3. Only after the user permits these changes, call `unity_install_bridge(..., confirmed=True)`. The default is a preview. Consent to inspect a scene is not installation consent. Respect existing authorization; don't ask again for the same approved action. Installation adds an embedded `Packages/com.bubble.codex-control` Editor package and does not rewrite the project's manifest, scenes or existing scripts.
4. Recommend saving work and restarting the selected Unity Editor. Do not close/restart it yourself. If the user prefers no restart, switching back to Unity with Auto Refresh enabled normally discovers and compiles the package. Otherwise use **Assets > Refresh** with consent. Wait for compilation and errors to settle, then list sessions again and match the same project. There is no built-in Unity Python Script Editor; never offer a fake Python paste step. A compilation error anywhere in the project may prevent startup.
5. Verify the selected PID with `unity_status` and `unity_scene_info`. Report the project and loaded scenes. Compilation/domain reload creates fresh credentials; rediscover the same project after it reconnects. The bridge stops in Play Mode and starts again in Edit Mode. Never auto-retry a script or menu operation after a timeout/reload/disconnect.

Uninstall uses `unity_uninstall_bridge` preview, then `confirmed=True` when authorized. Only unmodified owned package files are removed; changed files cause a conflict. Generated metadata and unrelated files remain. Refresh/restart the Editor afterward. Removing the Codex plugin alone does not remove the Unity project package.

If the user declines installation, explain that this Unity integration needs an Editor package; there is no temporary arbitrary-C# console built into Unity. They can manually add the bundled `unity` directory as the embedded package, but this is still a persistent project change and needs the same permission. Do not install an unrelated console or modify packages to work around a refusal.

Do not reveal tokens or session-file contents. Discovery records are under the user's `.bubble-unity/sessions` directory (or `BUBBLE_UNITY_SESSION_DIR`). Only bridged Editors appear. Stale records after a crash can be unreachable; that does not authorize selecting a different Editor. A read-only status failure is a connection diagnosis, never evidence that earlier mutation did not run.

## 更新与完整卸载

用户请求更新/检查版本时，即使已经连接，也要调用 `unity_installation_status`，核对软件版本或明确项目路径、`installed_version`、`available_version` 和实际 changes。先展示差异；得到用户同意后才用 `unity_install_bridge(confirmed=true)` 更新。没有文件变化不重复安装。安装记录是磁盘状态，不能证明运行中的旧桥接已重新加载；提示保存工作并重启，或使用本软件明确支持的刷新方式，然后重新发现原目标实例。

GitHub 推送只发布源码。Codex 端需刷新已注册的 Git 插件市场，随后重新加载聊天/必要时重启 Codex；不要假定现有 MCP 进程已经更新，也不要把插件市场更新当作软件端桥接已更新。

用户说“卸载插件”但范围不明时，区分只移除 Codex 集成与完整移除软件接入。完整移除应先在插件工具仍可用时预览并授权 `unity_uninstall_bridge`，提醒重启/刷新停止已加载的桥接，再移除 Codex 插件。保留用户改动、备份和其他文件。软件端卸载授权不自动扩展到其他项目或软件版本。

若旧版 Codex 缓存删除报 Windows 拒绝访问，定位明确属于该插件旧缓存的 MCP 进程；获得停止这些连接的授权后再停止并重试卸载。不要终止 Maya/其他创作软件、所有 Python 进程，或删除整个 Codex 缓存。卸载 Codex 插件不会自动删除软件端配置。
