# Maya 原生插件启动路径修复

日期：2026-10-18。Maya 0.2.6；其他插件维持 0.1.2。

真实 Maya 2027 插件加载器不会给本插件设置 `__file__`，原来的延迟启动因此报错。新版在 `initializePlugin` 中保存 `MFnPlugin.loadPath()` 提供的位置，再据此加载相邻桥接文件。实测该 API 返回目录；实现同时兼容文件路径，不从工作目录猜测位置。

- Maya 单元测试 42 项通过，1 项因符号链接权限跳过；市场测试 3 项通过。
- 新回归直接在没有 `__file__` 的命名空间中执行插件，覆盖空格和中文路径以及目录/文件两种加载路径。
- 作者与独立审查者均通过真实 Maya 2027 `mayapy` 原生测试：原生加载、批处理不监听、交互启动分支执行、真实 TCP 主线程场景查询、查询前后场景状态一致、卸载清理会话、临时桥接安装和卸载。交互模式判断与空闲调度由测试模拟，真实 `loadPlugin`、`MFnPlugin` 和场景 API 保留；不声称实际 GUI 重启已验收。
- 本机通过真实 Codex 安装 0.2.6，并发现 Maya 工具、成功调用桥接安装预览，核对版本与具体变更路径。
- 通过同一 MCP 安装器将已有临时修复桥接升级为 0.2.6，仅替换托管插件文件和安装记录。再次查询安装状态为 0.2.6、无待更新文件；未关闭、重启或热重载用户的 Maya。

此前原生测试只覆盖批处理分支，没有执行会报错的延迟启动；本轮已补足这个缺口。复跑命令：`mayapy.exe plugins/maya-control/tests/maya_plugin_smoke.py`。

# Codex 插件工具加载修复验证

日期：2026-10-17。Maya 0.2.5；其他五个插件 0.1.2。使用桌面应用实际运行的 Codex 后端 `0.163.0-alpha.10.2`。

根因对照：真实 `plugin/read` 对 `cwd: "/"` 和 `cwd: "C:/"` 返回空的 MCP 列表，技能仍可见；删除 `cwd` 或使用插件内路径后识别 Maya 服务。新版六插件移除两份 MCP 清单里的 `cwd`，保留启动器中的目录迁移。

`tests/codex_plugin_smoke.py --codex <桌面后端绝对路径> --install` 已实跑，严格断言版退出 0：

| 插件 | Codex 发现的工具数 | 安装后只读调用 |
| --- | ---: | --- |
| Maya | 9 | `maya_list_sessions` 成功 |
| Nuke | 8 | `nuke_list_sessions` 成功 |
| Houdini | 8 | `houdini_list_sessions` 成功 |
| 3ds Max | 9 | `max_list_sessions` 成功 |
| Unreal | 8 | `unreal_list_sessions` 成功 |
| Unity | 9 | `unity_list_sessions` 成功 |

测试通过 Codex 的 `plugin/install` 安装，核对安装版本，创建 ephemeral 会话，通过 `mcpServerStatus/list` 发现工具并核对插件来源，再通过 `mcpServer/tool/call` 调用。六个业务结果均为 `ok: true`、`data` 为列表。没有启动模型回合，也没有安装或修改软件端桥接。测试后通过官方卸载接口移除了原先未安装的五个插件，核对 `installed: false`；原已安装的 Maya 保留为 0.2.5。

另通过 223 项单元/市场测试，3 项因 Windows 符号链接权限跳过；无失败。六插件的运行中目录删除回归全部通过：从插件目录启动两代服务，12 个真实 MCP 进程迁出工作目录后，仍能删除临时插件副本并继续响应。生产变更、测试与说明经过独立审查。

本轮验证覆盖 Codex 后端的真实安装、工具加载、只读调用和卸载接口，不等于验证全部 GUI 点击路径或创作软件内操作；原生软件验收限制仍见下表。

# Windows 卸载修复验证（上一版）

日期：2026-10-17。Maya 0.2.4；其他五个插件 0.1.1。

- 市场一致性测试 3 项通过，覆盖版本化启动脚本、双 MCP 配置和锁定依赖一致性。
- 六插件现有单元测试全部复跑：223 项中 220 通过、3 因 Windows 符号链接权限跳过；加上市场测试共 226 项，223 通过、3 跳过，无失败。
- `tests/launcher_smoke.py` 六个插件全部通过，作者与独立审查者各自复跑。每个插件从实际 MCP 配置启动两个版本，共 12 个真实 MCP 进程；解释器、依赖环境和工作目录均在插件目录外，不同版本使用不同环境。进程连接期间完整删除复制的临时插件目录后，两端仍能响应工具列表请求。
- 本机旧版 `maya-control@bubble-plugins` 仅停止精确匹配其旧缓存的 MCP 进程后，通过 Codex 官方卸载接口成功移除；缓存目录和安装配置均已消失。未关闭 Maya 或修改软件侧配置、场景。
- 新版本的 Codex 界面卸载尚未实测；上述真实进程与目录删除测试覆盖本次 `os error 5` 的直接原因。原生软件 GUI 和多实例验收范围仍如下表所述。

复跑生命周期测试：使用装有 MCP SDK 的 Python 执行 `tests/launcher_smoke.py`；需要 `uv`、允许本机回环连接和下载锁定依赖。测试只删除自己创建的临时插件副本。

# 首次六插件交付验证

日期：2026-10-17。五个新增插件为 0.1.0；Maya 0.2.3 更新软件图标及同步版本号。

## 自动测试

| 范围 | 测试数 | 结果 |
| --- | ---: | --- |
| 市场、双清单一致性、资源与技能路径 | 3 | 全部通过 |
| Maya | 42 | 41 通过，1 跳过 |
| Nuke | 42 | 41 通过，1 跳过 |
| Houdini | 44 | 43 通过，1 跳过 |
| 3ds Max | 37 | 全部通过 |
| Unreal | 43 | 全部通过 |
| Unity | 15 | 全部通过 |

共 226 项，223 通过，3 跳过。跳过项均为 Windows 缺少创建符号链接权限；模拟的 junction / reparse 路径保护另有测试。网络测试在允许本机回环连接的环境执行。普通沙箱的临时目录 ACL 曾使 Unity 单测失败，权限合适的环境复跑通过。

新增五个插件均通过官方 MCP SDK `ClientSession` 的真实 stdio 握手、工具发现、调用及安装预览检查；宿主使用隔离替身，不代表真实 GUI 已通过。六个插件的通用清单与 MCP 清单通过 Agent Plugins 1.0 官方 JSON Schema 校验，锁文件通过离线一致性检查。

Unity 的生产 C# 桥接另以两个进程、真实 TCP 和 Unity API 替身测试：独立端口/令牌、主线程派发、错误鉴权、已过期请求、排队取消、执行超时、编译忙状态、重新加载清理与禁止异步方法。它已针对本机 Unity 6000.1.0f1 的真实 Editor 程序集编译成功。

## 原生软件验证

| 软件 | 已验证 | 尚需验收 |
| --- | --- | --- |
| Nuke 15.1v5 | `-t` 下场景查询、文件检查、Python 返回 42、读操作前后状态一致、批处理拒绝监听 | GUI 启动、主线程调度、重启与多窗口 |
| Houdini 20.5.487 | `hython` 下同类查询/检查/执行、用户偏好目录展开、批处理拒绝监听 | GUI `uiready.py`、主线程调度、重启与多窗口 |
| 3ds Max 2025/2026 | 协议、安装及宿主 API 替身测试 | 本机未安装 Max，原生启动与操作均待验收 |
| Unreal 5.5.4 | 临时项目 commandlet：项目插件及 Python 依赖自动发现、启动脚本、场景与 Registry 查询、Python 执行、非交互不监听 | 交互 Editor 的 Slate 调度、重启、PIE 切换与生产资源 |
| Unity 6000.1.0f1 | 真实程序集编译、C# TCP 测试和 Python/MCP 测试 | 临时 batch 项目因无可用无界面许可证未运行成功；真实 Editor、包刷新、Play Mode 与生产场景待验收 |

安装测试使用临时用户配置或临时项目，没有安装到用户的真实软件配置或生产项目。原生工具仍可能使用其常规共享缓存。检查覆盖范围见各插件 README，不声称验证所有资源类型或完整帧序列。

## 审查与复跑

代码作者与审查者分开：Nuke/Houdini 与 Unity 交叉审查，Max/Unreal 由主线程独立审查并复跑完整测试。市场集成、图标来源和 Maya 版本差异另经独立审查。发现的 Unreal 根包未注册误报、PIE 执行保护、严格安装确认、Unity 异步方法与平台限制、Houdini 帧占位符边界已修正并测试。

从仓库根目录运行 `py -3.13 -m unittest discover -s tests -v`。各插件目录运行 `uv run --locked python -m unittest discover -s tests -v`；新增插件的 `tests/stdio_smoke.py` 可用 `uv run --locked tests/stdio_smoke.py` 复跑。原生测试与 Unity C# 验证入口及要求见插件 README、`tests/host_smoke.py`、`tests/native_smoke.py`、`tests/editor_smoke.py` 和 `tests/protocol_smoke.py`。
