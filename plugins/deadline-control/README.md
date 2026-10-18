# Bubble Deadline

对接已安装并配置好的 **Deadline 10 Client**，提供任务查询、失败诊断、提交预览和指定任务重试。当前版本 0.1.0。

## 安装与使用

在 Bubble 市场安装；需要 `uv`、Python 3.10+ 和 Deadline 10 Client。自动搜索 `BUBBLE_DEADLINE_COMMAND`、`DEADLINE_PATH`、PATH 与常见安装目录。也可通过工具的 `command` 参数指定绝对 `deadlinecommand.exe` 路径。不安装 Deadline，不改 Repository 配置，不需要重启 Maya 等软件。

示例：“检查 Deadline 连接”“列出我的失败任务”“分析这个 Job ID 的错误报告”“先预览这两个 job 文件的提交”。

| 工具 | 作用 |
| --- | --- |
| deadline_status | 检测客户端，可选读取版本；不等同于农场连接成功 |
| deadline_list_jobs | AND 组合状态/用户筛选，显式报告截断 |
| deadline_job_info | 精确 Job ID 的信息 |
| deadline_job_tasks | Task ID、帧范围、状态和进度 |
| deadline_job_reports | 有界读取日志/错误报告，支持 bz2，标记不可读项 |
| deadline_submit_job | 已存在的 JobInfo/PluginInfo/辅助文件的预览与一次确认提交 |
| deadline_retry_tasks | Failed 任务恢复或 Completed 任务重新排队，精确选择并确认 |

提交和重试均默认只预览，需一次性、10 分钟有效的 preview_token 和 confirmed=true；文件或任务状态改变后需重新预览。令牌绑定路径、内容哈希、设置、CLI 路径和选定任务。每次写操作只尝试一次；超时/不明结果不自动重试，防止重复提交。JobInfo/PluginInfo 只检查结构，不替代软件专用提交规则；不承诺节点能访问场景/素材或许可证可用。任务 ID 不是帧号。命令使用参数数组且 shell=false。

默认查询 30 秒超时，提交 60 秒；每个输出流最多 1 MiB，报告最多 10 个、每个解码后最多 64 KiB。最多 32 个辅助文件，每个最多 128 MiB；超过此范围请通过 Deadline 原生提交器完成。报告中的错误行仅为线索。命令输出采用 UTF-8 解码，非 UTF-8 的少数字符可能替换显示。大型农场请缩小筛选条件，插件不会将截断结果说成完整检查。

更新：刷新市场后更新插件，版本号与版本化 uv 启动器保持一致。卸载：直接通过 Codex 卸载，不删除 Deadline、不修改现有任务；仅临时提交文件自动清理，预览令牌随服务退出消失。插件外部 uv 缓存由 uv 管理。

## 验证

`python -m unittest discover -s plugins/deadline-control/tests -p "test_*.py" -v`：参数保真、进程超时/输出上限、CLI 错误、预览不执行、内容变化拒绝、一次令牌、选定任务状态检查、报告解压上限。

`python plugins/deadline-control/tests/stdio_smoke.py`：真实 MCP stdio 初始化/工具发现/无客户端与无效 ID 返回；不提交或重试真实任务。Windows sandbox 内请将 TEMP/TMP 指向工作区测试目录。

## 接口依据

- [Deadline Jobs CLI](https://docs.thinkboxsoftware.com/products/deadline/latest/1_User%20Manual/manual/command-line-arguments-jobs.html)
- [Deadline Tasks CLI](https://docs.thinkboxsoftware.com/products/deadline/latest/1_User%20Manual/manual/command-line-arguments-tasks.html)
- [Manual Job Submission](https://docs.thinkboxsoftware.com/products/deadline/latest/1_User%20Manual/manual/manual-submission.html)
- [Version CLI](https://docs.thinkboxsoftware.com/products/deadline/latest/1_User%20Manual/manual/command-line-arguments-version.html)

本插件针对已有 Deadline 10 环境，不是 AWS Deadline Cloud 集成。图标为 Bubble 原创队列图案。
