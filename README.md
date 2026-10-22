# Bubble Codex Plugins

一个 Git 仓库维护自己的 Codex 插件市场。十三个插件可独立安装：九个连接本机创作软件，另四个提供渲染管理、序列检查、素材打包和插件诊断。

| 插件 | 目标版本 | 执行能力 | 安装范围 |
| --- | --- | --- | --- |
| [Bubble Maya](plugins/maya-control/README.md) | Maya 2027 | Python / MEL | Maya 用户配置 |
| [Bubble Nuke](plugins/nuke-control/README.md) | Nuke 15.1 | Python | Nuke 用户配置 |
| [Bubble Houdini](plugins/houdini-control/README.md) | Houdini 20.5，Python 3.11 | Python | 对应版本用户配置 |
| [Bubble 3ds Max](plugins/max-control/README.md) | Windows 3ds Max 2025/2026 | Python / MAXScript | 明确选择用户启动脚本目录 |
| [Bubble Unreal](plugins/unreal-control/README.md) | Unreal Engine 5.5 | Editor Python | 用户指定的 Unreal 项目 |
| [Bubble Unity](plugins/unity-control/README.md) | Unity 6 / 6000.x | 已编译 C# 静态方法 / 菜单命令 | 用户指定的 Unity 项目 |
| [Bubble Premiere](plugins/premiere-control/README.md) | Windows Premiere Pro 26.x | 项目、序列、时间线、素材检查与支持的项目操作 | 用户目录签名 CEP 扩展，无 CC/UPIA |
| [Bubble After Effects](plugins/after-effects-control/README.md) | Windows After Effects 26.x | 项目检查、合成、素材、图层、变换、保存与授权 JSX | 启动脚本自动连接，多实例按项目选择 |
| [Bubble Photoshop](plugins/photoshop-control/README.md) | Windows Photoshop 26.2+，原生 COM | 文档、PSD/图片输出、画布调整、图层与文字管理、ExtendScript | 仅安装 Codex 插件，无 PS 端桥接 |
| [Bubble Deadline](plugins/deadline-control/README.md) | 现有 Deadline 10 客户端 | 任务查询、日志检查、预览后提交/重提 | 无软件侧桥接 |
| [Bubble Sequence Check](plugins/sequence-check/README.md) | 本地图片序列 / EXR | 缺帧、损坏、通道、尺寸与像素异常检查 | 无软件侧桥接 |
| [Bubble Asset Package](plugins/asset-package/README.md) | 明确的依赖路径清单 | 预览、复制到新目录、SHA256 校验 | 无软件侧桥接 |
| [Bubble Plugin Doctor](plugins/plugin-doctor/README.md) | Bubble 插件及各自支持的桥接诊断 | 包/文件/实例诊断与维护流程入口 | 无软件侧桥接 |

检查范围各有区别：DCC 插件检查场景与文件引用；Unreal 检查 Asset Registry 的直接依赖；Unity 检查已加载场景中的缺失脚本与序列化引用。结果会标明跳过项、截断和覆盖限制。

九个软件现在均提供常用结构化编辑工具，优先通过插件完成操作。具体覆盖范围、版本和限制见 [功能清单](FEATURES.md)。多个实例先列出文件名和路径供选择，写入继续绑定所选实例与目标状态。

## 添加市场

在 Codex「添加插件市场」填写：

| 字段 | 内容 |
| --- | --- |
| 来源 | `git@github.com:popo-studio/bubble-codex-plugin.git` |
| Git 引用 | `main` |
| 稀疏路径 | 留空 |

也可以使用本地仓库 `D:\Workspace\Bubble\bubble-codex-plugins` 作为来源，Git 引用留空。仓库需同时包含 `.agents/plugins/marketplace.json` 与 `plugins/`，不要填写截图示例中的 `plugins/codex`。SSH 来源需要本机 Git 有仓库访问权限。

在市场中安装所需插件，再请求“连接 Nuke”或“连接这个 Unity 项目”。Codex 端需要 `uv` 和 Python ≥3.10；安装后的服务通过 `launch-<version>.py` 启动，依赖由相邻的 `.py.lock` 锁定，运行环境位于插件目录外。开发环境依赖由 `uv.lock` 锁定。

## 四个流程插件

这四个插件安装后直接提供工具，无需往创作软件复制代码或重启软件。

- Deadline 对接已安装且已配置 Repository/RCS 的 `deadlinecommand`，保留现有农场配置。查询只读；提交与重提先展示具体作业/任务和操作，再在授权后执行。
- Sequence Check 实际解码 PNG/JPEG/TIFF/BMP 和平面 EXR，检查缺帧、损坏、尺寸/通道变化、非有限数值及疑似黑帧/重复帧。提供预期首尾帧才能判断两端缺帧；深度或多层级 EXR 有覆盖限制。首版不生成预览视频，不代替艺术质量审核。
- Asset Package 使用明确路径或依赖清单，可由现有 DCC 的只读检查结果整理输入。预览实际文件、缺失项、大小和目标映射，授权后仅复制到新目录并生成校验清单。不会自行解析所有二进制场景、修改引用路径，也不把“文件复制成功”当作“另一台机器一定能打开场景”。
- Plugin Doctor 检查包、版本、桥接哈希、注册实例和指定日志。缓存存在不代表已启用或工具已加载；它返回维护流程，再由 Codex/对应插件的正式工具执行修复、更新与卸载。

四个新插件的逐项验收见 [流程插件验收](WORKFLOW_ACCEPTANCE.md)。

## Photoshop 无额外组件连接

0.5.0 增加文档复制、图层缩放/旋转/排序/混合模式、文字样式、历史记录查询与恢复、选区保存到 alpha 通道与读取，并扩展色彩平衡、运动模糊、杂色和锐化。历史恢复先核对当前历史列表，保存选区拒绝覆盖同名通道。

0.4.0 增加选区查询/修改与填充、栅格蒙版、亮度对比/色阶/反相/去色、高斯模糊/USM 锐化/中间值滤镜、嵌入式智能对象转换和位图内容替换。像素操作明确选择指定图层和复合通道，拒绝自动栅格化；这些调色/滤镜直接修改像素，不是调整图层或智能滤镜。智能对象替换不接受链接对象、脚本、PDF 或 RAW。为防止共享内容连带修改，只要任一打开文档中还存在其他智能对象，替换就会保守拒绝并列出相关图层；不会自动删除或关闭它们。

0.3.0 提供保存 PSD、导出 PNG/JPEG、关闭文档、图像/画布缩放、裁切、旋转，以及图层和组创建、文字编辑、重命名、可见性/透明度、复制、删除、移动和选择。图层按稳定 ID 定位；保存默认拒绝覆盖，关闭默认拒绝丢弃修改，导出处理副本以保留原文档图层。未专门封装的操作仍可使用已授权的 JSX；没有声称覆盖 PS 的全部功能。

0.2.1 可在没有文档时直接通过插件创建画布或打开文件，并按文档 ID 切换活动文档。创建、打开、切换、检查及已授权的脚本操作优先使用插件，无需 Computer Use。发布后应执行 `codex plugin marketplace upgrade bubble-plugins` 更新 Git 市场副本，再安装新版插件；刷新详情页不代表 Git 副本已经更新。

Windows Photoshop 26.2+ 使用 Adobe 自带 COM 自动化，无需 Creative Cloud、UPIA、UXP 面板、开发者工具或开发者模式。安装 Codex 插件后，打开目标 Photoshop 即可检测其版本、进程和文档。软件侧没有额外安装文件或监听服务，卸载 Codex 插件即移除该接入代码。

插件绑定已注册的具体版本并核对真实安装路径，不使用可能指向旧版本的通用 ProgID。仅连接已运行的实例，不自动启动软件；同一路径出现多个 Photoshop 进程时拒绝操作，因为 COM 无法保证按 PID 选择。多个文档按明确 ID 操作，写入前重新核对目标；超时不重试。

## Premiere 与 After Effects 新版接入（待实机验收）

两者面向 26.x，不兼容本机旧 PR 2021 / AE 2024。用户已确认先完成代码和自动化测试，升级软件后再验收原生操作；不能把工具加载、模拟宿主测试或磁盘安装成功当作新版软件实测。

PR 0.4.0 使用签名 CEP 后台扩展，由插件预览后安装到当前用户扩展目录，不需要 Creative Cloud、UPIA、用户开发者工具或调试开关。首次安装或更新后重启 PR，后台扩展自动发现当前 Windows 用户的 Codex 连接，日常无需打开面板或输入配对码。多个 PR 实例按项目名、路径和会话列出，由用户选择；多个 Codex 聊天可分别连接，宿主命令串行执行。断线后不重放写操作、不自动替换已选择的实例。更新需同步软件侧签名资源；完整卸载先移除自有扩展，再卸载 Codex 插件。

AE 0.3.0 使用软件自身的 Startup 脚本与定时任务自动连接。插件先预览并安装所选 AE 目录内的桥接文件；写入程序目录可能需要 Windows 管理员权限。首次安装需启用一次「允许脚本写入文件和访问网络」并重启 AE，不静默修改偏好。之后无需面板或配对码，多实例按会话与项目路径选择，命令只进入所选实例的队列。写操作检查项目状态和截止时间，超时不自动重放；完整卸载先移除自有启动脚本，再卸载 Codex 插件。新版原生启动仍待实机验收。

## 六个 DCC 首次连接

1. 展示具体软件版本、用户配置或项目路径和将修改的文件。
2. 获得用户同意后安装稳定的桥接文件，默认不会直接安装。
3. 提醒保存工作并重启对应软件。用户选择不重启时，提供该软件适用的加载代码或刷新步骤。
4. 读取当前场景/项目，确认连接。发现多个实例时，列出文件名和项目供用户编号选择，也可直接提供文件名。重名时补充完整路径。

上述六个 DCC 的每个实例使用独立随机本机端口、令牌和 PID。关闭或超时后不自动切到另一个窗口，也不自动重复执行写操作。列表只包含已加载桥接的实例；不可达记录会明确显示，不假定窗口已经关闭。

桥接独立于 Codex 插件缓存。更新市场插件后，需要再次预览并确认软件侧更新。卸载 Codex 插件不会自动删除软件侧桥接，应先运行该插件的卸载流程；用户修改过的文件会报告冲突并保留。完整流程及 Windows 缓存占用处理见 [更新与卸载](UPDATING.md)。

## 验收

刷新市场并安装所需 DCC 插件，然后分别完成：

- 预览安装：确认未同意前没有修改软件配置或项目。
- 同意安装，保存工作并重启，查询当前场景/项目名称。
- 执行一次只读脚本或静态方法，检查一次文件/资源报告。
- 打开两个已接入实例：用编号或文件名选择；同名文件要求进一步选择。
- 关闭选中的实例后再次调用，确认报告连接失败而不操作另一个窗口。
- 预览卸载并确认，检查原有启动脚本、项目文件和用户内容仍保留。

Unity 自定义脚本需先经过 Unity 编译，再调用其中的静态方法。现有项目编译错误可能阻止桥接加载。Unreal 需要内置 Python Script Plugin；项目禁用它时按设置说明处理。本机没有 3ds Max，尚未实机验证。真实 GUI 重启、多窗口和生产项目检查由用户验收，自动化测试不代替这些步骤。

九个软件图标使用产品资源，四个流程插件使用原创 SVG；来源见 [THIRD_PARTY_ASSETS.md](THIRD_PARTY_ASSETS.md)。本项目是独立第三方集成。

## 开发与测试

每个 `plugins/<名称>/` 自包含：通用 `plugin.json`、Codex 兼容清单、两份 MCP 配置、技能、服务、图标和测试；DCC 插件另带软件侧桥接。安装后无需引用兄弟插件。

```powershell
py -3.13 -m unittest discover -s tests -v
cd plugins/nuke-control
uv run --locked python -m unittest discover -s tests -v
uv run --locked tests/stdio_smoke.py
```

本次结果见 [验证记录](VALIDATION.md)。其他插件的具体验证命令和实机验证限制见各自 README。单元测试和软件宿主测试使用临时配置/项目；网络测试需允许本机回环连接。不要提交虚拟环境、用户场景、会话令牌或软件用户配置。

发布前还需用 **桌面应用实际使用的 Codex 后端** 验证插件加载。`tests/codex_plugin_smoke.py --codex <codex.exe绝对路径>` 默认只读取插件，检查十三个 MCP 服务及旧版 `cwd` 故障对照。加 `--install` 后会实际安装或更新十三个 Codex 插件，创建不持久化的测试会话，发现工具并调用只读的实例列表或状态；结束时卸载原先未安装的插件，保留已有插件的更新。它不安装软件侧桥接、不运行模型回合，也不提交渲染任务。此项会修改 Codex 插件安装状态，应在已授权的测试环境执行。

`tests/launcher_smoke.py` 另验证服务从插件目录启动后迁出，并在连接期间删除临时插件副本。两种测试都需要通过，独立 MCP SDK 的测试无法替代 Codex 插件加载测试。

`tests/workflow_smoke.py` 通过真实发布启动器在临时文件上验证序列解码、缺帧、打包确认与校验、诊断流程；需要已安装 MCP SDK 的 Python。Deadline 的提交流程测试使用替身命令，不操作生产农场。

更新时同步两个插件清单、Python 项目版本、软件侧版本和锁文件，并将启动脚本及相邻锁文件命名为新版本的 `launch-<version>.py` 与 `launch-<version>.py.lock`，同步两份 MCP 配置中的路径。版本化脚本让新旧服务使用独立的依赖环境。市场格式依据 [OpenAI 插件打包文档](https://developers.openai.com/plugins/build/plugins)。
