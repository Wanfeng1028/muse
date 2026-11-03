# v3.0 发版对照报告（dod-v3.0）

版本：v3.0 审核流
日期：2026-10-19
说明：本报告逐条对照检查清单给出结论。结论只依据已有事实，没有实测或没有记录的一律标为未验证或未通过。

## 1. 可靠性

- [通过] 测试金字塔：新增 41 例测试。ReviewServiceTest 29 例为状态机单测，覆盖并发版本冲突、幂等重入、非法流转；ReviewApiTest 9 例为 MockMvc 集成测试，覆盖跨项目 403、kind 不匹配 404、非法流转 409；RunExecutorReviewGateTest 3 例为执行门测试，覆盖拦截 PAUSED、放行提交、非 VIDEO 不受影响。
- [通过] 关键路径失败注入：RunExecutorReviewGateTest 覆盖执行门拦截路径（未过审 run 置 PAUSED），非法流转由 ReviewServiceTest 和 ReviewApiTest 覆盖。
- [通过] 错误处理策略写进文档：ReviewConflictException 经 GlobalExceptionHandler 返回 409；目标状态已是当前状态时幂等返回 changed=false；ReviewItem 用 @Version 乐观锁防并发提交。策略已写入 docs/REVIEW_FLOW.md。
- [通过] 数据库迁移版本化：Flyway V18__review_flow.sql，建 review_item 和 review_history 两张表，episode 删除级联，JPA @OnDelete 同步。
- [未通过] 健康检查端点、就绪探针、优雅关闭：本轮没有新增或改动这三项，没有实测记录。
排期/已知限制：属于项目既有能力范围，v3.0 未涉及，未验证现状，排期未定。

## 2. 可观测性

- [通过] 结构化日志和 request_id：关键路径有 slf4j 日志，包含等待剧本过审的日志。
- [不适用] request_id 新增：项目现有水平即已具备，本轮未新增，按本轮范围不适用。
- [未通过] 关键指标（请求量/延迟/错误率/队列积压）：本轮未新增 Prometheus 指标。
排期/已知限制：指标接入未排期，列为已知限制。
- [通过] 报错可定位到请求和代码：409 等错误由 GlobalExceptionHandler 统一处理，关键路径有日志，可定位到对应代码位置。
- [未通过] 基础告警规则：本轮没有新增告警规则，没有相关记录。
排期/已知限制：告警规则未排期，列为已知限制。

## 3. 数据与状态

- [未通过] 自动备份加一键恢复实测：项目有 docs/OPERATIONS.md，但本轮未新增自动备份实测。
排期/已知限制：本轮未做备份恢复实测，依赖 docs/OPERATIONS.md 现有内容，排期未定。
- [通过] 敏感数据策略：审核意见 comment 明文存库，本轮无新增敏感字段，现状已记录。
- [未通过] 配置与密钥分离、启动校验：本轮没有新增或改动配置与密钥分离及启动校验，无实测记录。
排期/已知限制：本轮未涉及，未验证现状，排期未定。
- [通过] tenant/user 落地：沿用项目现有 CurrentUser，审核 API 校验项目归属，跨项目返回 403。

## 4. 部署与运维

- [未通过] Docker Compose 一键部署：本轮没有新增或改动 Compose 配置，无实测记录。
排期/已知限制：本轮未涉及，未验证现状，排期未定。
- [未通过] 滚动更新与零停机说明：本轮没有相关说明或改动。
排期/已知限制：本轮未涉及，未验证现状，排期未定。
- [未通过] 资源限制、日志轮转、数据卷：本轮没有相关改动或记录。
排期/已知限制：本轮未涉及，未验证现状，排期未定。
- [通过] 运维手册：项目有 docs/OPERATIONS.md。

## 5. 安全与健壮性

- [通过] 输入校验、防注入、基础鉴权：审核 API 使用 @Valid 做输入校验；防注入沿用项目现有方案；鉴权沿用项目现有 CurrentUser，并校验项目归属，跨项目返回 403。
- [通过] 自审处理：单用户部署下自审不硬拦截，改为 ReviewDetailResponse.selfReviewed 透明标记加前端醒目提示，该设计权衡记录在 docs/REVIEW_FLOW.md v3.0a。
- [未通过] 依赖更新机制：本轮没有新增或改动依赖更新机制，无记录。
排期/已知限制：本轮未涉及，未验证现状，排期未定。
- [未通过] 限流、超时、熔断：本轮没有新增或改动限流、超时、熔断，无记录。
排期/已知限制：本轮未涉及，未验证现状，排期未定。

## 6. 可维护性

- [通过] 模块边界与 API 契约：审核流设计文档为 docs/REVIEW_FLOW.md，OpenAPI 已加 @Operation 注解。
- [通过] CHANGELOG 与升级指南：README 和 CHANGELOG 已同步。
- [通过] 技术债记录：已知限制已记录，包括全量 mvn verify 的预先失败项、冒烟覆盖范围、单用户自审设计权衡。
- [通过] 代码与文档同步：设计文档 docs/REVIEW_FLOW.md 与 README、CHANGELOG 已同步更新。
- [通过] 测试覆盖门禁配置：JaCoCo 门禁 LINE 0.92、BRANCH 0.94，在 pom 中锁定，只升不降。
- [未通过] 全量覆盖率门禁实测：全量 mvn verify 因预先失败项未达 check 阶段。新增代码单独测量：ReviewService 行 93.2%/分支 72.7%，ReviewController 行 71.4%/分支 50.0%，ReviewQueueController 行 100%，ReviewConflictException 行 100%。
排期/已知限制：全量门禁待预先失败项修复后实测，列为已知限制。

## 7. 发版前对照报告

- [通过] 本文件即 v3.0 发版对照报告，逐条对照检查清单给出结论。
- [通过] 冒烟验证：review API 全链（提交、一审、二审、过审、历史）用真实 jar 跑通；Run 放行门由 Spring 集成测试覆盖。无 AI 凭证，真实 run 跑不到 VIDEO 步，该限制已记录。
- [通过] 测试结果：v3.0 相关测试全绿。全量 mvn verify 存在预先失败项，与 v3.0 无关。
- [通过] 附带修复：修复预先损坏的 ScriptSplitterServiceDeepTest 反射构造 12 例，该问题为 Toonflow 移植落下，非本轮引入。

## 8. 周期机制

- [未通过] 技术债清理轮：本轮没有固定的技术债清理轮安排。
排期/已知限制：本轮未建立周期机制，排期未定。
- [未通过] 真实负载验证：本轮没有真实负载验证记录。冒烟为单链真实 jar 跑通，不构成负载验证。
排期/已知限制：本轮未做，排期未定。
- [未通过] 故障演练抽查：本轮没有故障演练记录。
排期/已知限制：本轮未做，排期未定。

## 已知限制汇总

1. 全量 mvn verify 存在预先失败项：canvas 切片1 在制品中、ffmpeg 需本机二进制、Qwen 需外网、PromptRecipe 在制品中、EgressProxyConfigTest 被 VideoPipelineNovaiE2eTest 的全局代理设置污染。这些与 v3.0 无关，v3.0 相关测试全绿。
2. 冒烟覆盖范围有限：review API 全链（提交、一审、二审、过审、历史）用真实 jar 跑通，Run 放行门只由 Spring 集成测试覆盖；无 AI 凭证，真实 run 跑不到 VIDEO 步。
3. 单用户自审为已知设计权衡：单用户部署下自审不硬拦截，改为 ReviewDetailResponse.selfReviewed 透明标记加前端醒目提示，记录在 docs/REVIEW_FLOW.md v3.0a。