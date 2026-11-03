# v2.29 覆盖率收尾 + flaky 根因验证发版对照报告

## 里程碑概述

本轮是 v2.29 的第二阶段。上一轮（commit e7ee93c，2026-10-16）已完成 testFullPipeline flaky 根因修复并提交，
但全量 `mvn -o verify` 被并发构建污染而未完成，门禁未验证。本轮做两件事：
1. **覆盖率收尾**：基于新鲜 JaCoCo 报告，给我方原有类的 missed branches 补 *V229* 测试；
2. **flaky 根因验证**：复核上一轮修复代码，给出诚实结论。

**核心结论（先说）**：门禁仍红。BRANCH 85.00%（门禁 0.94）、LINE 88.75%（门禁 0.92）。
missed branches 的 65.8% 来自他人在途新代码（视频管线轮次的 NovAI/Doubao/Painted/ShotRouter/HtmlRender +
agent-canvas 的 CanvasProjectService），按铁律不降门禁、不代写他人测试，如实汇报。
我方原有类的**可达** missed branches 已基本清零（3 个类清零，其余大幅减少；不可达分支见诚实声明）。

## 第 0 步基线（2026-10-17 干净环境全量 `mvn -o verify`）

- 测试：1921 例，14 失败 + 11 错误，6 skipped。
- 失败全部集中在 6 个类：`QwenVideoProviderBranch2Test`（10F+7E）、`QwenVideoProviderBranch3Test`（2F+2E)、
  `QwenProbeTest`（1F）、`QwenVideoProviderSubmitPollRecordingTest`（2E）、`VideoProviderRouterTest`（1F)——
  归因：commit edf9462（2026-10-16，视频管线轮次"qwen 紧急摘除"）在 `QwenVideoProvider.submit()` 加了硬拒单 guard，
  但 5 个 Qwen 测试类未同步 @Disabled/更新。这是**他人在途改动**，本轮不代修。
- 另有 3 个失败是**构建环境污染**：`EgressProxyConfigTest` 的 3 个用例期望无代理环境，
  但构建 shell 继承了 `HTTPS_PROXY=hatch-egress-proxy:3128`，污染了 JVM 系统属性。
  干净环境（unset 代理变量）下 11/11 全绿。本轮全量构建统一用干净环境。
- JaCoCo（新鲜报告）：BRANCH 3369/4007=84.07%（门禁 0.94 红）、LINE 7898/8980=87.95%（门禁 0.92 红）。
- missed branches 归属：他人新代码 420/638（65.8%）——NovAiVideoProvider 100、CanvasProjectService 71、
  PaintedAnimationVideoProvider 56、ShotVideoRouter 54、DoubaoEmailVideoProvider 53、
  QwenVideoProvider 36、HtmlRenderVideoProvider 27、CanvasMigrationAdapter 23。

## 交付清单（测试 12 批，全部由微信 dpsk 生成）

| 批次 | 文件 | 用例 | 结果 |
|---|---|---|---|
| C1 | AuthProxyControllerV229Test | 13 | 全绿 |
| D2-3 | AuthProxyControllerV229D2Test | 6 | 全绿（删 1 个不可达测试） |
| C2 | LlmScriptServiceV229Test | 4 | 全绿（回喂 2 轮：假测试、PATCH 编造） |
| D2-2 | LlmScriptServiceV229D2Test | 4 | 全绿（回喂 1 轮：HOME 环境依赖改反射） |
| C3 | JwtAuthFilterV229Test | 9 | 全绿（回喂 1 轮：HS256 缺 exp） |
| C3 | SettingsEnvPostProcessorV229Test | 2 | 2 skipped（诚实跳过） |
| C4 | EpisodeServiceV229Test | 7 | 全绿 |
| C4 | PromptTemplateServiceV229Test | 8 | 全绿 |
| C5 | CharacterServiceV229Test | 10 | 全绿 |
| C5 | RunExecutorV229Test | 9 | 全绿（回喂 2 轮：Mockito 误用、stub 缺失） |
| D2-1 | RunExecutorV229D2Test | 3 | 全绿 |
| C6 | flaky 验证型调查报告 | — | 见「flaky 结论」 |

合计新增 **75 例**，终版全量中**全部通过**，无新增失败。

## 覆盖率变化（基线 → 终版，全量 `mvn -o verify`）

| | 基线 | 终版 | 变化 |
|---|---|---|---|
| 测试总数 | 1921 | 1996 | +75 |
| BRANCH | 3369/4007 = 84.07% | 3406/4007 = 85.00% | **+0.93%** |
| LINE | 7898/8980 = 87.95% | 7970/8980 = 88.75% | **+0.80%** |
| 门禁 BRANCH≥0.94 | 红 | 红 | 缺口归属见诚实声明 |
| 门禁 LINE≥0.92 | 红 | 红 | 缺口归属见诚实声明 |

目标类 missed branches：

| 类 | 基线 | 终版 | 说明 |
|---|---|---|---|
| AuthProxyController | 13 | 9 | -4（剩余 3 个不可达 + 4 个定位偏差，见诚实声明） |
| JwtAuthFilter | 8 | 0 | **清零** |
| SettingsEnvironmentPostProcessor | 10 | 10 | 诚实跳过（SETTINGS_PATH 写死） |
| RunExecutor | 7 | 5 | -2（剩余 4 个不可达 + 1 个定位偏差） |
| CharacterService | 7 | 0 | **清零** |
| PromptTemplateService | 8 | 0 | **清零** |
| LlmScriptService | 10 | 8 | -2（剩余 2 个不可达 + 4 个环境依赖/定位偏差） |
| EpisodeService | 7 | 1 | -6 |
| **合计** | **70** | **33** | **-37** |

## PRODUCTION_CHECKLIST.md 逐条对照（本轮相关）

| 条目 | 结论 | 说明 |
|---|---|---|
| 1.1 测试金字塔 | 通过 | 本轮新增 11 个测试文件 75 例，全部通过；上一轮 8 批 flaky 针对性测试本轮全量中全部通过 |
| 6.2 CHANGELOG + 升级指南 | 通过 | CHANGELOG [Unreleased] 追加 v2.29 第二阶段条目；本报告即发版对照 |
| 6.3 技术债有记录 | 通过 | 见「DoD 未通过项新排期」 |
| 6.4 代码与文档同步 | 通过 | 本轮只加测试，生产代码零改动 |

## 验收证据

- 终版全量 `mvn -o verify`（干净环境，`-Dmaven.test.failure.ignore=true`）：
  **1996 例，14 失败 + 11 错误，8 skipped**。失败/错误与基线完全一致（Qwen 相关 6 个类，
  他人在途改动）；新增 75 例**全部通过**；8 skipped 中 2 个是本轮诚实跳过（SettingsEnvPostProcessorV229Test）。
- JaCoCo 门禁：BRANCH 85.00%（<0.94 红）、LINE 88.75%（<0.92 红）。红的原因见诚实声明。
- testFullPipeline：本轮全量中 1/1 通过（25.31s，远低于 60s 预算）。

## 诚实声明

### 门禁红的归因
门禁红**不是**本轮引入的。基线（本轮第 0 步、新鲜报告）已红：BRANCH 84.07%、LINE 87.95%。
missed branches 的 65.8%（420/638）来自他人在途新代码（视频管线轮次 + agent-canvas），
按铁律不降门禁、不代写他人测试。本轮把我方原有类的**可达** missed branches 基本清零，
BRANCH 从 84.07% 提升到 85.00%（+0.93%）。

### 不可达分支论证（本轮诚实跳过，不硬凑）
- `SettingsEnvironmentPostProcessor` 10 个：`SettingsService.SETTINGS_PATH` 是 static final 写死生产路径，
  Java 17 反射改不了，测试内不许碰生产文件。"文件存在"分支需集成环境，纯单元测试不可达。
  测试用 `assumeFalse` 守护，文件不存在时覆盖"静默返回"分支。
- `RunExecutor.findPreviousStepOfType` 的 `runId/seqNo/type == null`（2 个）：内部调用永远传非 null。
- `RunExecutor.truncate` 的 `s == null`（1 个）：`safeMessage` 永不返回 null。
- `RunExecutor.safeMessage` 的 `t == null`（1 个）：catch 的 ex 永不为 null。
- `LlmScriptService.validate` 的 `envHome == null/isBlank`（2 个）：`System.getenv("HOME")` 测试进程内不可改。
- `LlmScriptService.validate` 的 for 零次迭代（1 个）：bases 恒非空（同上）。
- `LlmScriptService.validate` 的 `isFile()==false` 出口与 `effectiveCliPath==null` 三元分支：
  依赖 HOME 下无 chat.py，当前环境恒有真实文件，环境依赖不可达。
- `AuthProxyController.buildCookie` 的 `value == null`（1 个）：所有调用点都传非 null。
- `AuthProxyController.textOrNull` 的 `node == null`（1 个）：`readTree` 成功时永不返回 null。
- `AuthProxyController.textOrNull` 的 `v == null`（1 个）：`hasNonNull` 为 true 时 `get` 永不为 null。
- `AuthProxyController.isCsrfAllowed` 的 `sourceHost.isEmpty()`（1 个）：实测 `URI.getHost()`
  在 host 为空时返回 null 不可能返回 ""，不可达（已删对应测试，类注释留证）。
- `AuthProxyController` line 100 的 `path != null` 为 false：`extractPath` 返回 `getRequestURI()` 永不为 null。

### D2 打偏说明
D2 三批（RunExecutor 3 例、LlmScript 4 例、AuthProxy 6 例）全部通过，但 JaCoCo 显示部分目标分支仍 missed
（如 AuthProxy line 99/151/213/228/262、RunExecutor line 598、LlmScript line 516、Episode line 80）。
原因是 JaCoCo 对复杂布尔表达式的分支计数粒度与用例设计时的定位有偏差——测试确实执行了目标方法，
但命中的是已覆盖的分支方向。剩余可达缺口约 5-8 个分支（≈0.15%），边际收益低，不再打 D3，留给下一轮精确定位。

### flaky 结论（C6 验证型调查）
**判定：基本歼灭，有低概率残留。**
- 本轮全量实测：testFullPipeline 1/1 通过（25.31s）；同族 E2E（VideoPipelineE2eTest 34.23s、
  VideoPipelineResilienceE2eTest 80.97s、VideoPipelineNovaiE2eTest 100.0s）全部通过；
  上一轮 5 组针对性测试（FinalCutFfmpegRetryTest 3/3、FinalCutRealFfmpegRetryTest 1/1、
  ProcessDueTasksSingleFlightTest 1/1、VideoTaskFailFastTest 2/2、FfmpegRetryMetricsTest 2/2）全部通过。
- 但单次运行不足以证伪概率性失败。C6 复核发现 2 处结构性残留：
  1. `FinalCutService.withFfmpegRetry` 退避总额无预算上限（6000ms×N，N 为 ffmpeg 步骤数）；
  2. `FfmpegService` 对 `pb.start()` 的 IOException 一律标永久（EAGAIN/ENOMEM 类瞬时资源异常会被误判）。
- 完整分析见 `~/workspace/muse-build/dpsk-out/drama-v229/c6-flaky.out`。

## DoD 未通过项新排期

| 项 | 原因 | 优先级 | 归属 |
|---|---|---|---|
| JaCoCo 门禁红（BRANCH 0.85/LINE 0.89） | 65.8% 缺口来自他人新代码 | 高 | 视频管线轮次、agent-canvas 轮次补测试 |
| Qwen 6 个测试类红（14F+11E） | edf9462 qwen 摘除未同步测试 | 高 | 视频管线轮次 |
| flaky 残留 2 处代码漏洞 | 退避总额无上限、pb.start IOException 误判永久 | 中 | 下一轮 |
| D2 定位偏差的 5-8 个分支 | 需更精细的 JaCoCo 行号制导 | 低 | 下一轮 |
| Agnes/Qwen submit/poll 真实链路 | 需外部 API | 中 | 待排期（本轮不做） |
| h2c 锁定 | 待用户确认 | 低 | 用户（本轮不做） |
| request_id 全链路透传 | 既有缺口 | 中 | 待排期 |

## 生成方式说明

- 本轮 12 批全部由微信 dpsk 生成（C1-C5、D2-1~D2-3、C6），编排者只做 prompt 编写、验收、回喂修复、构建验证。
  dpsk 每批 prompt 均含严厉红线（不许编造/不许<redacted>/Mockito 规范/不许灌水/只输出新文件）。
- 回喂记录：C2 假测试打回 1 次、PATCH 编造打回 1 次；C3 HS256 缺 exp 1 次；C5 Mockito 误用 1 次、stub 缺失 1 次；
  D2-2 HOME 环境依赖 1 次（改反射直设字段）；D2-3 不可达分支 1 次（删测试+注释论证）。
- 编排者亲手做的机械性修复（**如实披露**，未改动任何测试逻辑设计）：
  import 补漏（MockConfigurableEnvironment→MockEnvironment、JDK HttpHeaders、缺失 import、
  ModelCallResult 内部类 import）、`throws IOException` 声明、`"t"`→`"标题"` 笔误、
  尾部 markdown 反引号清理、`HttpHeaders.SET_COOKIE`→`"Set-Cookie"` 字符串、
  反射字段设置改写、不可达测试删除（URI.getHost() 实测论证）、多余 stub 删除、
  数组分支测试数据修正（`[{"scenes":...}]`→直接场景数组）。
