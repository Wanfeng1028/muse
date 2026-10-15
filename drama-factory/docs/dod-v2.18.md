# drama-factory v2.18 发版对照报告：分支覆盖冲 87%

- 日期：2026-10-15（第 17 轮覆盖率攻坚，DoD v2.17 排期首项）
- 结论：**目标达成**——分支覆盖 **85.33% → 87.09%**（+1.76pp，+58 分支），行覆盖 89.86% → 90.52%。
- 测试总数：1460 → **1519**（+59），全绿（2 skipped 为既有跳过）。
- pom JaCoCo 门禁棘轮：LINE 0.89→**0.90**、BRANCH 0.85→**0.87**；`mvn -o verify` BUILD SUCCESS。
- 生产代码零逻辑修改（纯测试增量 + pom 门禁数字）。

## 交付清单

| 批次 | 新测试文件 | 测试数 | 覆盖目标 |
| --- | --- | --- | --- |
| A | `service/SettingsServiceBranchTest.java` | 11 | SettingsService 18→3（剩余 3 个不可达，见诚实跳过） |
| B | `service/AssetServiceBranchTest.java` | 17 | AssetService 19→2（剩余 1 不可达 + 1 存疑，见下） |
| C | `controller/MediaControllerBranch2Test.java` | 3 | MediaController 4→0（全部拿下） |
| D | `service/RunServiceBranch2Test.java` | 17 | RunService 18→2（剩余 2 不可达）+ DramaProject/VideoTask/FinalCut 各 1 个 @PrePersist 分支 |
| E | `service/BranchCatchUpTest.java` | 7 | RunService 355/529/618、JwtVerifier 26、PromptRecipe/SceneService/CurrentUser 各对侧臂第一轮 |
| F | `service/BranchCatchUp2Test.java` | 5 | CurrentUser 25/29 对侧臂、PromptRecipe 78/81 对侧臂、SceneService 74 对侧臂、JwtVerifier 60 exp非数字臂 |

## 验收过程（修的真问题）

1. **B 批 `registerGenerated_traversalPath_throws` 两次失败**：prompt 指错路——`registerGenerated` 根本不调 `resolveSafePath`（只拼字符串就 save），穿越臂只能经 `delete()` 到达；且 `"assets/../evil.png"` normalize 后仍在 base 内（`assets/..` 抵消），必须用 `"assets/../../evil.png"`。改写为 `delete_traversalInsideAssetsPrefix_throws`（filePath=`"assets/../../evil.png"` 过第 140 行检查、在 resolveSafePath 被拦），通过。
2. **E/F 两批的"对侧臂"教训**：第一轮补漏测试只覆盖了"一侧臂"（如 CurrentUser 的 `instanceof` false 臂），对侧臂（true 臂）从来没人覆盖过——JaCoCo 的 mb=1 cb=1 就是"一侧有人、一侧没人"。F 批专门补对侧臂（无请求上下文、null request、null 默认值、缺失记录抛异常、exp 非数字）。
3. **AssetService 第 80 行 `originalName == null || isBlank()` 的 mb=1 成谜**：blank 文件名测试（`" "` → 回退 `"file"`）存在且通过，证明 isBlank-true 臂确实执行，但 JaCoCo 仍报 mb=1 cb=3。四个探针（null真/null假/blank真/blank假）按测试设计应全覆盖，原因未定位——记入诚实存疑，不硬凑。
4. **dpsk javadoc 注释里的行内 ``` 截断提取**：D 批输出的注释中含行内 ```，导致首个 ```java 块正则提前截断；改取"首个开围栏→最后一个闭围栏"提取。教训：prompt 里避免在正文写 ```，或提取时按首尾围栏取。

## 诚实跳过清单（经代码核验不可达，不写糊弄测试）

1. SettingsService 第 70 行 `e.getKey() == null` 真臂：JSON 对象键恒为字符串，Jackson 不可能产出 null 键。
2. SettingsService 第 146 行 maskedView `value == null` 臂：`loadAll()` 第 73 行已把 null 值转空串，maskedView 拿到的值永不为 null。
3. SettingsService 第 213 行 `hint != null` 假臂：`field()` 为私有，仅 `schema()` 调用，12 处调用的 hint 全为非空字面量。
4. RunService 第 422/431 行 approve `qcStep != null` 假臂：`findFinalCutId` 与 approve 调的是同一个 `findWaitingQcStep`，生产上两次调用返回一致；前者非 null 则后者必非 null。
5. AssetService 第 262 行 `lastSegment` 的 `idx < 0` 臂：`registerGenerated` 恒给 relative 加 `"assets/"` 前缀，relative 必含 `/`。
6. AssetService 第 80 行 mb=1（存疑，见上）：测试已覆盖该臂执行，探针仍报 missed，未定位原因。

## DoD 未通过项新排期（v2.19）

- Agnes/Qwen submit/poll 录制回放扩到真实链路（需外部 API，v2.9 起遗留）
- h2c 锁定待产品确认（v2.9 遗留）
- `DramaV2ApiIntegrationTest.testFullPipeline` flaky 根因（ffmpeg 环境抖动；考虑 mock 化视频轮询）
- 分支覆盖 87.09% → 88%：候选 VideoTaskService（3）、CurrentUser（剩余 1：`value.isBlank()` 真臂）、DramaMetrics（3）、ByokController（3）、SkillController（3）；AssetService 第 80 行存疑分支根因定位
