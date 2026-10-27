# 发版对照报告 v0.33.0：单监控延迟趋势

范围：Store 层 MonitorMonthlyLatency / MonitorLatencyTrend、Handlers 层 JSON / HTML / 页面三接口、控制台页 /monitor-latency-trend、19 页导航链追加、鉴权精确名单。无 schema 变更、无新环境变量、无依赖变更。

## 对照

- 测试金字塔：通过（部分）。单元与集成：store 新测 3 函数、handlers 新测 2 函数、web 新测 3 函数全部通过；store / handlers / web 三包全量通过。未通过：全量 go test ./... 本轮未跑（含 notify 慢包约 240 秒），排期下一轮补跑；新功能靶向覆盖已齐，不阻塞本版。
- 失败注入：不适用（本版为只读聚合查询，无外部调用链；失败检查排除已由双月测试覆盖）。
- 错误处理：通过。非法 end/months 返回 400（复用 parseSiteSLATrendParams 文案）；不存在的监控返回 404“监控不存在”；months 越界与月份越界均在 Store 层先校验。
- 数据库迁移：不适用（无 schema 变更，复用 checks 表既有查询）。
- 健康检查与优雅关闭：通过（既有 /healthz /readyz 与优雅关闭未动）。
- 结构化日志与 request_id：通过（既有中间件未动；冒烟日志含 request_id）。
- 指标与告警：不适用（本版未新增指标；既有 /api/metrics 未动）。
- 自动备份与一键恢复：通过（既有机制未动；冒烟使用隔离库与隔离备份目录，仓库 data/backups 未写入）。
- 敏感数据：通过（本版不处理敏感数据；冒烟 token 仅为隔离环境测试令牌）。
- 配置与密钥分离：通过（无新增配置；既有 SENTINEL_API_TOKEN 启动校验未动）。
- 多用户设计：通过（监控归属复用既有 tenant 字段；本版不改变隔离语义）。
- Docker Compose 一键部署：通过（既有 compose 未动；本版无新增端口与数据卷）。
- 资源限制与日志轮转：通过（既有 compose 限制未动）。
- 运维手册：不适用（无新增运维操作；API 与页面用法已记入 README 与 CHANGELOG）。
- 输入校验与鉴权：通过。数据接口均需鉴权（页面壳走既有白名单口径）；id 非法返回 400；SQL 全部参数化，无拼接。
- 依赖扫描：不适用（无依赖变更；上次全量扫描见 docs/dependency-scan-20261017.json）。
- 限流超时熔断：通过（既有 webhook 限流与熔断未动；本版查询为本地 SQLite 短查询）。
- 模块边界与 API 契约：通过。Store / Handlers / Web 三层与 v0.31.0 / v0.32.0 同构；JSON 字段与 HTML 导出字段已在 CHANGELOG 与测试中锁定。
- CHANGELOG 与升级指南：通过。CHANGELOG 新增 [0.33.0] 一节；升级无需迁移、无需改配置，平滑替换二进制即可。
- 技术债记录：通过。已知限制见下；无新增技术债（导航链 20 项在 1600 宽视口溢出属既有导航增长趋势，已记入限制，不属本版回归）。
- 文档代码同步：通过。README 特性、截图、API 表三处已同步；截图为真实数据状态。

## 验收实测

- go build ./... 通过；go vet（store / handlers / web）全洁；gofmt 全洁。
- 靶向测试：store 全包、handlers 全包、web 全包全绿；新测：store 3 函数、handlers 2 函数、web 3 函数。
- 真实服务冒烟：隔离服务 18503 端口，冒烟脚本 10/10（建监控、CheckNow、趋势 JSON 空月与实测月、404、months 400、end 400、HTML、页面壳）。
- 视觉验收：docs/screenshots/monitor-latency-trend-v033.png 已亲眼核对（20 链齐全、新页 active、截图UP、2026-10、成功检查总数 2、10 月 5.50/5.95/5.99/5.50、p95 蓝条 5.95 ms）。

## 已知限制

- 全量 go test ./... 本轮未跑（notify 慢包约 240 秒），排期下一轮补跑；靶向包已全绿。
- 导航链已达 20 项，1600 宽视口下末尾会被裁切（1920 宽可完整显示）；是否改导航折叠或横向滚动属产品决策，本轮未改。
- 截图 harness 的内联与路由代理改写仅限截图环境，产品代码未动。

## 结论

靶向范围可发版（v0.33.0）。全量测试缺口已排期，不阻塞本版。
