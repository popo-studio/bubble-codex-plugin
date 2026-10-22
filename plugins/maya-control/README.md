# Bubble Maya

Current Codex package: **0.3.1**. Software-side bridge: **0.3.0**, unchanged by this runtime dependency patch.
面向 Maya 2027 的本地 Codex 插件。通过 MCP 控制已打开的 Maya，执行 Python/MEL，检查当前场景中的引用与贴图路径。

```text
Codex → stdio MCP 服务（独立 Python）
      → 127.0.0.1 + 会话令牌
      → Maya 内桥接脚本 → Maya 主线程
```

## 准备

- Maya 2027 图形界面版本。
- 系统安装独立的 Python 3.10+ 和 [uv](https://docs.astral.sh/uv/getting-started/installation/)，并让启动 Codex 的环境能找到 `uv`。不要把 `mayapy.exe` 当作 MCP 虚拟环境的基础解释器。
- 安装本仓库的 Bubble Maya 插件。首次运行服务时，uv 下载依赖，需要网络；依赖只进入插件独立环境，不进入 Maya。

## 初次连接：安装后重启

安装 Codex 里的 **Bubble Maya** 后运行初始设置，或说“帮我安装 Maya 桥接插件”。默认不需要复制代码：

1. Codex 检查安装状态，展示 **Maya 2027** 的安装位置和启动配置变更。
2. 你同意后，安装器将独立运行文件复制到 Maya 用户目录，备份原有 `userSetup.py` 并追加本插件的启动块。其他启动代码保持原样，不需要管理员权限。
3. 安装完成后，**保存场景并自行重启 Maya**。桥接插件在 Maya 初始化后自动加载，以后每次启动都会连接。
4. 回到 Codex 说“检查 Maya 连接”，查询成功后即可使用。

默认 Windows 目标为系统“文档”目录下的 `maya/2027/scripts/bubble_maya_runtime/`。安装器尊重 `MAYA_APP_DIR` 和系统文档目录重定向，以预览中显示的绝对路径为准。运行文件不引用 Codex 的版本缓存，因此更新或清理缓存不会使已安装的 Maya 插件丢失。

Maya 的启动脚本检查或安全插件加载可能出现确认提示。核对是 Bubble Maya 后按 Maya 的界面处理；安装器不会关闭这些安全设置，也不会自动关闭或保存你的 Maya 场景。

### 暂时不想重启

告诉 Codex“先不重启，给我立即连接代码”。安装器会生成指向**已安装副本**的加载代码，在 Maya 的 **Script Editor → Python** 执行一次即可。以后启动仍会自动加载。

如果当前进程已加载旧版桥接，更新运行文件后仍建议重启；立即加载代码不会强制热替换正在工作的旧桥接。

### 只想临时连接，不安装

也可以告诉 Codex“不要安装，只临时连接”。它会根据当前插件路径提供原来的 `bubble_maya_bridge.start()` 代码。这种方式不修改 Maya 启动文件，本次 Maya 退出后连接结束。手动停止临时桥接使用 `bubble_maya_bridge.stop()`。

## 更新与卸载

更新 Codex 插件后运行初始设置，先预览再确认更新 Maya 端文件，重启 Maya 后生效。

说“卸载 Maya 桥接插件”可以预览并确认卸载。卸载仅移除本插件管理的文件和启动块，保留其他启动代码及备份；如果检测到文件被手工修改，会报告冲突而不是强行覆盖。已在运行的桥接可能持续到 Maya 退出。

移除 Codex 插件不会自动删除 Maya 端安装。需要完全移除时，先完成 Maya 桥接卸载，再移除 Codex 插件。

## 使用

在启用该插件的 Codex 聊天里说：

- “连接 Maya 2027，告诉我当前打开的场景和选中对象。”
- “检查当前场景是否有缺失贴图、丢失引用或未知节点，只报告问题。”
- “在 Maya 中创建一个名为 test_cube 的立方体，返回它的名称，不保存场景。”

| 工具 | 用途 |
| --- | --- |
| `maya_list_sessions` | 列出实例的实时场景名；可按文件名或完整路径查找 |
| `maya_status` | 验证连接、Maya 版本与进程 |
| `maya_scene_info` | 当前场景、选择和基础信息 |
| `maya_inspect_scene` | 只读场景资源检查 |
| `maya_execute_python` | 执行 Python，返回输出及 `result` 变量 |
| `maya_execute_mel` | 执行 MEL 并返回结果 |
| `maya_installation_status` | 查看 Maya 端安装状态和路径 |
| `maya_install_bridge` | 默认只预览；用户同意后安装或更新 |
| `maya_uninstall_bridge` | 默认只预览；用户同意后卸载 |

## 多开 Maya

每个 Maya 进程监听系统分配的独立本机端口，并生成独立令牌，发现文件以 PID 命名。用户不需要手工分配端口。

- Codex 会通过只读查询列出各个实例的**文件名、所在文件夹和 Maya 版本**，你可以回答“第 2 个”或直接说文件名，不必知道 PID。
- 也可以直接说“检查 `hero.ma` 的贴图”。文件名、完整路径或省略扩展名的文件名唯一匹配时直接选择；重名时列出各自完整路径让你确认，找不到时不会操作其他场景。
- 未保存的场景会显示“未保存场景”；多个未保存场景以版本和 PID 区分。暂时不可查询的实例会单独标注，不会因为它忙碌或离线就默认选中另一实例。列表仅涵盖已启动 Bubble Maya 桥接的实例。
- 存在多个发现记录时，不传 `pid` 的调用会被拒绝。选择后，每次操作都显式携带同一个 PID。
- 指定实例关闭或超时后会报告错误，不会自动转发给另一个 Maya。崩溃后可能残留发现文件，需要查询状态确认；重启后的新 PID 要重新识别。
- 安装、更新和卸载针对 Maya 2027 的用户配置目录，对使用该目录的后续新实例生效；不会关闭或重启当前其他实例。

Python 脚本示例：

```python
import maya.cmds as cmds
result = {"selection": cmds.ls(selection=True, long=True)}
```

## 范围与限制

- 检查当前已打开场景，不自动打开其他文件，不自动保存或修复。
- 第一版侧重文件贴图节点、引用和未知节点。UDIM/序列文件匹配只判断是否有匹配文件，不验证整个分块集或帧范围完整性；第三方渲染器节点和未加载引用内部资源可能需要专项检查。
- 检查结果基于当前机器可访问的文件系统；网络盘离线也会影响结果。
- Python/MEL 拥有 Maya 进程的完整权限。令牌用于限制桥接访问，不会把脚本变成沙箱。使用自己的可信脚本。
- 桥接仅监听 `127.0.0.1`，随机令牌保存在用户本地 `~/.bubble-maya/sessions/`，不会放入仓库或工具列表。Windows 依赖用户目录自身的访问控制。
- Maya 忙碌、模态对话框或长脚本可能导致超时。已开始执行的脚本无法安全强制中断；超时后先检查场景状态，不要自动重试。
- Maya 2027 是本次目标；其他 Python 3 Maya 版本尚未作兼容性验收，Maya 2020/Python 2 不支持。

## 排错

| 现象 | 处理 |
| --- | --- |
| Codex 找不到 `uv` | 在终端执行 `uv --version`；安装或修正 PATH 后重启 Codex |
| 没有会话 | 运行初始设置检查安装；安装完成后重启 Maya，或选择立即加载代码 |
| 出现多个会话 | 根据 PID、版本和场景选择目标 |
| 连接失败 | 确认目标 Maya 正在运行，检查启动脚本或插件确认提示，再查询状态 |
| 安装冲突 | 保留现场，根据报错检查已修改的托管文件，不要删除整个 scripts 目录 |
| 超时 | 关闭 Maya 模态对话框，等待主线程空闲；检查操作是否已完成 |
| 插件安装后工具未出现 | 重新加载或新开一个启用该插件的聊天 |
| `Bubble Maya bridge failed to start: name '__file__' is not defined` | 旧版原生插件假定 Maya 提供 `__file__`；0.2.6 改为使用 Maya API 返回的加载路径。更新 Codex 插件后，预览并更新软件侧桥接，再保存工作、重启 Maya。仅更新 Codex 缓存不足以修复已安装的旧桥接 |

## 开发验证

从仓库根目录运行：

```powershell
uv run --directory plugins/maya-control python -m unittest discover -s tests -v
uv run --directory plugins/maya-control python tests/stdio_smoke.py
& 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' plugins/maya-control/tests/mayapy_smoke.py
& 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' plugins/maya-control/tests/maya_plugin_smoke.py
```

`uv.lock` 固定依赖版本，插件启动使用 `uv run --locked`。`mayapy_smoke.py` 在独立进程和临时场景中测试真实 Maya API，不依赖 GUI，也不会打开现有用户场景。

安装测试使用临时 Maya 用户目录，不会修改开发者真实的 Maya 启动配置。原生插件生命周期通过独立 `mayapy` 验证；batch 模式不启动监听器。

自动化测试不能替代 Maya GUI 启动验收。上线前在测试环境中完成：预览 → 同意安装 → 重启 Maya → 读取场景 → 确认连接 → 预览卸载 → 同意卸载。还应验证“不重启，立即加载”的分支。不要用生产场景测试任意脚本。

相关官方文档：[Maya Python 初始化](https://help.autodesk.com/cloudhelp/2027/ENU/Maya-Scripting/files/GUID-640C1383-3FB8-410F-AE18-987A812B5914.htm)、[Maya 2027 线程与 Python](https://help.autodesk.com/cloudhelp/2027/ENU/Maya-Scripting/files/GUID-9B5AECBB-B212-4C92-959A-22599760E91A.htm)、[Maya 安全设置](https://help.autodesk.com/cloudhelp/2027/ENU/Maya-Customizing/files/GUID-2176117C-6998-4802-9F9F-1417DF41C661.htm)、[MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)。

## 更新和卸载的两层范围

GitHub 发布后需刷新已注册的 Codex 插件市场，并重新加载聊天或重启 Codex。软件/项目中的桥接独立保存，需预览差异、经同意后更新，再重启或使用该软件支持的刷新方式。完整卸载请先通过本插件工具卸载软件端桥接，再从 Codex 移除插件；只卸载 Codex 插件会保留软件端配置。Windows 旧版缓存被占用时，先停掉明确属于该插件的旧 MCP 进程，再重试，勿关闭创作软件或批量删除配置。


## Structured everyday tools

The new bridge adds `maya_scene_state`, `maya_scene_file`, `maya_query_nodes`,
`maya_create_node`, `maya_edit_node`, `maya_select_nodes`, `maya_node_attribute`,
`maya_node_connections`, and `maya_timeline`. Prefer these over arbitrary scripts.
Read the selected process's scene state immediately before writes and pass its explicit PID
and returned `expected_snapshot`. This is a structural guard (path, dirty flag, node identity
or names/types), not a guarantee that every parameter or UI edit is detected. Parameter
writes additionally compare `expected_value`; input rewiring compares `expected_input`.
New/open refuses unsaved work unless `discard_changes=true` was authorized. Saving over an
existing file always needs `overwrite=true`; deletion needs `confirm_delete=true`.
No automatic render starts. Opening scenes and creating native/custom nodes may run host callbacks.
Timeouts and errors can follow partial changes: inspect before any further action, never retry automatically.

Update the managed host bridge and restart the application once to load these tools.
An older running bridge explicitly rejects the new operations; there is no raw-script fallback.
Installer ownership migrates the old two-file payload safely to the new three-file payload;
unrelated files at the new module path block update and are preserved by uninstall.

Native acceptance lives in `tests/structured_host_smoke.py`: run only in a fresh isolated
batch process. It creates its own temporary scene and tests creation/query, parameter write,
stale guards, selection, timeline, save/overwrite refusal, delete confirmation, and reopening.

## Runtime security patch 0.3.1

The Codex package updates its locked Python dependencies. Software-side bridge code and its version remain unchanged; existing owned bridge installations do not require reinstalling for this dependency-only update. Reload the Codex plugin to start the patched runtime.
