# 发版对照报告：drama-factory v2.7（生产级补强第 6 轮）

日期：2026-10-14。DoD 第 6 轮排期四项（见 docs/dod-v2.6.md）：stats() 多用户口径 / CameraMove.fromLabel 行为 / 覆盖率 55% / LlmTransport·RunExecutor·providers 测试，**四项全交付**。

## 交付清单

| # | 项 | 交付物 | 验证 |
|---|---|---|---|
| 1 | stats() 多用户口径 | `ProjectService.stats()` 按 `currentUserId` 统计名下项目/剧集/角色/场景（`DramaProjectRepository` 新增 `countByOwnerId`）；`RunService.stats()` 只统计名下项目的 run（构造器新增 `CurrentUser`/`DramaProjectRepository` 注入）；`GET /api/stats` 与 `GET /api/runs/stats` 的 `@Operation` 文案同步；API 路径与响应字段零变更；`DramaMetrics` 保持全局口径 | `mvn -o verify` 180/180；新增 `StatsIsolationTest` 2 例（MockMvc：项目统计隔离、run 统计隔离）；开放模式（全 local）行为与旧全局口径一致 |
| 2 | CameraMove.fromLabel 行为变更 | `CameraMove.fromLabel`：null→null、空白→null、非法非空标签→抛 `IllegalArgumentException("未知的运镜标签: X")`，与 `ShotSize.fromLabel` 一致；`ScriptSplitterService` 两处 `try/catch(IllegalArgumentException)` 不再是死代码；`parseShotsJson` 非法运镜报错"第 N 个分镜的字段 cameraMove 非法: X"而非静默 null；`ShotSize.fromLabel` 未动 | `mvn -o verify`：`CameraMoveTest` 5 例通过；`ScriptSplitterServiceTest` 锁定旧行为的用例改为断言抛异常 |
| 3 | 覆盖率 55% | JaCoCo `minimum` 0.51→0.55；新增 40 例测试后实测行覆盖 51.3%→**58.5%**、分支 31.0%→**37.5%** | `mvn -o verify`：LINE 2669/4564 = 58.5%，BRANCH 640/1706 = 37.5%，门禁 0.55 通过 |
| 4 | LlmTransport·RunExecutor·providers 测试 | `LlmTransportTest` 17 例（代理纯函数/请求构建/注入执行体的状态码与异常契约/密码不泄露）、`MockVideoProviderTest` 6 例、`RunExecutorTest` 10 例（Mockito 编排）、`StatsIsolationTest` 2 例、`CameraMoveTest` 5 例，共 40 例；`LlmTransport` 抽出 `ProxySpec` + 纯函数 + `HttpExecutor` 函数式 seam（零行为变更） | `mvn -o verify`：Tests run 180, Failures 0, Errors 0, Skipped 0；BUILD SUCCESS |

## 本轮攻坚记录

1. **Call A 首版整批作废**：dpsk 凭空编造 `com.dramafactory.api` 包、写错 Records 包路径、擅改 `requireOwnedProject` 异常类型、丢方法加 noop 占位。打回后改**外科手术式 PATCH**（OLD 片段逐字锚定原文）+ 把相关文件真实内容贴进 prompt 当事实来源。
2. **applier 两次残留清理**：dpsk 在 NEW 片段尾部带出 `=== END` / `--- END` 标记行，编排者用脚本清除并收紧空行。
3. **LlmTransportTest 编译坑**：`org.apache.hc.client5.http.impl.classic.CloseableHttpResponse` 是 final 类，不可匿名继承——seam 改为 `HttpExecutor` 函数式接口，测试用 `ClassicResponseBuilder`（httpcore5 5.2.5 实测存在）构造 `ClassicHttpResponse`。
4. **buildPost 测试**：`HttpPost.getUri()` 抛 checked `URISyntaxException`，测试方法加 `throws Exception`。
5. **全量跑时 StatsIsolationTest 曾失败 1 例**：`DramaV2ApiIntegrationTest` 无 `@Transactional`，在共享 H2 mem 库留下 `ownerId=local` 的项目，污染"local 口径 projects=0"断言——改为 delta 断言（只验证本测试不污染 local 口径），不碰其他测试类。
6. **RunServiceTest**：构造器新增 `CurrentUser`/`DramaProjectRepository` 两个 mock 参数；stats 用例按新口径 stub。
7. **Scene 模型无 setTitle**（dpsk 编造），改为 `setLocation`。

## DoD 对照（本轮相关项）

- [通过] 测试金字塔大幅补强（40 新增；LlmTransport 无 socket 契约测试、RunExecutor 全 mock 编排测试、MockVideoProvider 测试）
- [通过] 错误处理策略明确（CameraMove 非法标签抛 IAE，与 ShotSize 一致；CHANGELOG 记录行为变更）
- [通过] tenant/user 多用户设计（stats() 按 owner 隔离；子实体经由项目继承隔离延续）
- [通过] 技术债有记录（COVERAGE.md 缺口表更新 + v2.8 排期）
- [通过] 代码与文档同步（CHANGELOG/COVERAGE/dod-v2.7；OpenAPI 文案同步）
- [不适用] 数据库迁移版本化（本轮无表结构变更，无新 Flyway 脚本）
- [不适用] 视觉验收（本轮无 UI 变更）
- [部分通过] 测试金字塔：集成/E2E 仍缺（Agnes/Qwen 真实 provider 需外部 API、Run 端到端全链路）→ 排期 v2.8

## 已知限制

- stats() 实现为 N+1 count（每项目查一次），个人自托管量级可接受；若项目数上千需改聚合查询。
- Run.stats() 中 projectId 为空或指向已删项目的孤儿 run 不计入（javadoc 已注明）。
- DramaMetrics 业务指标保持全局口径（运维视角），与用户 stats 口径分离。
- E2E 缺口：Run 全链路（建 run→多 step→审批→成片）的端到端测试仍无，排期 v2.8。

## v2.8 排期

- E2E：Run 全链路 MockMvc 端到端测试。
- Agnes/Qwen provider 契约测试（录制回放）。
- 分支覆盖冲 45%。
- stats() 聚合查询优化（若需要）。
