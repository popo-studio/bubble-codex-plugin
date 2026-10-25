# Bubble Unreal Engine

Current Codex package: **0.2.1**. Software-side bridge: **0.2.0**, unchanged by this runtime dependency patch.
连接本机 Unreal Editor 5.5，执行用户请求的 Python、读取地图/项目状态，检查直接资源包依赖。安装目标是单个项目，运行时使用 Unreal 自带 Python；外部 MCP 使用 Python 3.10+ 和 `uv run --locked`。

## 安装与连接

在 Codex 安装后，说“连接 Unreal 项目”，提供 `.uproject` 的完整路径。助手预览文件变化，经同意后创建 `项目/Plugins/BubbleCodexBridge/`。这是默认启用的项目内容插件，声明 `PythonScriptPlugin` 的 Editor 依赖；**不修改 `.uproject`、Engine 目录或现有项目启动脚本**。若项目明确禁用相关插件，先由用户在 Unreal Plugins 设置启用，再安装。

默认保存工作并重启项目，`Content/Python/init_unreal.py` 自动加载本地桥接。已经启用 Python 且不想重启时，可在 Unreal Python 控制台执行安装返回的 `no_restart_code`。Python 尚未启用时，不能靠该代码跳过首次启用所需的重启。已运行旧桥接的更新仍须重启。

`unreal_uninstall_bridge` 默认预览，获得确认后只删除拥有且未被改动的文件，保留用户文件和生成缓存。重启停止现有桥接；仅卸载 Codex 插件不会删除项目里的接入文件。

## 多实例和工具

`unreal_list_sessions(scene=...)` 展示地图、项目全路径、修改状态、版本和 PID。可用 `.uproject` 文件名/去扩展名/完整路径、地图 `.umap` 文件名/路径或 `/Game/Maps/Map` 包名精确匹配；同一项目开多个进程、同名地图或不可达会话时先列出编号选择。用户无须知道端口。选中后传 PID，写前检查地图/项目是否改变，不会在失败后切换另一实例。

- `unreal_scene_info`：当前地图包、对应 `/Game` 地图文件、项目、选择和脏包。
- `unreal_inspect_scene(package=None)`：默认已保存地图，也可指定 `/Game/Props/Chair`。读取 Asset Registry 的直接软/硬包依赖，不加载、保存、重新扫描或修复资产。
- `unreal_execute_python`：主线程执行，预置 `unreal`，用 `result` 返回值，捕获 Python 标准输出和错误。

依赖扫描尚未完成或根包未注册时返回 `complete=false`。未解析依赖是 registry 警告，不等于磁盘文件缺失。检查不覆盖传递依赖、外部源文件、资产加载错误、完整打包验证或修复。未保存地图必须先指定一个已保存的资源包。

每个编辑器进程使用随机回环端口、独立 token、PID 发现文件；网络线程排队，Slate tick 在主线程执行。队列超时取消未开始任务，已执行脚本可能部分生效，不自动重试。任意 Python 拥有完整用户权限。桥接面向交互编辑器，跳过 commandlet、`-unattended`、游戏和服务器进程，不用于打包游戏或 PIE 游戏世界。

## 验证与验收

自动测试覆盖回环双实例路由、令牌隔离、过期任务、文件名/项目歧义、安装预览/回滚/卸载/用户改动冲突和资源检查边界；真实 MCP SDK stdio 测试覆盖 8 个工具。

本机 **UE 5.5.4 原生 PythonScript commandlet** 已在仓库临时项目中验证：项目插件和 Python 依赖自动发现、`init_unreal.py` 运行、commandlet 不开启监听、原生场景信息/Asset Registry 查询、Python 返回 42，读取前后场景状态不变。交互式编辑器 Slate 主线程、重启连接和真实生产项目仍需用户验收。

```powershell
uv run --locked --directory plugins/unreal-control python -m unittest discover -s tests -v
uv run --locked --directory plugins/unreal-control tests/stdio_smoke.py
```

`tests/native_smoke.py` 需通过 UE PythonScript commandlet 在隔离项目运行，环境变量 `BUBBLE_UNREAL_NATIVE_RESULT` 指定临时结果文件，项目先安装本插件。不要对生产项目运行测试。

## 官方 API 依据

- [Epic：Editor Python、项目/插件 Python 路径与 init_unreal.py](https://dev.epicgames.com/documentation/en-us/unreal-engine/scripting-the-unreal-editor-using-python)
- [Epic：5.5 主线程 tick / shutdown 回调](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/module/unreal?application_version=5.5)
- [Epic：Asset Registry 查询](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/AssetRegistry?application_version=5.5)
- [Epic：只读脏包查询](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/EditorLoadingAndSavingUtils?application_version=5.5)

实现另核对了本机 UE 5.5 的 `PythonScriptPlugin.cpp`、`UnrealEditorSubsystem.h`、`EditorActorSubsystem.h` 与 `BlueprintPathsLibrary.h`。

## 更新和卸载的两层范围

GitHub 发布后需刷新已注册的 Codex 插件市场，并重新加载聊天或重启 Codex。软件/项目中的桥接独立保存，需预览差异、经同意后更新，再重启或使用该软件支持的刷新方式。完整卸载请先通过本插件工具卸载软件端桥接，再从 Codex 移除插件；只卸载 Codex 插件会保留软件端配置。Windows 旧版缓存被占用时，先停掉明确属于该插件的旧 MCP 进程，再重试，勿关闭创作软件或批量删除配置。

## Structured editing in 0.3.0

Prefer `unreal_list_objects`, `unreal_inspect_object`, `unreal_object_action`, `unreal_scene_action`, and `unreal_settings` for supported routine work instead of generating scripts. List objects first and retain both the explicit PID and returned `scene_token`; pass that token as `expected_scene`. IDs are actor object paths, guarded by the current native editor-world identity; they are not portable asset GUIDs. Re-query after scene/level changes or reconnect.

The object action supports create, select, duplicate, rename, delete, position/rotation/scale transforms, parent/detach, and Outliner folder organization. Creation kinds: actor, point_light, camera, static_mesh (empty mesh actor). Transforms use world position and world scale and rotation degrees `[pitch,yaw,roll]`. Parenting preserves world transform and rejects cycles and cross-scene/level targets. Use `parent_id=null` to detach; parent must be an observed current-world actor. `folder` uses relative slash-separated names; empty clears it. Animation/keyframes and arbitrary property editing remain outside these structured tools. Inspection returns hierarchy and component/modifier/material metadata, not a complete serialized property editor. Delete only when authorized. Errors and timeouts may follow partial work; never retry mutations automatically.

New/open refuse dirty affected scenes (Unreal also refuses dirty content packages), without implicitly saving or discarding anything. Save requires an explicit destination; replacing any existing file requires `overwrite=true` and user authorization. Unity new/open replaces all loaded scenes after checking every scene for unsaved changes. No build or render starts from the settings query.

Update the application-side bridge through the setup tool and restart/reload the relevant application after updating the Codex plugin; an old running bridge does not gain new operations automatically. Existing owned-file update and removal protections remain in place.

API references: [Epic EditorActorSubsystem 5.5](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/EditorActorSubsystem?application_version=5.5), [EditorLoadingAndSavingUtils 5.5](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/EditorLoadingAndSavingUtils?application_version=5.5).

Previous0.2.0 native validation: 45 existing Python regressions and real MCP stdio (13 tools) pass. In a marked disposable project, actual UE 5.5.4 full Editor mode passed actor creation, transforms, components, duplication/rename/delete, dirty-scene refusal, map save/overwrite refusal, new/open and world-token rejection. No user project was opened. PythonScript commandlet map creation crashed without full editor context; it is not used as evidence for editor lifecycle.

## Runtime security patch 0.2.1

The Codex package updates its locked Python dependencies. Software-side bridge code and its version remain unchanged; existing owned bridge installations do not require reinstalling for this dependency-only update. Reload the Codex plugin to start the patched runtime.

Version0.3.0 also updates the software-side bridge payload to0.3.0; update the owned bridge and restart/reload the application after upgrading. The previous0.2.1 dependency-only update note above describes that older release.

New actor API reference: [Actor 5.5 rotation, attachment and folder APIs](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/Actor?application_version=5.5). `tests/native_runner.py` owns one hidden, disposable full-Editor process; set `BUBBLE_UNREAL_EXE` to the available Editor executable. It never opens a user project.

0.3.0 adds4 isolated host-contract tests for rotation refusal/prevalidation, parent cycles/cross-level guards, stale parent identity and folder validation (49 Python tests total).

0.3.0 native acceptance also passed in UE5.5.4 full Editor mode using `UnrealEditor-Cmd.exe` without a commandlet: rotation, keep-world attach/detach, cycle refusal, Outliner folder/clear and invalid-folder refusal. Only the marked disposable project was opened; no user project or production render/build.
