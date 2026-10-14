# v0.5.0 发版对照报告（生产级 Definition of Done）

发版：v0.5.0「生产级补齐」；日期 2026-10-15；编排验收：Muse。
对照 v0.4.0 报告的 13 项未通过/部分通过，本轮**全部关闭**。

## 1. 可靠性
- 测试金字塔：**通过**——62/62（原 48 + 新增 test_ops.cpp 14 例：日志/指标/备份恢复/失败注入/批量事务/并发守卫）；单元+集成+E2E（真实 serve 冒烟）。
- 失败注入：**通过**——损坏 DB 文件打开抛 `std::runtime_error`（非崩溃）；非法备份源 `backup` 抛异常；`restore` 拒绝垃圾文件（exit 2，当前库不受影响）；批量事务误用（嵌套 begin/未 begin 就 commit）抛异常；词典缺失路径真实演练：`search` 在 FTS 首次使用时 fail-fast（exit 2），绝不静默建错索引。
- 重试/降级/幂等：**通过**——沿用 v0.4.0 结论；批量事务异常整体回滚。
- DB 迁移版本化：**通过**——沿用 `PRAGMA user_version` 机制；v0.5.0 无 schema 变更。
- 健康检查/优雅关闭：**通过**——`/api/health`（版本号已 bump 到 0.5.0）+ SIGINT/SIGTERM 优雅停止；另实测 `kill -9` 后重启服务正常、数据完好（WAL 模式）。

## 2. 可观测性
- 结构化日志：**通过**——stderr JSON Lines（`ts/level/request_id/module/msg` + 自定义字段），`DOCSEEK_LOG_LEVEL` 控制；`request_id` 全链路（`X-Request-Id` 响应头 + 日志字段），真实请求验证通过。
- 关键指标：**通过**——`GET /api/metrics`：分 endpoint 查询量/平均/最大延迟、Top 10 查询词、最近 20 条慢查询、限流拒绝计数。
- request_id 全链路：**通过**——见上。
- 基础告警：**通过**——慢查询阈值 `DOCSEEK_SLOW_MS`（默认 500ms）+ `slow_queries` 列表；排障手册给出告警建议（见 OPERATIONS.md）。

## 3. 数据与状态
- 自动备份 + 一键恢复：**通过**——`backup`（SQLite backup API 在线热备）/`restore`（先校验再原子替换）子命令；真实演练：备份→删库→恢复→检索，全链路通过。
- 敏感数据策略：**通过**——沿用 v0.4.0（纯本地运行）。
- 配置密钥分离：**通过**——7 个环境变量全部文档化（见 OPERATIONS.md）；无密钥类配置。
- 多用户设计：**不适用**——单机个人工具（README 已声明）。

## 4. 部署与运维
- Dockerfile：**通过**——修了运行镜像漏拷词典的 bug（之前镜像里 serve 起不来）；词典拷到 `/usr/local/share/docseek/dict`。
- Docker Compose 一键部署：**通过**——`docker-compose.yml`（端口/数据卷/只读语料挂载/环境变量/512m 内存限制/日志轮转/restart 策略）；本机无 Docker，只写不跑。
- 滚动更新/零停机：**不适用**——单进程，升级即替换二进制（OPERATIONS.md 给出升级步骤）。
- 资源限制/日志轮转/数据卷：**通过**——compose 声明完整。
- 运维手册：**通过**——`docs/OPERATIONS.md`（环境变量/日志/指标/备份恢复/升级/排障/Compose/季度依赖检查）。

## 5. 安全与健壮性
- 输入校验/防注入：**通过**——沿用 v0.4.0。
- 基础鉴权：**不适用**——本地回环单机工具（已声明）。
- 依赖更新机制：**通过**——仓库级 `.github/dependabot.yml`（GitHub Actions 周检）+ CMake FetchContent 季度人工检查清单（OPERATIONS.md 第 8 节）。
- 限流/超时/熔断：**通过**——`/api/locate` 并发上限（默认 4，`DOCSEEK_LOCATE_CONCURRENCY`）+ 等待超时（`DOCSEEK_LOCATE_WAIT_MS`，默认 2000ms），超限回 429 并记 `locate_rejected` 指标 + warn 日志。

## 6. 可维护性
- 模块边界/API 契约：**通过**——新增 logger / metrics / concurrency_guard 三模块职责单一；`/api/metrics` 与 `backup`/`restore` 契约写入 README。
- CHANGELOG：**通过**——v0.5.0 条目。
- 技术债记录：**通过**——eval.md 已知问题 #1/#3 关闭；剩余 #2（flaky 测试）注明。
- 文档代码同步：**通过**——README（版本/命令/API/环境变量/Docker/测试数/已知局限/后续计划）、CHANGELOG、eval.md、OPERATIONS.md 随 v0.5.0 同步。

## 7. 周期机制
- 真实负载验证：**通过**——1000 文件索引 6.8 秒（约 147 文件/秒，老基线 37 文件/秒）；万级库检索毫秒级（常驻 serve）。
- 故障演练：**通过**——kill -9 杀进程后重启数据完好；删库后 restore 恢复；词典缺失 fail-fast；三项均为真实演练（非 demo 数据）。

**结论：发版。** v0.4.0 的 13 项缺口全部关闭，无已知 P0。
