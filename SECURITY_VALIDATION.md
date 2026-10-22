# 2026-10-22 依赖安全更新验收

本轮处理 GitHub Dependabot 的 113 条未关闭告警。告警在多个清单中重复出现，不等于 113 个独立漏洞；实际涉及 Pillow、OpenEXR 和 certifi 三个依赖。

## 告警与修复

| 依赖 | 原版本 → 修复版本 | GitHub 告警数 | 修改范围 |
| --- | --- | ---: | --- |
| Pillow | 11.3.0 → 13.0.0 | 90 | 序列检查的项目依赖与独立启动器锁文件 |
| OpenEXR | 3.4.4 → 3.4.9 | 12 | 序列检查的项目依赖与独立启动器锁文件 |
| certifi | 2026.7.22 → 2026.10.19 | 11 | 11 个插件的项目依赖与独立启动器锁文件 |

GitHub 初始清单覆盖告警编号 1–113、52 个不同标题；Pillow 的 45 个标题和 OpenEXR 的 6 个标题分别同时出现在 `pyproject.toml` 与 `uv.lock`，certifi 的同一问题出现在 11 个插件锁文件中。修复版本也逐项核对了 GitHub 告警页的合并升级建议：[Pillow](https://github.com/popo-studio/bubble-codex-plugin/security/dependabot/112)、[OpenEXR](https://github.com/popo-studio/bubble-codex-plugin/security/dependabot/28)、[certifi](https://github.com/popo-studio/bubble-codex-plugin/security/dependabot/77)。没有忽略或手动关闭告警。

独立扫描使用 pip-audit 2.10.1 的 PyPI 数据源，解析全部 26 份锁文件（13 份项目锁文件、13 份启动器锁文件），包括当前机器未选中的 Python / 平台条件分支。升级前扫描 40 个唯一包版本组合；升级后扫描 39 个，**受影响依赖为 0、跳过依赖为 0**。同名依赖的不同版本分批扫描，避免解析器只选中一个版本而遗漏其他分支。PyPI 与 GitHub 的收录及别名归并不同，不以两者原始告警条数相等作为通过条件。

Pillow 13 已停止支持 Python 3.10，因此序列检查声明 Python ≥3.11，并在两份实际 MCP 清单中明确选择 Python 3.13。uv 为该插件建立独立环境，不更改 Maya、Houdini 或其他宿主的 Python。首次使用可能下载运行时；离线使用需提前缓存。其余插件保持 Python ≥3.10，未进行无关依赖的大范围升级。所有项目与启动器的锁定依赖版本均一致。

## 发布版本与桥接范围

| Codex 包 | 本次版本 | 软件侧版本 |
| --- | --- | --- |
| Maya | 0.3.1 | 0.3.0，未变化 |
| Nuke / Houdini / Max / Unreal / Unity | 0.2.1 | 0.2.0，未变化 |
| Premiere | 0.4.1 | 签名 CEP 0.4.0，未变化 |
| Deadline / Sequence Check / Asset Package | 0.1.1 | 无软件侧桥接 |
| Plugin Doctor | 0.1.7 | 无软件侧桥接 |
| Photoshop / After Effects | 仍为 0.5.0 / 0.3.0 | 已使用修复后的 certifi，本轮未修改 |

PR 签名发行文件、全部软件侧载荷、安装收据规则和会话选择逻辑未改动。包版本与桥接版本分别验证，不能把这次包补丁误判为软件侧更新。本次无需重新安装桥接、重启创作软件或修改用户工程；需刷新市场并重新加载 Codex 插件服务，以退出仍使用旧依赖的进程。

## 回归证据

- 11 个修改包的锁定环境单测：运行 361 项，结果 OK，其中 5 项按环境条件跳过；市场静态检查 4 项通过。
- 11 套实际 MCP stdio 冒烟通过，序列检查报告 Pillow 13.0.0 / OpenEXR 3.4.9。
- 部署启动器端到端流程通过：PNG 缺帧与重复像素；真实 EXR 尺寸、RGB 通道、NaN/Inf 样本、截断文件报错；源图片保持原样；素材包复制/哈希损坏检查；诊断日志脱敏。
- 全部 13 个插件的双版本运行环境与运行中删除包目录测试通过，新旧服务在删除后仍能响应。
- 真实 Codex app-server 安装全部 13 个插件、列出 203 个工具并逐个插件调用只读工具通过。通过正式卸载恢复此前未安装的 11 个插件；已安装的 Maya、PS 保留。
- PR 自动连接集成的 5 阶段通过：真实 Python HTTP broker、受保护发现文件、生产 Node 连接代码、多宿主/多聊天、断线不重放和收据撤销。Adobe DOM 使用测试替身，这不等于 PR 26.x 原生验收。首次运行曾遇到发现记录被 Node 读取时的 Windows 删除共享冲突；未改变生产清理逻辑，复跑通过。

本轮没有重新验收所有创作软件的原生编辑操作：软件侧代码未变，原生验收范围与缺少的新版环境仍以 [VALIDATION.md](VALIDATION.md) 为准。上述“无已知漏洞”仅表示当日所查数据源和锁定 Python 依赖的结果，不涵盖 Adobe、Autodesk、系统软件或未来公布的漏洞。

## 复核方式

实际部署与功能回归入口为 `tests/codex_plugin_smoke.py --install`、`tests/launcher_smoke.py`、`tests/workflow_smoke.py` 和 `tests/premiere_auto_acceptance.py`。EXR 工作流使用序列插件的锁定 Python 3.13 环境执行：

```powershell
uv run --locked --python 3.13 --project plugins/sequence-check python tests/workflow_smoke.py
```

依赖扫描针对每份锁文件中的 registry 包名与版本去重，按包名拆分冲突版本，再逐批执行：

```powershell
uv tool run --from pip-audit==2.10.1 pip-audit --disable-pip --no-deps --strict -r requirements.txt --format json --aliases on --desc on
```

同时核对报告覆盖全部输入包版本、`affected` 与 `skipped` 为空；不能只检查命令退出码。此次原始清单、扫描结果与集成日志保存在本地忽略目录 `.test-runtime/security-audit/` 及 `.test-runtime/security-*.log`。

依赖依据：[Pillow 13 发布说明](https://pillow.readthedocs.io/en/stable/releasenotes/13.0.0.html)、[OpenEXR 3.4.9](https://github.com/AcademySoftwareFoundation/openexr/releases/tag/v3.4.9)、[certifi 2026.10.19](https://github.com/certifi/python-certifi/releases/tag/2026.10.19)、[pip-audit](https://github.com/pypa/pip-audit)。市场更新流程见 [UPDATING.md](UPDATING.md)。
