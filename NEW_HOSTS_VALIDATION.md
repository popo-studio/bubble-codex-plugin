# Blender、Cinema 4D 与 Resolve 验收记录

日期：2026-10-25。新增三个 0.1.0 插件，Plugin Doctor 更新到 0.1.8；市场共 16 个插件。用户授权按公开接口开发未安装的软件，原生验收与协议/接口替身测试分开记录。

## 软件与实现范围

| 插件 | 工具数 | 接入方式 | 原生验证范围 |
| --- | ---: | --- | --- |
| Blender 0.1.0 | 19 | 用户 scripts 中的自有 Startup 模块、私有会话登记、随机本机端口，主线程 timer 执行 bpy | 已安装 4.5.3 LTS；5.2 LTS 未在本机验证 |
| Cinema 4D 0.1.0 | 7 | 连接管理与动态调用 Maxon 内置 MCP，工具名/schema 来自实际发现 | 未安装 Cinema 4D 2027，真实导出配置、原生工具和多窗口待验收 |
| DaVinci Resolve 0.1.0 | 20 | Windows Resolve Studio 21+ 官方外部 Python API，首次启用 Local | 未安装；SDK 包装器、原生 DLL 与 Python ABI 待实机验收 |
| Plugin Doctor 0.1.8 | 7（原有数量） | 新增三款包检查和维护指引；Blender bridge 检查，C4D/Resolve 转交各自诊断工具 | 不以包存在代替 Codex 工具加载成功 |

Resolve 的官方 API 没有公开的任意 PID 选择方式，多进程时只列出并拒绝执行。C4D 会话标识代表已选择的 MCP 连接，不等于 OS PID 或文档；文档状态校验以 Maxon 实际工具为准。没有声称三款软件具有完全相同的多实例或事务能力。

## 已完成验证

- 市场静态检查 4 项通过：16 个条目、双清单版本、两个锁文件、启动参数、自包含技能和图标、PR 原有签名资源一致性。
- Blender 40 项单元测试通过；真实 bpy 后台测试覆盖 14 组操作与拒绝条件。隔离的双 GUI 测试使用安装工具生成启动模块，验证自动连接、MCP 创建/读取/保存两个测试场景、同名文件歧义与完整路径选择、关闭所选测试进程后拒绝回退、卸载自有桥接。
- Blender 独立审查发现并修复：timer 注册失败后的 socket 清理、非 Euler 旋转模式的误写、负起止帧和过小分辨率被宿主截断、超长 UTF-8 名称被截断。修复后重新运行单测及真实 bpy 检查。
- Blender 最终复核增加每次桥接启动独有的随机会话标识并纳入快照，避免 Windows 复用 PID 且场景结构相同时接受旧操作。新回归证明旧快照被拒绝、重复启动现有桥接保持标识稳定；独立定向测试和最终双 GUI 原生测试再次通过。
- C4D 33 项测试通过，包含真实 stdio、回环 Streamable HTTP 和 SSE 的 MCP 测试服务；覆盖登记预览、连接/发现/调用、凭据遮蔽、同时连接冲突、超时/服务退出、配置变更、跨重连拒绝重复请求 ID。双层 stdio 测试发现 7 个 Bubble 工具并通过模拟原生服务完成调用。独立复核通过，未把这些服务误称为 Maxon 实机。
- Resolve 32 项测试及 20 工具 MCP stdio 验证通过，覆盖 PID/启动时间与项目 ID 校验、拒绝多进程、无项目创建/打开、预览、导入/移动媒体、时间线、bin/标记、渲染设置及结果边界。包含真实子进程测试：删除隔离包副本后，服务仍可读取状态并启动已快照的 worker；无效 PID 在加载 SDK 前被拒绝。
- Doctor 19 项测试运行完成，18 项通过，1 项因环境不能创建符号链接而跳过；真实 MCP stdio 发现 7 个工具并调用成功。Sequence Check 的 Python 3.13 启动参数不再被误报。
- 流程回归通过：真实版本化启动器执行图片/EXR 序列检查、素材复制与校验、Doctor 诊断；仅使用测试文件。
- 16 个插件全部通过 Windows 运行中移除测试：每包同时启动两套版本化服务，验证解释器、环境与工作目录均在包外；删除隔离包副本后，两套服务仍响应工具查询。Resolve 另有上述 worker 实际调用验证。
- 桌面实际使用的 Codex 0.164.0-alpha.11.1 后端完成全部 16 包安装、249 个工具发现及每包一次只读调用；测试前未安装的 14 个包经官方卸载接口移除，已有 Maya/PS 保留。旧版 `cwd=/` 配置仍可重现“有技能无工具”的故障对照。测试只创建临时会话，不运行模型回合或软件端安装。
- 依赖安全审计：pip-audit 2.10.1 / PyPI 覆盖全部 32 份项目/启动器锁文件、44 组包名与版本，0 个已知受影响版本，0 个跳过。这是截至检查时的漏洞数据库结果，不等于不存在未知漏洞。

独立审查与作者实现分开进行。测试不安装创作软件，不改动真实用户配置，不连接生产 Resolve/C4D，不提交渲染任务。Blender GUI 测试只启动并清理自己创建的进程和临时目录。

## 复现

在仓库根目录运行。`UV_PROJECT_ENVIRONMENT` 可设置到包外测试目录，避免开发测试生成的 `.venv` 被误当作发布安装布局。

```powershell
py -3.13 -m unittest discover -s tests -v
uv run --locked --project plugins/blender-control --python 3.13 python -m unittest discover -s plugins/blender-control/tests -v
uv run --locked --project plugins/blender-control --python 3.13 python plugins/blender-control/tests/stdio_smoke.py
uv run --locked --project plugins/blender-control --python 3.13 python plugins/blender-control/tests/native_gui_acceptance.py
uv run --locked --project plugins/cinema4d-control --python 3.13 python -m unittest discover -s plugins/cinema4d-control/tests -v
uv run --locked --project plugins/cinema4d-control --python 3.13 python plugins/cinema4d-control/tests/stdio_smoke.py
uv run --locked --project plugins/resolve-control --python 3.11 python -m unittest discover -s plugins/resolve-control/tests -v
uv run --locked --project plugins/resolve-control --python 3.11 python plugins/resolve-control/tests/stdio_smoke.py
```

Blender 原生 GUI 测试内的可执行路径对应开发机 4.5 安装，需要在其他机器按实际路径调整；不要改成连接用户已有的进程。原生后台测试脚本须由 Blender 执行。C4D 的网络测试启动本机 MCP 测试服务；其工具并非 Maxon 真实工具。

## 用户实机验收

1. Blender：安装 Codex 插件，预览具体版本的 scripts 目录，授权安装并重启；列出实例，创建并保存一个测试场景，再验证完整卸载保留其他文件。
2. C4D：在 2027 完整 GUI 中启用内置 MCP，保存私有导出 JSON 并登记；发现真实工具，读取当前测试文档再创建对象。两个实例须使用各自可区分的官方连接配置。检查导出格式、权限和断线后的明确重连流程。
3. Resolve：安装 Studio 21+ 并启用 Local 外部脚本；先检查 SDK/进程状态和项目，再在一次性测试项目中预览/创建 bin、导入素材、创建时间线和标记。验证多进程拒绝调用，最后卸载 Codex 插件。

C4D/Resolve 若实际官方接口与文档或契约有差异，应返回明确错误并修正适配，不自动退回 Computer Use、任意旧版桥接或其他实例。
