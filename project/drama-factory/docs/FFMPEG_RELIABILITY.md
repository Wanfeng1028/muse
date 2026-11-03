# ffmpeg 可靠性设计注记（v2.29）

v2.11 起 `DramaV2ApiIntegrationTest.testFullPipeline` 反复 flaky，v2.29 定位根因并落地修复，目标是把这个测试里的 ffmpeg 抖动问题按下去，让全量套件能稳定跑完。

## 根因回顾

两种 flaky 模式：

- **final-cuts 偶发 500**：final-cuts 接口在 ffmpeg 调用失败时直接把异常抛出去，返回 500。
- **60s 轮询超时**：异步任务在 ffmpeg 失败后没有快速标记 FAILED，一直在重试里空转，轮询端等不到终态就超时。

同源根因：**ffmpeg 瞬时失败（全量套件满负载下 OOM-kill / 抖动，libx264 720p 编码是测试里最重的外部进程调用）叠加三处生产代码缺口——失败分类缺失、final-cuts 没有重试、视频任务对永久失败也空转重试**。

## 瞬时/永久分类表

`FfmpegService.FfmpegException` 增加 `transientFailure` 分类和 `isTransient()` 方法。分类依据如下：

| 场景 | 分类 | 说明 |
| --- | --- | --- |
| 命令超时 | 瞬时 (true) | 进程还在跑但超时，可重试 |
| 等待被中断 | 瞬时 (true) | 等待期间线程被中断，可重试 |
| 非零退出码（含 137/143 信号杀死） | 瞬时 (true) | 被信号杀死、OOM-kill 等，可重试 |
| 输出目录创建失败 | 瞬时 (true) | 可能受当时文件系统/权限抖动影响 |
| concat 列表写入失败 | 瞬时 (true) | IO 抖动，可重试 |
| 字幕复制失败 | 瞬时 (true) | IO 抖动，可重试 |
| ffprobe 读取失败 | 瞬时 (true) | 可重试 |
| ffprobe 超时 | 瞬时 (true) | 可重试 |
| ffprobe 执行失败 | 瞬时 (true) | 可重试 |
| ffprobe 无输出 | 瞬时 (true) | 可重试 |
| ffprobe 解析失败 | 瞬时 (true) | 可重试 |
| 无法启动进程（`无法启动命令` / `无法启动 ffprobe`，如二进制缺失） | 永久 (false) | 重试也没用，直接失败 |
| 参数编程错误（拼接列表为空、输出缺父目录） | 永久 (false) | 代码问题，重试也没用 |

旧的双参构造器默认 `transient=true`（保守策略，用有界重试兜底）。具体到每个抛出点的判定以代码为准。

## 重试矩阵

| 调用方 | 触发条件 | 重试策略 | 耗尽后行为 | 指标 |
| --- | --- | --- | --- | --- |
| FinalCutService（concat / burn-subtitles / probe-duration 三步） | 瞬时失败 | 最多 3 次，退避 2000ms × attempt（即 2s、4s） | 标记 FAILED | `dramafactory_ffmpeg_retries_total{operation,kind,result}` |
| FinalCutService（同上三步） | 永久失败 | 不重试 | 直接 FAILED | 同上 |
| VideoTaskService 下载/生成 | 瞬时失败 | 现有 8 次指数退避（10s / 20s / 40s…封顶 10min） | 标记 FAILED | 现有指标 |
| VideoTaskService 下载/生成 | 非瞬时 `FfmpegException` | 不重试 | 直接 FAILED，日志带 `[永久失败，不再重试]` | 现有指标 |
| processDueTasks | 重叠调用 | 单飞保护，直接跳过 | 本次调用直接返回 | `dramafactory_video_poll_skipped_total` |

补充：`FfmpegService.run()` 执行超过 30 秒会打 warn 日志，便于排查慢命令。final-cuts 每次尝试都会打 `dramafactory_ffmpeg_retries_total`，标签 `operation` 区分步骤、`kind` 区分瞬时/永久、`result` 区分重试/成功/耗尽。

## 配置项

| 配置键 | 环境变量 | 默认 | 说明 |
| --- | --- | --- | --- |
| `drama.ffmpeg.retry-attempts` | `FFMPEG_RETRY_ATTEMPTS` | 3 | FinalCutService 三步对瞬时失败的最大尝试次数 |
| `drama.ffmpeg.retry-backoff-ms` | `FFMPEG_RETRY_BACKOFF_MS` | 2000 | 退避基数，实际等待为基数 × attempt |
| `drama.ffmpeg.retry-total-budget-ms` | `FFMPEG_RETRY_TOTAL_BUDGET_MS` | 20000 | 单次成片构建内所有 ffmpeg 步骤共享的退避预算，总睡眠不超过该值；耗尽后仍尝试剩余次数但不再睡眠 |

## 运维排障

- **exit 137 / 143**：进程被信号杀死（137 = SIGKILL，通常 OOM-kill；143 = SIGTERM）。这是瞬时失败，会走重试。如果频繁出现，说明机器内存紧张或并发太高，加内存或降并发。
- **命令超时**：查慢命令 warn 日志（`FfmpegService.run()` 超 30 秒会打 warn），看是哪些命令慢，判断是输入太大还是机器负载高。
- **无法启动命令**：报 `无法启动命令` / `无法启动 ffprobe`，属于永久失败，不会重试。检查机器上装了 ffmpeg / ffprobe 没有，或者设置 `FFMPEG_PATH` 指向正确路径。
- **重试次数突增**：看 `dramafactory_ffmpeg_retries_total`，按 `operation` / `kind` / `result` 拆开看。同时查当时的机器负载，确认是不是又到了满负载抖动。

## Prometheus 告警示例

```yaml
groups:
  - name: ffmpeg-reliability
    rules:
      # final-cut 构建失败率：5 分钟内失败占比超过 20% 告警
      - alert: FinalCutBuildFailureRateHigh
        expr: |
          sum(rate(dramafactory_ffmpeg_retries_total{operation="finalcut",result="exhausted"}[5m]))
          /
          sum(rate(dramafactory_ffmpeg_retries_total{operation="finalcut"}[5m]))
          > 0.2
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "final-cut 构建失败率偏高"
          description: "final-cut 步骤重试耗尽比例超过 20%，检查 ffmpeg 负载与内存。"

      # ffmpeg 瞬时重试突增：5 分钟内瞬时重试速率超过 1/s
      - alert: FfmpegTransientRetrySpike
        expr: |
          sum(rate(dramafactory_ffmpeg_retries_total{kind="transient",result="retry"}[5m])) > 1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "ffmpeg 瞬时重试突增"
          description: "瞬时重试速率超过 1/s，机器可能 OOM 抖动，检查负载与内存。"
```

## 故障演练

演练脚本见 `scripts/ffmpeg-chaos-drill.sh`，通过注入 ffmpeg 瞬时失败（如超时、非零退出码）验证重试、单飞保护和指标是否按预期生效。

## 已知限制

- **重试解决不了 ffmpeg 二进制缺失**：`无法启动命令` / `无法启动 ffprobe` 属于永久失败，直接 FAILED，不会重试，需要运维把二进制装好或设对 `FFMPEG_PATH`。
- **单飞保护只防同 JVM 重叠**：`processDueTasks` 的单飞保护在当前单实例部署下有效，只能防同一 JVM 内的重叠调用；多实例部署时跨 JVM 的重叠需要靠外部锁或其他机制，本版本未覆盖。
- 重试策略的具体判定点和异常归类细节，以代码为准。
