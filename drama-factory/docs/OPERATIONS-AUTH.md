# auth-service 运维手册

auth-service 是 drama-factory 的独立鉴权微服务（Spring Boot 3.3.5），默认端口 8082（`${PORT:8082}`），使用 H2 文件库（默认 `jdbc:h2:file:./data/auth`，数据文件 `<APP_HOME>/data/auth.mv.db`）。

## 1. 部署

### 构建与运行（docker / compose）

- 构建上下文为 `auth-service/` 目录：

  ```bash
  docker build -t drama-factory/auth-service:latest auth-service/
  ```

- 必需环境变量：
  - `AUTH_JWT_SECRET`：JWT 签名密钥。**缺失则拒绝启动。**
  - 生成方式：`openssl rand -base64 48`

- 可选环境变量：
  - `PORT`（默认 8082）
  - `DB_URL`（默认 `jdbc:h2:file:./data/auth`）

- 数据卷：挂载 `./data`，持久化 `auth.mv.db`。

- compose 示例（片段）：

  ```yaml
  auth-service:
    build:
      context: auth-service/
    environment:
      AUTH_JWT_SECRET: ${AUTH_JWT_SECRET}
      PORT: "8082"
    ports:
      - "8082:8082"
    volumes:
      - ./data:/app/data
  ```

## 2. 健康检查与指标

- 健康检查：`GET /actuator/health`
- 指标：`GET /actuator/prometheus`
- 以上端点当前**无鉴权**，请依赖网络隔离（见「已知限制」）。

### Prometheus 抓取示例

```yaml
scrape_configs:
  - job_name: auth-service
    metrics_path: /actuator/prometheus
    static_configs:
      - targets: ["auth-service:8082"]
```

### 告警规则（`prometheus/rules/auth-service.yml`）

- **5xx 错误率告警**：含义为 auth-service 返回 5xx 的比例超阈值，通常代表内部异常或依赖故障。
  - 排查步骤：查看服务日志异常栈；检查 `AUTH_JWT_SECRET` 是否被篡改；检查 H2 库文件是否被锁或磁盘满。
- **实例宕机告警**：`up == 0`，含义为 Prometheus 抓不到目标，服务不可用。
  - 排查步骤：`curl -fsS http://127.0.0.1:8082/actuator/health`；`pgrep -f 'auth-service.*\.jar'`；检查端口占用与容器状态。
- **登录失败激增告警**：含义为短时间登录失败次数异常升高，可能是撞库或配置错误。
  - 排查步骤：核对上游客户端密钥/时钟偏移；检查是否有异常来源 IP；确认用户数据未被误清。

## 3. 备份与恢复

### 备份

```bash
./scripts/backup-auth.sh
```

- 环境变量：`BACKUP_KEEP`（默认 7）、`APP_HOME`（默认脚本上一级）、`H2_JAR`（可选，自动在 `$HOME/.m2/repository`、`$HOME/workspace/muse-build/.m2repo` 搜索）。
- 使用 H2 Shell 在线备份，产物：`$APP_HOME/backups/auth/auth-service-<TS>.tar.gz`，内含 `db.zip` 与 `manifest.txt`（含 sha256）。
- 保留策略：按时间保留最近 `BACKUP_KEEP` 个。

### 恢复

```bash
./scripts/restore-auth.sh <备份包> [--force]
```

- 运行中默认拒绝恢复；`--force` 可强制，但会给出警告。
- 恢复前自动对当前库打快照：`$APP_HOME/backups/auth/pre-restore-auth-<TS>.tar.gz`。
- 恢复流程：解包 → 校验 manifest sha256 → 执行 `RESTORE` → `SELECT COUNT(*) FROM users;` 做完整性校验。
- **演练建议**：每月至少一次在非生产环境执行完整备份 + 恢复演练。

## 4. 数据库迁移（Flyway）

- 迁移脚本目录：`auth-service/src/main/resources/db/migration/`
- 基线脚本：`V1__baseline.sql`，来自老库结构导出。
- 老库首次启动：`baseline-on-migrate` 自动打基线，无需手工干预。
- 新增迁移：以 `V2__xxx.sql` 命名放入上述目录，随服务启动自动执行。
- `ddl-auto=validate`：**禁止手工修改表结构**，所有变更走迁移脚本。

## 5. 升级

1. 停止服务。
2. 执行备份：`./scripts/backup-auth.sh`。
3. 替换 jar 或镜像。
4. 启动服务。
5. 观察日志中 Flyway migrate 输出，确认无失败。
6. 健康检查：`curl -fsS http://127.0.0.1:8082/actuator/health`。

## 6. 常见故障排查

- **AUTH_JWT_SECRET 缺失 / 太短**：服务启动即失败。使用 `openssl rand -base64 48` 生成并注入环境变量，长度不足会导致签名相关异常。
- **Flyway 校验失败**：不要修改已执行过的迁移脚本。确需变更时新增 `V2__xxx.sql`；如确属历史脚本被误改，需按团队流程人工处理 `flyway_schema_history` 并评估影响。
- **H2 文件被锁**：确认是否有其他 java 进程持有 `auth.mv.db`。停止占用进程后重试，恢复操作前务必确保无进程持库。
- **/actuator 返回 404**：检查 `management.endpoints.web.exposure.include` 是否包含 `health,prometheus`。

## 7. 已知限制

- H2 为单机文件库，不支持多实例共享，横向扩展前需更换数据库。
- `/actuator/prometheus` 无鉴权，仅靠网络隔离保护，请勿暴露到公网。
- OAuth handshake 未实测，相关流程上线前需单独验证。
