# linkshort 发版对照报告 v1.2

日期：2026-10-14
对照版本：v1.1 报告（docs/PRODUCTION_CHECKLIST_REPORT_v1.1.md）
结论：**可发版**（v1.1 的条件项已全部关闭）

## 可靠性

| 项 | 状态 | 理由 |
| --- | --- | --- |
| 失败注入（关库后行为） | 通过 | 构造已关闭 DB 的服务，跳转 500、建链 500、health 仍 200、readyz 503、/metrics 仍 200，全程不 panic。 |
| 存活探针 | 通过 | `/api/health` 语义明确为存活，进程活着就 200。 |
| 就绪探针 | 通过 | 新增 `/api/readyz`，DB ping 通 200 否则 503，配套 `store.Ping()`。 |
| 限流 | 通过 | IP + API Key 双维度令牌桶，超限 429 + Retry-After: 1，探针与 /metrics 免限流。 |
| 高并发 clicks 检查 | 未通过 | 单连接串行写入缓解，未做分布式锁。 |
| `-race` 测试 | 通过 | 全过。 |

## 可观测性

| 项 | 状态 | 理由 |
| --- | --- | --- |
| Prometheus 指标 | 通过 | `GET /metrics`，零外部依赖手写文本 exposition，路由 label 取 chi RoutePattern 归一化。 |
| 指标覆盖 | 通过 | 请求/跳转/burn/限流拒绝计数 + 进程启动时间。 |
| 鉴权与免限流 | 通过 | /metrics 不走鉴权，且与 /api/health、/api/readyz 一起免限流。 |

## 数据

| 项 | 状态 | 理由 |
| --- | --- | --- |
| CSV 导入导出 7 列 | 通过 | 列扩展为 slug,url,title,enabled,expires_at,max_visits,burn；旧 5 列仍可导入。 |
| CSV 非法组合处理 | 通过 | burn+max_visits≠1、max_visits 越界/非数字、burn 非 bool 记错跳过。 |
| burn 销毁后数据保留 | 未通过 | 销毁后数据仍保留在库，可查统计。 |
| 备份恢复自动化演练 | 未通过 | 未做自动化演练。 |

## 部署运维

| 项 | 状态 | 理由 |
| --- | --- | --- |
| 运维手册 | 通过 | 新建 docs/OPERATIONS.md，覆盖部署/配置/备份恢复/升级/监控/排障/限流调参。 |
| 限流可配置 | 通过 | RPS/BURST/开关走环境变量，默认 20/40/true。 |

## 安全

| 项 | 状态 | 理由 |
| --- | --- | --- |
| API Key 鉴权 | 通过 | 沿用 v1.1 鉴权，未变更。 |
| 限流防护 | 通过 | 双维度令牌桶降低滥用风险，超限明确 429 响应。 |
| /metrics 暴露 | 不适用 | 按设计不走鉴权，部署侧需自行做网络隔离。 |

## 可维护性

| 项 | 状态 | 理由 |
| --- | --- | --- |
| 新增测试 | 通过 | 新增 24 例（metrics 5、ratelimit 6、handler 中间件集成 3、CSV 扩展 4、失败注入 6），go test ./... 全过。 |
| 依赖控制 | 通过 | /metrics 零外部依赖，手写文本 exposition。 |

## 真实服务冒烟

冒烟地址 127.0.0.1:18092，6 项结果：

1. /metrics 可抓，Prometheus 格式正常 — 通过
2. RPS=5 / BURST=3 下 10 连击出现 429，含 Retry-After 与 error body — 通过
3. burn 链 302→410 回归 — 通过
4. CSV 导出 7 列表头验证 — 通过
5. 存活/就绪探针行为符合预期 — 通过
6. 全程无 panic — 通过

## 已知缺口

1. 高并发 clicks 检查：单连接串行写入缓解，未做分布式锁。
2. burn 销毁后数据仍保留在库，可查统计。
3. 备份恢复未做自动化演练。
