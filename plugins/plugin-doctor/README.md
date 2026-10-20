# Bubble Plugin Doctor

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

支持八个软件插件及 Deadline、Sequence Check、Asset Package、Plugin Doctor。各缓存版本均展示；不会把缓存存在误报为“已启用”或“工具已加载”。启用状态和实际工具发现需要 Codex 宿主确认。本地来源版本不代表远端最新版本，不自动联网刷新市场。

PR / PS 的 UXP 面板使用当前 Codex 会话内的配对连接，由对应插件的 `*_list_sessions` 查询；不使用旧 DCC 的 PID 注册目录。诊断中心可检查其 Codex 包并提供官方安装、卸载和重新配对指引。

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
