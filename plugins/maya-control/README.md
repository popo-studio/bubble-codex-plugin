# Bubble Maya

面向 Maya 2027 的本地 Codex 插件。通过 MCP 控制已打开的 Maya，执行 Python/MEL，检查当前场景中的引用与贴图路径。

```text
Codex → stdio MCP 服务（独立 Python）
      → 127.0.0.1 + 会话令牌
      → Maya 内桥接脚本 → Maya 主线程
```

## 准备

- Maya 2027 图形界面版本。
- 系统安装独立的 Python 3.10+ 和 [uv](https://docs.astral.sh/uv/getting-started/installation/)，并让启动 Codex 的环境能找到 `uv`。不要把 `mayapy.exe` 当作 MCP 虚拟环境的基础解释器。
- 安装本仓库的 Bubble Maya 插件。首次运行服务时，uv 下载依赖，需要网络；依赖只进入插件独立环境，不进入 Maya。

## 启动 Maya 桥接

在 Maya 的 **Script Editor → Python** 中执行。下面路径对应此仓库；如果安装在其他位置，改为实际插件目录下的 `maya` 文件夹：

```python
import sys
bridge_path = r"D:\Workspace\Bubble\bubble-codex-plugins\plugins\maya-control\maya"
if bridge_path not in sys.path:
    sys.path.insert(0, bridge_path)
import bubble_maya_bridge
bubble_maya_bridge.start()
```

可以将这段代码选中后拖到 Maya Shelf，方便每次打开 Maya 后连接。桥接启动是当前 Maya 进程内的操作，不会修改 `userSetup.py`。

关闭桥接：

```python
bubble_maya_bridge.stop()
```

更新桥接源码后，在 Maya 中先停止再重新加载：

```python
import importlib
bubble_maya_bridge.stop()
importlib.reload(bubble_maya_bridge)
bubble_maya_bridge.start()
```

## 使用

在启用该插件的 Codex 聊天里说：

- “连接 Maya 2027，告诉我当前打开的场景和选中对象。”
- “检查当前场景是否有缺失贴图、丢失引用或未知节点，只报告问题。”
- “在 Maya 中创建一个名为 test_cube 的立方体，返回它的名称，不保存场景。”

| 工具 | 用途 |
| --- | --- |
| `maya_list_sessions` | 发现本机桥接会话 |
| `maya_status` | 验证连接、Maya 版本与进程 |
| `maya_scene_info` | 当前场景、选择和基础信息 |
| `maya_inspect_scene` | 只读场景资源检查 |
| `maya_execute_python` | 执行 Python，返回输出及 `result` 变量 |
| `maya_execute_mel` | 执行 MEL 并返回结果 |

多开 Maya 时通过 `pid` 指定目标，避免修改错误的场景。Python 示例：

```python
import maya.cmds as cmds
result = {"selection": cmds.ls(selection=True, long=True)}
```

## 范围与限制

- 检查当前已打开场景，不自动打开其他文件，不自动保存或修复。
- 第一版侧重文件贴图节点、引用和未知节点。UDIM/序列文件匹配只判断是否有匹配文件，不验证整个分块集或帧范围完整性；第三方渲染器节点和未加载引用内部资源可能需要专项检查。
- 检查结果基于当前机器可访问的文件系统；网络盘离线也会影响结果。
- Python/MEL 拥有 Maya 进程的完整权限。令牌用于限制桥接访问，不会把脚本变成沙箱。使用自己的可信脚本。
- 桥接仅监听 `127.0.0.1`，随机令牌保存在用户本地 `~/.bubble-maya/sessions/`，不会放入仓库或工具列表。Windows 依赖用户目录自身的访问控制。
- Maya 忙碌、模态对话框或长脚本可能导致超时。已开始执行的脚本无法安全强制中断；超时后先检查场景状态，不要自动重试。
- Maya 2027 是本次目标；其他 Python 3 Maya 版本尚未作兼容性验收，Maya 2020/Python 2 不支持。

## 排错

| 现象 | 处理 |
| --- | --- |
| Codex 找不到 `uv` | 在终端执行 `uv --version`；安装或修正 PATH 后重启 Codex |
| 没有会话 | 在目标 Maya 的 Python 页签执行启动代码 |
| 出现多个会话 | 根据 PID、版本和场景选择目标 |
| 连接失败 | 确认 Maya 仍运行，停止并重启桥接，再查询状态 |
| 超时 | 关闭 Maya 模态对话框，等待主线程空闲；检查操作是否已完成 |
| 插件安装后工具未出现 | 重新加载或新开一个启用该插件的聊天 |

## 开发验证

从仓库根目录运行：

```powershell
uv run --directory plugins/maya-control python -m unittest discover -s tests -v
uv run --directory plugins/maya-control python tests/stdio_smoke.py
& 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' plugins/maya-control/tests/mayapy_smoke.py
```

`uv.lock` 固定依赖版本，插件启动使用 `uv run --locked`。`mayapy_smoke.py` 在独立进程和临时场景中测试真实 Maya API，不依赖 GUI，也不会打开现有用户场景。

2026-10-17 验证记录：16 项回归测试通过；6 个工具的 MCP stdio → 模拟桥接通信通过；Maya 2027 standalone 下的引用、UDIM、缺失贴图、Python/MEL、选择及场景修改状态保持测试通过。插件清单、兼容配置与技能 YAML 检查通过。

尚未完成 Codex 实际安装和 Maya GUI 内的连接验收。自动化测试不能替代这两项。上线前在一个空白测试场景中完成：连接 → 读取场景 → 创建测试立方体 → 读取确认 → 手动撤销/清理 → 停止桥接。不要用生产场景测试任意脚本。

相关官方文档：[Maya 2027 线程与 Python](https://help.autodesk.com/cloudhelp/2027/ENU/Maya-Scripting/files/GUID-9B5AECBB-B212-4C92-959A-22599760E91A.htm)、[MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)。
