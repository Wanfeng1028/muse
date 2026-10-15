# v2.15 发版对照报告：分支覆盖冲 80%

- 日期：2026-10-15
- 目标：DoD v2.14 排期首项——分支覆盖从 75.54% 冲到 80%
- 基线（v2.14 实测）：分支 75.54%（2492/3299）、行 84.93%（6600/7771）、测试 1069

## 交付内容

6 批 dpsk 生成（全部走微信 ChatAPI DeepSeek-V4-Flash），A–F 批后分支仅到 79.21%（差 27 个分支），加急 G 批补足。8 个新测试文件、共 144 个测试：

| 批次 | 新测试文件 | 测试数 | 目标类（未覆盖分支） |
|------|-----------|--------|---------------------|
| A | ByokGenerateServiceBranchTest | 29 | ByokGenerateService（44） |
| B | ProviderServiceBranchTest | 22 | ProviderService（30） |
| C | MvServiceBranchTest | 18 | MvService（29） |
| D | UsageServiceBranchTest | 16 | UsageService（28） |
| E | PipelineServiceBranchTest | 12 | PipelineService（28，全方法零覆盖） |
| F | RunArtifactControllerBranchTest | 10 | RunArtifactController（28，全链零覆盖） |
| G | ProviderControllerBranchTest | 12 | ProviderController（24） |
| G | PromptRecipeServiceBranchTest | 25 | PromptRecipeService（26） |

候选 6 类合计 187 个未覆盖分支，80% 目标需净增约 148 个已覆盖分支。

## 验收

- `mvn -o verify`：**1214 测试全绿**（v2.14 为 1069；本轮 8 个新测试文件共 144 个 @Test），已知 flaky `DramaV2ApiIntegrationTest.testFullPipeline` 本轮一次通过。
- 覆盖率：分支 **75.54% → 80.57%**（2492 → 2658/3299，超额 0.57pp）、行 **84.93% → 87.30%**（6600 → 6784/7771）。
- 门禁棘轮已应用（pom.xml）：LINE 0.84→0.87、BRANCH 0.75→0.80；本次构建已用新门禁全绿通过。

## 本轮修的真问题（测试挖出来的）

无生产代码变更——本轮是纯测试补强轮，未发现生产 bug。

## 核验关闭的排期误判

- L141 switch default（ByokGenerateService.generate）：module 已在入口校验，default 不可达，跳过。
- L180/L253 轮询 deadline 超时分支：150s/240s 写死，测试不可达，跳过。
- L453 render clips.isEmpty()：空 sections 的 Timeline 经 fromJson（"时间轴为空"）/align（"作词结果为空"）/buildInstrumentalTimeline（totalMs<=0 抛错）都构造不出来，public 路径不可达，跳过。
- L541 findStep seqNo null：AgentStep.SEQ_NO 列 NOT NULL，null 存不进 DB，跳过。
- L570 resolveLocalAudio filePath==null：Asset.FILE_PATH 列 NOT NULL，跳过（".." 半支已有覆盖）。
- B 批 L344/L356/L367 matchXProvider name==null：MediaProvider.name 列 NOT NULL，public 路径不可达，改反射直测私有方法。
- C 批 L468/L587/L608/L630 render 字幕/muxAudio 分支：需真实 ffmpeg 链路，mock 下断言脆弱，跳过。
- E 批 L159 switch default：VideoTaskStatus 仅 4 值，default 不可达，跳过。

## 本轮教训

1. **dpsk PATCH 输出吞行首缩进**：apply_patches.py 是精确匹配，缩进一丢就锚定失败。本轮改用 METHOD 整方法替换 + python 括号配平应用，稳定可靠。
2. **dpsk 修方法时会重写坏方法体**：A 批回喂时它把 download 测试整个重写错（调 private 方法、raw type）。回喂后必须逐个 diff 检查替换后的方法，不能直接信任。
3. **Mockito 禁止 thenThrow 受检异常**：`HttpResponse.body()` 未声明受检异常，`thenThrow(new IOException)` 报 "Checked exception is invalid for this method"，改用 `doAnswer(inv -> { throw new IOException(...); })`。
4. **Map.copyOf 的 get(null)/containsKey(null) 抛 NPE**：断言不可变映射内容时别碰 null key。
5. **实例方法别当静态反射调**：extractRunId 是实例方法，`m.invoke(null, ...)` 直接 NPE。
6. **byok 三个 Provider 各有自己的 ConnectivityResult 嵌套类型**：不是 VideoProvider 的，mock 桩类型写错编译不过。
7. **Mockito 不允许 when() 嵌套**：helper 里调 `when()`，又被包在外层 `when(...).thenReturn(List.of(helper()))` 里 → "Unfinished stubbing"。全部 hoist 成局部变量。
8. **DB NOT NULL 约束是分支可达性的硬边界**：Asset 的 type/source/file_name/file_path、AgentStep.seqNo、MediaProvider.name 全是 NOT NULL，相关 null 防御分支只能反射直测或确认不可达。写测试前先看 entity 的 nullable。
9. **summary("", null, 0) 走 noFilter 快捷分支**：空串 provider + 空 model + days<=0 根本进不了过滤分支；测过滤分支的空串要用 ("", "m1", 0)。
10. **compose 是 @Transactional**：抛错后事务回滚，catch 块里 save 的 FAILED 状态会被回滚，不能断言 DB 状态（既有测试已有注释说明）。
11. **jacoco.exec 损坏**：之前 kill 掉的重复测试进程可能写了半截数据（agent 默认 append），report 报 "Unknown block type 2d"。删掉 exec 重跑 verify 解决。
12. **新测试禁 /tmp**：dpsk 在 storageDir 占位用了 Path.of("/tmp")，已全改为相对路径。

## DoD 未通过项新排期（v2.16）

- Agnes/Qwen submit/poll 录制回放扩到真实链路（需外部 API，v2.9 起遗留）
- h2c 锁定待产品确认（v2.9 遗留）
- 分支覆盖冲 85%（候选：RunExecutor 27、PromptRecipeService 26、ProviderController 24 等，见 jacoco 报告）
- `DramaV2ApiIntegrationTest.testFullPipeline` flaky 根因（ffmpeg 环境抖动；本轮一次通过，但根因未消，仍考虑 mock 化视频轮询）
