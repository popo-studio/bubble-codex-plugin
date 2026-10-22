# Bubble Plugin Doctor 0.1.7

集中检查 Bubble 插件包、软件桥接文件和实例连接，提供修复、更新、卸载流程。全部工具只读；维护操作转交 Codex 官方工具及对应软件插件，沿用它们的预览和确认机制。

## 使用

安装后可以说“检查 Bubble 插件”“诊断 Maya 连接”“帮我完整卸载 Nuke 插件”。需要 uv、Python >=3.10，无需修改任何创作软件配置。

| 工具 | 范围 |
| --- | --- |
| `doctor_status` | 本服务版本、Python、uv 和支持范围 |
| `doctor_inventory` | 最多 100 个缓存市场、每插件 30 个版本，总计最多 100 个缓存包；可比较指定本地仓库 |
| `doctor_check_package` | 清单与 MCP 配置一致性、启动文件、已知 cwd 和包内 .venv 问题 |
| `doctor_check_bridge` | 指定 runtime 目录的所有权记录与实际文件 SHA256 |
| `doctor_list_sessions` | 一个软件的注册实例；最多 16 个只读回环连接探测，返回场景名与 PID |
| `doctor_check_log` | 指定日志尾部最多 256 KiB 的已知错误分类；不返回原始日志 |
| `doctor_repair_guidance` | 修复/更新/卸载步骤，不执行写操作 |

支持九个软件插件及 Deadline、Sequence Check、Asset Package、Plugin Doctor。各缓存版本均展示；不会把缓存存在误报为“已启用”或“工具已加载”。启用状态和实际工具发现需要 Codex 宿主确认。本地来源版本不代表远端最新版本，不自动联网刷新市场。

PR 的 Codex 插件包为 0.4.1，软件侧桥接仍为 0.4.0，使用签名 CEP 后台扩展，在 PR 启动后自动发现当前用户的 Codex 连接；日常无需打开面板或输入配对码。首次安装或更新软件侧桥接后可能需要重启 PR；仅更新 Codex 包的依赖不需要重装或重启软件侧桥接。多个实例按会话和项目路径选择；诊断中心不再要求 Creative Cloud / UPIA 或重复配对。

AE 0.3.0 面向 26.x，通过自有 Startup 脚本自动连接。首次安装需要程序目录写入权限，并由用户启用一次 AE 脚本文件写入权限后重启。多个实例按项目路径和会话选择，不需面板或配对码，超时不重试。完整卸载先移除自有启动脚本，再卸载 Codex 插件。

新增的场景、对象和时间线工具需要软件内桥接同步更新。若 Codex 已显示新工具、软件仍加载旧桥接，先检查安装状态并更新，然后重启对应软件；不应改用任意脚本自动重试失败的写操作。

Photoshop 0.2.0 起为原生 Windows COM 直连，仅需 Codex 插件。诊断指引检查具体版本、路径和已运行进程，不再要求 Creative Cloud、Adobe 面板或配对。

桥接完整性仅与本地安装记录比较；不验证启动脚本，不把磁盘版本当作进程已加载版本。对软件配置的完整检查仍使用对应 `*_installation_status`。只探测注册的 127.0.0.1 服务，无法连接不等于软件已关闭；多实例必须选择。软链接、重解析目录不自动遍历，应改用实际目录。

## 更新与卸载

通过同一 Codex 市场更新/卸载。本插件无后台服务、常驻桥接或自建配置目录；不清除用户项目、日志或 uv 共享缓存。修复功能是受控流程入口，不会自动终止进程、修改其他插件或删除缓存。

## 验证

```powershell
uv run --locked python -m unittest discover -s tests -v
uv run --locked tests/stdio_smoke.py
```

测试覆盖损坏元数据、路径越界、文件篡改、令牌不回显、日志秘密不输出、多实例以及固定只读 TCP 操作；真实 Codex 加载和运行中卸载由仓库级集成测试验证。

插件结构与生命周期依据 [OpenAI 官方打包文档](https://developers.openai.com/plugins/build/plugins)。图标为本项目原创 SVG。

## Runtime security patch 0.1.7

The Codex package updates its locked Python dependencies. This does not change external software configuration or existing data. Reload the Codex plugin to start the patched runtime.
