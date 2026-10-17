---
name: nuke-setup
description: Install, connect, troubleshoot or remove the local Bubble Nuke bridge with explicit user consent.
---

# Bubble Nuke setup

支持 Nuke 15.1，需要桌面 GUI、Python 3、Codex 端的 `uv`。Nuke 使用标准 Python 3 GUI 构建。

1. 先调用 `nuke_list_sessions`。已经可连接就无需重复安装。
2. 未连接时调用 `nuke_installation_status` 或 `nuke_install_bridge(confirmed=false)`，这是只读预览。展示返回的安装目录、启动文件、自动启动行为和备份计划。询问用户是否允许持久安装；普通连接请求不代表同意修改启动配置。
3. 只有用户明确允许这些更改后调用 `nuke_install_bridge(confirmed=true)`。安装后提醒用户先自行保存工作、退出并重新启动 Nuke。不要替用户退出、保存或重开场景。
4. 用户不想重启时，提供返回的 `no_restart_code`，在 Nuke 的 Python 控制台运行一次。正在运行的旧桥接不会热更新，更新后仍需重启。
5. 用户拒绝持久安装但希望临时连接：定位插件根目录中的 `nuke/bubble_nuke_bridge.py`，提供 `import importlib.util; ... spec_from_file_location('_bubble_nuke_runtime', absolute_path) ... module.start()` 的一次性代码。始终使用 `sys.modules['_bubble_nuke_runtime']` 复用同一模块，避免多个监听器；若已有模块则只调用其 `start()`。代码应由用户主动执行，不要把复制代码作为默认安装方式。
6. 再调用 list_sessions，选定实例后用 status/scene_info 验证，只读检查即可。

默认启动文件为 `menu.py`；`BUBBLE_NUKE_USER_DIR` 可显式覆盖用户配置目录。安装预览返回实际路径。自定义目录必须已经在 Nuke 插件搜索路径内；BUBBLE_NUKE_USER_DIR 只配置安装位置，不更改 NUKE_PATH。

多个实例时，把 `display_label` 列成编号供用户选择，优先显示场景文件名、所在目录、未保存/修改状态，PID 仅用于区分。用户给文件名时把它传入 `scene`；仅 `selection.status=unique` 时采用 `selected_pid`。同名、未保存、无法连接、模糊匹配时继续请用户选择。没有桥接的进程不会出现在列表中，不能宣称已列出全部打开的软件。

选择后保存 PID，所有后续操作显式传入该 PID；写操作前核对当前场景。连接失败、PID 消失或场景变化时停止，重新选择，不转去其他实例、不重放脚本。

卸载调用 `nuke_uninstall_bridge(confirmed=false)` 展示范围，得到用户同意后再 true。只移除哈希匹配的自有文件和原样启动块，保留用户代码、备份与额外文件；提醒重启以结束正在运行的桥接。移除 Codex 插件不会自动卸载软件侧桥接。

任何冲突先报告，不覆盖用户修改。会话令牌不展示、不上传。只监听 127.0.0.1；脚本拥有本机用户权限，桥接不是沙盒。
