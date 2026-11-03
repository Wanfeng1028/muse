
```markdown
# DoD v2.10 — 分支覆盖冲 60%

- 里程碑：v2.10「分支覆盖冲 60%」（对应 docs/dod-v2.9.md 中 v2.10 排期第一项）
- 日期：2026-10-14
- 验证命令：`mvn -o verify`（离线）
- 门禁：JaCoCo LINE 0.75 / BRANCH 0.60（verify 阶段强制）

## 交付清单

4 批 dpsk 生成，编排者验收应用。

| # | 项 | 交付物 | 验证 |
|---|---|---|---|
| A | ChatService 可测性接缝 | 新增包可见 5 参构造器，注入 `java.util.function.Function<ObjectNode, String> modelCaller`；public 4 参构造器委托，默认走 `LlmTransport.postJson` 静态方法（真实网络）；`chat()` 内改调 `modelCaller.apply(body)`；删除私有 `callModel`。新建 `ChatServiceTest` 10 例（消息校验 3 例 + 历史截断/跳过/role 归一/body 形态/异常透传/边界 4000 字） | 测试通过；ChatService 分支覆盖 100%（20/20） |
| B | FinalCutService 单测 | 新建 `FinalCutServiceTest` 19 例（buildFinalCut：剧集不存在/无分镜/分镜无 DONE 视频三变体/成功全链路/拼接失败；qc：通过/打回/未完成/非法 verdict 两变体/不存在；get/list/toResponse 映射） | 测试通过；FinalCutService 分支覆盖 100%（28/28） |
| C | VideoTaskService 单测 | 新建 `VideoTaskServiceTest` 37 例（computeBackoffMs 7 例；submit 幂等/不存在/新建；submitAllForEpisode；retry 三态；get/listByShot；processDueTasks 17 例：空/提交默认 5 秒/8 秒/限流 45 秒与 5 秒取 max30/失败重试/达上限 FAILED/轮询 COMPLETED 四种 URL 形态/refresh 异常吞掉/FAILED/QUEUED/HTTP 下载失败/URL 为 null；awaitPollCompletion 空闲） | 测试通过；VideoTaskService 分支覆盖 92.9%（39/42） |
| D | 补遗（冲 60%） | `VideoTaskServiceTest` 追 6 例（provider agnes/qwen 分支、doPoll PROCESSING 结果、toResponse 本地文件缺失、awaitPollCompletion 在途完成/被中断——反射改 pollInFlight + 线程）；`FinalCutServiceTest` 追 1 例（finals 被文件占住致 createDirectories 抛 checked 异常，走 `new RuntimeException(e)` 分支）；新建 `RunLogServiceTest` 12 例（append/read 全分支，@TempDir） | 测试通过；RunLogService 分支覆盖 81.8%（18/22） |

### 全量验证数据

- `Tests run: 441, Failures: 0, Errors: 0, Skipped: 0`；BUILD SUCCESS；JaCoCo 新门禁（行 0.75/分支 0.60）通过。
- 全量行覆盖 73.6%→75.8%（7275/9593），分支覆盖 57.3%→60.8%（2286/3760），60% 目标达成。
- 门禁棘轮：pom JaCoCo LINE 0.70→0.75、BRANCH 0.55→0.60（只升不降）。

## 本轮攻坚记录

1. **ChatService 双构造器致 Spring 上下文失败。** 新增 5 参构造器后，40 个 Spring 上下文测试报 `No default constructor found`——与 v2.9 AuthProxyController 同款坑（单构造器 Spring 隐式选用，多构造器必须显式 `@Autowired`）。编排者手工补 `@Autowired` + import，全量恢复。
2. **apply_patches.py PATCH 解析缺陷污染测试文件。** 该脚本用 `re.search` 只取每块第一组 OLD/NEW（贪婪 NEW 吞掉后续组），Batch D 第一版把 `VideoTaskServiceTest` 污染（残留 `--- OLD ---` 标记行与 ``` 围栏）。编排者回滚该文件、用 `split-dpsk.py` 从 Batch C 输出恢复原文、把 D1 拆成 3 个单组 PATCH 块重放，另手工清掉首尾围栏。
3. **FfmpegServiceTest.burnSubtitles 偶发失败。** 整轮构建中出现过一次 ffmpeg 退出码 254 失败；单独复现同命令成功、内存充足，判定为环境抖动，重跑全量构建后通过。记为已知 flaky。
4. **split-dpsk.py 与 apply_patches.py 行为差异。** `split-dpsk.py` 不剥 ``` 代码围栏（`apply_patches.py` 会剥），混用两脚本恢复文件时需注意首尾围栏。

## DoD 对照

- [通过] 测试金字塔补强（新增 85 例；三类分支 100%/100%/92.9%）
- [通过] 门禁棘轮（行 0.75/分支 0.60，verify 阶段强制）
- [通过] 技术债有记录（COVERAGE.md 缺口表更新）
- [不适用] 数据库迁移版本化（本轮无表结构变更）
- [不适用] 视觉验收（本轮无 UI 变更）
- [未通过→排期] Agnes/Qwen 真实 provider submit/poll 分支（需外部 API）、LlmTransport 真实代理链路（沙箱无外网）——口径不变

## 已知限制

- 覆盖率数字为本机 `mvn -o verify` 实测；CI 环境跑全量后以 CI 为准。
- VideoTaskService 剩余 3 个未覆盖分支：awaitPollCompletion 2 个（25 秒超时 warn 路径及相关条件）、doPoll 1 个（switch 的隐式分支，QUEUED/PROCESSING/COMPLETED/FAILED 四标签均已覆盖）。
- RunLogService 剩余 4 个未覆盖分支：resolveFile 的 `startsWith(baseDir)` 防御分支（纯数字 id 下不可达）、read 的 `read<=0` 分支（`toRead>0` 时基本不可达）、append/read 的 IOException catch（单测难触发）。

## v2.11 排期

- 分支覆盖冲 65%（剩余大头：`UsageService.summary` 28、`AgnesVideoProvider.poll` 25、`ScriptSplitterService.callModel` 24、`EgressProxyConfig.configureFromEnv` 20 等；需逐个评估可测性）。
- Agnes/Qwen 真实 provider 录制回放扩到 probe 之外的 submit/poll 分支（需外部 API 时）。
- AuthProxyController 的 h2c 默认行为：评估是否在 `defaultHttpClient()` 显式 `.version(HTTP_1_1)` 锁定（行为变更，需产品确认，暂不做）。
```

