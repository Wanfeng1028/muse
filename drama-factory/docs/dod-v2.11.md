# DoD v2.11 — 分支覆盖冲 65%

- 里程碑：v2.11「分支覆盖冲 65%」（对应 docs/dod-v2.10.md 中 v2.11 排期第一项）
- 日期：2026-10-14
- 验证命令：`mvn -o -s ~/workspace/muse-build/m2-settings-noproxy.xml verify`（离线）
- 门禁：JaCoCo LINE 0.78 / BRANCH 0.65（verify 阶段强制；本轮棘轮上调）

## 交付清单

4 批 dpsk 生成，编排者验收应用。

| # | 项 | 交付物 | 验证 |
|---|---|---|---|
| A | UsageService 分支补齐 | `UsageServiceTest` 追加 27 例：三参 `summary` 快速路径（全空/空字符串）/过滤路径（days 正/非正、provider-model 行过滤、step 行 label 为 null/model 不匹配）、`requests`（modelUsed 为 null 跳过、step label 为 null、排序 null 时间三态、limit 截断）、`byDay`（model 过滤/provider 跳过/空 token 按 0 合并/负天数默认）、`byRun`（limit<=0 默认 20、Run 自带总量直用、goal 为 null）、`byModel`（null model/label 跳过）、`filters`（null AgentType 跳过） | 测试通过 |
| B | AgnesVideoProvider.poll 边界 | 新建 `AgnesVideoProviderPollBranchTest` 20 例：鉴权缺失/网关异常/429/500（null body/超长截断/短 body）/非法 JSON/无 status 与 status:null/completed 三取 URL 路径/failed 三取错误信息路径/processing 进度数字-文本-非法/taskId URL 编码 + 鉴权头断言 | 测试通过 |
| C | ScriptSplitterService.callModel 可测性接缝 | 生产代码：新增包可见 `@FunctionalInterface HttpExchange` + 包可见 8 参构造器；public 构造器加 `@Autowired`（双构造器 Spring 显式指定，v2.9/v2.10 同款坑）并委托默认接缝（行为零变更）。新建 `ScriptSplitterCallModelTest` 16 例：鉴权头有/无、发送异常、500 三形态、非法 JSON、choices 缺失/非数组/空/message 为 null/content 为 null/空白、请求体形态、episode 状态推进 | 测试通过 |
| D | EgressProxyConfig 可测性重构 | 生产代码：抽取包可见 `configureFromEnv(Map<String,String>)`，public 无参方法委托 `System.getenv()`（行为零变更）。新建 `EgressProxyConfigTest` 11 例：无变量零副作用/大小写变量优先级/非法 URI/无 host/属性设置/默认端口/ProxySelector 本地直连与远端代理/userInfo 安装 Authenticator/connectFailed 不抛；**@BeforeEach/@AfterEach 保存并恢复 JVM 全局状态**（5 个代理系统属性 + ProxySelector + Authenticator），不污染其他测试 | 测试通过 |

### 验收附带修（编排者）

- `ScriptSplitterService.callModel` 真 bug：大模型返回 `{"content": null}` 时，`message.get("content")` 得 Jackson NullNode，`asText()` 得字符串 `"null"`，旧代码当成有效内容返回，下游解析报 confusing 错误。已修为 `(contentNode == null || contentNode.isNull()) ? null : contentNode.asText()`，与"内容为空抛异常"契约一致；由 C 批 `contentNull` 测试锁定。

### 全量验证数据

- `Tests run: 515, Failures: 0, Errors: 0, Skipped: 0`；BUILD SUCCESS；JaCoCo 新门禁（行 0.78/分支 0.65）通过（`verify -DskipTests` 复核：All coverage checks have been met）。
- 全量行覆盖 **79.1%**（3774/4770），分支覆盖 **67.3%**（1266/1882）——65% 目标超额达成（v2.10：行 75.8%/分支 60.8%）。
- 门禁棘轮：pom JaCoCo LINE 0.75→0.78、BRANCH 0.60→0.65（只升不降）。

## 本轮攻坚记录

1. **dpsk 又漏 @Autowired import。** C 批生产 PATCH 里 public 构造器加了 `@Autowired` 注解但没给 import（v2.10 ChatService 同款遗漏），编排者手工补 `import org.springframework.beans.factory.annotation.Autowired;`。
2. **dpsk 批量裸类型名。** A 批 27 例里 `UsageSummary/RequestUsage/DailyUsage/RunUsage/FilterOptions` 全写成裸名（应为 `UsageService.` 嵌套限定），B 批 `CredentialResolver` 漏 import、C 批 record 访问器写成 `getShotNo()`（应为 `shotNo()`）、B 批 `getUri()`（应为 `uri()`）。编排者逐个修；另注意 `s.replace(bare, qualified)` 会误伤 `findForDailyUsage`→`findForUsageService.DailyUsage`，已精确回滚——以后这类批量改名必须用词边界正则。
3. **DramaV2ApiIntegrationTest.testFullPipeline 偶发 500。** build5 全量跑挂 1 例（final-cuts 期望 201 得 500），单独重跑通过（94s）。与 v2.10 记录的 ffmpeg 环境抖动同类，判 flaky，重跑全量通过。记为已知 flaky。
4. **EgressProxyConfigTest 全局状态隔离。** prompt 里写死红线：@BeforeEach 保存/ @AfterEach 恢复 5 系统属性 + ProxySelector + Authenticator；dpsk 一次做对。

## DoD 对照

- [通过] 测试金字塔补强（新增 74 例：27+20+16+11；四类目标分支大幅收敛）
- [通过] 门禁棘轮（行 0.78/分支 0.65，verify 阶段强制）
- [通过] 技术债有记录（COVERAGE.md 缺口表更新）
- [不适用] 数据库迁移版本化（本轮无表结构变更）
- [不适用] 视觉验收（本轮无 UI 变更）
- [未通过→排期] Agnes/Qwen 真实 provider submit/poll 分支（需外部 API）、LlmTransport 真实代理链路（沙箱无外网）——口径不变

## 已知限制

- 覆盖率数字为本机 `mvn -o verify` 实测；CI 环境跑全量后以 CI 为准。
- `DramaV2ApiIntegrationTest.testFullPipeline` 有偶发 500（ffmpeg 环境抖动），单独重跑通过，记为已知 flaky。

## v2.12 排期

- 分支覆盖冲 70%（剩余大头待 jacoco 实测：RunService 55、SurrogateAuthClient 44（Unix socket 需接缝）、LlmScriptService 43、RunExecutor 36 等；逐个评估可测性）。
- Agnes/Qwen 真实 provider 录制回放扩到 submit/poll（需外部 API 时）。
- AuthProxyController 的 h2c 默认行为：评估是否在 `defaultHttpClient()` 显式 `.version(HTTP_1_1)` 锁定（行为变更，需产品确认，暂不做）。
