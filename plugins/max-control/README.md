# Bubble 3ds Max

为本机 3ds Max 提供 Python / MAXScript 执行、场景信息和常规资源检查。第一版面向 Windows、Python 3 的 Max 2025/2026，兼容 PySide6 / PySide2。宿主运行时只用 Max 自带 Python 与 Qt；外部 MCP 使用 `uv run --locked` 和 Python 3.10+。

## 安装与连接

在 Codex 安装本插件后，说“连接 Max”。助手先检查连接并预览持久安装；得到你的同意后才创建用户启动脚本 `bubble_max_control.ms` 和 `bubble_max_runtime/`。现有启动脚本不被改写。

安装工具参数 `startup_directory` 是 Max 用户启动脚本目录。省略时仅选择唯一已存在的 Max 2025/2026 `%LOCALAPPDATA%/Autodesk/3dsMax/*/*/scripts/startup`；多个版本/语言时先选择。自定义路径以 Max 的 `getDir #userStartupScripts` 为准。不能把 Python 文件放进另一个软件的 Python 环境。

安装后保存工作并重启 Max，即自动连接。不想重启时可在 Max Python Listener 运行安装结果的 `no_restart_code`。已有桥接的更新仍须重启；重复加载不会开启第二个监听器。卸载使用 `max_uninstall_bridge`，默认预览；确认后仅移除本插件未被修改的文件，保留其他文件。已运行的桥接在重启后停止。

## 多实例与功能

`max_list_sessions(scene=...)` 返回文件名、路径、修改状态、版本和 PID。支持精确文件名、去扩展名或完整路径；同名、未保存或不可达时列出编号供选择。选定实例后传明确 PID，断线不会切换其他实例。

- `max_scene_info`：文件、项目、选择、时间、节点数量。
- `max_inspect_scene`：Bitmaptexture 搜索路径解析和顶层 scene XRefs，报告缺失资源。**不覆盖**第三方渲染器贴图/缓存、对象 XRefs、嵌套 XRefs 或完整序列/UDIM 集合。
- `max_execute_python`：可使用 `rt`（`pymxs.runtime`），通过 `result` 返回结果，捕获 Python 输出。
- `max_execute_maxscript`：返回 MAXScript 执行结果；Listener 输出不保证捕获。

每个进程使用独立随机 `127.0.0.1` 端口、随机令牌和 PID 发现文件。线程只处理网络，Qt 主线程执行宿主 API。未开始的超时任务取消；已开始的代码不能强行终止，不会自动重试。代码拥有当前用户权限，并非沙盒。

## 验证与限制

自动测试涵盖真实回环双实例路由、鉴权、队列截止时间、崩溃残留、文件名歧义、安装预览/回滚/卸载/冲突和宿主 API 替身。真实 MCP SDK stdio 握手测试覆盖全部 9 个工具。**开发机器未安装 Max，原生 GUI 启动、MAXScript bootstrap 和 Qt 主线程操作尚待用户验收。**

```powershell
uv run --locked --directory plugins/max-control python -m unittest discover -s tests -v
uv run --locked --directory plugins/max-control tests/stdio_smoke.py
```

## 官方 API 依据

- [Autodesk：Python 与 Max 主线程约束](https://help.autodesk.com/cloudhelp/2024/ENU/MAXDEV-Python/files/MAXDEV_Python_threading_html.html)
- [Autodesk：PySide6 用户界面](https://help.autodesk.com/cloudhelp/2026/ENU/MAXDEV-Python/files/MAXDEV_Python_creating_python_uis_html.html)
- [Autodesk：从 MAXScript 执行 Python](https://help.autodesk.com/cloudhelp/2021/ENU/Max-Python-API/executing_python/executing_python_from_maxscript.html)
- [Autodesk：用户 startup 目录和贴图/XRef 路径查询](https://help.autodesk.com/cloudhelp/2017/ENU/MAXScript-Help/files/GUID-F7577416-051E-478C-BB5D-81243BAAC8EC.htm)
- [Autodesk：XRefScene 查询](https://help.autodesk.com/cloudhelp/2022/ENU/MAXScript-Help/files/3ds-Max-Objects-and-Interfaces/Node-MAXWrapper/XRef-Objects-and-Scenes/GUID-090B28AB-5710-45BB-B324-8B6FD131A3C8.html)

## 更新和卸载的两层范围

GitHub 发布后需刷新已注册的 Codex 插件市场，并重新加载聊天或重启 Codex。软件/项目中的桥接独立保存，需预览差异、经同意后更新，再重启或使用该软件支持的刷新方式。完整卸载请先通过本插件工具卸载软件端桥接，再从 Codex 移除插件；只卸载 Codex 插件会保留软件端配置。Windows 旧版缓存被占用时，先停掉明确属于该插件的旧 MCP 进程，再重试，勿关闭创作软件或批量删除配置。
