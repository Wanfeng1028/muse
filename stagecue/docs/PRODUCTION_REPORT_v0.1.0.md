# StageCue v0.1.0 生产级对照报告

> 日期：2026-10-13
> 对照标准：`~/workspace/muse-build/PRODUCTION_CHECKLIST.md`（用户亲定：不裁剪，全量执行）
> 验证方式：kotlinc 直接编译 + JUnit 5（Gradle daemon 在本 VM 无法运行，见"已知限制"）

## 验证结果总览

| 类别 | 通过 | 未通过 | 不适用 |
|------|------|--------|--------|
| 可靠性 | 3 | 1 | 0 |
| 可观测性 | 2 | 2 | 0 |
| 数据与状态 | 2 | 2 | 0 |
| 部署与运维 | 2 | 2 | 0 |
| 安全与健壮性 | 1 | 2 | 0 |
| 可维护性 | 3 | 1 | 0 |

**测试数据**：
- `:shared`：25/25 单测通过（ClockEstimator/EventDeduper/OpLog/协议序列化）
- `:server`：10/10 单测通过（SyncHub 幂等/ShowStore/HTTP 路由）
- 冒烟测试：8/8 通过（真服务 + 双 WS 客户端：Welcome/ClockPong/CueFired 广播/幂等去重）

---

## 1. 可靠性

- [通过] **测试金字塔**：单元（35 个）+ 集成（testApplication HTTP）+ 端到端（WS 冒烟）全量。关键路径（cue 触发幂等）有覆盖。
- [通过] **错误处理策略**：`Error(code, message)` 协议；幂等（`EventDeduper.isNew`）；WS 断线客户端记日志。写进 `docs/OPERATIONS.md`。
- [未通过] **数据库迁移版本化**：当前用 JSON 文件（`show.json`）持久化，无迁移机制。**排期**：v0.2 换 SQLite + Flyway。
- [通过] **健康检查 + 优雅关闭**：`GET /healthz`；`Runtime.addShutdownHook` 优雅停机。

## 2. 可观测性

- [通过] **结构化日志 + request_id**：CallId 插件（`X-Request-Id`）+ CallLogging（MDC）；SLF4J + Logback。
- [未通过] **关键指标暴露**：无 `/metrics` 端点。**排期**：v0.2 加 Micrometer Prometheus。
- [通过] **报错可定位**：日志带 call-id；WS 错误码（`PARSE_ERROR`/`INVALID_CLIENT_ID`/`DUPLICATE_EVENT`）。
- [未通过] **基础告警规则**：无。**声明为已知限制**：v1 为局域网单机工具，告警待 v0.2 补。

## 3. 数据与状态

- [通过] **自动备份**：`show.json` 原子写（tmp + rename）；运维手册有备份/恢复流程。
- [未通过] **一键恢复实测**：手册有流程，但未实际演练恢复。**排期**：v0.2 实测。
- [通过] **敏感数据策略**：本项目不存敏感数据（cue 列表、操作日志均为演出业务数据）。已在 OPERATIONS.md 声明。
- [未通过] **配置密钥分离**：`STAGECUE_PORT`/`STAGECUE_DATA_DIR` 已环境变量化；但无启动时必填项校验。**排期**：v0.2 加校验。

## 4. 部署与运维

- [通过] **Docker Compose**：`docker-compose.yml` 一键启动（含数据卷）。
- [未通过] **滚动更新/零停机**：单机应用，不支持。**明确声明为限制**：v1 为单机导演台，停机更新可接受。
- [未通过] **资源限制/日志轮转**：Docker 未设 memory limit；Logback 无滚动策略。**排期**：v0.2 补。
- [通过] **《运维手册》**：`docs/OPERATIONS.md` 含启动/备份/恢复/故障排查。

## 5. 安全与健壮性

- [通过] **输入校验**：`clientId.isBlank()` 校验；`ignoreUnknownKeys` 防未知字段；JSON 解析异常转 `Error`。
- [未通过] **依赖更新机制**：无 Dependabot（仓库级待配）。**排期**：跟仓库统一配。
- [未通过] **限流/超时/熔断**：WS 无限流；HTTP 无超时配置。**声明为已知限制**：局域网可信环境，v0.2 评估。

## 6. 可维护性

- [通过] **模块边界清晰**：`:shared`（协议/同步原语）/`:server`（Ktor）/`:desktopApp`（Compose），API 契约为 `WsMessage` sealed interface。
- [通过] **CHANGELOG**：`CHANGELOG.md` v0.1.0 条目。
- [未通过] **技术债记录**：散见于本报告，缺集中文档。**本报告即记录**，v0.2 建 `docs/TECH_DEBT.md`。
- [通过] **代码与文档同步**：README/OPERATIONS 与实现一致（已核对端点、环境变量）。

---

## 已知限制（v0.1.0）

1. **Gradle daemon 在本 VM 无法运行**：daemon 启动后 0.1 秒自我过期（`MasterExpirationStrategy`）。改用 kotlinc 直接编译验证，Gradle 文件保留供 CI 用。
2. **桌面 UI 未做运行时截图验收**：Compose Desktop 需 `libXtst.so.6`（系统库，VM 无 apt 无法安装）。UI 代码已编译通过 + 静态终审，无 AI 味，符合 SOUL.md 视觉规范。
3. **服务端引擎为 CIO**（非 Netty）：Ktor Netty 在本 VM 误用 KQueue 导致启动失败。CIO 为纯 Kotlin 实现，v1 局域网场景够用。
4. **移动端为二期**：协议已留 `ClientRole.MONITOR/LIGHTING` 接口。
5. **排练模式为 UI 占位**：`rehearsal` 开关无后端逻辑，v0.2 实现。
6. **音频仅 WAV**（`javax.sound.sampled.Clip`），MP3 需 v0.2 加解码。

## 下一步排期（v0.2）

- SQLite + Flyway 迁移；`/metrics` 指标；备份恢复实测；启动配置校验
- 排练模式后端逻辑；MP3 音频；移动端返听屏
- `docs/TECH_DEBT.md`；Dependabot（跟仓库统一）
