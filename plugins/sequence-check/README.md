# Bubble Sequence Check 0.2.0

本地图像序列检查，使用真实解码器读取像素，不修改素材。通过现有 Bubble 插件市场安装；需要 `uv` 与 Python >=3.11，首次启动自动安装锁定依赖，无需软件侧桥接。

工具：`sequence_status` 检查运行环境；`sequence_discover` 在一个明确目录内分组；`sequence_inspect` 检查缺帧、重复帧号、损坏文件、尺寸/通道变化、非有限像素、疑似黑帧与完全相同像素。传入绝对目录和文件名 glob（例如 `shot.*.exr`）；不递归。帧号采用扩展名前最后一组数字；负帧号须显式设置 signed_frames=true，因为连字符也可能只是文件名分隔符。

0.2.0 新增 frame_step（须给出对齐的首尾帧）、expected_width/expected_height 和 required_channels。尺寸要求用于每个成功解码部件，通道要求用于部件并集；不支持或损坏的帧仍标记未验证/错误。`sequence_write_report` 预览并写入新建 JSON/CSV 报告，最大 8 MiB；需用户授权具体路径，绝不覆盖已有报告或修改素材。CSV 会中和公式样式文本；报告成功写入不代表质检通过。

必须给出期望首尾帧才能确认两端是否缺帧。没有匹配文件、超限或不支持的文件都不能视作通过。黑帧和重复像素只是线索，静帧或淡出可能完全正常。多组结果分别比较布局；布局基准为组内首个成功解码文件。

支持 PNG/JPEG/TIFF/BMP、平面单部件/多部件 EXR。EXR 先读取头信息再估计内存；deep EXR 不解码，tiled EXR 仅检查解码器提供的基础层级，多页/动画图片标记未验证。没有色彩管理或美术判断，不输出视频。扫描边界：10000 目录条目、1000 匹配文件、10001 帧跨度；每图/EXR 部件最多 16777216 像素；单文件 512 MiB、估计像素数据 256 MiB。解码器和分析可能有额外内存开销，这不是进程内存硬配额；请仅检查可信制作素材。

依赖：Pillow 13.0.0、OpenEXR 3.4.9、NumPy 2.2.6、certifi 2026.10.19、MCP 1.x（全部传递依赖锁定于版本启动脚本锁文件）。启动遵循现有插件规范：不设置 manifest cwd，uv 立即移出插件目录，版本化 PEP 723 环境位于外部缓存，禁止写入包内字节码，方便 Windows 卸载/更新。通过 Codex 正常更新或卸载；不安装常驻服务或软件启动脚本。

图标是本仓库原创 SVG，不使用第三方商标。API 依据 [OpenEXR Python 文档](https://openexr.com/en/latest/python.html) 与 [Pillow Image 文档](https://pillow.readthedocs.io/en/stable/reference/Image.html)。

测试：`uv run --locked --python 3.13 --project plugins/sequence-check python -m unittest discover -s plugins/sequence-check/tests -v`（开发测试环境与发布启动环境分离）；`tests/smoke.py` 验证真实 stdio 工具发现和状态调用。原始测试样本在临时目录生成，不扫描用户素材。

## Runtime security patch 0.1.1

The Codex package updates Pillow to 13.0.0, OpenEXR to 3.4.9 and certifi to 2026.10.19. Pillow requires Python >=3.11; the deployed launcher selects uv-managed Python 3.13 to use tested Windows decoder wheels. No Adobe/DCC application environment is modified. Reload the Codex plugin to start the patched runtime.
