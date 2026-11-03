# 发版对照报告：drama-factory v2.8（生产级补强第 7 轮）

日期：2026-10-14。里程碑 v2.8「分支覆盖冲 45%」，对应 docs/dod-v2.7.md 的 v2.8 排期最后一项未完成项（E2E、Agnes/Qwen 契约测试、stats 聚合优化已在之前 commit 落地）。本轮核心：测试金字塔大幅补强，分支覆盖超额达成。

## 交付清单

| # | 项 | 交付物 | 验证 |
|---|---|---|---|
| 1 | 测试金字塔补强 | 测试总数 232 → 336（新增 104 例，全部通过）；覆盖 `LlmScriptService`、`RunService`、`ScriptSplitterService`、`RunExecutor`、新建 `ProviderServiceProbeTest` | `mvn -o verify` 全绿：Tests run 336, Failures 0, Errors 0, Skipped 0；BUILD SUCCESS |
| 2 | LlmScriptServiceTest 扩充 | 8 → 34（+26）：`validate()` 9 例（A1-A9：禁用/空模型/非法数值/非法 CLI 路径/可执行 CLI/自动探测）；`parseScenes()` 12 例（B1-B12：null 内容/围栏变体/数组根/缺字段/非法值/可选字段默认值）；`buildUserContent()` 5 例（C1-C5：捕获 body 断言 user 文本：无 project/空标题/空大纲/null 与空白角色表/project 懒加载抛异常防御分支） | `mvn -o verify`：LlmScriptServiceTest 34 例通过 |
| 3 | RunServiceTest 扩充 | 15 → 33（+18）：`planPreview()` 12 例（P1-P12：null goal/集数溢出/空对象/非法 JSON/超量截断/空标题回退/缺集号/围栏无换行/空白返回/非数组/长目标截断/0 集）；`createRun/pause/resume` 6 例（P13-P18：正常建 run 断言 5 种 AgentType 与 RUNNING、空 goal/plan 拒绝、run 不存在、resume 正常/拒绝） | `mvn -o verify`：RunServiceTest 33 例通过 |
| 4 | ScriptSplitterServiceTest 扩充 | 15 → 35（+20）：`parse/strip` 6 例（S1-S6：围栏无换行/字符串镜号回退序号/字符串时长回 5/缺 cameraMove 得 null/缺 shotSize 抛"第 1 个分镜的字段 shotSize 非法: null"/数字 description 转文本）；`replaceShots` 14 例（S7-S20：episode 不存在/items null/空/超 30/正常替换旧分镜/缺镜号/非法景别/非法运镜/null 运镜/null 时长回 5/非法时长/splitFromScript 两处守卫） | `mvn -o verify`：ScriptSplitterServiceTest 35 例通过 |
| 5 | RunExecutorTest 扩充 | 10 → 36（+26）：`advanceRun` 与各 step 异常分支 13 例（E1-E4/E6-E14：run 不存在/状态已变/无 step/无 PENDING 只有 RUNNING QC/type 缺失/各服务返回 null/缺 episodeId/BOARD 缺前置/EDIT 正常与 null）；QC 自动门/`checkVideoStep`/`finalize` 13 例（Q1-Q5：真实临时文件 QC 通过/缺文件/无 filePath/缺 EDIT/空输出；C1-C4：空任务抛异常/失败任务 null 错误信息/非 mock provider 成本未知/无时间戳；F1 未知成本致 totalCostCents null；H1 空白审批配置仍等待；H2 超长错误信息截断 500；H3 null 信息用类名） | `mvn -o verify`：RunExecutorTest 36 例通过 |
| 6 | ProviderServiceProbeTest 新建 | 14 例（T1-T10：provider 不存在/非 VIDEO 模块/未知名称/null 名称/agnes 匹配探测/dashscope 匹配 qwen/mock 匹配/鉴权失败透传/checkedAt ISO 格式/null provider map 不抛 NPE；M1-M4：maskKey 四分支） | `mvn -o verify`：ProviderServiceProbeTest 14 例通过 |
| 7 | 覆盖率与门禁棘轮 | JaCoCo 实测行覆盖 58.5% → 71.0%；分支覆盖 37.5% → 52.7%（目标 45%，超额达成）；pom.xml 新增 BRANCH 0.45；LINE 0.55 → 0.65（棘轮，只升不降） | `mvn -o verify`：LINE 71.0%，BRANCH 52.7%，门禁 0.65/0.45 通过 |

## 本轮攻坚记录

1. **首轮两批超时作废**：`--max-tokens 24000/30000` 生成超 90 秒超时，整批作废；改为每批 ≤8000 token、9 批分批生成。
2. **3b 输出块头非约定格式**：输出 "PATCH 1/2/3" 简写块头（非约定格式），编排者手工转标记后应用。
3. **5a 尾部残留标记行**：输出尾部带 "=== END FILE ===" 标记行，已删除。
4. **4b OLD 锚点失效**：因 4a 先合入而失效，编排者从输出中提取 13 个测试体重锚应用；附带修复生成代码两处编译问题（Q1 漏 `Run run = runningRun()`、C1 缺 assertThrows 导入）。
5. **B12 brief 场景数误写**：误写单场 JSON（parseScenes 要求恰好 4 场），已修正为 4 场。
6. **P3 brief 断言误写**：误写 hasSize(1)（goal 含"2 集"，fallback 应为 2 集），已修正。
7. **1c 生成代码漏 import**：漏 import（JsonNode/mock/when），已补。
8. **核验纠正**：`ShotSize.fromLabel(null)` 是抛 IllegalArgumentException（不是返回 null），S5 预期已按真实行为写为抛"第 1 个分镜的字段 shotSize 非法: null"。

## DoD 对照（本轮相关项）

- [通过] 测试金字塔大幅补强（新增 104 例；核心链路分支覆盖 52.7%）
- [通过] 门禁棘轮（行 0.65/分支 0.45，verify 阶段强制）
- [通过] 技术债有记录（COVERAGE.md 缺口表更新，见下）
- [不适用] 数据库迁移版本化（本轮无表结构变更）
- [不适用] 视觉验收（本轮无 UI 变更）
- [未通过→排期] AuthProxyController 110 个分支缺口：`proxy()` 内 HttpClient 为构造器内新建，无法注入 mock，需可测性重构（构造器注入 HttpClient），排期 v2.9
- [未通过→排期] Agnes/Qwen 真实 provider 分支（需外部 API）、LlmTransport 真实代理链路（沙箱无外网）

## 已知限制

- 分支 52.7% 中 dto/model 样板代码计入分母，口径既定不排除。
- 覆盖率数字为本机 `mvn -o verify` 实测；CI 环境跑全量后以 CI 为准。
- AuthProxyController 代理分支未覆盖（110 个分支缺口，需可测性重构）。
- Agnes/Qwen 真实 provider 分支未覆盖（需外部 API）。
- LlmTransport 真实代理链路未覆盖（沙箱无外网）。

## v2.9 排期

- AuthProxyController 可测性重构（HttpClient 构造器注入）+ 代理分支测试（目标：该类分支覆盖 ≥60%）。
- 分支覆盖冲 55%（剩余缺口：ChatService/FinalCutService/VideoTaskService 等）。
- Agnes/Qwen 真实 provider 录制回放扩到 probe 之外的 submit/poll 分支（需外部 API 时）。
