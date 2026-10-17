# Bubble Codex Plugins

自己的 Codex 插件市场，一个 Git 仓库维护多个插件。首个插件 **Bubble Maya** 面向 **Maya 2027**，提供本地脚本执行和场景检查。

```text
.agents/plugins/marketplace.json    市场目录
plugins/
  maya-control/
    plugin.json                   通用插件清单
    .codex-plugin/plugin.json     Codex 兼容清单
    mcp.json / .mcp.json          本地 MCP 配置
    skills/                       工作流与连接指导
    server/                       Codex 侧 MCP 服务
    maya/                         Maya 内桥接脚本
    tests/                        自动化测试
```

## 先在本机使用

在 Codex 的「添加插件市场」窗口中填写：

| 字段 | 内容 |
| --- | --- |
| 来源 | 当前仓库的绝对路径，例如 `D:\Workspace\Bubble\bubble-codex-plugins` |
| Git 引用 | 留空 |
| 稀疏路径 | 留空 |

添加后安装 **Bubble Maya**，运行其初始设置。Codex 会先展示 Maya 安装位置，获得同意后安装桥接插件；保存场景并重启 Maya 后自动连接。不想重启时可以选择复制一次加载代码。连接步骤见 [Maya 插件说明](plugins/maya-control/README.md)。CLI 等价操作：

```powershell
codex plugin marketplace add 'D:\Workspace\Bubble\bubble-codex-plugins'
codex plugin add maya-control@bubble-plugins
```

## 从 GitHub 添加

代码推送到 GitHub 后，在相同窗口填写：

| 字段 | 内容 |
| --- | --- |
| 来源 | `git@github.com:popo-studio/bubble-codex-plugin.git` |
| Git 引用 | `main` |
| 稀疏路径 | 留空 |

不要照抄截图里的 `plugins/codex`，那只是示例。这个仓库需要同时包含根目录的市场清单和 `plugins/` 下的插件。私有仓库需要本机 Git 有访问权限。

```powershell
codex plugin marketplace add git@github.com:popo-studio/bubble-codex-plugin.git --ref main
codex plugin add maya-control@bubble-plugins
```

更新源码时同时提高插件的两个清单及 Python 项目中的版本号，更新锁文件后提交并推送；然后刷新市场、更新插件并重新加载对应聊天。运行初始设置预览并确认 Maya 端更新，再重启 Maya。卸载 Codex 插件前，可先运行 Maya 桥接卸载流程，撤销自动启动。

## 增加其他插件

在 `plugins/<新插件名>/` 创建独立的清单、技能和服务，再在 `.agents/plugins/marketplace.json` 的 `plugins` 数组新增一项，`source.path` 指向 `./plugins/<新插件名>`。保持每个插件自包含，避免引用兄弟插件的文件，以便缓存安装后仍然可用。

本仓库用于 Git 插件市场分发，不需要先上传到 ChatGPT 的公开插件目录。

## 开发与验证

```powershell
uv run --directory plugins/maya-control python -m unittest discover -s tests -v
```

验证范围及 Maya 真实环境测试见插件说明。不要提交虚拟环境、用户场景、会话令牌或 Maya 用户配置。

格式依据：[OpenAI 插件打包与市场文档](https://developers.openai.com/plugins/build/plugins)。
