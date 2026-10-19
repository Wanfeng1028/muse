# HyperFrames CLI 真实联调实验报告

- 报告日期：2026-10-20
- 实验环境：Ubuntu VM（本机实测）
- 实验对象：hyperframes@0.8.176
- 报告人：drama-factory 运维工程师

## 环境

| 项目 | 值 |
| --- | --- |
| Node.js | v24.20.0 |
| npm | 10.9.4 |
| 操作系统 | Ubuntu VM |
| hyperframes | 0.8.176 |

安装记录：

- `npm view hyperframes` 确认 `hyperframes@0.8.176` 存在。
- `npm install` 本地安装共拉取 77 个包，耗时约 2 分钟。
- `hyperframes --version` 输出 `0.8.176`，退出码 0。

`hyperframes render --help` 核验到的真实 flag：

| flag | 说明 |
| --- | --- |
| `-c` / `--composition` | 指定 composition 入口 |
| `-o` / `--output` | 指定输出文件 |
| `-f` / `--fps` | 指定帧率 |
| `-w` / `--workers` | worker 数量，默认 auto，每个 worker 约 256MB RAM |
| `--resolution` | 分辨率预设，含 1080p 别名（landscape 1920x1080 等预设） |
| `--no-browser-gpu` | 强制软件渲染 SwiftShader |
| `--docker` | 容器内运行 |
| `--hdr` / `--sdr` | HDR / SDR 输出选择 |
| `--crf` | 编码质量参数 |

## 探活结论

使用 `scripts/hyperframes_probe.sh` 实测两种分支。

CLI 缺失时（退出码 0，降级为 chromium 引擎）：

```json
{"node":{"ok":true,"version":"v24.20.0"},"npm":{"ok":true,"version":"10.9.4"},"hyperframes":{"ok":false,"cli":"hyperframes","version":""},"engine":"chromium","note":"hyperframes 不可用（未找到 CLI: hyperframes），降级为 chromium 引擎。"}
```

CLI 存在时（`HYPERFRAMES_CLI` 指向本地安装）：

- `hyperframes.ok=true`
- `version=0.8.176`
- `engine=hyperframes`

结论：探活脚本在 CLI 缺失与 CLI 存在两种情况下均能正确判定，并在缺失时安全降级到 chromium 引擎。

## 真实渲染

真实渲染命令（命令形如代码生成）：

```
hyperframes render -c index.html -o out/video.mp4 --resolution 1080p --fps 24 -w 1 --no-browser-gpu
```

渲染对象：2 秒静态 composition。

实测结果：

| 项目 | 值 |
| --- | --- |
| 渲染耗时 | 1 分 39.5 秒 |
| 产出文件 | out/video.mp4 |
| 产出大小 | 16.2KB |
| ffprobe 确认时长 | 2.000000 秒 |

说明：本次仅实测 `--resolution 1080p` 与 `--fps 24` 组合，未测试 4K、HDR 等其他分辨率或输出模式。

## 实测坑位记录

1. composition 必须能被推断时长
   - 静态页面需在根 div 加 `data-duration="2"`，否则报 `Composition has zero duration`。

2. 45 秒 timeline 就绪等待
   - 无动画的静态 composition 会触发 `sub_timeline_readiness_timeout` 警告，但不影响产出。

3. 磁盘空间
   - `/tmp` 剩余 0.5GB 时 CLI 报 `Low disk space` 警告；可用 `TMPDIR` 指向工作区目录绕过。

## 与代码实现的对应

`HtmlRenderVideoProvider` 的 hyperframes 分支拼装的命令为：

```
[cli, "render", "-c", "composition.html", "-o", "out/video.mp4", "--resolution", "1080p", "--fps", "<fps>", "--no-browser-gpu"]
```

对照 `hyperframes render --help` 逐项核验：

| 代码参数 | 核验结果 |
| --- | --- |
| `render` | 合法子命令 |
| `-c` | 合法，等价 `--composition` |
| `-o` | 合法，等价 `--output` |
| `--resolution 1080p` | 合法，1080p 为预设别名 |
| `--fps <fps>` | 合法，等价 `-f` |
| `--no-browser-gpu` | 合法 |

注意：代码未传 `-w`，即使用 CLI 默认 `auto`。本次真实渲染实验为隔离变量显式使用了 `-w 1`，与线上代码默认行为不同，需在容量评估时考虑 `auto` 可能带来的多 worker 内存占用（每个 worker 约 256MB RAM）。

## 运维建议

1. 生产环境建议 `npm i -g hyperframes` 或直接打包进镜像，避免运行时临时安装（本地安装 77 个包约 2 分钟，会显著拉长首次任务耗时）。
2. 无 GPU 机器务必配置 `--no-browser-gpu`，强制软件渲染 SwiftShader，避免因 GPU 缺失导致的渲染失败。
3. `/tmp` 空间要求：`/tmp` 剩余 0.5GB 时会触发 `Low disk space` 警告，建议为渲染任务预留充足磁盘，或通过 `TMPDIR` 指向工作区目录绕过。
4. `engine=chromium` 为安全默认：CLI 缺失时探活脚本会降级为 chromium 引擎，保证渲染链路不中断，建议保留该降级行为。
5. worker 内存评估：CLI 默认 `-w auto`，每个 worker 约 256MB RAM，容量规划需按 `auto` 可能派生的 worker 数量预留内存。
