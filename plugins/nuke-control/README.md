# Bubble Nuke Control

Current Codex package: **0.3.0**. Software-side bridge: **0.3.0**. Update the owned host bridge through setup, then restart/reload the application once.
面向 Nuke 15.1 的本机 Codex 插件，提供 Python 执行、场景信息、文件依赖检查与多实例文件名选择。软件侧仅使用内置 Python；Codex 端依赖 `uv` 和 Python ≥3.10，锁定 MCP 1.x。

## 安装与使用

在 Bubble Plugins 市场安装 `nuke-control`，请求“连接 Nuke”。助手先预览用户目录中的稳定运行时和 `menu.py` 启动块，获得同意后安装并提醒重启。无需每次复制代码；不想重启时可选用返回的 Python 代码。源插件缓存被移动也不影响已安装的运行时。

默认 Nuke 用户目录是 `~/.nuke`，覆盖变量 `BUBBLE_NUKE_USER_DIR`。自定义目录必须已位于 Nuke 的插件搜索路径（NUKE_PATH）；BUBBLE_NUKE_USER_DIR 只告诉安装器位置，不修改 Nuke 搜索路径。版本参数表示支持目标，不会自动启动应用或修改版本设置。仅 GUI 启动桥接，批处理不监听。

多开时每个进程随机分配独立的 127.0.0.1 端口和令牌。用“检查 hero.nk”匹配文件名，或从编号列表选择。重名必须进一步选目录/实例；没有接入桥接的窗口不能发现。超时不重放，关闭目标不跳转其他实例。

## 工具

`nuke_installation_status`、`nuke_install_bridge`、`nuke_uninstall_bridge`、`nuke_list_sessions`、`nuke_status`、`nuke_scene_info`、`nuke_inspect_scene`、`nuke_execute_python`。

安装/卸载默认 `confirmed=false`，只预览；得到用户同意后才设 true。安装备份原启动脚本，保留编码和其他内容，自有文件被改动时拒绝覆盖；卸载保留备份及额外文件。仅卸载 Codex 插件不会移除软件侧启动配置。正在运行的桥接需退出应用后停止。

执行工具拥有本机用户权限，非沙盒。传输限制 1 MiB，输出截取 128 KiB，最长执行等待 120 秒；开始执行后的超时不能撤销已经发生的修改。队列中超时的请求会被取消。令牌在用户目录的会话文件中，仅本机客户端使用。

检查覆盖有限：Nuke 检查 Read/DeepRead/ReadGeo 与启用文件读取的 Camera2/Axis2，跳过 Tcl/Python 字符串表达式。序列/UDIM 仅证明至少一个匹配文件存在，不保证完整。

## 验证

在本插件目录运行 `uv run --locked python -m unittest discover -s tests -v`测试临时目录安装、回滚、所有权、双实例隔离、超时取消和宿主 API 适配；需允许本机回环套接字。

在本插件目录运行 `uv run --locked tests/stdio_smoke.py` 测试真实 stdio 工具握手。测试不安装到真实应用配置。

GUI 重启、实际用户素材和多个真实窗口仍需人工验收。脚本不自动启动 GUI，不自动保存用户场景。

## API 依据

- https://learn.foundry.com/nuke/developers/14.0/pythonreference/startup.html
- https://learn.foundry.com/nuke/developers/70/pythonreference/nuke.executeInMain-module.html

真实宿主只读冒烟：以 Nuke `-t tests/host_smoke.py` 运行对应插件脚本，使用隔离临时用户配置。执行信息查询、引用扫描、返回 42 的 Python 和无界面拒绝监听验证。

## 更新和卸载的两层范围

GitHub 发布后需刷新已注册的 Codex 插件市场，并重新加载聊天或重启 Codex。软件/项目中的桥接独立保存，需预览差异、经同意后更新，再重启或使用该软件支持的刷新方式。完整卸载请先通过本插件工具卸载软件端桥接，再从 Codex 移除插件；只卸载 Codex 插件会保留软件端配置。Windows 旧版缓存被占用时，先停掉明确属于该插件的旧 MCP 进程，再重试，勿关闭创作软件或批量删除配置。


## Structured everyday tools

The new bridge adds `nuke_scene_state`, `nuke_scene_file`, `nuke_query_nodes`,
`nuke_create_node`, `nuke_edit_node`, `nuke_select_nodes`, `nuke_node_attribute`,
`nuke_node_connections`, and `nuke_timeline`. Prefer these over arbitrary scripts.
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


## 日常操作补全 0.3.0

- `nuke_keyframes`：单 view 数值 knob 的指定 component 关键帧查询、写入、删除；先 get 并传 `expected_keys=revision`，已有键覆盖和删除各需明确标记。保护 expression knob，插值沿用 Nuke 原生默认/现有行为。
- `nuke_graph_transfer`：显式根层节点/整个 Group 导出 `.nk` 片段、导入用户授权的本地片段。恢复原选择，导入不自动连接已有选中节点，导出禁止覆盖当前工程；同名导入采用 Nuke 原生改名并返回实际节点路径。文件可能执行脚本/回调，不能将导入视为数据沙箱。
- `nuke_project_settings`：读取/设置项目宽高、pixel aspect、FPS；先 get 获取 `expected_settings=revision`，省略参数保持原值，单改FPS保留原图像区域；改变宽高时建立完整图像区域格式，不重定时关键帧、不启动渲染。格式定义加入当前 Nuke 会话，不写用户首选项。

API：[Double_Knob](https://learn.foundry.com/nuke/developers/151/pythondevguide/_autosummary/nuke.Double_Knob.html)、[nodePaste](https://learn.foundry.com/nuke/developers/151/pythondevguide/_autosummary/nuke.nodePaste.html)。

实机：Nuke 15.1v5 独立 `--safe -t` 临时工程已通过关键帧回读/删除、旧revision/覆盖拒绝、片段往返和选择恢复、512×512/25 FPS 设置与回读。没有连接现有 GUI 场景。

当前 MCP 工具共 20 个。优先使用上述结构化工具；每次写入仍须选定实例并传最新场景身份。Maya/Nuke/Houdini 的 snapshot 包含随机桥接 session 身份，重启或重新连接后的旧 snapshot 无效；它不覆盖每个属性编辑。

此版本保留已修复的依赖锁，不升级第三方依赖。软件侧 payload 已改变，需要通过 setup 预览并更新；不会自动更改用户启动配置。安装/卸载所有权、冲突保护、多实例选择逻辑继续生效。
