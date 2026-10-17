# Bubble Codex Plugins

一个 Git 仓库维护自己的 Codex 插件市场。六个插件可独立安装：连接本机创作软件，检查当前场景或项目，并执行用户请求的脚本或编辑器命令。

| 插件 | 目标版本 | 执行能力 | 安装范围 |
| --- | --- | --- | --- |
| [Bubble Maya](plugins/maya-control/README.md) | Maya 2027 | Python / MEL | Maya 用户配置 |
| [Bubble Nuke](plugins/nuke-control/README.md) | Nuke 15.1 | Python | Nuke 用户配置 |
| [Bubble Houdini](plugins/houdini-control/README.md) | Houdini 20.5，Python 3.11 | Python | 对应版本用户配置 |
| [Bubble 3ds Max](plugins/max-control/README.md) | Windows 3ds Max 2025/2026 | Python / MAXScript | 明确选择用户启动脚本目录 |
| [Bubble Unreal](plugins/unreal-control/README.md) | Unreal Engine 5.5 | Editor Python | 用户指定的 Unreal 项目 |
| [Bubble Unity](plugins/unity-control/README.md) | Unity 6 / 6000.x | 已编译 C# 静态方法 / 菜单命令 | 用户指定的 Unity 项目 |

检查范围各有区别：DCC 插件检查场景与文件引用；Unreal 检查 Asset Registry 的直接依赖；Unity 检查已加载场景中的缺失脚本与序列化引用。结果会标明跳过项、截断和覆盖限制。

## 添加市场

在 Codex「添加插件市场」填写：

| 字段 | 内容 |
| --- | --- |
| 来源 | `git@github.com:popo-studio/bubble-codex-plugin.git` |
| Git 引用 | `main` |
| 稀疏路径 | 留空 |

也可以使用本地仓库 `D:\Workspace\Bubble\bubble-codex-plugins` 作为来源，Git 引用留空。仓库需同时包含 `.agents/plugins/marketplace.json` 与 `plugins/`，不要填写截图示例中的 `plugins/codex`。SSH 来源需要本机 Git 有仓库访问权限。

在市场中安装所需插件，再请求“连接 Nuke”或“连接这个 Unity 项目”。Codex 端需要 `uv` 和 Python ≥3.10；安装后的服务通过 `launch-<version>.py` 启动，依赖由相邻的 `.py.lock` 锁定，运行环境位于插件目录外。开发环境依赖由 `uv.lock` 锁定。

## 首次连接

1. 展示具体软件版本、用户配置或项目路径和将修改的文件。
2. 获得用户同意后安装稳定的桥接文件，默认不会直接安装。
3. 提醒保存工作并重启对应软件。用户选择不重启时，提供该软件适用的加载代码或刷新步骤。
4. 读取当前场景/项目，确认连接。发现多个实例时，列出文件名和项目供用户编号选择，也可直接提供文件名。重名时补充完整路径。

每个实例使用独立随机本机端口、令牌和 PID。关闭或超时后不自动切到另一个窗口，也不自动重复执行写操作。列表只包含已加载桥接的实例；不可达记录会明确显示，不假定窗口已经关闭。

桥接独立于 Codex 插件缓存。更新市场插件后，需要再次预览并确认软件侧更新。卸载 Codex 插件不会自动删除软件侧桥接，应先运行该插件的卸载流程；用户修改过的文件会报告冲突并保留。完整流程及 Windows 缓存占用处理见 [更新与卸载](UPDATING.md)。

## 验收

刷新市场并安装五个新插件，然后分别完成：

- 预览安装：确认未同意前没有修改软件配置或项目。
- 同意安装，保存工作并重启，查询当前场景/项目名称。
- 执行一次只读脚本或静态方法，检查一次文件/资源报告。
- 打开两个已接入实例：用编号或文件名选择；同名文件要求进一步选择。
- 关闭选中的实例后再次调用，确认报告连接失败而不操作另一个窗口。
- 预览卸载并确认，检查原有启动脚本、项目文件和用户内容仍保留。

Unity 自定义脚本需先经过 Unity 编译，再调用其中的静态方法。现有项目编译错误可能阻止桥接加载。Unreal 需要内置 Python Script Plugin；项目禁用它时按设置说明处理。本机没有 3ds Max，尚未实机验证。真实 GUI 重启、多窗口和生产项目检查由用户验收，自动化测试不代替这些步骤。

软件图标使用原始资源，来源见 [THIRD_PARTY_ASSETS.md](THIRD_PARTY_ASSETS.md)。本项目是独立第三方集成。

## 开发与测试

每个 `plugins/<名称>/` 自包含：通用 `plugin.json`、Codex 兼容清单、两份 MCP 配置、技能、服务、软件侧桥接、图标和测试。安装后无需引用兄弟插件。

```powershell
py -3.13 -m unittest discover -s tests -v
cd plugins/nuke-control
uv run --locked python -m unittest discover -s tests -v
uv run --locked tests/stdio_smoke.py
```

本次结果见 [验证记录](VALIDATION.md)。其他插件的具体验证命令和实机验证限制见各自 README。测试只使用临时配置/项目；网络测试需允许本机回环连接。不要提交虚拟环境、用户场景、会话令牌或软件用户配置。

更新时同步两个插件清单、Python 项目版本、软件侧版本和锁文件，并将启动脚本及相邻锁文件命名为新版本的 `launch-<version>.py` 与 `launch-<version>.py.lock`，同步两份 MCP 配置中的路径。版本化脚本让新旧服务使用独立的依赖环境。市场格式依据 [OpenAI 插件打包文档](https://developers.openai.com/plugins/build/plugins)。
