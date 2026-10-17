# Bubble Houdini Control

面向 Houdini 20.5 的本机 Codex 插件，提供 Python 执行、场景信息、文件依赖检查与多实例文件名选择。软件侧仅使用内置 Python；Codex 端依赖 `uv` 和 Python ≥3.10，锁定 MCP 1.x。

## 安装与使用

在 Bubble Plugins 市场安装 `houdini-control`，请求“连接 Houdini”。助手先预览用户目录中的稳定运行时和 `python3.11libs/uiready.py` 启动块，获得同意后安装并提醒重启。无需每次复制代码；不想重启时可选用返回的 Python 代码。源插件缓存被移动也不影响已安装的运行时。

Houdini 20.5 使用其用户偏好目录（Windows Documents/houdini20.5），遵循 `HOUDINI_USER_PREF_DIR`（覆盖值必须含 `__HVER__`，安装时展开成 `20.5`）；仅 Python 3.11 构建。版本参数表示支持目标，不会自动启动应用或修改版本设置。仅 GUI 启动桥接，批处理不监听。

多开时每个进程随机分配独立的 127.0.0.1 端口和令牌。用“检查 hero.hip”匹配文件名，或从编号列表选择。重名必须进一步选目录/实例；没有接入桥接的窗口不能发现。超时不重放，关闭目标不跳转其他实例。

## 工具

`houdini_installation_status`、`houdini_install_bridge`、`houdini_uninstall_bridge`、`houdini_list_sessions`、`houdini_status`、`houdini_scene_info`、`houdini_inspect_scene`、`houdini_execute_python`。

安装/卸载默认 `confirmed=false`，只预览；得到用户同意后才设 true。安装备份原启动脚本，保留编码和其他内容，自有文件被改动时拒绝覆盖；卸载保留备份及额外文件。仅卸载 Codex 插件不会移除软件侧启动配置。正在运行的桥接需退出应用后停止。

执行工具拥有本机用户权限，非沙盒。传输限制 1 MiB，输出截取 128 KiB，最长执行等待 120 秒；开始执行后的超时不能撤销已经发生的修改。队列中超时的请求会被取消。令牌在用户目录的会话文件中，仅本机客户端使用。

检查覆盖有限：Houdini 使用 fileReferences，跳过反引号、op/opdef 等非本地引用，缺失候选可能是未来输出路径。序列/UDIM 仅证明至少一个匹配文件存在，不保证完整。

## 验证

在本插件目录运行 `uv run --locked python -m unittest discover -s tests -v`测试临时目录安装、回滚、所有权、双实例隔离、超时取消和宿主 API 适配；需允许本机回环套接字。

在本插件目录运行 `uv run --locked tests/stdio_smoke.py` 测试真实 stdio 工具握手。测试不安装到真实应用配置。

GUI 重启、实际用户素材和多个真实窗口仍需人工验收。脚本不自动启动 GUI，不自动保存用户场景。

## API 依据

- https://www.sidefx.com/docs/houdini/hom/locations.html
- https://www.sidefx.com/docs/houdini/hom/hou/ui.html
- https://www.sidefx.com/docs/houdini/hom/hou/fileReferences.html
- https://www.sidefx.com/docs/houdini/news/20_5/platforms.html

- https://www.sidefx.com/docs/houdini/ref/env

真实宿主只读冒烟：以 Houdini `hython tests/host_smoke.py` 运行对应插件脚本，使用隔离临时用户配置。执行信息查询、引用扫描、返回 42 的 Python 和无界面拒绝监听验证。

## 更新和卸载的两层范围

GitHub 发布后需刷新已注册的 Codex 插件市场，并重新加载聊天或重启 Codex。软件/项目中的桥接独立保存，需预览差异、经同意后更新，再重启或使用该软件支持的刷新方式。完整卸载请先通过本插件工具卸载软件端桥接，再从 Codex 移除插件；只卸载 Codex 插件会保留软件端配置。Windows 旧版缓存被占用时，先停掉明确属于该插件的旧 MCP 进程，再重试，勿关闭创作软件或批量删除配置。
