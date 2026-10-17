# v2.31 flaky 收尾：退避预算上限 + 启动异常精细分类发版对照报告

## 里程碑概述

本轮 v2.31（2026-10-17）关闭 v2.29 C6 发现的两处结构性残留：

1. `FinalCutService.withFfmpegRetry` 的退避总额无预算上限。单次成片构建内多个 ffmpeg 步骤各自重试时，退避睡眠可能累积放大，缺少一个全局约束。本轮为其加单次构建共享退避预算：`drama.ffmpeg.retry-total-budget-ms`（`FFMPEG_RETRY_TOTAL_BUDGET_MS`，默认 20000ms），由包可见静态方法 `claimRetryBackoff` 认领睡眠；预算耗尽后仍尝试剩余次数但不再睡眠；构造器改为 13 参 `@Autowired`，并保留 12 参委托构造器（默认 20000L），既有测试零改动。
2. `FfmpegService` 对 `pb.start()` 抛出的 `IOException` 一律标为永久失败。本轮引入 `isTransientLaunchFailure` 正向识别，把 cannot allocate memory / too many open files / resource temporarily unavailable 判为瞬时，其余保持永久。

诚实根因报告见 `docs/FLAKY_ROOT_CAUSE.md`。

## 交付清单

| 批次 | 内容 | 结果 |
| --- | --- | --- |
| B1 | 生产 PATCH：`FinalCutService` 退避预算上限 | 完成 |
| B2 | 生产 PATCH：`FfmpegService.isTransientLaunchFailure` | 完成 |
| B3 | 新测试：`FinalCutRetryBudgetV231Test`（7 例） | 完成 |
| B4 | 新测试：`FfmpegLaunchClassifyV231Test`（10 例） | 完成 |
| B5 | 新文档：`docs/FLAKY_ROOT_CAUSE.md` | 完成 |
| B6 | 收尾文档批（本批：对照报告 + CHANGELOG + 根因报告回填 + 配置文档同步） | 完成 |
| B4-FIX1 | 回喂：修 `Method.invoke` 把异常包进 `InvocationTargetException` 的 bug | 1 轮修好 |

## 验证

- 新测试：17/17 全绿（`FinalCutRetryBudgetV231Test` 7 例 + `FfmpegLaunchClassifyV231Test` 10 例）。
- 既有相关 8 类（`FinalCutServiceTest`、`FinalCutFfmpegRetryTest`、`FinalCutRealFfmpegRetryTest`、`FfmpegServiceTest`、`FfmpegExceptionClassificationTest`、`VideoTaskFailFastTest`、`ProcessDueTasksSingleFlightTest`、`FfmpegRetryMetricsTest`）：38/38 全绿，无回归。
- `testFullPipeline`：修复前基线 2/2 通过（163.1s、167.0s，flaky 未复现）；修复后 10/10 通过（耗时 161.8s~320.5s；VM 高负载下依然全绿）。
- 全量 `mvn -o verify`：2013 例，14 失败 + 11 错误，8 skipped；JaCoCo BRANCH 83.94%（门禁 0.94，红）、LINE 86.41%（门禁 0.92，红）；missed branches 的 70.9%（458/646）来自他人在途新代码（NovAI 105、CanvasProjectService 71、Doubao 64、ShotVideoRouter 58、Painted 56、HtmlRender 45、Qwen 36、CanvasMigration 23）；失败/错误全部集中在 Qwen 相关 6 个测试类（QwenProbeTest 1F、QwenVideoProviderBranch2Test 10F+7E、QwenVideoProviderBranch3Test 2F+2E、QwenVideoProviderSubmitPollRecordingTest 2E、VideoProviderRouterTest 1F），与 v2.29 基线完全一致，系另一轮次 qwen 紧急摘除未同步测试所致，本轮按铁律不碰。

## PRODUCTION_CHECKLIST.md 逐条对照

本轮相关条目：

- 1.1 测试金字塔：通过（新测试 17 例 + 既有相关 8 类 38/38 无回归）。
- 6.2 CHANGELOG：通过（Unreleased 首条插入 v2.31）。
- 6.3 技术债有记录：通过（`docs/FLAKY_ROOT_CAUSE.md` §9）。
- 6.4 代码与文档同步：通过（`application.yml` 与配置文档同步）。

## 诚实声明

- 门禁：全量 `mvn -o verify` 的 JaCoCo BRANCH 83.94%、LINE 86.41% 均低于门禁（0.94 / 0.92），为红。missed branches 的 70.9%（458/646）来自他人在途新代码（NovAI 105、CanvasProjectService 71、Doubao 64、ShotVideoRouter 58、Painted 56、HtmlRender 45、Qwen 36、CanvasMigration 23）。本轮未处理这部分，如实记录。
- Qwen：14 失败 + 11 错误全部集中在 Qwen 相关 6 个测试类，与 v2.29 基线完全一致，系另一轮次 qwen 紧急摘除未同步测试所致，非本轮引入。本轮按铁律不碰。
- 概率性：`testFullPipeline` 属概率性用例。修复前基线 2/2 通过、flaky 未复现，说明其为低概率残留；修复后 10/10 通过，是在当前样本量下的观测结果，不能据此推断概率性已彻底消除。

## 生成方式说明

本轮由 6 批 dpsk 完成：B1 生产 PATCH（`FinalCutService`）、B2 生产 PATCH（`FfmpegService`）、B3 新测试 `FinalCutRetryBudgetV231Test`（7 例）、B4 新测试 `FfmpegLaunchClassifyV231Test`（10 例）、B5 新文档 `docs/FLAKY_ROOT_CAUSE.md`、B6 收尾文档批（本批）；另有 B4-FIX1 回喂 1 轮，修 `Method.invoke` 把异常包进 `InvocationTargetException` 的 bug。

编排者承担机械性工作：PATCH 应用、构建验证、10x 重跑、基线对照。

=== END ===
=== PATCH: CHANGELOG.md ===
--- OLD
## [Unreleased]

### Added

- v2.30「OpenAPI 接口分组 + 依赖治理」（DoD 第 4 轮排期）：
--- NEW
## [Unreleased]

### Added

- v2.31「flaky 收尾：退避预算上限 + 启动异常精细分类」（2026-10-17，dod-v2.28 排期"flaky 残留 2 处代码漏洞"全交付）：
  - `FinalCutService`：单次成片构建内所有 ffmpeg 步骤共享退避预算，
    `drama.ffmpeg.retry-total-budget-ms`（`FFMPEG_RETRY_TOTAL_BUDGET_MS`，默认 20000ms）；
    `claimRetryBackoff(AtomicLong, long)` 认领睡眠；预算耗尽后仍尝试剩余次数但不再睡眠；
    13 参 `@Autowired` 构造器 + 保留 12 参委托构造器（默认 20000L），既有测试零改动。
  - `FfmpegService.isTransientLaunchFailure(IOException)`：正向识别 cannot allocate memory /
    too many open files / resource temporarily unavailable 为瞬时，其余保持永久（v2.29 行为）。
  - 测试 17 例：`FinalCutRetryBudgetV231Test` 7 例 + `FfmpegLaunchClassifyV231Test` 10 例（含真实缺失二进制端到端）。
  - 文档：新增 `docs/FLAKY_ROOT_CAUSE.md`（诚实根因报告）；`docs/dod-v2.31.md` 为发版对照；
    `application.yml` + `docs/FFMPEG_RELIABILITY.md` + `docs/OPERATIONS.md` 同步新配置键。
  - 验证：新测试 17/17；既有相关 8 类 38/38 无回归；testFullPipeline 基线 2/2 → 修复后 10/10 通过（耗时 161.8s~320.5s；VM 高负载下依然全绿）；
    全量 verify 2013 例，14 失败 + 11 错误，8 skipped，JaCoCo BRANCH 83.94%（门禁 0.94，红）、LINE 86.41%（门禁 0.92，红）；missed branches 的 70.9%（458/646）来自他人在途新代码（NovAI 105、CanvasProjectService 71、Doubao 64、ShotVideoRouter 58、Painted 56、HtmlRender 45、Qwen 36、CanvasMigration 23）。
- 发版对照报告：`docs/dod-v2.31.md`。

- v2.30「OpenAPI 接口分组 + 依赖治理」（DoD 第 4 轮排期）：
=== END ===
=== PATCH: docs/FLAKY_ROOT_CAUSE.md ===
--- OLD
## 8. v2.31 验证数据

```
（待编排者回填：基线 10 次重跑通过率 / 修复后 10 次重跑通过率 / 全量 mvn verify 结果）
```
--- NEW
## 8. v2.31 验证数据

- 基线（修复前代码）：testFullPipeline 连续 2 次通过（163.1s、167.0s），flaky 未复现（与 v2.29"低概率残留"一致）。
- 修复后：testFullPipeline 连续 10/10 通过（耗时 161.8s~320.5s；VM 高负载下依然全绿）。
- 新测试 17/17 全绿（FinalCutRetryBudgetV231Test 7、FfmpegLaunchClassifyV231Test 10）；既有相关 8 类 38/38 全绿，无回归。
- 全量 `mvn -o verify`：2013 例，14 失败 + 11 错误，8 skipped；JaCoCo BRANCH 83.94%（门禁 0.94，红）、LINE 86.41%（门禁 0.92，红）；missed branches 的 70.9%（458/646）来自他人在途新代码（NovAI 105、CanvasProjectService 71、Doubao 64、ShotVideoRouter 58、Painted 56、HtmlRender 45、Qwen 36、CanvasMigration 23）；失败/错误全部集中在 Qwen 相关 6 个测试类（QwenProbeTest 1F、QwenVideoProviderBranch2Test 10F+7E、QwenVideoProviderBranch3Test 2F+2E、QwenVideoProviderSubmitPollRecordingTest 2E、VideoProviderRouterTest 1F），与 v2.29 基线完全一致，系另一轮次 qwen 紧急摘除未同步测试所致，本轮按铁律不碰。
=== END ===
=== PATCH: src/main/resources/application.yml ===
--- OLD
  # v2.29 flaky 根因歼灭：ffmpeg 单步瞬时失败有界重试（成片构建 concat/burn-subtitles/probe）
  ffmpeg-retry-attempts: ${FFMPEG_RETRY_ATTEMPTS:3}
  ffmpeg-retry-backoff-ms: ${FFMPEG_RETRY_BACKOFF_MS:2000}
--- NEW
  # v2.29 flaky 根因歼灭：ffmpeg 单步瞬时失败有界重试（成片构建 concat/burn-subtitles/probe）
  ffmpeg-retry-attempts: ${FFMPEG_RETRY_ATTEMPTS:3}
  ffmpeg-retry-backoff-ms: ${FFMPEG_RETRY_BACKOFF_MS:2000}
  # v2.31 flaky 收尾：单次成片构建内所有 ffmpeg 步骤共享退避预算，总睡眠不超过预算
  ffmpeg-retry-total-budget-ms: ${FFMPEG_RETRY_TOTAL_BUDGET_MS:20000}
=== END ===
=== PATCH: docs/FFMPEG_RELIABILITY.md ===
--- OLD
| `drama.ffmpeg.retry-backoff-ms` | `FFMPEG_RETRY_BACKOFF_MS` | 2000 | 退避基数，实际等待为基数 × attempt |
--- NEW
| `drama.ffmpeg.retry-backoff-ms` | `FFMPEG_RETRY_BACKOFF_MS` | 2000 | 退避基数，实际等待为基数 × attempt |
| `drama.ffmpeg.retry-total-budget-ms` | `FFMPEG_RETRY_TOTAL_BUDGET_MS` | 20000 | 单次成片构建内所有 ffmpeg 步骤共享的退避预算，总睡眠不超过该值；耗尽后仍尝试剩余次数但不再睡眠 |
=== END ===
=== PATCH: docs/OPERATIONS.md ===
--- OLD
代码里 `FfmpegService.FfmpegException#isTransient()` 就是这么判的：超时 / 137 / 143 / OOM 算瞬时，`无法启动命令` 算永久。`FinalCutService` 对 concat、burn-subtitles、probe-duration 这三种操作的瞬时失败会做有界重试，默认 3 次，退避是 2000ms × 当前 attempt 数。想改的话用环境变量 `FFMPEG_RETRY_ATTEMPTS` 和 `FFMPEG_RETRY_BACKOFF_MS`。
--- NEW
代码里 `FfmpegService.FfmpegException#isTransient()` 就是这么判的：超时 / 137 / 143 / OOM 算瞬时，`无法启动命令` 算永久（v2.31 起 EAGAIN/ENOMEM/EMFILE 类资源耗尽信号算瞬时）。`FinalCutService` 对 concat、burn-subtitles、probe-duration 这三种操作的瞬时失败会做有界重试，默认 3 次，退避是 2000ms × 当前 attempt 数；另有总预算 `FFMPEG_RETRY_TOTAL_BUDGET_MS`（默认 20000ms），单次构建内所有步骤的退避睡眠合计不超过该值。想改的话用环境变量 `FFMPEG_RETRY_ATTEMPTS`、`FFMPEG_RETRY_BACKOFF_MS` 和 `FFMPEG_RETRY_TOTAL_BUDGET_MS`。
