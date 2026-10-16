# StageCue v0.4.0 发版对照报告

- 版本：v0.4.0「可观测性收尾」
- 日期：2026-10-16
- 范围：Logback 日志轮转（A 批）+ Prometheus 告警规则与 Alertmanager 示例（B 批）+ docker-compose 资源限制与文档收尾（C 批）
- 对照基准：仓库统一生产级 checklist（8 节）

> 说明：本报告按 checklist 逐条给结论，不回避未通过项。未通过项一律给出排期或声明为已知限制，不写成"通过"。

## 1. 可靠性

| 条目 | 结论 | 说明 |
|------|------|------|
| 服务存活探针 | 通过 | `GET /healthz` 存活检查，探针免限流。 |
| 服务就绪探针 | 通过 | `GET /readyz`，settings 表可读才返回 200 ready，否则 503。 |
| WS 广播背压 | 通过 | 每客户端有界队列（64）+ 专属发送协程，队列满 DROP_OLDEST，慢消费者不断线；丢弃数经 `stagecue_ws_broadcast_dropped_total` 可观测。 |
| IP 限流 | 通过 | 令牌桶限流，非法配置启动即报错退出；超限 429 + `Retry-After`。 |
| 请求超时 | 通过 | 由 Ktor CIO 引擎与 WS ping 超时（30s）覆盖。 |
| 熔断 | 不适用 | 当前为单机应用、无下游 RPC 依赖，无熔断对象；如后续引入外部依赖再评估。 |

## 2. 可观测性

| 条目 | 结论 | 说明 |
|------|------|------|
| 指标端点 | 通过 | `GET /metrics`，Prometheus 文本格式，覆盖 WS 连接、cue 触发/预备、HTTP 请求、限流拒绝数、广播丢弃数、DB 迁移数。 |
| 结构化日志与链路 | 通过 | SLF4J + Logback，HTTP 请求带 `X-Request-Id`（CallId）全链路。 |
| 日志轮转 | 通过 | A 批：控制台 + 文件双输出，日志目录 `STAGECUE_DATA_DIR/logs`（Main.kt 内 `resolveLogDir(dataDir)` 计算，系统属性 `stagecue.log.dir` 传入，未设置默认 `./data/logs`）；按天轮转 + 单文件 50MB 切分，保留 14 天，总量上限 512MB；root 级别跟 `STAGECUE_LOG_LEVEL`；`org.flywaydb` 与 `io.ktor` 只记 WARN 以上。 |
| 告警规则 | 通过 | B 批：`docs/alerts/stagecue.rules.yml` 5 条规则（StageCueDown[critical]、StageCueWsDisconnectSpike[warning]、StageCueRateLimitSpike[warning]、StageCueBroadcastDrop[warning]、StageCueDbMigrationStuck[warning]），`server/src/main/resources/alerts/stagecue.rules.yml` 为随发行版分发的同内容拷贝；`docs/alerts/alertmanager.example.yml` 给出邮件 + 企业微信 webhook 占位；`docs/OPERATIONS.md` 新增"## 告警规则"节。 |
| 告警规则真机联调 | 未通过 | 规则文件与接收器示例已就位，但未在真实 Prometheus/Alertmanager 实例上做端到端触发演练。**排期**：v0.5 起在部署环境接入 Prometheus + Alertmanager 后补一次 firing 演练，并把演练记录补进本报告。 |

## 3. 数据与状态

| 条目 | 结论 | 说明 |
|------|------|------|
| 版本化迁移 | 通过 | SQLite + Flyway 版本化迁移（v0.2.0 起）。 |
| 旧数据导入 | 通过 | 旧版 `show.json` 幂等导入。 |
| 备份恢复 | 通过 | v0.2.0 已真实演练通过（SQLite 单文件，备份即拷贝）。 |
| 排练模式状态持久化 | 通过 | 服务端真实开关，重启不丢失。 |
| 多人同时编辑同一份 show | 未通过 | 未支持，当前为单导演假设。**声明为已知限制**，二期（v0.5+）支持，协议已留 `ClientRole.MONITOR/LIGHTING` 位。 |

## 4. 部署与运维

| 条目 | 结论 | 说明 |
|------|------|------|
| 容器化编排 | 通过 | `docker-compose.yml` 仅编排 server（desktopApp 是本地 GUI，不进 compose），挂载 `installDist` 产物运行。 |
| 资源限制 | 通过 | C 批：`deploy.resources.limits`（cpus `'1.0'`、memory `512M`）+ `reservations.memory 128M`。单机 compose 下需 `--compatibility` 或 swarm 才完全生效，已在文件内以注释说明，作为声明式约束。 |
| 容器日志轮转 | 通过 | C 批：json-file driver，`max-size: "10m"`、`max-file: "5"`，防止长期运行打爆磁盘。 |
| 数据卷持久化 | 通过 | `./data:/app/data`，日志落在数据卷内 `/app/data/logs`。 |
| 滚动更新 / 零停机 | 未通过 | 单机应用，停机更新。**声明为可接受限制**：演出前窗口更新，不追求零停机。 |
| 桌面端运行验收 | 未通过 | 桌面 UI 运行时截图未验收：VM 缺 `libXtst.so.6` 系统库，Compose Desktop 无法启动；代码已全量编译通过。**排期**：有 GUI 环境后补截图验收。 |

## 5. 安全与健壮性

| 条目 | 结论 | 说明 |
|------|------|------|
| 启动配置校验 | 通过 | 非法配置启动即报错退出（含限流参数）。 |
| 限流保护 | 通过 | IP 令牌桶，超限 429 + `Retry-After`（秒）+ JSON 错误体。 |
| 探针免限流 | 通过 | `/healthz`、`/readyz`、`/metrics` 免限流，避免探针被限流误判。 |
| 依赖更新机制 | 未通过 | 无 Dependabot。**声明为仓库级事项**，跟仓库统一配，不在本项目单独立项。 |
| 认证 / 授权 | 不适用 | 局域网单机部署、单导演使用场景，当前版本未引入账户体系；如后续多用户场景再评估。 |

## 6. 可维护性

| 条目 | 结论 | 说明 |
|------|------|------|
| 测试金字塔 | 部分通过 | 有单元测试 + 集成测试（ktor test host）；**无 E2E 真机测试**。**排期**：E2E 依赖 GUI 环境，与桌面端验收一起补。 |
| 技术债登记与关闭 | 通过 | `docs/TECH_DEBT.md` 每轮发版前更新，本轮关闭"告警规则""日志轮转 / 资源限制"两项。 |
| 变更日志 | 通过 | `CHANGELOG.md` 按 Keep a Changelog 中文格式，v0.4.0 条目已补。 |
| 运维文档 | 通过 | `docs/OPERATIONS.md` 新增"## 告警规则"节（规则加载、5 条告警含义与排查）。 |

## 7. 发版对照

| 条目 | 结论 | 说明 |
|------|------|------|
| 版本号与日期 | 通过 | v0.4.0 / 2026-10-16，CHANGELOG、本报告、PROJECTS 条目草稿一致。 |
| 新增能力可追溯 | 通过 | A 批日志轮转、B 批告警规则、C 批 compose 资源限制均在 CHANGELOG 与 README 有对应描述。 |
| 未通过项显式列出 | 通过 | 见第 2、3、4、5、6 节"未通过 / 部分通过"条目。 |
| 随发行版分发的规则文件 | 通过 | `server/src/main/resources/alerts/stagecue.rules.yml` 为 `docs/alerts/stagecue.rules.yml` 的同内容拷贝。 |

## 8. 周期机制

| 条目 | 结论 | 说明 |
|------|------|------|
| 每轮发版更新技术债表 | 通过 | TECH_DEBT.md 已按轮次分节（v0.2.0 / v0.3.0 / v0.4.0 已偿还 + 剩余债务表）。 |
| 每轮发版产出对照报告 | 通过 | 本报告即为 v0.4.0 对照报告，后续版本沿用同结构。 |
| 未通过项带回下轮 | 通过 | 本报告"未通过"项已写明排期或已知限制，交由下轮 checklist 复核。 |

## 附：本轮未通过项汇总（带回下轮）

1. 告警规则真机联调（Prometheus/Alertmanager firing 演练）——排期 v0.5。
2. 多人同时编辑同一份 show——二期。
3. 滚动更新 / 零停机——声明为可接受限制（演出前窗口更新）。
4. 桌面 UI 运行时截图验收——待 GUI 环境（VM 缺 `libXtst.so.6`）。
5. 依赖更新机制（Dependabot）——仓库级事项，跟仓库统一配。
6. E2E 真机测试缺失——与桌面端验收一起补。
