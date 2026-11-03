# v2.26 发版对照报告：账号体系 P0#3「auth-service 生产级补强」

**日期**：2026-10-16
**范围**：dod-v2.25 排期第 1、3 项（auth-service 接 Flyway；auth-service 指标/备份/运维手册补齐）
**生成方式**：微信 ChatAPI DeepSeek-V4-Flash 分 4 批生成（Flyway / 指标 / 备份脚本+运维手册 / 在线备份端点），编排验收+修补+真实 E2E 验证。

## 交付清单

### 1. Flyway 版本化迁移（Batch A）
- `auth-service/pom.xml`：新增 `org.flywaydb:flyway-core`。
- `application.yml`：`ddl-auto: update` → `validate`；新增 `spring.flyway`（`enabled: true`、`baseline-on-migrate: true`，老库首次启动自动基线）。
- `src/main/resources/db/migration/V1__baseline.sql`：**由真实 Hibernate 启动日志逐字导出**（`ddl-auto=create`），含 `users` / `sessions` / `oauth_accounts` 三表 + 两条 FK（约束名沿用 Hibernate 真实生成的 `FKn6j2b3ur1fcj3vkodrmqtdxmi` / `FKruie73rneumyyd1bgo6qw8vjt`，validate 方能通过）。
- `AuthFlywayMigrationTest`：2 例（V1 已应用 + validate 下实体映射一致）。
- 测试：全量 25 例通过（16 旧 + 2 Flyway + 4 指标 + 3 备份）。

### 2. 指标（Batch B，对标主服务 v2.4）
- `pom.xml`：新增 `spring-boot-starter-actuator` + `micrometer-registry-prometheus`。
- `application.yml`：`management.endpoints.web.exposure.include=health,prometheus`（无鉴权，靠网络隔离，注释写清）。
- `AuthMetrics`（`com.dramaauth.metrics`）：Counter（`dramaauth_registrations_total` / `dramaauth_logins_total{result}` / `dramaauth_token_refreshes_total{result}` / `dramaauth_oauth_callbacks_total{provider,result}`，OAuth 用 ConcurrentHashMap 缓存防标签爆炸）+ Gauge 快照（`dramaauth_users_total` / `dramaauth_sessions_active`，`@Scheduled(30s)` 刷新，抓取不查库，异常隔离）；`@EnableScheduling` 已补。
- 埋点：`AuthService.register/login/refresh`、`OAuthController.callback`（try/catch 计 success/failure）。
- `prometheus/rules/auth-service.yml`：3 条告警（5xx 错误率 critical / 实例宕机 critical / 登录失败激增 warning 疑似撞库）。
- `AuthMetricsTest`：4 例。
- 真实验证：`/actuator/prometheus` 可见全部 `dramaauth_*` 指标；注册/登录成功失败计数正确。

### 3. 备份/恢复脚本 + 运维手册（Batch C）
- `scripts/backup-auth.sh`：在线/离线双模式。**关键发现**：H2 嵌入式文件库持有独占文件锁，独立 JVM 进程在应用运行时无法打开同一库文件（`Database may be already in use`），主服务 `backup.sh` 的"在线备份"同样受此限制。本脚本在线模式改走应用内端点（见下），离线模式走 H2 Shell。
- `scripts/restore-auth.sh`：停服检查（运行中拒绝，除非 `--force`）→ 解包 → manifest sha256 校验 → 恢复前快照 → `org.h2.tools.Restore` 恢复 → `SELECT COUNT(*) FROM users` 完整性校验。
- `docs/OPERATIONS-AUTH.md`：部署/健康检查与指标/备份恢复/数据库迁移/升级/故障排查/已知限制 7 节。
- 真实验证：在线备份（应用运行中）→ 删库 → 恢复 → 用户数据完整回来，全链路通过。

### 4. 应用内在线备份端点（Batch D，修复"在线备份"伪命题）
- `BackupService`：`JdbcTemplate` 执行 `BACKUP TO '<服务端生成路径>'`；备份目录 `./data/backups`；文件名时间戳；路径服务端生成防穿越。
- `AdminController`：`POST /api/auth/admin/backup`，`WebMvcConfig` 已覆盖 `/api/auth/**` 故自动 JWT 鉴权，端点内再校验 `userRole==ADMIN`（非 ADMIN 403）。
- `BackupEndpointTest`（MockMvc）：3 例（USER 调 403 / ADMIN 调 200 octet-stream / 无 token 401）。
- `backup-auth.sh` 在线模式：`AUTH_ADMIN_EMAIL/PASSWORD` 登录取 token → 调端点下载 `db.zip` → 打 manifest → 打包。

## 生产级 checklist 对照

### 通过
- DB 迁移版本化：Flyway V1 基线 + validate，老库 baseline-on-migrate 自动接入。
- 结构化日志：既有（本轮未动）。
- 指标暴露：`/actuator/prometheus` + 6 业务指标 + 3 告警规则。
- 备份恢复：在线/离线双模式脚本 + 恢复前快照 + sha256 校验 + 真实演练通过。
- 运维手册：`docs/OPERATIONS-AUTH.md` 新建。
- 输入校验/鉴权：备份端点 ADMIN 强制；`BACKUP TO` 路径服务端生成。
- 测试：25/25 全绿（`mvn -o test`）。

### 未通过 → 排期
- token httpOnly Cookie 化（dod-v2.25 排期第 2 项，未做）。
- 全站 i18n（dod-v2.25 排期第 4 项，未做）。
- 分支覆盖冲 95%（长期低优先级，未做）。
- Agnes/Qwen submit/poll 真实链路（需外部 API）。
- h2c 锁定待产品确认（多轮遗留）。
- `testFullPipeline` flaky 根因（多轮遗留）。

### 不适用
- 滚动更新：单机部署，限制已在运维手册声明。

## 本轮修 dpsk 输出 / 编排手工修（诚实记录）

1. Batch A PATCH 缩进：dpsk 两处 OLD 丢缩进（pom.xml、application.yml），编排按原文缩进修正后应用。
2. Batch A yml 结构事故：dpsk 的 flyway PATCH 把 `jpa` 下的 `show-sql/open-in-view/properties` 错挂到 `flyway` 下，编排发现后修复并用 YAML 解析验证。
3. Batch B AuthService 构造器 PATCH：dpsk OLD 缩进与原文不符（12 空格 vs 23 空格对齐），编排修正。
4. Batch B register 埋点：`return toDto(userRepository.save(u));` 在文件出现 3 次，编排改用 `u.setRole` 长锚定唯一定位 register。
5. Batch B 缺 `@EnableScheduling`：dpsk 未加，`@Scheduled` 不生效，编排补上。
6. Batch D 测试 import 编造：dpsk 写 `com.dramaauth.dto.TokenPair/UserDto`（实为 `AuthService` 嵌套 record），编排修正。
7. Batch D 测试框架：dpsk 的 TestRestTemplate 在 RANDOM_PORT 下触发 Micrometer observation `status -1` 断言，编排改写为 MockMvc；另 H2 `BACKUP TO` 不支持内存库，测试改用 `target/` 下文件库。
8. 备份脚本三次返工（均在编排侧真实 E2E 中发现）：
   - `mktemp -d` 无模板落 `/tmp`（违反仓库禁 /tmp 规范）→ 改走 `$BACKUP_DIR` 模板；
   - STAGE 定义顺序错（mktemp 在 mkdir 之前）→ 统一移至顶部；
   - 打包扁平结构 vs restore 期望根目录 → 统一为带根目录；
   - `tar` 解包缺 `--no-same-owner`（root 环境 chown 失败）→ 补上；
   - `RESTORE FROM` 非法（H2 无此 SQL）→ 改用 `org.h2.tools.Restore -file <db.zip> -dir <dir> -db <name>`；
   - 我的 Python 修复脚本一次误操作打坏 `backup-auth.sh`（33 行）与截断 `restore-auth.sh`，两人均从头重写干净版。
9. 密钥显示层误报：测试用 dummy secret 在日志显示为 `<redacted>`，经字节级核验文件实际为明文 dummy 值，无真实密钥入库。

## 诚实声明

- 本轮生产代码有逻辑新增（BackupService/AdminController/AuthMetrics/埋点），非零修改。
- 在线备份的"在线"是真在线（应用内执行），但依赖管理员凭证经 HTTP 登录；离线备份依赖 H2 Shell。
- `dramaauth_users_total` 在 Prometheus 展露为 `dramaauth_users`（Micrometer 对 Gauge 剥离 `_total` 后缀，符合 Prometheus 命名规范；Micrometer 内部名不变，测试按内部名断言）。
