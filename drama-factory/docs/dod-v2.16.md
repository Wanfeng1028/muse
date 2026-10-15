# 发版对照报告：v2.16 分支覆盖攻坚（第 15 轮）

- 日期：2026-10-15
- 目标：DoD v2.15 排期首项——分支覆盖 80.57% → 85%
- 实际：分支 **80.57% → 82.45%**（+1.88pp），行 87.30% → **88.30%**（+1.0pp）
- 结论：**85% 目标未达成**（差 2.55pp / 约 420 个分支），但为纯测试增量轮，无生产代码变更、无回归风险。门禁已棘轮（LINE 0.87→0.88、BRANCH 0.80→0.82），`mvn -o verify` 全绿。

## 本轮工作（5 批 dpsk 生成，微信 ChatAPI DeepSeek-V4-Flash）

| 批次 | 新测试文件 | 测试数 | 目标类未覆盖分支变化 |
| --- | --- | --- | --- |
| A | `controller/MvControllerBranchTest.java` | 27 | MvController 21 → **0**（清零） |
| B | `service/CredentialResolverBranchTest.java` | 15 | CredentialResolver 21 → **0**（清零） |
| C | `service/PresetServiceTest.java` | 12 | PresetService 21 → **1** |
| D | `controller/AuthProxyControllerBranchTest.java` | 17 | AuthProxyController 23 → **14** |
| E | `service/RunServiceApproveTest.java` | 10 | RunService 22 → **18**（审批流+技能分支） |

- 测试总数：1214 → **1295**（+81），全绿。
- 覆盖分支数：+310（16495 总分支，未覆盖 3205 → 2895）。

## 验收过程（修的真问题）

1. **A 批 `create_withEmptyBody_returnsBadRequest`**：dpsk 先写空 body 期望 400，实测 Spring 框架层直接 500（`@RequestBody Map` 空 body 反序列化失败，到不了 controller）；改发 `"null"` 字面量仍被框架层拦。结论：`body==null` 分支走 HTTP 实际不可达，改为直接 `new MvController(mock, dir).create(null)` 调用覆盖，并注释说明原因。
2. **E 批包名编造**：dpsk 写成 `com.dramafactory.entity.*` / `com.dramafactory.enums.*`，实际为 `com.dramafactory.model.*`；另把 `DramaProjectRepository` 写成 `ProjectRepository`。sed 批量修正。
3. **E 批 record 构造**：dpsk 用 `new Records.ProjectResponse(7L)`（单参），实际 record 有 11 个组件。改为 `Mockito.mock(Records.ProjectResponse.class)` + stub `id()`。
4. **E 批 `doNothing().when(finalCutService).qc(...)`**：`qc` 返回 `Records.FinalCutResponse` 非 void，Mockito 抛 "Only void methods can doNothing()"。删掉（返回值被忽略，默认 null 即可）。
5. **E 批 `times(3)`**：dpsk 误算 createRun 的 step 数（1 集 × 5 种 AgentType = 5 个 save），改为 `times(5)`。
6. **E 批缺 `CurrentUser` import**：补 `com.dramafactory.config.CurrentUser`。

以上 6 处均为 dpsk 输出问题，生产代码零修改。

## 本轮教训

1. **走 HTTP 不可达的防御分支要诚实标注**：`@RequestBody` 为 null 的情况 Spring 框架层根本放不进来，硬用 MockMvc 测只会得到框架层的 400/500。直接调方法 + 注释说明，比"测了个寂寞"诚实。
2. **dpsk 对 record 的构造一律不信任**：record 组件数必须先 grep 确认，超过 3 个组件的一律用 mock + stub。
3. **void 方法假设要先查签名**：`doNothing()` 前先 `grep "public .* methodName("` 确认返回 void。
4. **Mockito 的 `times()` 数字要数清楚**：createRun 的 step 数 = 集数 × AgentType 种类数（5），不是拍脑袋的 3。

## DoD 未通过项新排期（v2.17）

- 分支覆盖冲 85%（还差约 420 分支；候选：RunExecutor 27、QwenVideoProvider 20、LlmScriptService 剩余、AuthProxyController 剩余 14、ByokGenerateService 剩余等）
- Agnes/Qwen submit/poll 录制回放扩到真实链路（需外部 API，v2.9 起遗留）
- h2c 锁定待产品确认（v2.9 遗留）
- `DramaV2ApiIntegrationTest.testFullPipeline` flaky 根因（ffmpeg 环境抖动；考虑 mock 化视频轮询）
