# testFullPipeline flaky 诚实根因报告

本报告记录 DramaV2ApiIntegrationTest.testFullPipeline 概率性失败的调查过程、根因分析、证据、已排除项、缓解措施与残余风险。所有数字均取自既有事实材料，未做推算或润色。凡证据不足处一律标注"未证实"或"证据不足"，不使用"已歼灭""彻底解决"等结论性措辞。

## 1. 现象

DramaV2ApiIntegrationTest.testFullPipeline 偶发返回 500。

该失败不是每次必现，而是概率性出现（flaky）。在同一代码版本、同一测试命令下，该用例有时通过、有时失败，因此无法用单次运行结果直接判定其是否已被消除。

## 2. 时间线

- v2.15（2026-10-14/15）：首次记录 flaky，根因怀疑为 ffmpeg 环境抖动。该轮 testFullPipeline 一次通过，但记录明确指出"根因未消"，并考虑后续对视频轮询做 mock 化。
- v2.21：testFullPipeline flaky 根因仍未消除。该轮同样为一次通过，记录仍标注"根因未消"。
- v2.29（2026-10-16）：三处生产代码修复落地，分别为 FfmpegException 瞬时/永久分类、FinalCutService 有界重试、VideoTaskService 单飞 CAS。
- v2.29 第二阶段：进行 C6 验证型调查，产出验证型调查报告与 DoD 结论。
- v2.31（2026-10-17，本轮）：收尾修复，针对 C6 发现的两处结构性残留实施缓解措施。
- v2.32（2026-10-17，本轮）：关闭残余风险 ③④⑥，针对 ffmpeg 输出读取竞争、InterruptedException 重包装、其它 RuntimeException 逃逸重试路径实施生产修复与单测覆盖。

## 3. 根因分析

综合既有材料，本问题的成因可归纳为：底层存在瞬时失败源，上层存在三处放大缺口，二者叠加导致概率性 500。

瞬时失败源：ffmpeg 进程启动或执行阶段的抖动。此类抖动在真实高负载环境下更易出现，属于概率性事件。

三处放大缺口（v2.29 之前的状态）：

1. 无分类：FfmpegException 未区分瞬时失败与永久失败，瞬时抖动与确定性错误被同等对待。
2. 无重试：FinalCutService 缺乏有界重试，单次瞬时抖动即可直接导致失败向上传播。
3. 重入：VideoTaskService 缺乏单飞 CAS 保护，存在重入路径放大失败概率。

C6 调查在两处生产代码修复之后，进一步发现两处结构性残留：

1. 退避总额无预算上限：FinalCutService.withFfmpegRetry 的退避总额无预算上限（6000ms×N，N 为 ffmpeg 步骤数）。当多个 ffmpeg 步骤同时遭遇瞬时失败时，退避睡眠总额可能超出预期。
2. pb.start() 的 IOException 一律标永久：FfmpegService 对 pb.start() 抛出的 IOException 一律标记为永久失败。EAGAIN、ENOMEM 这类瞬时资源异常因此会被误判为永久失败，从而不进入重试路径。

上述两处残留被判定为在真实高负载下仍可能触发偶发失败。

## 4. 证据

历次实测数据如下：

- v2.29 全量：testFullPipeline 1/1 通过，耗时 25.31s，远低于 60s 预算。
- 同族 E2E 全部通过：VideoPipelineE2eTest 34.23s、VideoPipelineResilienceE2eTest 80.97s、VideoPipelineNovaiE2eTest 100.0s。
- 上一轮新增的 5 组针对性测试全部通过：FinalCutFfmpegRetryTest 3/3、FinalCutRealFfmpegRetryTest 1/1、ProcessDueTasksSingleFlightTest 1/1、VideoTaskFailFastTest 2/2、FfmpegRetryMetricsTest 2/2。

对上述证据的诚实限定（保留 C6 原话）：单次通过不能证伪概率性失败。本轮仅有一次全量运行证据，不足以在统计意义上判定"已歼灭"。因此上述数据只能说明在当前观测条件下未复现失败，不能据此得出 flaky 已被消除的结论。

## 5. 已排除项

以下项经调查后排除与 flaky 的因果关系：

- 单飞 CAS：VideoTaskService 的单飞 CAS 在 finally 中全覆盖，未发现漏洞。
- 重试循环：重试循环中不可达 throw 的逻辑经核查正确。
- 全量失败集中现象：全量失败集中在 Qwen 相关的 6 个测试类，原因为另一轮次 qwen 摘除未同步测试所致，与 flaky 无因果。
- EgressProxyConfigTest 的 3 个失败：为构建环境代理变量污染，干净环境下全绿，与 flaky 无关。

## 6. 缓解措施（v2.31/v2.32）

v2.31 本轮针对 C6 发现的两处结构性残留实施修复：

1. 退避预算上限（FinalCutService）：单次成片构建内所有 ffmpeg 步骤共享一份退避预算。配置键为 drama.ffmpeg.retry-total-budget-ms，环境变量为 FFMPEG_RETRY_TOTAL_BUDGET_MS，默认 20000ms。新增包可见静态方法 claimRetryBackoff(AtomicLong, long) 做预算认领。预算耗尽后仍继续尝试剩余次数，但不再睡眠，即尝试次数保证不变。构造器新增 13 参重载（@Autowired），保留 12 参委托构造器（默认 20000L），既有测试零改动。
2. 启动异常精细分类（FfmpegService）：新增包可见静态方法 isTransientLaunchFailure(IOException)，正向识别 cannot allocate memory、too many open files、resource temporarily unavailable 为瞬时；其余情况（含消息为 null、无法识别的消息）保持永久，与 v2.29 既有行为一致。
3. 新增测试 17 例：FinalCutRetryBudgetV231Test 共 7 例（认领足额、截断、耗尽、非正请求，加零预算不睡眠、预算封顶总睡眠、永久失败不扣预算）；FfmpegLaunchClassifyV231Test 共 10 例（9 个分类断言加真实缺失二进制端到端）。

v2.32 本轮针对残余风险 ③④⑥ 实施修复：

1. ffmpeg 输出读取竞争（FfmpegService）：run() 的 reader.join(2000) 改为"有上限循环 join + reader.isAlive() 守卫"；预算耗尽仍未结束时 message 明确标注"可能不完整"，不伪装完整；join 被中断时恢复中断标志后直接抛不带 snippet 的异常。新增 public static 内部类 FfmpegInterruptedException extends FfmpegException（构造器 (String, Throwable) → super(m, t, false)）。
2. InterruptedException 重包装收敛（FfmpegService + FinalCutService）：FfmpegService 中 run() 的 process.waitFor 中断、reader.join 中断、probeDurationSeconds() 的 waitFor 中断三处 throw 点由 FfmpegException(..., true) 收敛为 FfmpegInterruptedException；FinalCutService.withFfmpegRetry 在 catch (FfmpegException) 之前新增 catch (FfmpegInterruptedException) 直接 throw（终止重试循环，不睡眠、不重试），Thread.sleep 的 catch 改抛 FfmpegInterruptedException(..., ie)（修复 cause=null）；VideoTaskService.processDueTasks() 在 catch (RateLimitedException) 之后新增 catch (FfmpegInterruptedException)——恢复中断标志 + failOrRetry(task, msg, true) 标记永久失败，不重排。
3. 其它 RuntimeException 逃逸重试路径（FinalCutService）：withFfmpegRetry 的 catch (RuntimeException e) { throw e; } 收敛为"未知 RuntimeException 保守按瞬时失败处理"（包装为 transient FfmpegException 走统一重试分支）；catch (Exception e) 保持 throw new RuntimeException(e) 并加注"理论路径，实际不可达"。

## 7. 残余风险

以下按概率排序，其中前两条已由 v2.31 关闭，第 3、4、6 条已由 v2.32 关闭，第 5 条未关闭。

已关闭：

1. 多 ffmpeg 步骤同时瞬时失败导致退避总额超预算（原概率：中）。已由 v2.31 退避预算上限关闭。
2. pb.start() 的 IOException 被误判为永久失败（EAGAIN/ENOMEM 类）（原概率：低）。已由 v2.31 精细分类关闭。
3. ffmpeg 输出读取线程与主流程竞争导致 output 内容不完整（原概率：低）。已由 v2.32 关闭：FfmpegService.run() 的 reader.join(2000) 改为有上限循环 join + reader.isAlive() 守卫，预算耗尽未结束时 message 明确标注“可能不完整”、不伪装完整。证据：新增 FfmpegOutputRaceV232Test 3/3 通过（2.621s）。此处“关闭”指已实施针对性修复并有测试覆盖，单次/有限样本不能证伪概率性失败。
4. InterruptedException 重包装为瞬时异常导致任务被重排而非终止（原概率：低）。已由 v2.32 关闭：FfmpegService 三处中断 throw 点收敛为 FfmpegInterruptedException，FinalCutService.withFfmpegRetry 新增 catch (FfmpegInterruptedException) 直接 throw（不睡眠、不重试），Thread.sleep 的 catch 改抛 FfmpegInterruptedException(..., ie)（修复 cause=null），VideoTaskService.processDueTasks() 新增 catch (FfmpegInterruptedException) 恢复中断标志 + failOrRetry(task, msg, true) 标记永久失败、不重排。证据：新增 FfmpegInterruptV232Test 3/3 通过（12.92s）。此处“关闭”指已实施针对性修复并有测试覆盖，单次/有限样本不能证伪概率性失败。
6. 其它 RuntimeException 逃逸重试路径（原概率：低）。已由 v2.32 关闭：FinalCutService.withFfmpegRetry 的 catch (RuntimeException e) { throw e; } 收敛为“未知 RuntimeException 保守按瞬时失败处理”（包装为 transient FfmpegException 走统一重试分支），catch (Exception e) 保持 throw new RuntimeException(e) 并加注“理论路径，实际不可达”。证据：新增 FfmpegRetryEscapeV232Test 3/3 通过（14.12s）。此处“关闭”指已实施针对性修复并有测试覆盖，单次/有限样本不能证伪概率性失败。

未关闭：

5. 多实例部署下进程内 CAS 单飞失效（概率：低，不在单测范围）。

## 8. v2.31 验证数据

- 基线（修复前代码）：testFullPipeline 连续 2 次通过（163.1s、167.0s），flaky 未复现（与 v2.29"低概率残留"一致）。
- 修复后：testFullPipeline 连续 10/10 通过（耗时 161.8s~320.5s；VM 高负载下依然全绿）。
- 新测试 17/17 全绿（FinalCutRetryBudgetV231Test 7、FfmpegLaunchClassifyV231Test 10）；既有相关 8 类 38/38 全绿，无回归。
- 全量 `mvn -o verify`：2013 例，14 失败 + 11 错误，8 skipped；JaCoCo BRANCH 83.94%（门禁 0.94，红）、LINE 86.41%（门禁 0.92，红）；missed branches 的 70.9%（458/646）来自他人在途新代码（NovAI 105、CanvasProjectService 71、Doubao 64、ShotVideoRouter 58、Painted 56、HtmlRender 45、Qwen 36、CanvasMigration 23）；失败/错误全部集中在 Qwen 相关 6 个测试类（QwenProbeTest 1F、QwenVideoProviderBranch2Test 10F+7E、QwenVideoProviderBranch3Test 2F+2E、QwenVideoProviderSubmitPollRecordingTest 2E、VideoProviderRouterTest 1F），与 v2.29 基线完全一致，系另一轮次 qwen 紧急摘除未同步测试所致，本轮按铁律不碰。

## 8.1 v2.32 验证数据

- 新增测试 9 例，全部通过：FfmpegOutputRaceV232Test 3/3（2.621s）、FfmpegInterruptV232Test 3/3（12.92s）、FfmpegRetryEscapeV232Test 3/3（14.12s）。
- 回归：既有相关 10 类（FinalCutServiceTest 20、FinalCutFfmpegRetryTest 3、FinalCutRealFfmpegRetryTest 1、FfmpegServiceTest 4、FfmpegExceptionClassificationTest 5、VideoTaskFailFastTest 2、ProcessDueTasksSingleFlightTest 1、FfmpegRetryMetricsTest 2、FinalCutRetryBudgetV231Test 7、FfmpegLaunchClassifyV231Test 10）+ 新增 3 类，共 13 类 64/64 全绿；修复前基线为 10 类 55/55 全绿，无回归。
- 回喂统计：B2 回喂 2 轮、B4 回喂 2 轮、B6 回喂 2 轮；另有 2 处编排者机械修正（`new FfmpegService()` → 双参构造器 3 处；补 `import java.nio.file.Files;`），未改动测试语义。
- 上述数据仅为单轮有限样本下的验证结果，不能据此在统计意义上证伪概率性失败；在获得 §9 所述 CI 重复 N≥20 次量化证据之前，相关判定均应视为阶段性结论。

## 9. 排期

- 残余风险 3、4、6 已由 v2.32 关闭。
- 残余风险 5 在多实例部署场景下再议。
- C6 建议的"CI 中重复 N≥20 次采集通过率"作为量化证据，待 CI 条件具备后执行。在获得该量化证据之前，本问题的概率性特征无法在统计意义上被证伪，上述判定均应视为阶段性结论。

