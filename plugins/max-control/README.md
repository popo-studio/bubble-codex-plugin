# Bubble 3ds Max

Current Codex package: **0.3.0**. Software-side bridge: **0.3.0**. Update the owned host bridge through setup, then restart/reload the application once.
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

自动测试涵盖真实回环双实例路由、鉴权、队列截止时间、崩溃残留、文件名歧义、安装预览/回滚/卸载/冲突和宿主 API 替身。真实 MCP SDK stdio 握手测试覆盖全部 16 个工具。**开发机器未安装 Max，原生 GUI 启动、MAXScript bootstrap 和 Qt 主线程操作尚待用户验收。**

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

## Structured editing in 0.2.0

Prefer `max_list_objects`, `max_inspect_object`, `max_object_action`, `max_scene_action`, and `max_settings` for supported routine work instead of generating scripts. List objects first and retain both the explicit PID and returned `scene_token`; pass that token as `expected_scene`. IDs are 3ds Max node handles, protected by a random scene epoch invalidated by new/reset/open callbacks; they are not portable asset GUIDs. Re-query after scene/level changes or reconnect.

The object action supports create, select, duplicate, rename, delete, and position/rotation/scale transforms. Creation kinds: box, sphere, plane, cylinder, point. Transforms use host world position and local scale; animation/keyframe editing and arbitrary property assignment remain outside structured coverage. Inspection returns hierarchy and component/modifier/material metadata, not a complete serialized property editor. Delete only when authorized. Errors and timeouts may follow partial work; never retry mutations automatically.

New/open refuse dirty affected scenes, without implicitly saving or discarding anything. Save requires an explicit destination; replacing any existing file requires `overwrite=true` and user authorization. No build or render starts from the settings query.

Update the application-side bridge through the setup tool and restart/reload the relevant application after updating the Codex plugin; an old running bridge does not gain new operations automatically. Existing owned-file update and removal protections remain in place.

API references: [Autodesk scene files](https://help.autodesk.com/cloudhelp/2025/ENU/MAXDEV-Python/files/using_pymxs/MAXDEV_Python_using_pymxs_pymxs_files_html.html), [Python callbacks](https://help.autodesk.com/cloudhelp/2021/ENU/Max-Python-API/using_pymxs/pymxs_registering_callbacks.html).

Validation: 38 existing Python regressions plus 6 structured-host safety tests pass using fake Max APIs. Real MCP stdio exposes 16 tools. 3ds Max is not installed; native object/controller/callback behavior remains pending.


## 日常操作补全 0.3.0

- `max_object_action(action="transform")` 增加 `rotation=[x,y,z]`，XYZ Euler 角度转为原生 quaternion；对象查询返回 `rotation_xyz_degrees`。先校验所有向量，避免坏参数导致前半段位置已写入。
- `max_parent_object`：显式对象 handle 建立/解除父级，保持世界 transform。必须提供场景 token 与读到的旧 `expected_parent_id`；拒绝循环、过时父级、冻结/动画/组/XRef 节点。
- `max_layers`：列出图层及对象、创建/改名、分配显式对象、设置隐藏/冻结；写入需要 get 返回的 `revision` 作为 `expected_layers`，以及 `scene_token` 作为 `expected_scene`。不删除图层，不隐式更改 current layer；默认图层不可改名，移动成员前验证全部目标。

API：[EulerAngles](https://help.autodesk.com/cloudhelp/2026/ENU/MAXScript-Help/files/MAXScript-Language-Reference/Values/Basic-Data-Values/GUID-87BB6468-79E2-4FA2-9BAB-42E427219C4F.html)、[LayerManager](https://help.autodesk.com/cloudhelp/2026/ENU/MAXScript-Help/files/3ds-Max-Objects-and-Interfaces/Interfaces/Core-Interfaces/Core-Interfaces-Documentation/L/GUID-79537E16-FE25-4567-BEA6-06F39E0A5C1F.html)、[LayerProperties](https://help.autodesk.com/cloudhelp/2021/ENU/3DSMax-MAXScript/files/GUID-78B79975-7BA5-4A03-8FEF-27E78D14B575.htm)。

验证：真实 MCP stdio 与50项 Python contract/安装/路由回归通过。**本机未安装 Max，本轮没有原生 Max 验收；Euler、LayerManager、父级变换语义仍须在实际 Max 中验收。**

当前 MCP 工具共 16 个。优先使用上述结构化工具；每次写入仍须选定实例并传最新场景身份。Maya/Nuke/Houdini 的 snapshot 包含随机桥接 session 身份，重启或重新连接后的旧 snapshot 无效；它不覆盖每个属性编辑。

此版本保留已修复的依赖锁，不升级第三方依赖。软件侧 payload 已改变，需要通过 setup 预览并更新；不会自动更改用户启动配置。安装/卸载所有权、冲突保护、多实例选择逻辑继续生效。
