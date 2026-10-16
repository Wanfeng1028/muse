# feedflow v1.4 发版对照报告（生产级 Definition of Done）

版本：v1.4「生产级收尾 + 移动端阅读优化」· 2026-10-16
范围：v1.3 对照报告遗留三项（OPERATIONS.md Fever 章节 / Prometheus 指标 / 失败注入测试）+ 后续计划"移动端阅读优化"。
生成方式：微信 ChatAPI DeepSeek-V4-Flash 分 4 批并行生成（指标代码 / 失败注入测试 / 文档 / 移动端前端），编排者逐批验收、手工修复 17 处 dpsk 输出问题后合入。

## 1. 可靠性
- [通过] 测试金字塔：pytest 102 例全过（84 基线 + 18 新增：test_metrics.py 6 + test_failure_injection.py 12），ruff check 全洁。
- [通过] 失败注入测试 12 例：DB 连接斩断（500 不崩 + 恢复）、healthz 降级、抓取 500/超时/连接拒绝、坏备份拒绝、trafilatura 回落、Fever 关闭态、无效 OPML、单条目失败隔离、404、dedup 坏输入。
- [通过] 错误处理策略：抓取失败分类（timeout/dns/http_4xx/http_5xx/parse_error/unknown）+ 指数退避重试（既有，文档已补进运维手册第 7 节）。
- [通过] DB 迁移版本化：PRAGMA user_version（既有 v1→v3）。
- [通过] 健康检查 /healthz + 优雅关闭（既有）。

## 2. 可观测性
- [通过] 结构化日志：JSON Lines + request_id 全链路（既有）。
- [通过] Prometheus 指标（本轮新增）：`GET /metrics`（text/plain; version=0.0.4），9 个指标系列——http_requests_total{method,route,status}、fetch_total{status}、fetch_errors_total{kind}、articles_stored_total、fetch_duration_seconds_total、feeds/articles/unread/starred_total（gauge 实时读 store.stats）。零新依赖，手写 exposition，线程安全；埋点失败只记 warning 日志，永不影响主流程。真实服务冒烟验证通过。
- [通过] 告警建议：运维手册第 4 节给出 3 条告警建议（fetch_errors_total 持续增长 / unread_total 异常归零 / healthz degraded）。

## 3. 数据与状态
- [通过] 备份恢复：backup/restore CLI（既有）；失败注入覆盖坏备份拒绝恢复；运维手册第 5 节补齐流程与恢复前快照建议。
- [通过] 敏感数据策略：Fever api_key 只存环境变量、服务端只认 md5；运维手册第 3 节写清轮换流程与"不明文落盘"要求。
- [通过] 配置密钥分离：全环境变量化 + 启动校验 fail-fast（既有）；运维手册第 1 节环境变量表已按 config.py 实际默认值修正（之前全错）。

## 4. 部署与运维
- [通过] docker-compose 一键部署（既有；手册注明未在本机实跑）。
- [部分通过] 运维手册：本轮从 23 行 stub 补全为 8 章完整手册（环境变量/启动停止/Fever/指标/备份恢复/升级回滚/故障排查/日志）。滚动更新/零停机未声明——单进程 SQLite，自托管场景重启即停机，已在手册升级节如实写清步骤，未虚报零停机。

## 5. 安全与健壮性
- [通过] Fever 鉴权 hmac 常量时间比较（既有）；未配置 key 时 /fever 返回 auth=0 关闭态（测试锁定）。
- [未通过] Dependabot：仓库级 `.github/dependabot.yml` 已存在（v5 工程化时建的）；pip 依赖定期扫描排期后续（与 ledger 等项目同，等 gh token 补 workflow 权限后统一处理）。
- [不适用] 限流：自托管单用户阅读器，抓取端已有超时/重试/退避；HTTP 层限流未做，排期 v1.5 评估。

## 6. 可维护性
- [通过] CHANGELOG.md 新增 v1.4 条目；README 新增"监控指标"节 + v1.4 更新记录 + 移动端真实截图。
- [通过] 技术债记录：本轮 dpsk 输出问题 17 处已全部修复并记录（见 PROJECTS.md 本轮小节）；无新增已知 bug。

## 7. 视觉验收
- [通过] 桌面端：reader 三栏真实数据截图亲眼验收，v1.4 零视觉变化（所有新增样式包在 @media 内）。
- [通过] 移动端：390px 三视图（订阅/文章/正文）切换截图亲眼验收；验收抓出 1 真实 UI bug（顶栏 nav 在窄屏下纵向堆叠——模板用 `.mainnav` 而 CSS 基线只定义了 `.topnav`，致 nav 无样式），已修复重拍通过。截图入 docs/screenshots/reader-mobile.png，README 已引用。

## 结论
**可发版**。v1.3 遗留三项全部关闭。遗留排期：v1.5（HTTP 层限流评估、pip 依赖扫描机制、全文 RSS 输出）。
